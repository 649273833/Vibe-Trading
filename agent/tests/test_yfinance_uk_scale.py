"""yfinance loader scales GBp-quoted UK (.L) prices to GBP.

Yahoo-family data serves LSE UK names in pence (VOD.L ~117p); the loader
must normalize ÷100 so ``code_currency``'s GBP matches the values (#1206).
"""
from __future__ import annotations

import pandas as pd
import pytest

import backtest.loaders.yfinance_loader as yfl


def _download_frame() -> pd.DataFrame:
    # Penny-scale LSE close: 117.5p.
    return pd.DataFrame(
        {
            "Open": [117.0, 118.0],
            "High": [118.5, 119.0],
            "Low": [116.0, 117.0],
            "Close": [117.5, 118.5],
            "Volume": [100, 200],
        },
        index=pd.DatetimeIndex(["2025-01-02", "2025-01-03"], name="Date"),
    )


def test_fetch_scales_lse_pence_to_gbp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIBE_TRADING_DATA_CACHE", raising=False)

    def fake_download(tickers, start_date, end_date, interval):
        assert tickers == ["VOD.L"]
        return _download_frame()

    monkeypatch.setattr(yfl, "_download_history", fake_download)

    result = yfl.DataLoader().fetch(["VOD.L"], "2025-01-01", "2025-01-03")

    frame = result["VOD.L"]
    # 117.5p -> £1.175; volume untouched.
    assert frame["close"].iloc[0] == pytest.approx(1.175)
    assert frame["high"].iloc[1] == pytest.approx(1.19)
    assert frame["low"].iloc[0] == pytest.approx(1.16)
    assert frame["volume"].iloc[0] == 100


def test_fetch_scales_other_lse_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIBE_TRADING_DATA_CACHE", raising=False)

    def fake_download(tickers, start_date, end_date, interval):
        assert tickers == ["BARC.L"]
        return _download_frame()

    monkeypatch.setattr(yfl, "_download_history", fake_download)

    result = yfl.DataLoader().fetch(["BARC.L"], "2025-01-01", "2025-01-03")

    assert result["BARC.L"]["close"].iloc[0] == pytest.approx(1.175)


def test_fetch_leaves_us_prices_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIBE_TRADING_DATA_CACHE", raising=False)

    def fake_download(tickers, start_date, end_date, interval):
        assert tickers == ["AAPL"]
        return _download_frame()

    monkeypatch.setattr(yfl, "_download_history", fake_download)

    result = yfl.DataLoader().fetch(["AAPL.US"], "2025-01-01", "2025-01-03")

    assert result["AAPL.US"]["close"].iloc[0] == pytest.approx(117.5)


def test_fetch_leaves_gbp_quoted_lse_unscaled(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reviewer finding: .L is not uniformly GBp — VUSA.L is priced GBP and
    # must NOT be ÷100'd. Scale only on the declared currency.
    monkeypatch.delenv("VIBE_TRADING_DATA_CACHE", raising=False)

    def fake_download(tickers, start_date, end_date, interval):
        assert tickers == ["VUSA.L"]
        return _download_frame()

    monkeypatch.setattr(yfl, "_download_history", fake_download)
    monkeypatch.setattr(yfl, "_declared_currency", lambda symbol: "GBP")

    result = yfl.DataLoader().fetch(["VUSA.L"], "2025-01-01", "2025-01-03")

    frame = result["VUSA.L"]
    assert frame["close"].iloc[0] == pytest.approx(117.5)  # untouched


def test_fetch_leaves_usd_quoted_lse_unscaled(monkeypatch: pytest.MonkeyPatch) -> None:
    # VUSD.L is USD-priced .L: suffix alone would wrongly ÷100.
    monkeypatch.delenv("VIBE_TRADING_DATA_CACHE", raising=False)

    def fake_download(tickers, start_date, end_date, interval):
        assert tickers == ["VUSD.L"]
        return _download_frame()

    monkeypatch.setattr(yfl, "_download_history", fake_download)
    monkeypatch.setattr(yfl, "_declared_currency", lambda symbol: "USD")

    result = yfl.DataLoader().fetch(["VUSD.L"], "2025-01-01", "2025-01-03")

    frame = result["VUSD.L"]
    assert frame["close"].iloc[0] == pytest.approx(117.5)  # untouched


def test_fetch_fails_closed_when_currency_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # A missing declared currency means "do not scale", not "assume pence":
    # the suffix heuristic must never be the fallback.
    monkeypatch.delenv("VIBE_TRADING_DATA_CACHE", raising=False)

    def fake_download(tickers, start_date, end_date, interval):
        assert tickers == ["VOD.L"]
        return _download_frame()

    monkeypatch.setattr(yfl, "_download_history", fake_download)
    monkeypatch.setattr(yfl, "_declared_currency", lambda symbol: None)

    result = yfl.DataLoader().fetch(["VOD.L"], "2025-01-01", "2025-01-03")

    frame = result["VOD.L"]
    assert frame["close"].iloc[0] == pytest.approx(117.5)  # NOT ÷100'd


def test_fetch_scales_only_on_gbp_pence(monkeypatch: pytest.MonkeyPatch) -> None:
    # GBp remains the only scaling trigger: real pence names still ÷100.
    monkeypatch.delenv("VIBE_TRADING_DATA_CACHE", raising=False)

    def fake_download(tickers, start_date, end_date, interval):
        assert tickers == ["VOD.L"]
        return _download_frame()

    monkeypatch.setattr(yfl, "_download_history", fake_download)
    monkeypatch.setattr(yfl, "_declared_currency", lambda symbol: "GBp")

    result = yfl.DataLoader().fetch(["VOD.L"], "2025-01-01", "2025-01-03")

    frame = result["VOD.L"]
    assert frame["close"].iloc[0] == pytest.approx(1.175)  # still scaled
