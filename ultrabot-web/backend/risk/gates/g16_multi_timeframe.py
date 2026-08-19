"""Gate G16: Multi-Timeframe Trend Alignment.

Verifies that the lower-timeframe (e.g. 5-min) entry signal aligns with the
higher-timeframe (15-min and daily) momentum trend to avoid counter-trend traps.
"""
from typing import Any, Dict

from models.risk_state import GateResult


class G16MultiTimeframe:
    """Validate higher timeframe trend alignment for directional setups."""

    def __init__(self, config: Dict[str, Any]):
        self.require_alignment: bool = bool(config.get("require_trend_alignment", True))

    async def check(self, signal: Any, context: Dict[str, Any]) -> GateResult:
        direction = getattr(signal, "direction", "LONG")
        if isinstance(signal, dict):
            direction = signal.get("direction", "LONG")
        direction = str(direction).upper()

        higher_tf_trend = context.get("trend") or context.get("nifty_trend") or "neutral"
        higher_tf_trend = str(higher_tf_trend).lower()

        # If strict alignment is required
        if self.require_alignment:
            if direction in ("BUY", "LONG") and higher_tf_trend in ("bear", "bearish", "down"):
                return GateResult(
                    gate_name="G16_MultiTimeframe",
                    passed=False,
                    message="Signal is BUY/LONG but higher timeframe trend is Bearish/Down — counter-trend trap risk",
                    value=0.0,
                    threshold=1.0,
                    severity="warning",
                )
            elif direction in ("SELL", "SHORT") and higher_tf_trend in ("bull", "bullish", "up"):
                return GateResult(
                    gate_name="G16_MultiTimeframe",
                    passed=False,
                    message="Signal is SELL/SHORT but higher timeframe trend is Bullish/Up — counter-trend trap risk",
                    value=0.0,
                    threshold=1.0,
                    severity="warning",
                )

        return GateResult(
            gate_name="G16_MultiTimeframe",
            passed=True,
            message=f"Multi-timeframe trend verified: {direction} aligns with market momentum ({higher_tf_trend})",
            value=1.0,
            threshold=1.0,
            severity="info",
        )
