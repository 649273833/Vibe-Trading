from __future__ import annotations

from decimal import Decimal

from src.portfolio.config import PortfolioSettingsStore
from src.portfolio.normalization import auth_metadata
from src.portfolio.service import PortfolioService
from src.portfolio.store import PortfolioStore
from src.trading.types import TradingProfile


def _settings_store(tmp_path):
    store = PortfolioSettingsStore(tmp_path / "portfolio.json")
    store.connection_store.ensure("ibkr", "ibkr-live-official-mcp-readonly", "IBKR")
    store.connection_store.ensure(
        "longbridge", "longbridge-live-sdk-readonly", "Longbridge"
    )
    store.connection_store.ensure("binance", "binance-live-sdk-readonly", "Binance")
    store.save(
        {
            "display_currency": "USD",
            "sources": [
                {"connection_id": "ibkr", "label": "IBKR", "order": 0},
                {"connection_id": "longbridge", "label": "Longbridge", "order": 1},
                {"connection_id": "binance", "label": "Binance", "order": 2},
            ],
        }
    )
    return store


def test_refresh_aggregates_three_readonly_connectors(tmp_path):
    accounts = {
        "ibkr-live-official-mcp-readonly": {
            "summary": [{"tag": "NetLiquidation", "value": "1000", "currency": "USD"}]
        },
        "longbridge-live-sdk-readonly": {
            "balances": [{"net_assets": "7800", "currency": "HKD"}]
        },
        "binance-live-sdk-readonly": {"balances": []},
    }
    positions = {
        "ibkr-live-official-mcp-readonly": {
            "positions": [
                {
                    "symbol": "AAPL",
                    "sec_type": "STK",
                    "exchange": "SMART",
                    "currency": "USD",
                    "position": 2,
                    "avg_cost": 100,
                }
            ]
        },
        "longbridge-live-sdk-readonly": {
            "positions": [
                {
                    "symbol": "700.HK",
                    "symbol_name": "Tencent",
                    "quantity": 10,
                    "cost_price": 300,
                    "currency": "HKD",
                    "market": "HK",
                }
            ]
        },
        "binance-live-sdk-readonly": {
            "positions": [
                {"symbol": "BTC", "quantity": 0.1, "free": 0.1, "used": 0},
                {"symbol": "USDT", "quantity": 50, "free": 50, "used": 0},
            ]
        },
    }

    def get_account(profile_id):
        return accounts[profile_id]

    def get_positions(profile_id):
        return positions[profile_id]

    def get_quote(symbol, profile_id, **kwargs):
        prices = {"AAPL": 150, "700.HK": 390, "BTC/USDT": 60000}
        return {"quote": {"last": prices[symbol]}}

    service = PortfolioService(
        PortfolioStore(tmp_path / "portfolio.sqlite3"),
        settings_store=_settings_store(tmp_path),
        get_account=get_account,
        get_positions=get_positions,
        get_quote=get_quote,
        fx_fetcher=lambda: (
            Decimal("7.2"),
            Decimal("7.8"),
            "2026-08-09T00:00:00+00:00",
        ),
    )
    snapshot = service.refresh()

    assert snapshot["complete"] is True
    assert snapshot["totals"]["usd"] == 8050.0
    assert len(snapshot["positions"]) == 4
    assert snapshot["positions"][0]["symbol"] == "BTC"
    assert len(snapshot["combined_holdings"]) == 4
    assert service.latest()["snapshot_id"] == snapshot["snapshot_id"]
    assert len(service.history()) == 1
    assert "broker,symbol" in service.export_csv()
    context = service.analysis_context()
    assert context["privacy"].startswith("No account numbers")
    assert "quantity" not in context["holdings"][0]


def test_partial_refresh_is_saved_and_marked_incomplete(tmp_path):
    def get_account(profile_id):
        if profile_id.startswith("longbridge"):
            raise ConnectionError("offline")
        return {"summary": []}

    service = PortfolioService(
        PortfolioStore(tmp_path / "portfolio.sqlite3"),
        settings_store=_settings_store(tmp_path),
        get_account=get_account,
        get_positions=lambda profile_id: {"positions": []},
        get_quote=lambda *args, **kwargs: {},
        fx_fetcher=lambda: (
            Decimal("7.2"),
            Decimal("7.8"),
            "2026-08-09T00:00:00+00:00",
        ),
    )

    snapshot = service.refresh()
    assert snapshot["complete"] is False
    assert any("longbridge" in warning.lower() for warning in snapshot["warnings"])


def test_failed_broker_uses_last_successful_data_without_polluting_history(tmp_path):
    offline = False

    def get_account(profile_id):
        if offline and profile_id.startswith("ibkr"):
            raise ConnectionError("offline")
        if profile_id.startswith("ibkr"):
            return {
                "summary": [
                    {"tag": "NetLiquidation", "value": "1000", "currency": "USD"}
                ]
            }
        return {"summary": []}

    service = PortfolioService(
        PortfolioStore(tmp_path / "portfolio.sqlite3"),
        settings_store=_settings_store(tmp_path),
        get_account=get_account,
        get_positions=lambda profile_id: {
            "positions": (
                [
                    {
                        "symbol": "AAPL",
                        "sec_type": "STK",
                        "exchange": "SMART",
                        "currency": "USD",
                        "position": 2,
                        "avg_cost": 100,
                    }
                ]
                if profile_id.startswith("ibkr")
                else []
            ),
        },
        get_quote=lambda *args, **kwargs: {"quote": {"last": 150}},
        fx_fetcher=lambda: (
            Decimal("7.2"),
            Decimal("7.8"),
            "2026-08-09T00:00:00+00:00",
        ),
    )
    complete = service.refresh()
    offline = True
    partial = service.refresh()

    ibkr = next(item for item in partial["accounts"] if item["broker"] == "ibkr")
    assert complete["complete"] is True
    assert partial["complete"] is False
    assert partial["totals"]["usd"] == complete["totals"]["usd"]
    assert ibkr["status"] == "stale"
    assert ibkr["last_success_at"] == complete["created_at"]
    assert (
        next(item for item in partial["positions"] if item["broker"] == "ibkr")["stale"]
        is True
    )
    assert [item["id"] for item in service.history()] == [complete["snapshot_id"]]
    assert len(service.store.history(complete_only=False)) == 2


def test_generic_readonly_profile_uses_common_account_and_position_fields(tmp_path):
    settings = PortfolioSettingsStore(tmp_path / "portfolio.json")
    settings.connection_store.ensure(
        "main-stocks",
        "alpaca-live-sdk-readonly",
        "Main stocks",
    )
    settings.save(
        {
            "display_currency": "CNY",
            "sources": [
                {
                    "connection_id": "main-stocks",
                    "label": "Main stocks",
                    "enabled": True,
                    "order": 0,
                    "include_cash": False,
                }
            ],
        }
    )
    service = PortfolioService(
        PortfolioStore(tmp_path / "portfolio.sqlite3"),
        settings_store=settings,
        get_account=lambda profile_id: {
            "account": {"portfolio_value": "1000", "cash": "200", "currency": "USD"}
        },
        get_positions=lambda profile_id: {
            "positions": [
                {
                    "symbol": "AAPL",
                    "quantity": "4",
                    "average_cost": "150",
                    "current_price": "200",
                    "market_value": "800",
                }
            ]
        },
        get_quote=lambda *args, **kwargs: {},
        fx_fetcher=lambda: (
            Decimal("7.2"),
            Decimal("7.8"),
            "2026-08-09T00:00:00+00:00",
        ),
    )

    snapshot = service.refresh()
    account = snapshot["accounts"][0]
    position = snapshot["positions"][0]
    assert snapshot["display_currency"] == "CNY"
    assert snapshot["totals"]["usd"] == 800.0
    assert account["source_id"] == "main-stocks"
    assert account["cash_usd"] == 0.0
    assert position["source_label"] == "Main stocks"
    assert position["market_value_usd"] == 800.0


def test_auth_metadata_describes_the_profile_without_claiming_key_permissions():
    profile = TradingProfile(
        id="example-live-readonly",
        connector="example",
        label="Example",
        environment="live",
        transport="broker_sdk",
        capabilities=("account.read", "positions.read"),
        readonly=True,
        notes="Use credentials configured by the local operator.",
    )

    assert auth_metadata(profile) == {
        "method": "API credentials",
        "renewal": "provider_managed",
        "readonly": True,
        "detail": "Use credentials configured by the local operator.",
    }
