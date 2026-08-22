"""IBKR official MCP mappings for the generic read-only trading service."""

from __future__ import annotations

from typing import Any

_REMOTE_TOOL_NAMES = {
    "account": "get_account_summary",
    "positions": "get_account_positions",
    "orders": "get_account_orders",
}


def remote_tool_name(operation: str) -> str | None:
    """Return the official IBKR tool for a generic read operation."""
    return _REMOTE_TOOL_NAMES.get(operation)


def remote_arguments(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """IBKR's account read tools operate on the authorized account implicitly."""
    return {}


def normalize_result(operation: str, result: dict[str, Any]) -> dict[str, Any]:
    """Convert official IBKR MCP responses to Vibe-Trading's read shapes."""
    status = str(result.get("status") or "ok").lower()
    if status in {"error", "failed", "not_authorized"}:
        return result

    payload = result.get("data")
    if not isinstance(payload, dict):
        payload = result.get("structured_content")
    if not isinstance(payload, dict):
        payload = {}

    if operation == "account":
        currency = str(payload.get("currency") or "USD").upper()
        tags = {
            "NetLiquidation": "net_liquidation",
            "EquityWithLoanValue": "equity_with_loan_value",
            "BuyingPower": "buying_power",
            "GrossPositionValue": "gross_position_value",
            "TotalCashValue": "total_cash_value",
            "AvailableFunds": "available_funds",
            "InitialMarginReq": "initial_margin",
            "MaintMarginReq": "maintenance_margin",
            "ExcessLiquidity": "excess_liquidity",
        }
        summary = [
            {"tag": tag, "value": payload[key], "currency": currency}
            for tag, key in tags.items()
            if payload.get(key) is not None
        ]
        return {"status": "ok", "summary": summary, **payload}

    if operation == "positions":
        positions = []
        for item in payload.get("positions") or []:
            if not isinstance(item, dict):
                continue
            description = str(item.get("contract_description") or "").strip()
            positions.append(
                {
                    "contract_id": item.get("contract_id"),
                    "symbol": description,
                    "local_symbol": description,
                    "position": item.get("position"),
                    "market_price": item.get("market_price"),
                    "market_value": item.get("market_value"),
                    "currency": item.get("currency") or "USD",
                    "avg_cost": item.get("average_price"),
                    "unrealized_pnl": item.get("unrealized_pnl"),
                    "sec_type": item.get("asset_class") or "STK",
                    "asset_class": item.get("asset_class"),
                }
            )
        return {"status": "ok", "positions": positions}

    if operation == "orders":
        return {"status": "ok", "orders": payload.get("orders") or []}

    return result
