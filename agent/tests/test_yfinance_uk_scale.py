"""yfinance loader scales GBp-quoted UK (.L/.IL) prices to GBP.

Yahoo-family data serves LSE/ISE UK names in pence (VOD.L ~117p); the loader
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


def test_fetch_scales_irish_gbp_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIBE_TRADING_DATA_CACHE", raising=False)

    def fake_download(tickers, start_date, end_date, interval):
        assert tickers == ["DCC.IL"]
        return _download_frame()

    monkeypatch.setattr(yfl, "_download_history", fake_download)

    result = yfl.DataLoader().fetch(["DCC.IL"], "2025-01-01", "2025-01-03")

    assert result["DCC.IL"]["close"].iloc[0] == pytest.approx(1.175)


def test_fetch_leaves_us_prices_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIBE_TRADING_DATA_CACHE", raising=False)

    def fake_download(tickers, start_date, end_date, interval):
        assert tickers == ["AAPL"]
        return _download_frame()

    monkeypatch.setattr(yfl, "_download_history", fake_download)

    result = yfl.DataLoader().fetch(["AAPL.US"], "2025-01-01", "2025-01-03")

    assert result["AAPL.US"]["close"].iloc[0] == pytest.approx(117.5)
