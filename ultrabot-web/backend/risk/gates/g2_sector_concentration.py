"""Gate G2: Sector Concentration.

Blocks new trades when too many positions already exist in the same sector
as the incoming signal's symbol.
"""
from typing import Any, Dict

from models.risk_state import GateResult
from utils.market_utils import get_stock_sector


class G2SectorConcentration:
    """Limit the number of positions per sector."""

    def __init__(self, config: Dict[str, Any]):
        self.max_per_sector: int = config.get("max_per_sector", 2)

    async def check(self, signal: Any, context: Dict[str, Any]) -> GateResult:
        sector = get_stock_sector(signal.symbol)
        positions_by_sector: Dict[str, int] = context.get("positions_by_sector", {})
        current_count = positions_by_sector.get(sector, 0)

        if current_count >= self.max_per_sector:
            return GateResult(
                gate_name="G2_SectorConcentration",
                passed=False,
                message=(
                    f"Sector '{sector}' has {current_count} positions, "
                    f"limit is {self.max_per_sector}"
                ),
                value=float(current_count),
                threshold=float(self.max_per_sector),
                severity="warning",
            )

        return GateResult(
            gate_name="G2_SectorConcentration",
            passed=True,
            message=(
                f"Sector '{sector}' has {current_count} positions, "
                f"limit is {self.max_per_sector}"
            ),
            value=float(current_count),
            threshold=float(self.max_per_sector),
            severity="info",
        )
