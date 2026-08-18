"""Gate G4: Max Daily Trades.

Blocks new trades when the daily trade count reaches the configured limit.
"""
from typing import Any, Dict

from models.risk_state import GateResult


class G4MaxDailyTrades:
    """Limit the total number of trades taken in a single day."""

    def __init__(self, config: Dict[str, Any]):
        self.max_daily_trades: int = config.get("max_daily_trades", 10)

    async def check(self, signal: Any, context: Dict[str, Any]) -> GateResult:
        daily_trades = context.get("daily_trades", 0)

        if daily_trades >= self.max_daily_trades:
            return GateResult(
                gate_name="G4_MaxDailyTrades",
                passed=False,
                message=(
                    f"Daily trades ({daily_trades}) >= limit ({self.max_daily_trades})"
                ),
                value=float(daily_trades),
                threshold=float(self.max_daily_trades),
                severity="warning",
            )

        return GateResult(
            gate_name="G4_MaxDailyTrades",
            passed=True,
            message=(
                f"Daily trades ({daily_trades}) < limit ({self.max_daily_trades})"
            ),
            value=float(daily_trades),
            threshold=float(self.max_daily_trades),
            severity="info",
        )
