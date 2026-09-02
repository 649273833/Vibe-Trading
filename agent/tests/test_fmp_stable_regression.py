"""Regression for issue 1270: FMP Stable endpoint and no silent fallback for explicit source=fmp."""

import pandas as pd

from backtest.loaders.fmp_loader import _parse_historical
from backtest.loaders.base import NoAvailableSourceError


def _stable_bars():
    return [
        {"date": "2024-01-03", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100.0},
        {"date": "2024-01-04", "open": 3.0, "high": 4.0, "low": 2.5, "close": 3.5, "volume": 200.0},
    ]


def test_parse_stable_top_level_array():
    """Stable API returns a top-level array, not {"historical": [...]}."""
    payload = _stable_bars()
    df = _parse_historical(payload)
    assert df is not None
    assert len(df) == 2
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_parse_stable_empty_array_returns_none():
    assert _parse_historical([]) is None


def test_explicit_fmp_does_not_fallback_to_yahoo(monkeypatch):
    """Explicit source=fmp must not silently return yahoo data when FMP 403s."""
    from src.market_data import fetch_market_data

    class FailFMP:
        name = "fmp"
        markets = {"us_equity"}
        def __init__(self): pass
        def is_available(self): return True
        def fetch(self, codes, start_date, end_date, interval="1D"):
            raise RuntimeError("FMP 403 legacy retired")

    class YahooOK:
        name = "yahoo"
        markets = {"us_equity"}
        def __init__(self): pass
        def is_available(self): return True
        def fetch(self, codes, start_date, end_date, interval="1D"):
            df = pd.DataFrame([{"trade_date": pd.Timestamp("2024-01-03"), "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]).set_index("trade_date")
            return {codes[0]: df}

    def resolver(name):
        if name == "fmp":
            return FailFMP
        if name == "yahoo":
            return YahooOK
        class Fail:
            name = name
            markets = {"us_equity"}
            def __init__(self): pass
            def is_available(self): return False
            def fetch(self, *a, **kw): raise RuntimeError("unavailable")
        return Fail

    result = fetch_market_data(
        codes=["AAPL.US"],
        start_date="2024-01-01",
        end_date="2024-01-31",
        source="fmp",
        interval="1D",
        loader_resolver=resolver,
        include_provenance=True,
    )
    # Must not contain yahoo data
    assert "AAPL.US" not in result, "explicit fmp should not fallback to yahoo"
    assert "_unresolved" in result and "AAPL.US" in result["_unresolved"]
    # provenance must not claim yahoo
    prov = result.get("_provenance", {})
    assert not any(v.get("source") == "yahoo" for v in prov.values())


def test_explicit_fmp_unavailable_raises_no_fallback(monkeypatch):
    """registry: explicit fmp unavailable must raise, not fallback to yahoo."""
    from backtest.loaders.registry import get_loader_cls_with_fallback
    from backtest.loaders import registry

    fmp_cls = registry.LOADER_REGISTRY["fmp"]
    monkeypatch.setattr(fmp_cls, "is_available", lambda self: False)
    try:
        get_loader_cls_with_fallback("fmp")
        assert False, "should have raised NoAvailableSourceError"
    except NoAvailableSourceError as exc:
        assert "does not fall back" in str(exc)
