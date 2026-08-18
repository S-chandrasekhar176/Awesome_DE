"""Comprehensive Tests for Fyers Real-Time Options Trading Pipeline.

Verifies:
1. Strike selection (ATM/OTM based on Direction and VIX).
2. Liquidity gating (OI, Volume, Bid-Ask spread).
3. Expiry rollover (rolling when nearest expiry <= 2 days).
4. Options capital & risk constraints (5% trade limit, 2% loss limit).
5. Greeks calculation (Delta, Gamma, Theta, Vega, IV).
6. End-to-end Opportunity -> Confirm flow with tradeable Fyers option symbols.
"""
import asyncio
from datetime import datetime, date, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

from options.option_chain import OptionChainFetcher
from options.strike_selector import StrikeSelector
from options.liquidity_filter import LiquidityFilter
from options.options_risk import OptionsRiskChecker
from options.greeks import GreeksCalculator
from core.engine import UltraBotEngine

IST = ZoneInfo("Asia/Kolkata")


def make_synthetic_fyers_chain(spot_price=24120.0, days_to_expiry=5):
    """Generate realistic synthetic Fyers option chain response payload."""
    today = datetime.now(IST).date()
    exp1_date = today + timedelta(days=days_to_expiry)
    exp2_date = today + timedelta(days=days_to_expiry + 7)
    exp1_epoch = int(datetime(exp1_date.year, exp1_date.month, exp1_date.day, 15, 30, tzinfo=IST).timestamp())
    exp2_epoch = int(datetime(exp2_date.year, exp2_date.month, exp2_date.day, 15, 30, tzinfo=IST).timestamp())

    options_chain = []
    strikes = [24000, 24050, 24100, 24150, 24200, 24250, 24300]

    for strike in strikes:
        # CE
        options_chain.append({
            "strike_price": float(strike),
            "option_type": "CE",
            "symbol": f"NSE:NIFTY{exp1_date.strftime('%y%b').upper()}{strike}CE",
            "ltp": max(10.0, 200.0 - (strike - 24000) * 0.7),
            "volume": 25000,
            "oi": 85000,
            "bid": 99.0,
            "ask": 100.0,
            "expiry": exp1_epoch,
            "iv": 14.5,
            "delta": 0.55 if strike <= 24100 else 0.42,
            "spot_price": spot_price,
        })
        # PE
        options_chain.append({
            "strike_price": float(strike),
            "option_type": "PE",
            "symbol": f"NSE:NIFTY{exp1_date.strftime('%y%b').upper()}{strike}PE",
            "ltp": max(10.0, 50.0 + (strike - 24000) * 0.6),
            "volume": 32000,
            "oi": 95000,
            "bid": 88.0,
            "ask": 89.0,
            "expiry": exp1_epoch,
            "iv": 15.0,
            "delta": -0.45 if strike <= 24100 else -0.58,
            "spot_price": spot_price,
        })

    return {
        "s": "ok",
        "code": 200,
        "data": {
            "optionsChain": options_chain,
            "expiryData": [
                {"date": exp1_date.strftime("%d-%b-%Y"), "expiry": exp1_epoch},
                {"date": exp2_date.strftime("%d-%b-%Y"), "expiry": exp2_epoch},
            ],
        },
    }


def test_strike_selector_direction_and_vix():
    selector = StrikeSelector()
    spot = 24120.0  # Nifty spot -> ATM = 24100

    # 1. BUY signal + Normal VIX (15.0) -> 1 Strike OTM Call (24150 CE)
    long_res = selector.select_strike(
        symbol="NIFTY", direction="BUY", entry_price=spot, vix=15.0
    )
    assert long_res["option_type"] == "CE"
    assert long_res["atm_strike"] == 24100.0
    assert long_res["strike"] == 24150.0

    # 2. SELL signal + Normal VIX (15.0) -> 1 Strike OTM Put (24050 PE)
    short_res = selector.select_strike(
        symbol="NIFTY", direction="SELL", entry_price=spot, vix=15.0
    )
    assert short_res["option_type"] == "PE"
    assert short_res["strike"] == 24050.0

    # 3. High VIX (22.0) -> ATM Strike selected for delta preservation
    high_vix_res = selector.select_strike(
        symbol="NIFTY", direction="BUY", entry_price=spot, vix=22.0
    )
    assert high_vix_res["strike"] == 24100.0
    assert "ATM" in high_vix_res["selection_reason"]


def test_liquidity_filter_rejects_illiquid_strikes():
    filter_engine = LiquidityFilter(min_oi=5000, min_volume=100, max_bid_ask_spread_pct=5.0)

    # Liquid contract
    liquid_contract = {
        "strike": 24100,
        "oi": 50000,
        "volume": 2000,
        "bid": 100.0,
        "ask": 101.0,  # 1% spread
    }
    passed, msg = filter_engine.validate_strike_liquidity(liquid_contract)
    assert passed is True

    # Low OI contract
    low_oi_contract = {
        "strike": 24100,
        "oi": 1500,  # < 5000
        "volume": 2000,
        "bid": 100.0,
        "ask": 101.0,
    }
    passed_oi, msg_oi = filter_engine.validate_strike_liquidity(low_oi_contract)
    assert passed_oi is False
    assert "Open interest" in msg_oi

    # Wide bid-ask spread contract
    wide_spread_contract = {
        "strike": 24100,
        "oi": 50000,
        "volume": 2000,
        "bid": 80.0,
        "ask": 100.0,  # 22.2% spread > 5%
    }
    passed_spread, msg_spread = filter_engine.validate_strike_liquidity(wide_spread_contract)
    assert passed_spread is False
    assert "Bid-ask spread" in msg_spread


def test_expiry_rollover_triggers_on_near_expiry():
    fetcher = OptionChainFetcher(min_days_to_expiry=2)

    # Dataset A: Nearest expiry 5 days away -> Trades nearest expiry (no rollover)
    raw_chain_5days = make_synthetic_fyers_chain(spot_price=24100, days_to_expiry=5)
    parsed_5days = fetcher.parse_fyers_chain(raw_chain_5days, symbol="NIFTY")
    assert parsed_5days["rolled_over"] is False

    # Dataset B: Nearest expiry 1 day away -> Automatically rolls over to next expiry
    raw_chain_1day = make_synthetic_fyers_chain(spot_price=24100, days_to_expiry=1)
    parsed_1day = fetcher.parse_fyers_chain(raw_chain_1day, symbol="NIFTY")
    assert parsed_1day["rolled_over"] is True
    # Verify the active expiry string matches the 2nd expiry date
    exp2_str = raw_chain_1day["data"]["expiryData"][1]["date"]
    assert parsed_1day["expiry"] == exp2_str


def test_options_risk_checker_limits():
    risk_checker = OptionsRiskChecker()
    total_capital = 100000.0  # ₹1 Lakh

    # 1. Normal trade within 5% capital cap and 2% max loss cap (₹1,750 <= ₹2,000 / ₹5,000)
    normal_res = risk_checker.check_capital_limits(
        entry_price=24100.0,
        lot_size=25,
        premium=70.0,  # ₹1,750 premium cost <= 2% max loss (₹2,000)
        total_capital=total_capital,
    )
    assert normal_res["passed"] is True


    # 2. Oversized trade exceeding 5% cap (₹10,000 premium cost > ₹5,000)
    oversized_res = risk_checker.check_capital_limits(
        entry_price=24100.0,
        lot_size=50,
        premium=250.0,  # ₹12,500 cost
        total_capital=total_capital,
    )
    assert oversized_res["passed"] is False
    assert any("exceeds max per-trade limit" in r for r in oversized_res["reasons"])


def test_greeks_calculator_delta_gamma_theta_vega():
    calc = GreeksCalculator()
    S = 24100.0
    K = 24100.0  # ATM
    T = 7.0 / 365.0  # 7 days
    sigma = 0.15  # 15% IV

    greeks_ce = calc.all_greeks(S=S, K=K, T=T, sigma=sigma, option_type="CE")
    assert 0.45 <= greeks_ce["delta"] <= 0.60
    assert greeks_ce["gamma"] > 0
    assert greeks_ce["theta"] < 0  # Theta is negative decay
    assert greeks_ce["vega"] > 0

    greeks_pe = calc.all_greeks(S=S, K=K, T=T, sigma=sigma, option_type="PE")
    assert -0.60 <= greeks_pe["delta"] <= -0.45


def test_confirm_opportunity_fno_places_real_option_order():
    """Integration test verifying confirm_opportunity with segment=FNO."""
    mock_broker = MagicMock()
    mock_broker.place_order = AsyncMock(return_value={
        "order_id": "FYERS-ORDER-12345",
        "status": "FILLED",
        "filled_price": 125.50,
        "filled_quantity": 25,
    })
    synthetic_chain = make_synthetic_fyers_chain(spot_price=24120.0, days_to_expiry=4)
    mock_broker.get_option_chain = AsyncMock(return_value=synthetic_chain)

    mock_repo = MagicMock()
    mock_repo.create_trade = AsyncMock()
    mock_repo.create_position = AsyncMock()

    async def get_repo():
        return mock_repo

    mock_config = MagicMock()
    mock_config.get_risk_config = MagicMock(return_value={"opportunity_ttl_seconds": 300, "price_mismatch_threshold_pct": 5.0})
    mock_config.get_fees_config = MagicMock(return_value={})

    engine = UltraBotEngine(
        config=mock_config,
        repository_getter=get_repo,
        error_engine=MagicMock(),
        risk_engine=MagicMock(),
        position_sizer=MagicMock(),
        partial_booker=MagicMock(),
        daily_risk_manager=MagicMock(),
        broker_factory=MagicMock(),
        feed_manager=MagicMock(),
        session_manager=MagicMock(),
    )
    engine.broker = mock_broker
    engine.vix = 15.0
    engine.current_regime = "Bull"
    engine._broadcast = AsyncMock()
    engine._run_risk_gates = AsyncMock(return_value={"passed": True, "all_gates": []})
    engine._calculate_position_size = AsyncMock(return_value={"quantity": 25, "position_size": 25000})

    # Register pending opportunity
    opp_id = "opp-nifty-fno"
    engine.pending_opportunities[opp_id] = {
        "id": opp_id,
        "symbol": "NIFTY",
        "direction": "BUY",
        "entry_price": 24120.0,
        "stop_loss": 24000.0,
        "target": 24300.0,
        "quantity": 25,
        "strategy": "ORB",
        "confidence": 0.85,
        "created_at": datetime.now(IST).isoformat(),
    }

    loop = asyncio.new_event_loop()
    try:
        confirm_res = loop.run_until_complete(
            engine.confirm_opportunity(opportunity_id=opp_id, segment="FNO")
        )
    finally:
        loop.close()

    # Verify broker.place_order was called with tradeable Fyers option symbol
    assert mock_broker.place_order.called
    call_kwargs = mock_broker.place_order.call_args[1]
    placed_symbol = call_kwargs["symbol"]
    assert placed_symbol.startswith("NSE:NIFTY")
    assert "CE" in placed_symbol  # Long direction selected Call option
    assert call_kwargs["segment"] == "FNO"

    # Verify DB position creation received option metadata
    assert mock_repo.create_position.called
    pos_kwargs = mock_repo.create_position.call_args[1]
    assert pos_kwargs["extra"]["segment"] == "FNO"
    assert pos_kwargs["extra"]["underlying_symbol"] == "NIFTY"
    assert pos_kwargs["extra"]["option_symbol"] == placed_symbol
    assert pos_kwargs["extra"]["delta"] > 0
