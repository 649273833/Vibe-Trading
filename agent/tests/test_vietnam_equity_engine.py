"""Tests for the Vietnam (HOSE) equity engine."""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.engines._market_hooks import _detect_market
from backtest.engines.vietnam_equity import (
    HOSE_LOT_SIZE,
    VietnamEquityEngine,
    hose_price_limits,
    hose_round_down,
    hose_round_up,
    hose_tick_size,
)
from backtest.models import Position


def _engine(**overrides) -> VietnamEquityEngine:
    config = {"initial_capital": 1_000_000_000.0, **overrides}
    return VietnamEquityEngine(config)


class TestMarketDetection:
    def test_vn_symbols_route_to_vietnam(self) -> None:
        assert _detect_market("VIC.VN") == "vietnam_equity"
        assert _detect_market("vic.vn") == "vietnam_equity"

    def test_tsx_venture_still_routes_to_canada(self) -> None:
        # ``.V`` and ``.VN`` are distinct suffixes; neither may claim the other.
        assert _detect_market("PNG.V") == "ca_equity"


class TestTickGrid:
    @pytest.mark.parametrize(
        "price,tick",
        [(5_000, 10.0), (9_990, 10.0), (10_000, 50.0), (49_950, 50.0),
         (50_000, 100.0), (122_300, 100.0)],
    )
    def test_tick_size_bands(self, price: float, tick: float) -> None:
        assert hose_tick_size(price) == tick

    def test_round_down_and_up(self) -> None:
        assert hose_round_down(24_267) == 24_250
        assert hose_round_up(24_267) == 24_300

    def test_on_grid_price_is_unchanged(self) -> None:
        assert hose_round_down(24_250) == 24_250
        assert hose_round_up(24_250) == 24_250


class TestPriceBand:
    def test_published_worked_example(self) -> None:
        # HOSE convention: the ceiling truncates down and the floor rounds up,
        # so both bounds stay inside the +/-7% band.
        assert hose_round_down(122_301) == 122_300
        assert hose_round_up(106_299) == 106_300

    def test_band_bounds_are_on_grid(self) -> None:
        upper, lower = hose_price_limits(24_250, 0.07)
        assert upper == 25_900
        assert lower == 22_600
        assert upper % hose_tick_size(upper) == 0
        assert lower % hose_tick_size(lower) == 0


class TestLotSize:
    def test_orders_floor_to_whole_lots(self) -> None:
        engine = _engine()
        assert engine.round_size(1_234, 24_250) == 1_200
        assert engine.round_size(HOSE_LOT_SIZE, 24_250) == HOSE_LOT_SIZE

    def test_sub_lot_order_is_not_executable(self) -> None:
        # HOSE accepts odd lots on a separate board; not modelled here.
        assert _engine().round_size(99, 24_250) == 0

    def test_negative_size_floors_to_zero(self) -> None:
        assert _engine().round_size(-500, 24_250) == 0


class TestShortSelling:
    def test_allow_short_is_refused(self) -> None:
        with pytest.raises(ValueError, match="long-only"):
            _engine(allow_short=True)

    def test_short_direction_blocked(self) -> None:
        engine = _engine()
        bar = pd.Series({"open": 24_250.0, "close": 24_300.0})
        assert engine.can_execute("VIC.VN", -1, bar) is False


class TestSettlement:
    """T+2 cycle: a buy at bar N is sellable from bar N+2."""

    def _open_position(self, engine: VietnamEquityEngine, entry_idx: int) -> None:
        engine.positions["VIC.VN"] = Position(
            symbol="VIC.VN",
            direction=1,
            entry_price=24_250.0,
            entry_time=pd.Timestamp("2026-01-05"),
            size=1_000.0,
            leverage=1.0,
            entry_bar_idx=entry_idx,
        )

    @pytest.mark.parametrize("elapsed,allowed", [(0, False), (1, False), (2, True), (5, True)])
    def test_sell_is_held_until_settlement(self, elapsed: int, allowed: bool) -> None:
        engine = _engine(price_limit=0)
        self._open_position(engine, entry_idx=10)
        engine._bar_idx = 10 + elapsed
        bar = pd.Series({"open": 24_250.0, "close": 24_300.0})
        assert engine.can_execute("VIC.VN", 0, bar) is allowed

    def test_settlement_lag_is_configurable(self) -> None:
        # Scenario testing / future rule changes: the hold follows config.
        engine = _engine(price_limit=0, vn_settlement_bars=1)
        self._open_position(engine, entry_idx=10)
        engine._bar_idx = 11
        bar = pd.Series({"open": 24_250.0, "close": 24_300.0})
        assert engine.can_execute("VIC.VN", 0, bar) is True

    def test_buy_is_never_held(self) -> None:
        engine = _engine(price_limit=0)
        self._open_position(engine, entry_idx=10)
        engine._bar_idx = 10
        bar = pd.Series({"open": 24_250.0, "close": 24_300.0})
        assert engine.can_execute("VIC.VN", 1, bar) is True


class TestBandBlocking:
    def test_buy_blocked_at_ceiling(self) -> None:
        engine = _engine()
        # Reference 24,250 -> ceiling 25,900. An open at the ceiling has no ask.
        bar = pd.Series({"open": 25_900.0, "pre_close": 24_250.0})
        assert engine.can_execute("VIC.VN", 1, bar) is False

    def test_buy_allowed_inside_band(self) -> None:
        engine = _engine()
        bar = pd.Series({"open": 24_500.0, "pre_close": 24_250.0})
        assert engine.can_execute("VIC.VN", 1, bar) is True

    def test_band_check_inactive_without_reference(self) -> None:
        engine = _engine()
        bar = pd.Series({"open": 24_500.0})
        assert engine.can_execute("VIC.VN", 1, bar) is True


class TestCostStack:
    def test_buy_pays_brokerage_only(self) -> None:
        engine = _engine()
        cost = engine.calc_commission(1_000, 24_250.0, direction=1, is_open=True)
        assert cost == pytest.approx(1_000 * 24_250.0 * 0.0015)

    def test_sell_adds_transfer_tax(self) -> None:
        engine = _engine()
        notional = 1_000 * 24_250.0
        cost = engine.calc_commission(1_000, 24_250.0, direction=1, is_open=False)
        # 0.1% of gross proceeds on top of brokerage, levied on gain or loss.
        assert cost == pytest.approx(notional * (0.0015 + 0.001))


class TestSlippage:
    def test_buy_slips_up_onto_the_grid(self) -> None:
        engine = _engine(slippage=0.001)
        filled = engine.apply_slippage(24_250.0, 1)
        assert filled == hose_round_up(24_250.0 * 1.001)
        assert filled % hose_tick_size(filled) == 0

    def test_sell_slips_down_onto_the_grid(self) -> None:
        engine = _engine(slippage=0.001)
        filled = engine.apply_slippage(24_250.0, -1)
        assert filled == hose_round_down(24_250.0 * 0.999)
        assert filled % hose_tick_size(filled) == 0
