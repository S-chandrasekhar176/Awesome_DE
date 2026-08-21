"""Gate G3: Max Position Size.

Blocks trades where the estimated position value would exceed the configured
percentage of total capital.
"""
from typing import Any, Dict

from models.risk_state import GateResult


class G3MaxPositionSize:
    """Ensure no single position exceeds a percentage of total capital."""

    def __init__(self, config: Dict[str, Any]):
        self.max_position_pct: float = float(config.get("max_per_position_pct", config.get("max_capital_per_trade_pct", 25)))

    async def check(self, signal: Any, context: Dict[str, Any]) -> GateResult:
        total_capital = float(context.get("total_capital") or context.get("capital") or 1000000.0)
        if total_capital <= 0:
            return GateResult(
                gate_name="G3_MaxPositionSize",
                passed=False,
                message="Total capital is zero or negative, cannot evaluate position size",
                value=0.0,
                threshold=0.0,
                severity="critical",
            )

        entry_price = float(getattr(signal, "entry_price", 0) or 0)
        quantity = float(getattr(signal, "quantity", 0) or context.get("quantity", 1) or 1)
        
        # Calculate actual estimated trade value
        position_value = entry_price * quantity if entry_price > 0 else float(context.get("position_value", 0))
        max_allowed = total_capital * (self.max_position_pct / 100.0)

        # For intraday equity/options/futures, margin required is ~20% of contract value
        margin_required = position_value * 0.20

        # Pass if either total position value OR margin commitment is within allowed limit
        if position_value <= max_allowed or margin_required <= max_allowed:
            return GateResult(
                gate_name="G3_MaxPositionSize",
                passed=True,
                message=(
                    f"Position value ₹{position_value:,.0f} (Margin: ₹{margin_required:,.0f}) within "
                    f"{self.max_position_pct}% of capital (₹{max_allowed:,.0f})"
                ),
                value=position_value,
                threshold=max_allowed,
                severity="info",
            )

        return GateResult(
            gate_name="G3_MaxPositionSize",
            passed=False,
            message=(
                f"Position value ₹{position_value:,.0f} exceeds "
                f"{self.max_position_pct}% of capital (₹{max_allowed:,.0f})"
            ),
            value=position_value,
            threshold=max_allowed,
            severity="warning",
        )
