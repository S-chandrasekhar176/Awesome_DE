from typing import Dict, Optional, Any
import pandas as pd
import numpy as np

from ..base import BaseStrategy
from utils.indicators import calculate_vwap, calculate_obv, calculate_atr, calculate_sma


class VolumeClimax(BaseStrategy):
    """VC — Volume Climax Strategy.

    Identifies institutional money flows via sudden, decisive volume climaxes (>3x 20-period avg)
    with strong close in directional extreme, supported by VWAP context and OBV multi-candle highs/lows.
    """

    name: str = "VC"
    description: str = "Volume Climax strategy capturing institutional volume surges with OBV and VWAP alignment."
    preferred_timeframes = ["5min"]
    best_regimes = ["Bull", "Bear", "Sideways"]
    worst_regimes = ["Volatile"]

    def __init__(self, params: Dict[str, Any] = None):
        super().__init__(params=params)

    async def scan(
        self,
        symbol: str,
        candles: pd.DataFrame,
        regime: str,
        vix: float,
    ) -> Optional[Dict]:
        if candles is None or len(candles) < 22:
            return None

        for col in ["open", "high", "low", "close", "volume"]:
            if col not in candles.columns:
                return None

        df = candles.copy()

        # Time filter:
        # Best entries: 9:15-11:30 AM & 13:00-14:00 PM. Avoid: 11:30-12:30 PM and after 14:30 PM
        if isinstance(df.index, pd.DatetimeIndex):
            curr_time = df.index[-1].time()
            curr_min = curr_time.hour * 60 + curr_time.minute
            is_morning = (9 * 60 + 15) <= curr_min <= (11 * 60 + 30)
            is_afternoon = (13 * 60) <= curr_min <= (14 * 60 + 30)
            if not (is_morning or is_afternoon):
                return None

        close = df["close"]
        open_p = df["open"]
        high = df["high"]
        low = df["low"]
        vol = df["volume"]

        curr_close = float(close.iloc[-1])
        curr_open = float(open_p.iloc[-1])
        curr_high = float(high.iloc[-1])
        curr_low = float(low.iloc[-1])
        curr_vol = float(vol.iloc[-1])
        prev_vol = float(vol.iloc[-2])

        if curr_close <= 0 or curr_open <= 0:
            return None

        # 1. Volume Climax Detection
        vol_sma = calculate_sma(vol, period=20)
        avg_vol = float(vol_sma.iloc[-2]) if not vol_sma.isna().iloc[-2] else float(vol.iloc[:-1].mean())
        if avg_vol <= 0:
            return None

        # Volume must be > 3.0x 20-period avg
        vol_ratio = curr_vol / avg_vol
        if vol_ratio < 3.0:
            return None

        # Highest volume in last 20 candles
        lookback_vol = vol.iloc[-20:]
        if curr_vol < lookback_vol.max():
            return None

        # Sudden spike: previous candle volume < 2.0x avg
        prev_vol_ratio = prev_vol / avg_vol
        if prev_vol_ratio >= 2.0:
            return None

        # 2. Price Action Filters
        candle_range = curr_high - curr_low
        body = abs(curr_close - curr_open)
        body_pct = body / curr_open

        # Body must be > 0.4% of price
        if body_pct < 0.004 or candle_range <= 0:
            return None

        # 3. VWAP Context
        vwap_series = calculate_vwap(high, low, close, vol)
        curr_vwap = float(vwap_series.iloc[-1]) if not vwap_series.isna().iloc[-1] else curr_close

        # 4. OBV Confirmation
        obv_series = calculate_obv(close, vol)
        curr_obv = float(obv_series.iloc[-1])
        recent_obv = obv_series.iloc[-20:]

        # 5. ATR for Stop Loss
        atr_series = calculate_atr(high, low, close, period=14)
        atr = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else curr_close * 0.005

        direction = None

        # LONG Criteria:
        # - Bullish candle (close > open)
        # - Close in upper 40% of range ((close - low) / range >= 0.60)
        # - Upper wick < 30% of range ((high - close) / range <= 0.30)
        # - Price at or above VWAP (or crossed above)
        # - OBV makes new 20-candle high
        if (
            curr_close > curr_open
            and ((curr_close - curr_low) / candle_range) >= 0.60
            and ((curr_high - curr_close) / candle_range) <= 0.30
            and curr_close >= curr_vwap
            and curr_obv >= recent_obv.max()
        ):
            if regime != "Volatile":
                direction = "BUY"

        # SHORT Criteria:
        # - Bearish candle (close < open)
        # - Close in lower 40% of range ((high - close) / range >= 0.60)
        # - Lower wick < 30% of range ((close - low) / range <= 0.30)
        # - Price at or below VWAP (or crossed below)
        # - OBV makes new 20-candle low
        elif (
            curr_close < curr_open
            and ((curr_high - curr_close) / candle_range) >= 0.60
            and ((curr_close - curr_low) / candle_range) <= 0.30
            and curr_close <= curr_vwap
            and curr_obv <= recent_obv.min()
        ):
            if regime != "Volatile":
                direction = "SELL"

        if direction is None:
            return None

        entry_price = curr_close

        # Stop Loss Calculation
        # SL = Entry - 1.0 * ATR(14) (BUY) / Entry + 1.0 * ATR(14) (SELL)
        # Minimum SL: 0.3%, Maximum SL: 0.8%
        min_sl_dist = entry_price * 0.003
        max_sl_dist = entry_price * 0.008
        raw_sl_dist = 1.0 * atr
        sl_dist = max(min_sl_dist, min(raw_sl_dist, max_sl_dist))

        if direction == "BUY":
            sl_price = round(entry_price - sl_dist, 2)
            target_price = round(entry_price + (1.8 * sl_dist), 2)
        else:
            sl_price = round(entry_price + sl_dist, 2)
            target_price = round(entry_price - (1.8 * sl_dist), 2)

        risk = abs(entry_price - sl_price)
        reward = abs(target_price - entry_price)
        risk_reward = round(reward / risk, 2) if risk > 0 else 1.8

        confidence = 0.82
        if vol_ratio > 4.0:
            confidence += 0.05
        if (direction == "BUY" and curr_open < curr_vwap <= curr_close) or (
            direction == "SELL" and curr_open > curr_vwap >= curr_close
        ):
            # Extra strength for VWAP crossover
            confidence += 0.05
        confidence = min(0.92, round(confidence, 2))

        return {
            "symbol": symbol,
            "direction": direction,
            "entry_price": round(entry_price, 2),
            "sl_price": sl_price,
            "target_price": target_price,
            "confidence": confidence,
            "strategy": self.name,
            "risk_reward": risk_reward,
            "extra_details": {
                "vol_ratio": round(vol_ratio, 2),
                "vwap": round(curr_vwap, 2),
                "atr": round(atr, 2),
                "obv": round(curr_obv, 2),
            },
        }
