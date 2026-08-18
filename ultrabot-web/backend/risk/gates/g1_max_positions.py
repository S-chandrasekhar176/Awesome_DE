"""Gate G1: Max Open Positions.

Blocks new trades when the number of open positions reaches the configured limit.
"""
from typing import Any, Dict

from models.risk_state import GateResult


class G1MaxPositions:
    """Check if the total number of open positions has reached the maximum."""

    def __init__(self, config: Dict[str, Any]):
        self.max_open_positions: int = config.get("max_open_positions", 5)

    async def check(self, signal: Any, context: Dict[str, Any]) -> GateResult:
        """Return PASS if open positions are below the limit, otherwise FAIL."""
        open_count = context.get("open_positions_count", 0)

        if open_count >= self.max_open_positions:
            return GateResult(
                gate_name="G1_MaxPositions",
                passed=False,
                message=(
                    f"Open positions ({open_count}) >= limit ({self.max_open_positions})"
                ),
                value=float(open_count),
                threshold=float(self.max_open_positions),
                severity="warning",
            )

        return GateResult(
            gate_name="G1_MaxPositions",
            passed=True,
            message=(
                f"Open positions ({open_count}) < limit ({self.max_open_positions})"
            ),
            value=float(open_count),
            threshold=float(self.max_open_positions),
            severity="info",
        )
