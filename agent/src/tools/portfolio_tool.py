"""Read-only, sanitized portfolio context for model-assisted analysis."""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool
from src.portfolio.service import PortfolioService


class PortfolioSummaryTool(BaseTool):
    name = "portfolio_summary"
    description = (
        "Read the latest sanitized IBKR, Longbridge and Binance portfolio snapshot. "
        "Returns deterministic totals, account allocation, combined holdings, weights, "
        "unrealized P/L and data-quality warnings. It never returns credentials, account "
        "numbers, order IDs, personal names, or local paths. Use it for portfolio analysis; "
        "use the Web Portfolio refresh button before requesting current data."
    )
    parameters = {"type": "object", "properties": {}, "required": []}
    repeatable = True
    is_readonly = True

    def execute(self, **_: Any) -> str:
        context = PortfolioService().analysis_context()
        if context is None:
            return json.dumps(
                {
                    "status": "empty",
                    "message": "No portfolio snapshot exists. Refresh the Portfolio page first.",
                },
                ensure_ascii=False,
            )
        return json.dumps({"status": "ok", "context": context}, ensure_ascii=False)
