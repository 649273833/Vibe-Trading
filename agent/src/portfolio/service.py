"""Deterministic, read-only aggregation across configured trading profiles."""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from src.portfolio.config import (
    PortfolioSettingsStore,
    PortfolioSource,
    source_catalog,
)
from src.portfolio.normalization import (
    STABLECOINS,
    account_cash_usd,
    account_total_usd,
    auth_metadata,
    normalize_position,
    value_position,
)
from src.portfolio.store import PortfolioStore
from src.trading.profiles import profile_by_id


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value is None or value == "":
            return default
        result = Decimal(str(value))
        return result if result.is_finite() else default
    except (InvalidOperation, ValueError, TypeError):
        return default


def _number(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.00000001")))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quote_price(payload: dict[str, Any]) -> Decimal | None:
    quote = payload.get("quote") or {}
    for key in ("last", "close"):
        price = _decimal(quote.get(key))
        if price > 0:
            return price
    bid, ask = _decimal(quote.get("bid")), _decimal(quote.get("ask"))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    return bid if bid > 0 else ask if ask > 0 else None


class PortfolioService:
    def __init__(
        self,
        store: PortfolioStore | None = None,
        *,
        settings_store: PortfolioSettingsStore | None = None,
        get_account: Callable[..., dict[str, Any]] | None = None,
        get_positions: Callable[..., dict[str, Any]] | None = None,
        get_quote: Callable[..., dict[str, Any]] | None = None,
        get_longbridge_quotes: Callable[..., dict[str, Any]] | None = None,
        fx_fetcher: Callable[[], tuple[Decimal, Decimal, str]] | None = None,
        progress_callback: Callable[[str, str, str | None], None] | None = None,
    ) -> None:
        self._use_longbridge_worker = get_account is None and get_positions is None
        self._noninteractive_ibkr = get_account is None and get_positions is None
        if get_account is None or get_positions is None or get_quote is None:
            from src.trading import service as trading

            get_account = get_account or trading.get_account
            get_positions = get_positions or trading.get_positions
            get_quote = get_quote or trading.get_quote
        self.store = store or PortfolioStore()
        self._get_account = get_account
        self._get_positions = get_positions
        self._get_quote = get_quote
        self._get_longbridge_quotes = get_longbridge_quotes
        self._fx_fetcher = fx_fetcher or self._fetch_fx
        self._progress_callback = progress_callback
        self.settings_store = settings_store or PortfolioSettingsStore()

    def settings(self) -> dict[str, Any]:
        """Return credential-free editable settings."""
        return self.settings_store.load().to_dict()

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and persist editable settings."""
        return self.settings_store.save(payload).to_dict()

    def sources(self) -> list[dict[str, Any]]:
        """Return local read-only connections eligible for this portfolio."""
        return source_catalog(
            self.settings_store.load(),
            self.settings_store.connection_store,
        )

    def _connection_profile(self, source: PortfolioSource):
        connection = self.settings_store.connection_store.get(source.connection_id)
        return connection, profile_by_id(connection.profile_id)

    def refresh(self) -> dict[str, Any]:
        settings = self.settings_store.load()
        sources = [source for source in settings.sources if source.enabled]
        if not sources:
            raise RuntimeError("请先在持仓页添加并启用至少一个只读账户")
        usd_cny, usd_hkd, fx_at, fx_stale = self._rates()
        refreshed_at = _now()
        results: dict[str, dict[str, Any]] = {}
        # The Longbridge Python SDK wraps a native runtime whose contexts are
        # not safe to create inside this refresh thread pool on macOS. Keep the
        # manual refresh deterministic and sequential; a failed broker remains
        # isolated and never prevents the other accounts from refreshing.
        for source in sources:
            if self._progress_callback is not None:
                self._progress_callback(source.id, "refreshing", None)
            try:
                results[source.id] = self._collect_source(source)
                if self._progress_callback is not None:
                    self._progress_callback(source.id, "ok", None)
            except Exception as exc:  # read failures are isolated per connector
                connection, profile = self._connection_profile(source)
                results[source.id] = {
                    "source_id": source.id,
                    "profile_id": connection.profile_id,
                    "label": source.label,
                    "broker": profile.connector,
                    "status": "error",
                    "error_code": type(exc).__name__,
                    "error": str(exc)[:300],
                    "positions": [],
                }
                if self._progress_callback is not None:
                    self._progress_callback(source.id, "error", str(exc)[:160])

        positions: list[dict[str, Any]] = []
        accounts: list[dict[str, Any]] = []
        for source in sources:
            result = results[source.id]
            broker = result["broker"]
            connection, profile = self._connection_profile(source)
            if result["status"] != "ok":
                cached = self.store.latest_successful_source(source.id)
                if cached is None:
                    accounts.append(
                        {
                            "source_id": source.id,
                            "profile_id": connection.profile_id,
                            "label": source.label,
                            "broker": broker,
                            "status": "error",
                            "error": result.get("error"),
                            "error_code": result.get("error_code"),
                            "auth": auth_metadata(profile),
                        }
                    )
                    continue
                cached_account = dict(cached["account"])
                cached_account.update(
                    source_id=source.id,
                    profile_id=connection.profile_id,
                    label=source.label,
                    broker=profile.connector,
                    status="stale",
                    data_state="cached",
                    last_success_at=cached["created_at"],
                    error=result.get("error"),
                    error_code=result.get("error_code"),
                    auth=auth_metadata(profile),
                )
                cached_positions = [dict(item) for item in cached["positions"]]
                cached_priced = sum(
                    (
                        _decimal(item.get("market_value_usd"))
                        for item in cached_positions
                    ),
                    Decimal("0"),
                )
                cached_cash = _decimal(cached_account.get("cash_usd"))
                cached_unpriced = _decimal(cached_account.get("unpriced_or_other_usd"))
                if "unpriced_or_other_usd" not in cached_account:
                    cached_unpriced = max(
                        Decimal("0"),
                        _decimal(cached_account.get("cash_or_unallocated_usd"))
                        - cached_cash,
                    )
                if not source.include_cash:
                    cached_account["total_usd"] = _number(
                        max(
                            Decimal("0"),
                            _decimal(cached_account.get("total_usd")) - cached_cash,
                        )
                    )
                    cached_cash = Decimal("0")
                cached_account.update(
                    priced_value_usd=_number(cached_priced),
                    cash_usd=_number(cached_cash),
                    unpriced_or_other_usd=_number(cached_unpriced),
                    priced_position_count=sum(
                        1 for item in cached_positions if item.get("priced")
                    ),
                    unpriced_position_count=sum(
                        1 for item in cached_positions if not item.get("priced")
                    ),
                )
                cached_account["total_cny"] = _number(
                    _decimal(cached_account.get("total_usd")) * usd_cny
                )
                accounts.append(cached_account)
                for cached_position in cached_positions:
                    cached_position["source_id"] = source.id
                    cached_position["profile_id"] = connection.profile_id
                    cached_position["source_label"] = source.label
                    cached_position["stale"] = True
                    cached_position["market_value_cny"] = _number(
                        _decimal(cached_position.get("market_value_usd")) * usd_cny
                    )
                    positions.append(cached_position)
                continue
            broker_positions = [
                value_position(row, usd_hkd=usd_hkd, usd_cny=usd_cny)
                for row in result["positions"]
            ]
            priced_total = sum(
                (_decimal(row.get("market_value_usd")) for row in broker_positions),
                Decimal("0"),
            )
            account_total = account_total_usd(
                broker,
                result["account"],
                usd_hkd,
                usd_cny,
                priced_total,
            )
            if broker == "binance":
                account_total = priced_total
            cash_total = min(
                account_total,
                account_cash_usd(broker, result["account"], usd_hkd, usd_cny),
            )
            if not source.include_cash:
                account_total = max(Decimal("0"), account_total - cash_total)
                cash_total = Decimal("0")
            unpriced_or_other = max(
                Decimal("0"), account_total - priced_total - cash_total
            )
            priced_count = sum(1 for row in broker_positions if row.get("priced"))
            accounts.append(
                {
                    "source_id": source.id,
                    "profile_id": connection.profile_id,
                    "label": source.label,
                    "broker": broker,
                    "status": "ok",
                    "data_state": "fresh",
                    "last_success_at": refreshed_at,
                    "total_usd": _number(account_total),
                    "total_cny": _number(account_total * usd_cny),
                    "priced_value_usd": _number(priced_total),
                    "cash_usd": _number(cash_total),
                    "unpriced_or_other_usd": _number(unpriced_or_other),
                    # Retain the original field for older frontends/API users.
                    "cash_or_unallocated_usd": _number(cash_total + unpriced_or_other),
                    "position_count": len(broker_positions),
                    "priced_position_count": priced_count,
                    "unpriced_position_count": len(broker_positions) - priced_count,
                    "auth": auth_metadata(profile),
                }
            )
            positions.extend(broker_positions)

        total_usd = sum(
            (_decimal(row.get("total_usd")) for row in accounts), Decimal("0")
        )
        complete = len(accounts) == len(sources) and all(
            row["status"] == "ok" for row in accounts
        )
        priced_usd = sum(
            (_decimal(row.get("priced_value_usd")) for row in accounts), Decimal("0")
        )
        cash_usd = sum(
            (_decimal(row.get("cash_usd")) for row in accounts), Decimal("0")
        )
        unpriced_usd = sum(
            (_decimal(row.get("unpriced_or_other_usd")) for row in accounts),
            Decimal("0"),
        )
        identified_usd = priced_usd + cash_usd
        payload = {
            "snapshot_id": uuid.uuid4().hex,
            "created_at": refreshed_at,
            "complete": complete,
            "display_currency": settings.display_currency,
            "totals": {"usd": _number(total_usd), "cny": _number(total_usd * usd_cny)},
            "valuation": {
                "priced_usd": _number(priced_usd),
                "cash_usd": _number(cash_usd),
                "unpriced_or_other_usd": _number(unpriced_usd),
                "identified_coverage": (
                    _number(identified_usd / total_usd) if total_usd > 0 else 0.0
                ),
            },
            "fx": {
                "usd_cny": _number(usd_cny),
                "usd_hkd": _number(usd_hkd),
                "fetched_at": fx_at,
                "stale": fx_stale,
            },
            "accounts": accounts,
            "positions": sorted(
                positions,
                key=lambda row: _decimal(row.get("market_value_usd")),
                reverse=True,
            ),
            "combined_holdings": self._combine_holdings(positions),
            "warnings": self._warnings(accounts, positions, fx_stale),
        }
        self.store.save_snapshot(payload)
        return payload

    def latest(self) -> dict[str, Any] | None:
        snapshot = self.store.latest()
        if snapshot is None:
            return None
        enabled = {
            source.id for source in self.settings_store.load().sources if source.enabled
        }
        observed = {
            str(account.get("source_id") or account.get("broker"))
            for account in snapshot.get("accounts", [])
        }
        return snapshot if enabled and observed == enabled else None

    def reconnect_source(self, source_id: str) -> dict[str, Any]:
        """Run a supported source's interactive OAuth flow on explicit request."""
        from src.config.loader import load_agent_config
        from src.tools.mcp import MCPServerAdapter

        source = next(
            (
                item
                for item in self.settings_store.load().sources
                if item.id == source_id
            ),
            None,
        )
        if source is None:
            raise RuntimeError("未找到该持仓账户")
        _, profile = self._connection_profile(source)
        if profile.transport != "remote_mcp":
            raise RuntimeError("该账户不使用 OAuth，无需重新连接")
        server = (load_agent_config().mcp_servers or {}).get(profile.connector)
        if server is None:
            raise RuntimeError(f"{profile.connector.upper()} MCP 连接尚未配置")
        tools = MCPServerAdapter(
            profile.connector,
            server,
            max_list_tools_attempts=1,
            interactive_oauth=True,
        ).discover_tools()
        return {
            "status": "ok",
            "authorized": True,
            "source_id": source.id,
            "enabled_read_tools": [item.remote_name for item in tools],
        }

    def history(self, limit: int = 180) -> list[dict[str, Any]]:
        return self.store.history(limit, complete_only=True)

    def export_csv(self) -> str:
        snapshot = self.latest()
        if snapshot is None:
            return ""
        fields = [
            "source_id",
            "source_label",
            "profile_id",
            "broker",
            "symbol",
            "name",
            "asset_type",
            "market",
            "currency",
            "quantity",
            "cost_price",
            "market_price",
            "market_value_usd",
            "market_value_cny",
            "unrealized_pnl_usd",
            "priced",
            "updated_at",
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(snapshot["positions"])
        return output.getvalue()

    def analysis_context(self) -> dict[str, Any] | None:
        """Return a credential/account-id-free snapshot suitable for an LLM."""
        snapshot = self.latest()
        if snapshot is None:
            return None
        total = _decimal(snapshot["totals"]["usd"])
        holdings = []
        for row in snapshot.get("combined_holdings", []):
            market_value = _decimal(row.get("market_value_usd"))
            holdings.append(
                {
                    "symbol": row["symbol"],
                    "asset_type": row["asset_type"],
                    "markets": row["markets"],
                    "brokers": row["brokers"],
                    "market_value_usd": row["market_value_usd"],
                    "weight": _number(market_value / total) if total > 0 else 0.0,
                    "unrealized_pnl_usd": row["unrealized_pnl_usd"],
                }
            )
        return {
            "as_of": snapshot["created_at"],
            "complete": snapshot["complete"],
            "totals": snapshot["totals"],
            "account_allocation": [
                {
                    "broker_alias": f"account_{index + 1}",
                    "asset_provider_type": row["broker"],
                    "status": row["status"],
                    "total_usd": row.get("total_usd"),
                }
                for index, row in enumerate(snapshot["accounts"])
            ],
            "holdings": holdings,
            "warnings": snapshot["warnings"],
            "privacy": "No account numbers, credentials, order IDs, names, or local paths included.",
        }

    @staticmethod
    def _combine_holdings(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in positions:
            symbol = str(row.get("symbol") or "").upper()
            currency = str(row.get("currency") or "").upper()
            market = str(row.get("market") or "").upper()
            if symbol.endswith(".US"):
                canonical = symbol[:-3]
            elif symbol.endswith(".HK"):
                canonical = symbol[:-3].lstrip("0") or "0"
            else:
                canonical = symbol
            region = (
                "HK"
                if currency == "HKD" or market == "HK" or symbol.endswith(".HK")
                else (
                    "CRYPTO"
                    if row.get("asset_type") in {"crypto", "stablecoin"}
                    else "US"
                )
            )
            key = f"{region}:{canonical}"
            item = grouped.setdefault(
                key,
                {
                    "canonical_id": key,
                    "symbol": canonical,
                    "asset_type": row.get("asset_type"),
                    "brokers": [],
                    "sources": [],
                    "markets": [],
                    "market_value_usd": Decimal("0"),
                    "market_value_cny": Decimal("0"),
                    "unrealized_pnl_usd": Decimal("0"),
                },
            )
            if row.get("broker") not in item["brokers"]:
                item["brokers"].append(row.get("broker"))
            source_label = row.get("source_label") or row.get("broker")
            if source_label not in item["sources"]:
                item["sources"].append(source_label)
            if row.get("market") not in item["markets"]:
                item["markets"].append(row.get("market"))
            item["market_value_usd"] += _decimal(row.get("market_value_usd"))
            item["market_value_cny"] += _decimal(row.get("market_value_cny"))
            item["unrealized_pnl_usd"] += _decimal(row.get("unrealized_pnl_usd"))
        result = []
        for item in grouped.values():
            item["brokers"].sort()
            item["sources"].sort()
            item["markets"] = sorted(str(value) for value in item["markets"] if value)
            item["duplicate_across_brokers"] = len(item["brokers"]) > 1
            for key in ("market_value_usd", "market_value_cny", "unrealized_pnl_usd"):
                item[key] = _number(item[key])
            result.append(item)
        return sorted(
            result, key=lambda row: _decimal(row["market_value_usd"]), reverse=True
        )

    def _collect_source(self, source: PortfolioSource) -> dict[str, Any]:
        connection, profile = self._connection_profile(source)
        if not profile.readonly:
            raise RuntimeError(
                "portfolio sources must use a read-only connector profile"
            )
        broker = profile.connector
        profile_id = profile.id
        longbridge_batch: dict[str, Any] | None = None
        if (
            broker == "longbridge"
            and profile_id == "longbridge-live-sdk-readonly"
            and self._use_longbridge_worker
        ):
            isolated = self._read_longbridge_isolated()
            account = isolated["account"]
            positions_payload = isolated["positions"]
            longbridge_batch = isolated.get("quotes")
        else:
            read_options = (
                {"interactive_oauth": False}
                if broker == "ibkr" and self._noninteractive_ibkr
                else {}
            )
            if profile.transport == "local_plugin":
                read_options["connection_id"] = connection.id
            account = self._get_account(profile_id, **read_options)
            positions_payload = self._get_positions(profile_id, **read_options)
        for label, payload in (("account", account), ("positions", positions_payload)):
            if str(payload.get("status") or "ok").lower() not in {"ok", "success"}:
                raise RuntimeError(
                    str(payload.get("error") or f"{broker} {label} read failed")
                )
        normalized_rows = [
            normalize_position(broker, raw)
            for raw in positions_payload.get("positions", [])
        ]
        for row in normalized_rows:
            row.update(
                source_id=source.id,
                profile_id=connection.profile_id,
                source_label=source.label,
            )
        longbridge_prices: dict[str, Decimal] | None = None
        longbridge_price_error: str | None = None
        if broker == "longbridge" and longbridge_batch is not None:
            longbridge_prices = {
                str(item.get("symbol") or "").upper(): _decimal(item.get("last"))
                for item in longbridge_batch.get("quotes", [])
                if _decimal(item.get("last")) > 0
            }
            if str(longbridge_batch.get("status") or "ok").lower() not in {
                "ok",
                "success",
            }:
                longbridge_price_error = str(
                    longbridge_batch.get("error") or "Longbridge quote read failed"
                )[:160]
        elif broker == "longbridge" and self._get_longbridge_quotes is not None:
            try:
                batch = self._get_longbridge_quotes(
                    [str(row["quote_symbol"]) for row in normalized_rows]
                )
                longbridge_prices = {
                    str(item.get("symbol") or "").upper(): _decimal(item.get("last"))
                    for item in batch.get("quotes", [])
                    if _decimal(item.get("last")) > 0
                }
            except Exception as exc:
                longbridge_prices = {}
                longbridge_price_error = str(exc)[:160]

        rows = []
        for normalized in normalized_rows:
            quantity = _decimal(normalized["quantity"])
            if quantity == 0:
                continue
            try:
                if broker == "binance" and normalized["symbol"] in STABLECOINS:
                    normalized["market_price"] = 1.0
                    normalized["price_currency"] = "USD"
                    normalized["pricing_basis"] = "USDT/USD proxy"
                elif _decimal(normalized.get("market_price")) > 0:
                    normalized["price_currency"] = normalized["currency"]
                    normalized["pricing_basis"] = f"{broker} position snapshot"
                elif broker == "longbridge" and longbridge_prices is not None:
                    price = longbridge_prices.get(
                        str(normalized["quote_symbol"]).upper()
                    )
                    normalized["market_price"] = _number(price) if price else None
                    normalized["price_currency"] = normalized["currency"]
                    normalized["pricing_basis"] = (
                        "Longbridge official quote"
                        if longbridge_batch is not None
                        else "Fallback market quote"
                    )
                    if not price and longbridge_price_error:
                        normalized["price_error"] = longbridge_price_error
                else:
                    quote_symbol = normalized["quote_symbol"]
                    quote = self._get_quote(
                        quote_symbol,
                        profile_id,
                        exchange=normalized.get("exchange") or "SMART",
                        currency=normalized["currency"],
                        sec_type="STK",
                        **(
                            {"connection_id": connection.id}
                            if profile.transport == "local_plugin"
                            else {}
                        ),
                    )
                    price = _quote_price(quote)
                    normalized["market_price"] = _number(price) if price else None
                    normalized["price_currency"] = normalized["currency"]
            except Exception as exc:
                normalized["price_error"] = str(exc)[:160]
            rows.append(normalized)
        return {
            "source_id": source.id,
            "profile_id": connection.profile_id,
            "label": source.label,
            "broker": broker,
            "status": "ok",
            "account": account,
            "positions": rows,
        }

    @staticmethod
    def _read_longbridge_isolated() -> dict[str, Any]:
        marker = "VIBE_PORTFOLIO_JSON="
        process = subprocess.run(
            [sys.executable, "-m", "src.portfolio.longbridge_worker"],
            check=False,
            capture_output=True,
            text=True,
            timeout=40,
        )
        payload: dict[str, Any] | None = None
        for line in reversed(process.stdout.splitlines()):
            if line.startswith(marker):
                parsed = json.loads(line[len(marker) :])
                if isinstance(parsed, dict):
                    payload = parsed
                break
        if payload is None:
            raise RuntimeError("Longbridge isolated reader returned no payload")
        if payload.get("error"):
            raise RuntimeError(f"Longbridge isolated reader failed: {payload['error']}")
        if "account" not in payload or "positions" not in payload:
            raise RuntimeError(
                "Longbridge isolated reader returned an incomplete payload"
            )
        return payload

    def _rates(self) -> tuple[Decimal, Decimal, str, bool]:
        try:
            usd_cny, usd_hkd, fetched_at = self._fx_fetcher()
            self.store.save_fx("USD", "CNY", str(usd_cny), fetched_at)
            self.store.save_fx("USD", "HKD", str(usd_hkd), fetched_at)
            return usd_cny, usd_hkd, fetched_at, False
        except Exception:
            cny = self.store.load_fx("USD", "CNY")
            hkd = self.store.load_fx("USD", "HKD")
            if cny is None or hkd is None:
                raise RuntimeError(
                    "FX service unavailable and no prior USD/CNY + USD/HKD cache exists"
                )
            return _decimal(cny[0]), _decimal(hkd[0]), min(cny[1], hkd[1]), True

    @staticmethod
    def _fetch_fx() -> tuple[Decimal, Decimal, str]:
        url = "https://api.frankfurter.app/latest?from=USD&to=CNY,HKD"
        request = urllib.request.Request(
            url, headers={"User-Agent": "Vibe-Trading/portfolio"}
        )
        with urllib.request.urlopen(
            request, timeout=8
        ) as response:  # noqa: S310 - fixed HTTPS host
            payload = json.load(response)
        return (
            _decimal(payload["rates"]["CNY"]),
            _decimal(payload["rates"]["HKD"]),
            _now(),
        )

    @staticmethod
    def _warnings(
        accounts: list[dict[str, Any]], positions: list[dict[str, Any]], fx_stale: bool
    ) -> list[str]:
        warnings = []
        if fx_stale:
            warnings.append("汇率服务暂时不可用，当前使用上一次成功获取的汇率。")
        stale = [
            str(row.get("label") or row["broker"])
            for row in accounts
            if row["status"] == "stale"
        ]
        if stale:
            warnings.append(
                "以下账户刷新失败，已保留上一次成功数据：" + "、".join(stale)
            )
        failed = [
            str(row.get("label") or row["broker"])
            for row in accounts
            if row["status"] == "error"
        ]
        if failed:
            warnings.append("以下账户尚无可用缓存，请检查连接：" + "、".join(failed))
        unpriced = [
            f"{row['broker']}:{row['symbol']}"
            for row in positions
            if not row.get("priced")
        ]
        if unpriced:
            warnings.append("暂未取得价格的持仓：" + "、".join(unpriced[:20]))
        if any(row.get("broker") == "binance" for row in positions):
            warnings.append("Binance 现货按 USDT≈USD 进行估值。")
        return warnings
