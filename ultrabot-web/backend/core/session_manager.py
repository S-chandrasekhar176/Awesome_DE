"""Session manager for UltraBot trading sessions.

Creates, saves, recovers, and closes trading sessions via the Repository.
"""
from __future__ import annotations

import json
import logging
import uuid
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class SessionManager:
    """Manages trading session lifecycle: create, save state, recover, close."""

    def __init__(self, repo_getter):
        """Initialize SessionManager.

        Args:
            repo_getter: An async callable that returns a Repository instance.
                         This decouples the session manager from the DB session lifecycle.
        """
        self._repo_getter = repo_getter

    async def _get_repo(self):
        """Get a repository instance from the getter."""
        return await self._repo_getter()

    @asynccontextmanager
    async def _repo_context(self):
        """Context manager yielding repository and ensuring session cleanup."""
        getter_res = self._repo_getter()
        repo = await getter_res if asyncio.iscoroutine(getter_res) else getter_res
        try:
            yield repo
        finally:
            if hasattr(repo, "close") and callable(repo.close):
                try:
                    close_res = repo.close()
                    if asyncio.iscoroutine(close_res):
                        await close_res
                except Exception:
                    pass

    async def create_session(
        self,
        mode: str,
        broker: str,
        initial_capital: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new trading session record in the database.

        Args:
            mode: 'paper' or 'live'.
            broker: Broker identifier (e.g., 'angel_one', 'shoonya').
            initial_capital: Starting capital for the session.
            metadata: Optional additional metadata to store with the session.

        Returns:
            The session UUID string.
        """
        engine_state = {
            "mode": mode,
            "broker": broker,
            "initial_capital": initial_capital,
            "current_regime": "Sideways",
            "vix": 15.0,
            "nifty_price": 0.0,
            "open_positions": [],
            "watchlist": [],
            "daily_risk": {},
            "active_strategies": [],
            "pending_opportunities": [],
        }

        meta = metadata or {}
        meta["broker"] = broker
        meta["mode"] = mode
        meta["initial_capital"] = initial_capital

        async with self._repo_context() as repo:
            session = await repo.create_session(
                engine_state=engine_state,
                metadata_json=meta,
            )
            session_id = session.id

        logger.info(
            "Created session %s (mode=%s, broker=%s, capital=%.2f)",
            session_id,
            mode,
            broker,
            initial_capital,
        )
        return session_id

    async def save_state(self, session_id: str, engine) -> None:
        """Capture and persist the current engine state into the session.

        Serializes: open positions, watchlist, daily risk, active strategies,
        and regime into the session's engine_state JSON field.

        Args:
            session_id: The session UUID.
            engine: The UltraBotEngine instance (duck-typed for attributes).
        """
        # Collect open positions from engine
        open_positions: List[Dict[str, Any]] = []
        if hasattr(engine, 'broker') and engine.broker is not None:
            try:
                positions = await engine.broker.get_positions()
                if positions and isinstance(positions, list):
                    for pos in positions:
                        open_positions.append({
                            "symbol": getattr(pos, "symbol", str(pos.get("symbol", ""))) if isinstance(pos, dict) else getattr(pos, "symbol", ""),
                            "quantity": getattr(pos, "quantity", pos.get("quantity", 0)) if isinstance(pos, dict) else getattr(pos, "quantity", 0),
                            "avg_price": getattr(pos, "avg_price", pos.get("avg_price", 0)) if isinstance(pos, dict) else getattr(pos, "avg_price", 0),
                            "pnl": getattr(pos, "pnl", pos.get("pnl", 0)) if isinstance(pos, dict) else getattr(pos, "pnl", 0),
                        })
            except Exception:
                logger.debug("Could not fetch positions from broker for state save")

        # Get watchlist items
        watchlist: List[Dict[str, Any]] = []
        async with self._repo_context() as repo:
            try:
                watchlist_items = await repo.get_active_watchlist()
                for item in watchlist_items:
                    watchlist.append({
                        "symbol": item.symbol,
                        "name": getattr(item, "name", ""),
                        "is_active": item.is_active,
                    })
            except Exception:
                logger.debug("Could not fetch watchlist for state save")

            # Get daily risk status
            daily_risk: Dict[str, Any] = {}
            if hasattr(engine, 'daily_risk') and engine.daily_risk is not None:
                try:
                    risk_status = await engine.daily_risk.get_daily_risk_status()
                    if hasattr(risk_status, 'model_dump'):
                        daily_risk = risk_status.model_dump()
                    elif isinstance(risk_status, dict):
                        daily_risk = risk_status
                except Exception:
                    logger.debug("Could not get daily risk status for state save")

            # Active strategies from engine
            active_strategies: List[str] = []
            if hasattr(engine, 'current_regime'):
                active_strategies = getattr(engine, 'active_strategies', [])
                if not isinstance(active_strategies, list):
                    active_strategies = []

            # Build state
            state = {
                "mode": getattr(engine, 'mode', None),
                "broker": getattr(engine, 'broker', None),
                "initial_capital": getattr(engine, 'initial_capital', 0),
                "current_regime": getattr(engine, 'current_regime', "Sideways"),
                "vix": getattr(engine, 'vix', 15.0),
                "nifty_price": getattr(engine, 'nifty_price', 0.0),
                "open_positions": open_positions,
                "watchlist": watchlist,
                "daily_risk": daily_risk,
                "active_strategies": active_strategies,
                "pending_opportunities": list(getattr(engine, 'pending_opportunities', {}).keys()),
                "saved_at": datetime.now(IST).isoformat(),
            }

            await repo.save_session_state(session_id, state)
            logger.info("Saved engine state for session %s (%d positions, %d watchlist items)",
                         session_id, len(open_positions), len(watchlist))

    async def recover_state(self, session_id: str) -> Dict[str, Any]:
        """Recover a previously saved session state.

        Args:
            session_id: The session UUID to recover.

        Returns:
            Dict with recovered state data. Keys: session_id, mode, broker,
            initial_capital, current_regime, vix, nifty_price, open_positions,
            watchlist, daily_risk, active_strategies, pending_opportunity_ids.

        Raises:
            ValueError: If session_id is not found.
        """
        async with self._repo_context() as repo:
            session = await repo.get_session(session_id)

        if session is None:
            raise ValueError(f"Session {session_id} not found")

        # Parse stored engine_state JSON
        engine_state: Dict[str, Any] = {}
        if session.engine_state:
            if isinstance(session.engine_state, str):
                try:
                    engine_state = json.loads(session.engine_state)
                except (json.JSONDecodeError, TypeError):
                    engine_state = {}
            elif isinstance(session.engine_state, dict):
                engine_state = session.engine_state

        # Parse metadata
        metadata: Dict[str, Any] = {}
        if session.metadata_json:
            if isinstance(session.metadata_json, str):
                try:
                    metadata = json.loads(session.metadata_json)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
            elif isinstance(session.metadata_json, dict):
                metadata = session.metadata_json

        recovered = {
            "session_id": session.id,
            "date": session.date,
            "status": session.status,
            "mode": engine_state.get("mode") or metadata.get("mode", "paper"),
            "broker": engine_state.get("broker") or metadata.get("broker", "paper"),
            "initial_capital": engine_state.get("initial_capital") or metadata.get("initial_capital", 0),
            "current_regime": engine_state.get("current_regime", "Sideways"),
            "vix": engine_state.get("vix", 15.0),
            "nifty_price": engine_state.get("nifty_price", 0.0),
            "open_positions": engine_state.get("open_positions", []),
            "watchlist": engine_state.get("watchlist", []),
            "daily_risk": engine_state.get("daily_risk", {}),
            "active_strategies": engine_state.get("active_strategies", []),
            "pending_opportunity_ids": engine_state.get("pending_opportunities", []),
            "saved_at": engine_state.get("saved_at"),
            "raw_engine_state": engine_state,
        }

        logger.info(
            "Recovered session %s (mode=%s, broker=%s, %d positions)",
            session_id,
            recovered["mode"],
            recovered["broker"],
            len(recovered["open_positions"]),
        )
        return recovered

    async def close_session(
        self,
        session_id: str,
        final_capital: float,
        status: str = "completed",
    ) -> None:
        """Close a trading session.

        Updates the session status and saves final capital in metadata.

        Args:
            session_id: The session UUID to close.
            final_capital: Final capital at end of session.
            status: Terminal status ('completed', 'error', 'stopped').
        """
        async with self._repo_context() as repo:
            await repo.update_session(
                session_id,
                status=status,
                metadata_json={
                    "final_capital": final_capital,
                    "closed_at": datetime.now(IST).isoformat(),
                },
            )

        logger.info(
            "Closed session %s with status=%s, final_capital=%.2f",
            session_id,
            status,
            final_capital,
        )

    async def get_active_session(self) -> Optional[Dict[str, Any]]:
        """Get the most recent active (running) session.

        Returns:
            Dict with session info if an active session exists, else None.
        """
        async with self._repo_context() as repo:
            session = await repo.get_latest_session()

        if session is None:
            return None

        if session.status not in ("running", "paused"):
            return None

        # Parse engine state
        engine_state: Dict[str, Any] = {}
        if session.engine_state:
            if isinstance(session.engine_state, str):
                try:
                    engine_state = json.loads(session.engine_state)
                except (json.JSONDecodeError, TypeError):
                    engine_state = {}
            elif isinstance(session.engine_state, dict):
                engine_state = session.engine_state

        return {
            "session_id": session.id,
            "date": session.date,
            "status": session.status,
            "start_time": session.start_time,
            "updated_at": session.updated_at,
            "mode": engine_state.get("mode", "unknown"),
            "broker": engine_state.get("broker", "unknown"),
            "initial_capital": engine_state.get("initial_capital", 0),
            "current_regime": engine_state.get("current_regime", "Sideways"),
            "vix": engine_state.get("vix", 15.0),
        }
