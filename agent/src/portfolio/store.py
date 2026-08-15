"""SQLite persistence for immutable portfolio snapshots and FX cache."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.config.paths import get_runtime_root


class PortfolioStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (get_runtime_root() / "portfolio" / "portfolio.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    complete INTEGER NOT NULL,
                    total_usd TEXT NOT NULL,
                    total_cny TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_created
                    ON portfolio_snapshots(created_at DESC);
                CREATE TABLE IF NOT EXISTS portfolio_fx_cache (
                    base TEXT NOT NULL,
                    quote TEXT NOT NULL,
                    rate TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (base, quote)
                );
                """)

    def save_snapshot(self, payload: dict[str, Any]) -> None:
        totals = payload["totals"]
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO portfolio_snapshots
                    (id, created_at, complete, total_usd, total_cny, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["snapshot_id"],
                    payload["created_at"],
                    int(payload["complete"]),
                    str(totals["usd"]),
                    str(totals["cny"]),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def latest(self, *, complete_only: bool = False) -> dict[str, Any] | None:
        where = "WHERE complete = 1" if complete_only else ""
        with self._connect() as db:
            row = db.execute(
                f"SELECT payload FROM portfolio_snapshots {where} ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def history(
        self, limit: int = 180, *, complete_only: bool = True
    ) -> list[dict[str, Any]]:
        where = "WHERE complete = 1" if complete_only else ""
        with self._connect() as db:
            rows = db.execute(
                f"""
                SELECT id, created_at, complete, total_usd, total_cny
                FROM portfolio_snapshots
                {where}
                ORDER BY created_at DESC LIMIT ?
                """,
                (max(1, min(int(limit), 2000)),),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def latest_successful_source(self, source_id: str) -> dict[str, Any] | None:
        """Return the newest genuinely fresh payload for one configured source.

        Cached/stale accounts are intentionally skipped so a sequence of failed
        refreshes always points back to the original successful observation and
        preserves its real ``last_success_at`` timestamp.
        """
        with self._connect() as db:
            rows = db.execute("""
                SELECT created_at, payload
                FROM portfolio_snapshots
                ORDER BY created_at DESC LIMIT 2000
                """).fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            account = next(
                (
                    item
                    for item in payload.get("accounts", [])
                    if (item.get("source_id") or item.get("broker")) == source_id
                    and item.get("status") == "ok"
                ),
                None,
            )
            if account is None:
                continue
            return {
                "created_at": str(account.get("last_success_at") or row["created_at"]),
                "account": account,
                "positions": [
                    item
                    for item in payload.get("positions", [])
                    if (item.get("source_id") or item.get("broker")) == source_id
                ],
            }
        return None

    def latest_successful_broker(self, broker: str) -> dict[str, Any] | None:
        """Compatibility alias for snapshots written before configurable sources."""
        return self.latest_successful_source(broker)

    def save_fx(self, base: str, quote: str, rate: str, fetched_at: str) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO portfolio_fx_cache (base, quote, rate, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(base, quote) DO UPDATE SET
                    rate = excluded.rate, fetched_at = excluded.fetched_at
                """,
                (base, quote, rate, fetched_at),
            )

    def load_fx(self, base: str, quote: str) -> tuple[str, str] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT rate, fetched_at FROM portfolio_fx_cache WHERE base = ? AND quote = ?",
                (base, quote),
            ).fetchone()
        return (str(row["rate"]), str(row["fetched_at"])) if row else None
