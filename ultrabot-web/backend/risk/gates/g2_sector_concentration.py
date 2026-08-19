"""Gate G2: Sector Concentration.

Blocks new trades when too many positions already exist in the same sector
as the incoming signal's symbol.
"""
from typing import Any, Dict

from models.risk_state import GateResult
from utils.market_utils import get_stock_sector


class G2SectorConcentration:
    """Limit the number of positions and capital concentration per sector."""

    def __init__(self, config: Dict[str, Any]):
        self.max_per_sector: int = int(config.get("max_per_sector", 2))
        self.max_sector_pct: float = float(config.get("max_sector_concentration_pct", 40.0))

    async def check(self, signal: Any, context: Dict[str, Any]) -> GateResult:
        sym = str(
            getattr(signal, "symbol", "")
            or (signal.get("symbol", "") if isinstance(signal, dict) else "")
            or context.get("symbol", "")
        )
        sector = get_stock_sector(sym)
        positions_by_sector: Dict[str, int] = context.get("positions_by_sector", {})
        current_count = positions_by_sector.get(sector, 0)
        max_positions = int(context.get("max_open_positions", 5))

        # Check count limit
        effective_max = min(self.max_per_sector, max(1, int(max_positions * self.max_sector_pct / 100.0))) if self.max_sector_pct < 100 else self.max_per_sector

        if current_count >= effective_max:
            return GateResult(
                gate_name="G2_SectorConcentration",
                passed=False,
                message=(
                    f"Sector '{sector}' has {current_count} positions, "
                    f"limit is {effective_max} (max {self.max_sector_pct}% concentration)"
                ),
                value=float(current_count),
                threshold=float(effective_max),
                severity="warning",
            )

        return GateResult(
            gate_name="G2_SectorConcentration",
            passed=True,
            message=(
                f"Sector '{sector}' has {current_count} positions, "
                f"within limit {effective_max}"
            ),
            value=float(current_count),
            threshold=float(effective_max),
            severity="info",
        )
