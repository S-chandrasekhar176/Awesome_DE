"""Gate G3: Max Position Size.

Blocks trades where the estimated position value would exceed the configured
percentage of total capital.
"""
from typing import Any, Dict

from models.risk_state import GateResult


class G3MaxPositionSize:
    """Ensure no single position exceeds a percentage of total capital."""

    def __init__(self, config: Dict[str, Any]):
        self.max_position_pct: float = float(config.get("max_per_position_pct") or config.get("max_position_size_pct") or config.get("max_capital_per_trade_pct") or 25)

    async def check(self, signal: Any, context: Dict[str, Any]) -> GateResult:
        total_capital = float(context.get("total_capital") or context.get("capital") or 100000.0)
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
        quantity = float(getattr(signal, "quantity", 0) or context.get("quantity", 0) or 0)
        
        # Calculate actual estimated trade value (position_value/position_size in context or entry_price * quantity)
        if "position_value" in context and context["position_value"] is not None:
            position_value = float(context["position_value"])
        elif "position_size" in context and context["position_size"] is not None:
            position_value = float(context["position_size"])
        elif hasattr(signal, "position_size") and getattr(signal, "position_size") is not None:
            position_value = float(getattr(signal, "position_size"))
        elif quantity > 0 and entry_price > 0:
            position_value = entry_price * quantity
        else:
            position_value = entry_price
        max_allowed = total_capital * (self.max_position_pct / 100.0)


        if position_value > max_allowed:
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

        return GateResult(
            gate_name="G3_MaxPositionSize",
            passed=True,
            message=(
                f"Position value ₹{position_value:,.0f} within "
                f"{self.max_position_pct}% of capital (₹{max_allowed:,.0f})"
            ),
            value=position_value,
            threshold=max_allowed,
            severity="info",
        )
