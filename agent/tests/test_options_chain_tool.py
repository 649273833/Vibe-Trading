"""Tests for get_options_chain: expiration validation, empty ticker, exceptions.

Yahoo Finance ``get_options`` is mocked so no test reaches a live endpoint.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from src.tools import options_chain_tool as oct
from src.tools.options_chain_tool import OptionsChainTool

_SAMPLE_RESULT = {
    "expirationDates": [1787270400, 1787529600, 1787702400],
    "options": [{
        "expirationDate": 1787270400,
        "calls": [{
            "contractSymbol": "AAPL260821C00110000",
            "strike": 110.0,
            "lastPrice": 200.96,
            "bid": 199.0,
            "ask": 201.0,
            "volume": 10,
            "openInterest": 500,
            "impliedVolatility": 0.25,
            "inTheMoney": True,
            "expiration": 1787270400,
        }],
        "puts": [{
            "contractSymbol": "AAPL260821P00110000",
            "strike": 110.0,
            "lastPrice": 0.05,
            "bid": 0.0,
            "ask": 0.10,
            "volume": 100,
            "openInterest": 5000,
            "impliedVolatility": 0.30,
            "inTheMoney": False,
            "expiration": 1787270400,
        }],
    }],
}


def test_success_with_valid_expiration():
    with patch.object(oct.yahoo_client, "get_options", return_value=_SAMPLE_RESULT):
        out = OptionsChainTool().execute(ticker="AAPL.US", expiration=1787270400)
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["data"]["calls_count"] == 1
    assert payload["data"]["puts_count"] == 1


def test_success_without_expiration_returns_nearest():
    with patch.object(oct.yahoo_client, "get_options", return_value=_SAMPLE_RESULT):
        out = OptionsChainTool().execute(ticker="AAPL.US")
    payload = json.loads(out)
    assert payload["ok"] is True


def test_invalid_expiration_returns_error_with_available_dates():
    """When the requested expiration is not in the available dates list,
    the error must surface that with the available dates."""
    with patch.object(oct.yahoo_client, "get_options", return_value=_SAMPLE_RESULT):
        out = OptionsChainTool().execute(ticker="AAPL.US", expiration=9999999999)
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "not among the available" in payload["error"]
    assert "1787270400" in payload["error"]


def test_empty_ticker_returns_error():
    out = OptionsChainTool().execute(ticker="")
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "ticker" in payload["error"].lower()


def test_bad_expiration_format_returns_error():
    out = OptionsChainTool().execute(ticker="AAPL.US", expiration="not-an-int")
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "epoch" in payload["error"].lower()


def test_yahoo_request_failure_is_caught():
    with patch.object(
        oct.yahoo_client, "get_options", side_effect=RuntimeError("HTTP 429")
    ):
        out = OptionsChainTool().execute(ticker="AAPL.US")
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "429" in payload["error"]


def test_contract_normalization():
    """Yahoo camelCase fields are mapped to snake_case and capped at 60 per side."""
    result = {
        "expirationDates": [1787270400],
        "options": [{
            "expirationDate": 1787270400,
            "calls": [
                {"contractSymbol": "AAPL260821C00110000", "strike": 110.0,
                 "lastPrice": 200.96, "bid": 199.0, "ask": 201.0,
                 "volume": 10, "openInterest": 500, "impliedVolatility": 0.25,
                 "inTheMoney": True, "expiration": 1787270400},
            ] * 65,  # 65 contracts — must be capped to 60
            "puts": [
                {"contractSymbol": "AAPL260821P00110000", "strike": 110.0,
                 "lastPrice": 0.05, "bid": 0.0, "ask": 0.10,
                 "volume": 100, "openInterest": 5000, "impliedVolatility": 0.30,
                 "inTheMoney": False, "expiration": 1787270400},
            ],
        }],
    }
    with patch.object(oct.yahoo_client, "get_options", return_value=result):
        out = OptionsChainTool().execute(ticker="AAPL.US", expiration=1787270400)
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["data"]["calls_count"] == 60  # capped
    assert payload["data"]["puts_count"] == 1
    # Verify snake_case mapping
    call = payload["data"]["calls"][0]
    assert call["contract_symbol"] == "AAPL260821C00110000"
    assert call["last_price"] == 200.96
    assert call["implied_volatility"] == 0.25
    assert call["in_the_money"] is True


def test_omitted_expiration_passthrough():
    """When no expiration is passed, the nearest is used — passthrough, no validation."""
    result = {
        "expirationDates": [1787270400],
        "options": [{
            "expirationDate": 1787270400,
            "calls": [{"contractSymbol": "X", "strike": 100, "lastPrice": 1,
                       "bid": 1, "ask": 1, "volume": 1, "openInterest": 1,
                       "impliedVolatility": 0.2, "inTheMoney": False,
                       "expiration": 1787270400}],
            "puts": [],
        }],
    }
    with patch.object(oct.yahoo_client, "get_options", return_value=result):
        out = OptionsChainTool().execute(ticker="AAPL.US")
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["data"]["calls_count"] == 1
    assert payload["data"]["expirations"] == [1787270400]


def test_omitted_expiration_not_validated():
    """When no expiration is passed, the nearest is used — no validation."""
    result_empty = {"expirationDates": [], "options": []}
    with patch.object(oct.yahoo_client, "get_options", return_value=result_empty):
        out = OptionsChainTool().execute(ticker="AAPL.US")
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["data"]["calls_count"] == 0


def test_explicit_expiration_without_expiration_dates_returns_malformed_error():
    """When Yahoo result lacks expirationDates entirely, surface a malformed error."""
    result_no_dates = {"options": [
        {"expirationDate": 1787270400, "calls": [], "puts": []}
    ]}
    with patch.object(oct.yahoo_client, "get_options", return_value=result_no_dates):
        out = OptionsChainTool().execute(ticker="AAPL.US", expiration=1787270400)
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "malformed" in payload["error"].lower()


def test_malformed_expiration_dates_not_list():
    """expirationDates as a non-list must be rejected as malformed upstream."""
    malformed = {"expirationDates": "not-a-list", "options": []}
    with patch.object(oct.yahoo_client, "get_options", return_value=malformed):
        out = OptionsChainTool().execute(ticker="AAPL.US", expiration=1787270400)
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "malformed" in payload["error"].lower()


def test_empty_options_with_explicit_expiration():
    """An empty options list with an explicit expiration must return an error,
    not a silent ok:true with 0 contracts."""
    no_options = {"expirationDates": [1787270400], "options": []}
    with patch.object(oct.yahoo_client, "get_options", return_value=no_options):
        out = OptionsChainTool().execute(ticker="AAPL.US", expiration=1787270400)
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "no option chain" in payload["error"].lower()


def test_block_expiration_mismatch():
    """When options[0].expirationDate differs from the requested expiration,
    the error must surface the mismatch."""
    mismatch = {
        "expirationDates": [1787270400, 1787529600],
        "options": [{"expirationDate": 1787529600, "calls": [], "puts": []}],
    }
    with patch.object(oct.yahoo_client, "get_options", return_value=mismatch):
        out = OptionsChainTool().execute(ticker="AAPL.US", expiration=1787270400)
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "did not match" in payload["error"]
    assert "1787529600" in payload["error"]


def test_malformed_options_block_returns_error_not_500():
    """A non-dict entry in options must not crash the tool — return an error envelope."""
    malformed = {
        "expirationDates": [1787270400],
        "options": [None, {"expirationDate": 1787270400, "calls": [], "puts": []}],
    }
    with patch.object(oct.yahoo_client, "get_options", return_value=malformed):
        out = OptionsChainTool().execute(ticker="AAPL.US", expiration=1787270400)
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "malformed" in payload["error"].lower()
