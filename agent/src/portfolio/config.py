"""Editable, credential-free settings for the portfolio dashboard."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.config.paths import get_runtime_root
from src.trading.connections import ConnectionStore
from src.trading.profiles import list_profiles, profile_by_id
from src.trading.types import TradingProfile

CONFIG_FILENAME = "portfolio.json"
_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


@dataclass(frozen=True)
class PortfolioSource:
    """One enabled or disabled local connection selected for aggregation."""

    connection_id: str
    label: str
    enabled: bool = True
    order: int = 0
    include_cash: bool = True

    @property
    def id(self) -> str:
        """Compatibility alias used by snapshots and refresh progress."""
        return self.connection_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioSettings:
    """Portfolio display preferences and selected read-only sources."""

    display_currency: str = "USD"
    sources: tuple[PortfolioSource, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_currency": self.display_currency,
            "sources": [source.to_dict() for source in self.sources],
        }


def eligible_profiles() -> list[TradingProfile]:
    """Return profiles that are structurally safe for portfolio reads."""
    return sorted(
        (
            profile
            for profile in list_profiles()
            if profile.readonly
            and (
                (
                    "account.read" in profile.capabilities
                    and "positions.read" in profile.capabilities
                )
                or "mcp.read.discovery" in profile.capabilities
            )
        ),
        key=lambda profile: (profile.connector, profile.environment, profile.label),
    )


def source_catalog(
    settings: PortfolioSettings,
    connection_store: ConnectionStore | None = None,
) -> list[dict[str, Any]]:
    """Describe configured local connections without exposing secret values."""
    store = connection_store or ConnectionStore()
    selected = {source.connection_id: source for source in settings.sources}
    rows = []
    for connection in store.public_list():
        source = selected.get(connection["id"])
        rows.append(
            {
                **connection,
                "connection_id": connection["id"],
                "selected": source is not None,
                "source_id": source.id if source is not None else None,
            }
        )
    return rows


def parse_settings(
    payload: dict[str, Any],
    connection_store: ConnectionStore | None = None,
) -> PortfolioSettings:
    """Validate untrusted Web settings against the local connection registry."""
    store = connection_store or ConnectionStore()
    currency = str(payload.get("display_currency") or "USD").strip().upper()
    if currency not in {"USD", "CNY"}:
        raise ValueError("display_currency must be USD or CNY")

    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("sources must be a list")
    if len(raw_sources) > 50:
        raise ValueError("at most 50 portfolio sources are allowed")

    seen_ids: set[str] = set()
    sources: list[PortfolioSource] = []
    for index, raw in enumerate(raw_sources):
        if not isinstance(raw, dict):
            raise ValueError("each portfolio source must be an object")
        connection_id = (
            str(raw.get("connection_id") or raw.get("id") or "").strip().lower()
        )
        if not _SOURCE_ID_RE.fullmatch(connection_id):
            raise ValueError(f"invalid portfolio connection id: {connection_id or '?'}")
        legacy_profile_id = str(raw.get("profile_id") or "").strip().lower()
        if legacy_profile_id:
            legacy_profile = profile_by_id(legacy_profile_id)
            connection = store.ensure(
                connection_id,
                legacy_profile.id,
                str(raw.get("label") or legacy_profile.label),
            )
        else:
            connection = store.get(connection_id)
        profile = profile_by_id(connection.profile_id)
        if profile not in eligible_profiles():
            raise ValueError(
                f"connection is not eligible for read-only portfolios: {connection_id}"
            )
        if connection_id in seen_ids:
            raise ValueError("portfolio connection ids must be unique")
        label = str(raw.get("label") or connection.label).strip()
        if (
            not label
            or len(label) > 80
            or any(ord(character) < 32 for character in label)
        ):
            raise ValueError(
                "portfolio source labels must contain 1 to 80 printable characters"
            )
        seen_ids.add(connection_id)
        sources.append(
            PortfolioSource(
                connection_id=connection_id,
                label=label,
                enabled=bool(raw.get("enabled", True)),
                order=int(raw.get("order", index)),
                include_cash=bool(raw.get("include_cash", True)),
            )
        )
    return PortfolioSettings(
        display_currency=currency,
        sources=tuple(sorted(sources, key=lambda item: (item.order, item.id))),
    )


class PortfolioSettingsStore:
    """Owner-only JSON store containing no broker credentials."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        connection_store: ConnectionStore | None = None,
    ) -> None:
        self.path = path or (get_runtime_root() / CONFIG_FILENAME)
        connection_path = (
            self.path.with_name("connections.json") if path is not None else None
        )
        self.connection_store = connection_store or ConnectionStore(connection_path)

    def load(self) -> PortfolioSettings:
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid portfolio settings: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError("invalid portfolio settings: root must be an object")
            settings = parse_settings(payload, self.connection_store)
            if any("profile_id" in source for source in payload.get("sources", [])):
                self.save(settings)
            return settings

        settings = PortfolioSettings()
        self.save(settings)
        return settings

    def save(self, settings: PortfolioSettings | dict[str, Any]) -> PortfolioSettings:
        validated = (
            parse_settings(settings, self.connection_store)
            if isinstance(settings, dict)
            else parse_settings(settings.to_dict(), self.connection_store)
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".portfolio-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(validated.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return validated
