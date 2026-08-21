import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import get_current_user, get_engine
from core.engine import UltraBotEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engine", tags=["engine"])


class EngineStartRequest(BaseModel):
    mode: str = Field("paper", pattern=r"^(paper|live)$")
    broker: str = Field("paper", pattern=r"^(paper|yahoofinance|angel_one|angelone|shoonya|dhan|fyers|zerodha|upstox)$")
    strategies: Optional[List[str]] = None
    initial_capital: Optional[float] = None


@router.post("/start")
async def start_engine(
    body: EngineStartRequest,
    username: str = Depends(get_current_user),
    engine: UltraBotEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Start the trading engine with the given mode, broker, and strategies."""
    try:
        result = await engine.start(
            mode=body.mode,
            broker_name=body.broker,
            strategy_names=body.strategies,
            initial_capital=body.initial_capital,
        )
        return result
    except Exception as exc:
        logger.error("Engine start failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Engine start failed: {str(exc)}",
        )


@router.post("/stop")
async def stop_engine(
    username: str = Depends(get_current_user),
    engine: UltraBotEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Gracefully stop the trading engine."""
    try:
        result = await engine.stop()
        return result
    except Exception as exc:
        logger.error("Engine stop failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Engine stop failed: {str(exc)}",
        )


@router.post("/pause")
async def pause_engine(
    username: str = Depends(get_current_user),
    engine: UltraBotEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Pause the engine scanning loop. Position management continues."""
    try:
        result = await engine.pause()
        if result.get("status") == "not_running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Engine is not running (current state: {result.get('state', 'unknown')})",
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Engine pause failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Engine pause failed: {str(exc)}",
        )


@router.post("/resume")
async def resume_engine(
    username: str = Depends(get_current_user),
    engine: UltraBotEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Resume the engine scanning loop."""
    try:
        result = await engine.resume()
        if result.get("status") == "not_paused":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Engine is not paused (current state: {result.get('state', 'unknown')})",
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Engine resume failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Engine resume failed: {str(exc)}",
        )


@router.get("/status")
async def engine_status(
    username: str = Depends(get_current_user),
    engine: UltraBotEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Get full engine status."""
    try:
        status_data = await engine.get_status()
        return status_data
    except Exception as exc:
        logger.error("Engine status failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get engine status: {str(exc)}",
        )


@router.get("/scan-telemetry")
async def engine_scan_telemetry(
    username: str = Depends(get_current_user),
    engine: UltraBotEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Get real-time scan and strategy rejection telemetry."""
    try:
        telemetry = engine.get_scan_telemetry()
        return telemetry
    except Exception as exc:
        logger.error("Engine scan telemetry failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get scan telemetry: {str(exc)}",
        )
