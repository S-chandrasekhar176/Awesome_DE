import asyncio
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

IST = ZoneInfo("Asia/Kolkata")

from core.engine import UltraBotEngine

async def test_opportunity_validation():
    print("Testing UltraBotEngine Continuous Opportunity Validation...")

    config = MagicMock()
    config.get_risk_config.return_value = {
        "price_mismatch_threshold_pct": 0.5,
        "opportunity_ttl_seconds": 120,
    }
    config.get_capital_config.return_value = {"virtual_capital": 100000}
    config.get_broker_config.return_value = {}
    config.get_partial_booking_config.return_value = {}

    repo_getter = AsyncMock()
    repo_mock = AsyncMock()
    repo_getter.return_value = repo_mock

    feed_manager = MagicMock()
    broker_factory = MagicMock()
    session_manager = MagicMock()
    ws_manager = MagicMock()
    ws_manager.broadcast = AsyncMock()

    engine = UltraBotEngine(
        config=config,
        repository_getter=repo_getter,
        error_engine=MagicMock(),
        risk_engine=MagicMock(),
        position_sizer=MagicMock(),
        partial_booker=MagicMock(),
        daily_risk_manager=MagicMock(),
        broker_factory=broker_factory,
        feed_manager=feed_manager,
        session_manager=session_manager,
        ws_manager=ws_manager,
    )

    # Mock feed for prices
    feed_mock = MagicMock()
    async def mock_get_latest_price(symbol):
        prices = {
            "RELIANCE": 1420.0, # Target was 1412 -> Target Hit!
            "HDFCBANK": 1620.0, # StopLoss was 1628.5 -> SL Breached!
            "SBIN": 818.5,      # Entry 818.4 -> Valid!
            "TCS": 4115.0,      # Expired TTL
        }
        return prices.get(symbol, 0.0)

    feed_mock.get_latest_price = mock_get_latest_price
    engine.feed = feed_mock

    now = datetime.now(IST)

    # 1. RELIANCE: Target reached
    engine.pending_opportunities["opp-reliance"] = {
        "id": "opp-reliance",
        "symbol": "RELIANCE",
        "direction": "BUY",
        "entry_price": 1382.50,
        "target": 1412.00,
        "stop_loss": 1368.00,
        "created_at": now.isoformat(),
        "status": "pending",
    }

    # 2. HDFCBANK: SL breached
    engine.pending_opportunities["opp-hdfc"] = {
        "id": "opp-hdfc",
        "symbol": "HDFCBANK",
        "direction": "BUY",
        "entry_price": 1642.80,
        "target": 1672.00,
        "stop_loss": 1628.50,
        "created_at": now.isoformat(),
        "status": "pending",
    }

    # 3. SBIN: Still valid
    engine.pending_opportunities["opp-sbin"] = {
        "id": "opp-sbin",
        "symbol": "SBIN",
        "direction": "BUY",
        "entry_price": 818.40,
        "target": 838.00,
        "stop_loss": 809.50,
        "created_at": now.isoformat(),
        "status": "pending",
    }

    # 4. TCS: TTL timed out (created 150s ago > 120s TTL)
    engine.pending_opportunities["opp-tcs"] = {
        "id": "opp-tcs",
        "symbol": "TCS",
        "direction": "BUY",
        "entry_price": 4115.00,
        "target": 4205.00,
        "stop_loss": 4075.00,
        "created_at": (now - timedelta(seconds=150)).isoformat(),
        "status": "pending",
    }

    print(f"Pending opportunities before validation: {len(engine.pending_opportunities)}")
    assert len(engine.pending_opportunities) == 4

    # Run validation
    await engine._validate_pending_opportunities()

    print(f"Pending opportunities after validation: {len(engine.pending_opportunities)}")
    print(f"Invalidated opportunities: {len(engine.invalidated_opportunities)}")

    # Check results
    assert "opp-sbin" in engine.pending_opportunities, "SBIN should remain in pending"
    assert "opp-reliance" not in engine.pending_opportunities, "RELIANCE should be pruned (Target hit)"
    assert "opp-hdfc" not in engine.pending_opportunities, "HDFCBANK should be pruned (SL breached)"
    assert "opp-tcs" not in engine.pending_opportunities, "TCS should be pruned (TTL expired)"

    assert "opp-reliance" in engine.invalidated_opportunities
    assert engine.invalidated_opportunities["opp-reliance"]["invalidation_code"] == "TARGET_ACHIEVED_BEFORE_ENTRY"
    print(f"RELIANCE invalidation reason: {engine.invalidated_opportunities['opp-reliance']['invalidation_reason']}")

    assert "opp-hdfc" in engine.invalidated_opportunities
    assert engine.invalidated_opportunities["opp-hdfc"]["invalidation_code"] == "STOP_LOSS_BREACHED"
    print(f"HDFCBANK invalidation reason: {engine.invalidated_opportunities['opp-hdfc']['invalidation_reason']}")

    assert "opp-tcs" in engine.invalidated_opportunities
    assert engine.invalidated_opportunities["opp-tcs"]["invalidation_code"] == "SETUP_TIMEOUT_EXPIRED"
    print(f"TCS invalidation reason: {engine.invalidated_opportunities['opp-tcs']['invalidation_reason']}")

    # Test confirm rejection on stale / hit target
    engine.pending_opportunities["opp-reliance-stale"] = {
        "id": "opp-reliance-stale",
        "symbol": "RELIANCE",
        "direction": "BUY",
        "entry_price": 1382.50,
        "target": 1412.00,
        "stop_loss": 1368.00,
        "quantity": 50,
        "strategy": "Breakout",
        "created_at": now.isoformat(),
        "status": "pending",
    }
    confirm_result = await engine.confirm_opportunity("opp-reliance-stale")
    print(f"Confirming target-hit opportunity result: {confirm_result}")
    assert confirm_result.get("status") == "rejected"
    assert "Target" in confirm_result.get("reason", "")

    print("\nALL ENGINE OPPORTUNITY VALIDATION TESTS PASSED SUCCESSFULLY! ✓")

if __name__ == "__main__":
    asyncio.run(test_opportunity_validation())
