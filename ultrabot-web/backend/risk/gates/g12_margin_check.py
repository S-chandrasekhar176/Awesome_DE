"""Gate G12: Margin Check.

Blocks trades when the required margin for the proposed position
exceeds the available margin/capital.
"""
from typing import Any, Dict, Optional

from models.risk_state import GateResult
from utils.market_utils import get_lot_size, is_fno_stock



class G12MarginCheck:
    """Ensure sufficient margin is available for the new position."""

    def __init__(self, config: Dict[str, Any]):
        self.max_capital_usage_pct: float = float(
            config.get("max_capital_usage_pct", 90)
        )

    async def check(self, signal: Any, context: Dict[str, Any]) -> GateResult:
        available_margin = float(context.get("available_capital") or context.get("margin_available") or 0.0)
        entry_price = float(getattr(signal, "entry_price", 0) or 0)
        total_capital = float(context.get("total_capital") or context.get("capital") or 0.0)

        if entry_price <= 0:
            return GateResult(
                gate_name="G12_MarginCheck",
                passed=False,
                message="Signal entry_price is zero or negative, cannot calculate margin",
                severity="critical",
            )

        if total_capital <= 0:
            return GateResult(
                gate_name="G12_MarginCheck",
                passed=False,
                message="Total capital is zero, cannot evaluate margin",
                severity="critical",
            )

        # Estimate quantity: use explicit quantity if specified, else F&O lot size or 1
        qty = float(getattr(signal, "quantity", 0) or context.get("quantity", 0) or 0)
        if qty <= 0:
            seg = str(getattr(signal, "segment", "") or context.get("segment", "")).upper()
            sym = str(getattr(signal, "symbol", "") or context.get("symbol", ""))
            if seg in ("FNO", "F&O", "NFO", "OPTIONS", "FUTURES") or is_fno_stock(sym):
                qty = float(get_lot_size(sym))
            else:
                qty = 1.0


        required_margin = entry_price * qty
        max_allowed_margin = total_capital * (self.max_capital_usage_pct / 100.0)

        if required_margin > available_margin:
            return GateResult(
                gate_name="G12_MarginCheck",
                passed=False,
                message=(
                    f"Required margin (₹{required_margin:,.0f}) exceeds "
                    f"available (₹{available_margin:,.0f})"
                ),
                value=required_margin,
                threshold=available_margin,
                severity="critical",
            )

        return GateResult(
            gate_name="G12_MarginCheck",
            passed=True,
            message=(
                f"Required margin (₹{required_margin:,.0f}) within "
                f"available (₹{available_margin:,.0f}), "
                f"max usage (₹{max_allowed_margin:,.0f})"
            ),
            value=required_margin,
            threshold=available_margin,
            severity="info",
        )
