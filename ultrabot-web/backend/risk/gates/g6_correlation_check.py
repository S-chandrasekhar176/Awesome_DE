"""Gate G6: Correlation Check.

Evaluates cross-asset / inter-stock correlation matrix.
Blocks trades if the proposed asset has high correlation (> threshold, e.g. 0.85)
with an already open position, preventing systemic portfolio risk.
"""
from typing import Any, Dict, List
from models.risk_state import GateResult

# Standard empirical correlation coefficients between major Indian liquid assets
_PAIR_CORRELATIONS: Dict[frozenset, float] = {
    frozenset({"HDFCBANK", "ICICIBANK"}): 0.88,
    frozenset({"HDFCBANK", "KOTAKBANK"}): 0.82,
    frozenset({"ICICIBANK", "AXISBANK"}): 0.85,
    frozenset({"INFY", "TCS"}): 0.89,
    frozenset({"INFY", "WIPRO"}): 0.84,
    frozenset({"TCS", "WIPRO"}): 0.81,
    frozenset({"RELIANCE", "ONGC"}): 0.78,
    frozenset({"TATAMOTORS", "MARUTI"}): 0.76,
    frozenset({"NIFTY", "BANKNIFTY"}): 0.86,
    frozenset({"NIFTY", "FINNIFTY"}): 0.91,
    frozenset({"BANKNIFTY", "FINNIFTY"}): 0.94,
    frozenset({"SBIN", "BANKNIFTY"}): 0.87,
    frozenset({"HDFCBANK", "BANKNIFTY"}): 0.92,
}


class G6CorrelationCheck:
    """Block trades when correlation with existing open positions exceeds threshold."""

    def __init__(self, config: Dict[str, Any]):
        self.max_correlation: float = float(config.get("max_pairwise_correlation", config.get("max_correlation", 0.85)))

    def get_correlation(self, sym1: str, sym2: str) -> float:
        """Return estimated pairwise correlation between two symbols."""
        if not sym1 or not sym2:
            return 0.0
        if sym1.upper() == sym2.upper():
            return 1.0
        return _PAIR_CORRELATIONS.get(frozenset({sym1.upper(), sym2.upper()}), 0.40)

    async def check(self, signal: Any, context: Dict[str, Any]) -> GateResult:
        sym = str(getattr(signal, "symbol", "") or context.get("symbol", ""))
        open_positions = context.get("open_position_symbols") or context.get("open_positions_list") or []
        
        # If open_positions is provided
        if open_positions:
            for p in open_positions:
                pos_sym = p if isinstance(p, str) else getattr(p, "symbol", p.get("symbol", "") if isinstance(p, dict) else "")
                if not pos_sym or pos_sym.upper() == sym.upper():
                    continue
                corr = self.get_correlation(sym, str(pos_sym))
                if corr >= self.max_correlation:
                    return GateResult(
                        gate_name="G6_CorrelationCheck",
                        passed=False,
                        message=(
                            f"High correlation ({corr:.2f}) between incoming {sym} and open position {pos_sym} "
                            f"(limit: {self.max_correlation:.2f})"
                        ),
                        value=corr,
                        threshold=self.max_correlation,
                        severity="warning",
                    )

        return GateResult(
            gate_name="G6_CorrelationCheck",
            passed=True,
            message=f"Correlation check passed for {sym} (all pairs < {self.max_correlation:.2f})",
            value=0.0,
            threshold=self.max_correlation,
            severity="info",
        )
