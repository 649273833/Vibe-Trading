from src.trading.connectors.ibkr.mcp import (
    normalize_result,
    remote_arguments,
    remote_tool_name,
)


def test_ibkr_read_tool_mapping_has_no_write_tools():
    assert remote_tool_name("account") == "get_account_summary"
    assert remote_tool_name("positions") == "get_account_positions"
    assert remote_tool_name("orders") == "get_account_orders"
    assert remote_tool_name("quote") is None
    assert remote_tool_name("submit_order") is None
    assert remote_arguments("positions", {"account_number": "ignored"}) == {}


def test_normalizes_account_summary_and_positions():
    account = normalize_result(
        "account",
        {
            "status": "ok",
            "data": {
                "currency": "USD",
                "net_liquidation": 1234.5,
                "buying_power": 100,
            },
        },
    )
    assert account["summary"][0] == {
        "tag": "NetLiquidation",
        "value": 1234.5,
        "currency": "USD",
    }

    positions = normalize_result(
        "positions",
        {
            "status": "ok",
            "data": {
                "positions": [
                    {
                        "contract_id": 42,
                        "contract_description": "AAPL",
                        "position": 2,
                        "market_price": 150,
                        "market_value": 300,
                        "currency": "USD",
                        "average_price": 100,
                        "unrealized_pnl": 100,
                        "asset_class": "STK",
                    }
                ]
            },
        },
    )
    assert positions["positions"][0]["symbol"] == "AAPL"
    assert positions["positions"][0]["market_price"] == 150
