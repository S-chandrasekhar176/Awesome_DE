"""Gate G7: VIX Filter.

Blocks new trades when the India VIX exceeds the configured threshold,
signalling excessive market volatility.
"""
from typing import Any, Dict

from models.risk_state import GateResult


class G7VIXFilter:
    """Block new trades when VIX is above threshold."""

    def __init__(self, config: Dict[str, Any]):
        self.vix_threshold: float = float(config.get("vix_threshold") or config.get("vix_high_threshold") or 22.0)
        self.vix_extreme_threshold: float = float(config.get("vix_extreme_threshold", 35.0))

    async def check(self, signal: Any, context: Dict[str, Any]) -> GateResult:
        vix = context.get("vix")
        if vix is None:
            vix = context.get("india_vix")

        # If VIX is not available, allow the trade (we can't block on missing data)
        if vix is None:
            return GateResult(
                gate_name="G7_VIXFilter",
                passed=True,
                message="VIX data not available, gate passed by default",
                value=None,
                threshold=self.vix_threshold,
                severity="info",
            )

        vix_val = float(vix)

        if vix_val >= self.vix_extreme_threshold:
            return GateResult(
                gate_name="G7_VIXFilter",
                passed=False,
                message=f"Extreme market panic: VIX ({vix_val:.1f}) >= extreme threshold ({self.vix_extreme_threshold})",
                value=vix_val,
                threshold=self.vix_extreme_threshold,
                severity="critical",
            )

        if vix_val > self.vix_threshold:
            return GateResult(
                gate_name="G7_VIXFilter",
                passed=False,
                message=f"VIX ({vix_val:.1f}) > threshold ({self.vix_threshold})",
                value=vix_val,
                threshold=self.vix_threshold,
                severity="warning",
            )

        return GateResult(
            gate_name="G7_VIXFilter",
            passed=True,
            message=f"VIX ({vix_val:.1f}) <= threshold ({self.vix_threshold})",
            value=vix_val,
            threshold=self.vix_threshold,
            severity="info",
        )
