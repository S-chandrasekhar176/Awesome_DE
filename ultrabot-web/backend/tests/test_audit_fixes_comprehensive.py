import pytest
from zoneinfo import ZoneInfo
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from risk.daily_risk_manager import DailyRiskManager
from risk.gates.g15_volume_liquidity import G15VolumeLiquidity
from risk.gates.g16_multi_timeframe import G16MultiTimeframe
from risk.position_sizer import PositionSizer
from strategies.performance_tracker import PerformanceTracker
from feeds.shoonya_websocket import ShoonyaWebSocketFeed
from api.routes.risk import GATE_NAMES


def test_daily_risk_manager_ist_date_and_drawdown():
    config = {"max_daily_loss_pct": 3.0, "max_drawdown_pct": 5.0}
    manager = DailyRiskManager(config=config, total_capital=100000.0)

    # Date should match IST date
    status = manager.check_daily_limits()
    assert status.date == datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    assert status.max_drawdown_pct == 0.0

    # Record profitable trade (peak updates to 110,000)
    manager.record_trade_result(10000.0)
    assert manager.peak_capital == 110000.0

    # Record losing trade (loss 4,000, current = 106,000, drawdown from peak 110,000 is ~3.64%)
    manager.record_trade_result(-4000.0)
    status2 = manager.check_daily_limits()
    assert status2.max_drawdown_pct > 3.5
    assert status2.drawdown_limit_hit is False


@pytest.mark.asyncio
async def test_g15_volume_liquidity_calculation():
    gate = G15VolumeLiquidity(config={"min_volume_ratio": 1.5})

    # High volume context should pass
    res_pass = await gate.check(signal={}, context={"volume": 3000, "avg_volume": 1500})
    assert res_pass.passed is True
    assert res_pass.value == 2.0

    # Low volume context should fail
    res_fail = await gate.check(signal={}, context={"volume": 1000, "avg_volume": 2000})
    assert res_fail.passed is False
    assert res_fail.value == 0.5


@pytest.mark.asyncio
async def test_g16_multi_timeframe_neutral_fallback():
    gate = G16MultiTimeframe(config={"require_trend_alignment": True})

    # Without context, neutral fallback should allow both BUY and SELL without bias
    res_buy = await gate.check(signal={"direction": "BUY"}, context={})
    assert res_buy.passed is True

    res_sell = await gate.check(signal={"direction": "SELL"}, context={})
    assert res_sell.passed is True


def test_position_sizer_half_size_reduction():
    sizer = PositionSizer(
        config={"kelly_min_fraction": 0.02, "kelly_max_fraction": 0.08},
        capital_config={"max_capital_usage_pct": 50.0, "max_per_position_pct": 20.0, "min_position_size": 1000.0, "virtual_capital": 100000.0},
    )

    # Standard sizing
    res_normal = sizer.calculate(
        signal={"symbol": "RELIANCE", "entry_price": 2000.0, "sl_price": 1950.0, "confidence": 0.8},
        context={},
    )

    # Half-sized sizing (TRS)
    res_half = sizer.calculate(
        signal={"symbol": "RELIANCE", "entry_price": 2000.0, "sl_price": 1950.0, "confidence": 0.8, "extra_details": {"half_size": True}},
        context={},
    )

    assert res_half.adjusted_fraction == pytest.approx(res_normal.adjusted_fraction * 0.5)


def test_performance_tracker_cursor_persistence():
    repo = MagicMock()
    repo.batch_insert_performance = MagicMock()

    tracker = PerformanceTracker(repository=repo, persist_interval=2)

    # Record 1 trade - not yet persisted
    tracker.record_trade("EMABreakout", "bull", 500.0, 60.0)
    assert repo.batch_insert_performance.call_count == 0

    # Record 2nd trade - triggers persistence of 2 records
    tracker.record_trade("EMABreakout", "bull", 300.0, 45.0)
    assert repo.batch_insert_performance.call_count == 1
    args, _ = repo.batch_insert_performance.call_args
    assert len(args[0]) == 2

    # Record 3rd and 4th trades - should only persist the new 2 records, not all 4
    tracker.record_trade("EMABreakout", "bull", 200.0, 30.0)
    tracker.record_trade("EMABreakout", "bull", -100.0, 20.0)
    assert repo.batch_insert_performance.call_count == 2
    args2, _ = repo.batch_insert_performance.call_args
    assert len(args2[0]) == 2


def test_gate_names_and_aliases():
    assert len(GATE_NAMES) == 16
    assert "G1_MaxPositions" in GATE_NAMES
    assert "G16_MultiTimeframe" in GATE_NAMES


def test_broker_factory_alias_normalization():
    from brokers.factory import BrokerFactory
    from brokers.paper_broker import PaperBroker

    broker_angel = BrokerFactory.create("angelone", mode="paper")
    assert isinstance(broker_angel, PaperBroker)

    broker_angel_hyphen = BrokerFactory.create("angel-one", mode="paper")
    assert isinstance(broker_angel_hyphen, PaperBroker)


def test_strategy_registry_multi_suite_discovery():
    from strategies.registry import StrategyRegistry
    registry = StrategyRegistry()
    registry.discover()
    strategies = registry.get_all()
    # At least 7 V2 strategies + core + advanced
    assert len(strategies) >= 15
    assert "OpeningRangeBreakout" in strategies or "ORB" in strategies or "Opening Range Breakout" in strategies


@pytest.mark.asyncio
async def test_g7_vix_filter_config_aliases():
    from risk.gates.g7_vix_filter import G7VIXFilter
    gate = G7VIXFilter(config={"vix_high_threshold": 18.0})
    assert gate.vix_threshold == 18.0
    res = await gate.check(signal={}, context={"vix": 19.5})
    assert res.passed is False

