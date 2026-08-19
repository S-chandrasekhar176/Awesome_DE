import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.dependencies import get_current_user, get_engine, get_repository
from db.repository import Repository
from core.engine import UltraBotEngine
from config.settings import settings

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

router = APIRouter(prefix="/api/risk", tags=["risk"])

# The 16 risk gate names as defined in the system
GATE_NAMES = [
    "trade_window_gate",
    "sector_concentration_gate",
    "position_size_gate",
    "capital_usage_gate",
    "daily_loss_limit_gate",
    "max_open_positions_gate",
    "vix_gate",
    "consecutive_loss_gate",
    "price_mismatch_gate",
    "signal_confidence_gate",
    "drawdown_gate",
    "risk_reward_gate",
    "regime_compatibility_gate",
    "strategy_cooldown_gate",
    "volume_liquidity_gate",
    "multi_timeframe_gate",
]


@router.get("/status")
async def get_risk_status(
    username: str = Depends(get_current_user),
    engine: UltraBotEngine = Depends(get_engine),
    repo: Repository = Depends(get_repository),
) -> Dict[str, Any]:
    """Get the current daily risk status."""
    try:
        # Try engine's daily risk manager first
        if engine and hasattr(engine, "daily_risk"):
            try:
                risk_status = await engine.daily_risk.get_daily_risk_status()
                if hasattr(risk_status, "model_dump"):
                    return risk_status.model_dump()
                if isinstance(risk_status, dict):
                    return risk_status
            except Exception:
                pass

        # Fallback: build from repo data
        pnl = await repo.get_todays_pnl()
        open_positions = await repo.get_open_positions()
        consecutive = await repo.get_consecutive_losses()
        capital_in_use = await repo.get_capital_in_use()
        capital_config = settings.get_capital_config()
        total_capital = capital_config.get("virtual_capital", 100000)

        return {
            "date": datetime.now(IST).strftime("%Y-%m-%d"),
            "total_trades": pnl.get("total_trades", 0),
            "wins": pnl.get("wins", 0),
            "losses": pnl.get("losses", 0),
            "breakeven": pnl.get("breakeven", 0),
            "net_pnl": pnl.get("net_pnl", 0.0),
            "net_pnl_pct": 0.0,
            "daily_loss_pct": 0.0,
            "consecutive_losses": consecutive,
            "max_consecutive_losses_hit": False,
            "daily_trade_limit_hit": False,
            "daily_loss_limit_hit": False,
            "max_drawdown_pct": await repo.get_max_drawdown_pct(),
            "drawdown_limit_hit": False,
            "capital_in_use": round(capital_in_use, 2),
            "capital_usage_pct": round(capital_in_use / total_capital * 100, 2) if total_capital > 0 else 0,
            "open_positions": len(open_positions),
            "max_positions_hit": False,
            "in_cooloff": False,
            "cooloff_until": None,
            "vix": engine.vix if engine else None,
            "vix_above_threshold": False,
            "regime": engine.current_regime if engine else None,
            "can_take_new_trades": True,
            "block_reason": None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get risk status: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get risk status: {str(exc)}",
        )


@router.get("/gates")
async def get_risk_gates(
    username: str = Depends(get_current_user),
    engine: UltraBotEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Get all 13 risk gate configs and their last results."""
    try:
        risk_config = settings.get_risk_config()
        gates_data = {}

        # Get gate configs from settings
        gates_config = risk_config.get("gates", {})

        # Get last risk gate results from engine's pending opportunities or recent signals
        last_results: Dict[str, Any] = {}
        if engine and hasattr(engine, "pending_opportunities"):
            # Look at the most recent opportunity for gate results
            for opp_data in engine.pending_opportunities.values():
                risk_gates = opp_data.get("risk_gates", opp_data.get("risk_gate_results", {}))
                if risk_gates:
                    last_results = risk_gates
                    break

        for gate_name in GATE_NAMES:
            gate_cfg = gates_config.get(gate_name, {})
            gate_result = last_results.get(gate_name, {})
            gates_data[gate_name] = {
                "name": gate_name,
                "config": gate_cfg,
                "last_result": gate_result,
                "last_passed": gate_result.get("passed", None) if gate_result else None,
            }

        # Add general limits from config
        limits = {
            "max_daily_trades": risk_config.get("max_daily_trades", 10),
            "max_daily_loss_pct": risk_config.get("max_daily_loss_pct", 3.0),
            "max_open_positions": risk_config.get("max_open_positions", 5),
            "max_position_size_pct": risk_config.get("max_position_size_pct", 20.0),
            "max_consecutive_losses": risk_config.get("max_consecutive_losses", 3),
            "max_drawdown_pct": risk_config.get("max_drawdown_pct", 10.0),
            "max_sector_concentration_pct": risk_config.get("max_sector_concentration_pct", 40.0),
            "vix_high_threshold": risk_config.get("vix_high_threshold", 25.0),
            "vix_extreme_threshold": risk_config.get("vix_extreme_threshold", 35.0),
            "max_capital_usage_pct": risk_config.get("max_capital_usage_pct", 80.0),
            "cooloff_minutes": risk_config.get("cooloff_minutes", 30),
            "min_signal_confidence": risk_config.get("min_signal_confidence", 0.6),
        }

        return {
            "gates": gates_data,
            "limits": limits,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get risk gates: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get risk gates: {str(exc)}",
        )


class RiskLimitsUpdate(BaseModel):
    """Risk limit updates. Every field has a hard min/max so a fat-fingered
    or malicious value can never reach the live risk config — FastAPI
    rejects out-of-bounds values with 422 automatically. These bounds are
    deliberately conservative (see prior risk-review discussion): the goal
    is capital preservation, not maximum theoretical flexibility.
    """
    max_daily_trades: Optional[int] = Field(default=None, ge=1, le=50)
    max_daily_loss_pct: Optional[float] = Field(default=None, ge=0.5, le=5.0)
    max_open_positions: Optional[int] = Field(default=None, ge=1, le=6)
    max_position_size_pct: Optional[float] = Field(default=None, ge=1.0, le=15.0)
    max_consecutive_losses: Optional[int] = Field(default=None, ge=1, le=10)
    max_drawdown_pct: Optional[float] = Field(default=None, ge=1.0, le=15.0)
    max_sector_concentration_pct: Optional[float] = Field(default=None, ge=5.0, le=50.0)
    vix_high_threshold: Optional[float] = Field(default=None, ge=10.0, le=40.0)
    max_capital_usage_pct: Optional[float] = Field(default=None, ge=10.0, le=95.0)
    cooloff_minutes: Optional[int] = Field(default=None, ge=5, le=120)
    min_signal_confidence: Optional[float] = Field(default=None, ge=0.3, le=0.95)
    kelly_max_fraction: Optional[float] = Field(default=None, ge=0.03, le=0.15)
    hard_risk_pct: Optional[float] = Field(default=None, ge=0.25, le=2.0)




@router.put("/limits")
async def update_risk_limits(
    body: RiskLimitsUpdate,
    username: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update risk limits in the live settings."""
    try:
        update_data = body.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )

        # Update the in-memory raw config across appropriate sections
        risk_config = settings._raw_config.setdefault("risk", {})
        pos_config = settings._raw_config.setdefault("position_sizing", {})
        cap_config = settings._raw_config.setdefault("capital", {})

        for key, value in update_data.items():
            if key in {"kelly_max_fraction", "hard_risk_pct"}:
                pos_config[key] = value
                risk_config[key] = value
            elif key == "max_position_size_pct":
                risk_config["max_position_size_pct"] = value
                risk_config["max_per_position_pct"] = value
                cap_config["max_per_position_pct"] = value
            elif key == "vix_high_threshold":
                risk_config["vix_high_threshold"] = value
                risk_config["vix_threshold"] = value
            elif key == "max_capital_usage_pct":
                risk_config["max_capital_usage_pct"] = value
                cap_config["max_capital_usage_pct"] = value
            else:
                risk_config[key] = value

        # Persist to disk
        saved = settings.save()
        if not saved:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist updated limits to configuration file",
            )

        return {
            "message": "Risk limits updated successfully",
            "updated": update_data,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update risk limits: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update risk limits: {str(exc)}",
        )


@router.get("/events")
async def get_risk_events(
    username: str = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
    severity: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    """Get risk events log."""
    try:
        if severity:
            events = await repo.get_risk_events_by_severity(severity)
        else:
            events = await repo.get_risk_events(limit=limit, offset=offset)

        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "severity": e.severity,
                "message": e.message,
                "gate_name": e.gate_name,
                "trade_id": e.trade_id,
                "session_id": e.session_id,
                "extra": e.extra if e.extra else {},
                "created_at": e.created_at,
            }
            for e in events
        ]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get risk events: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get risk events: {str(exc)}",
        )
