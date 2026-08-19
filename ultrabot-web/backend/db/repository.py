"""
Complete async repository for all UltraBot Web models.
Provides CRUD operations for every table plus domain-specific queries.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from db.migrations import (
    Session as SessionModel,
    Trade,
    Signal,
    Position,
    WatchlistItem,
    StrategyPerformance,
    RiskEvent,
    BrokerCredential,
    ErrorLog,
    BacktestRun,
    DailySummary,
)

from utils.market_utils import get_stock_sector

IST = ZoneInfo("Asia/Kolkata")


def _ist_now() -> str:
    return datetime.now(IST).isoformat()


def _today_str() -> str:
    return date.today().isoformat()


def _to_json(data: Any) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, default=str)


def _from_json(text: Optional[str]) -> Any:
    if text is None:
        return {}
    if isinstance(text, (dict, list)):
        return text
    return json.loads(text)


class Repository:
    """Async CRUD repository for all UltraBot models."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def close(self) -> None:
        """Close the underlying session and release the database connection."""
        if self.session is not None:
            try:
                await self.session.close()
            except Exception:
                pass

    async def __aenter__(self) -> "Repository":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None and self.session is not None:
            try:
                await self.session.rollback()
            except Exception:
                pass
        await self.close()

    # ────────────────────────────────────────
    # Generic helpers
    # ────────────────────────────────────────

    async def _add_and_flush(self, obj) -> Any:
        self.session.add(obj)
        await self.session.flush()
        await self.session.commit()
        return obj

    async def _get_by_id(self, model, obj_id: str) -> Optional[Any]:
        stmt = select(model).where(model.id == obj_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_all(self, model, limit: int = 100, offset: int = 0) -> List[Any]:
        stmt = select(model).order_by(model.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _delete_by_id(self, model, obj_id: str) -> bool:
        stmt = delete(model).where(model.id == obj_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def _count(self, model) -> int:
        stmt = select(func.count()).select_from(model)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    # ────────────────────────────────────────
    # SESSIONS
    # ────────────────────────────────────────

    async def create_session(self, date_str: Optional[str] = None, engine_state: Optional[Dict] = None, metadata_json: Optional[Dict] = None) -> SessionModel:
        obj = SessionModel(
            id=str(uuid.uuid4()),
            date=date_str or _today_str(),
            start_time=_ist_now(),
            status="running",
            engine_state=_to_json(engine_state or {}),
            metadata_json=_to_json(metadata_json or {}),
            created_at=_ist_now(),
            updated_at=_ist_now(),
        )
        return await self._add_and_flush(obj)

    async def get_session(self, session_id: str) -> Optional[SessionModel]:
        return await self._get_by_id(SessionModel, session_id)

    async def get_latest_session(self) -> Optional[SessionModel]:
        stmt = select(SessionModel).order_by(SessionModel.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_sessions(self, limit: int = 50, offset: int = 0) -> List[SessionModel]:
        return await self._get_all(SessionModel, limit, offset)

    async def update_session(self, session_id: str, **kwargs) -> Optional[SessionModel]:
        obj = await self.get_session(session_id)
        if obj is None:
            return None
        for key, value in kwargs.items():
            if key in ("engine_state", "metadata_json") and isinstance(value, dict):
                value = _to_json(value)
            if hasattr(obj, key):
                setattr(obj, key, value)
        obj.updated_at = _ist_now()
        await self.session.flush()
        await self.session.commit()
        return obj

    async def save_session_state(self, session_id: str, state: Dict[str, Any]) -> Optional[SessionModel]:
        return await self.update_session(session_id, engine_state=state, updated_at=_ist_now())

    async def delete_session(self, session_id: str) -> bool:
        return await self._delete_by_id(SessionModel, session_id)

    # ────────────────────────────────────────
    # TRADES
    # ────────────────────────────────────────

    async def create_trade(self, **kwargs) -> Trade:
        data = {
            "id": str(uuid.uuid4()),
            "created_at": _ist_now(),
            "updated_at": _ist_now(),
        }
        if "tags" in kwargs and isinstance(kwargs["tags"], list):
            kwargs["tags"] = _to_json(kwargs["tags"])
        if "extra" in kwargs and isinstance(kwargs["extra"], dict):
            kwargs["extra"] = _to_json(kwargs["extra"])
        data.update(kwargs)
        obj = Trade(**data)
        return await self._add_and_flush(obj)

    async def get_trade(self, trade_id: str) -> Optional[Trade]:
        return await self._get_by_id(Trade, trade_id)

    async def get_trades(self, limit: int = 100, offset: int = 0) -> List[Trade]:
        return await self._get_all(Trade, limit, offset)

    async def get_trades_by_date(self, trade_date: str, limit: int = 100) -> List[Trade]:
        stmt = (
            select(Trade)
            .where(Trade.entry_time.startswith(trade_date))
            .order_by(Trade.entry_time.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_trades_by_status(self, status: str) -> List[Trade]:
        stmt = select(Trade).where(Trade.status == status).order_by(Trade.entry_time.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_trades_by_symbol(self, symbol: str, limit: int = 50) -> List[Trade]:
        stmt = select(Trade).where(Trade.symbol == symbol).order_by(Trade.entry_time.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_trades_by_strategy(self, strategy: str, limit: int = 50) -> List[Trade]:
        stmt = select(Trade).where(Trade.strategy == strategy).order_by(Trade.entry_time.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_todays_trades(self) -> List[Trade]:
        today = _today_str()
        return await self.get_trades_by_date(today, limit=500)

    async def update_trade(self, trade_id: str, **kwargs) -> Optional[Trade]:
        obj = await self.get_trade(trade_id)
        if obj is None:
            return None
        for key, value in kwargs.items():
            if key in ("tags", "extra") and isinstance(value, (dict, list)):
                value = _to_json(value)
            if hasattr(obj, key):
                setattr(obj, key, value)
        obj.updated_at = _ist_now()
        await self.session.flush()
        await self.session.commit()
        return obj

    async def delete_trade(self, trade_id: str) -> bool:
        return await self._delete_by_id(Trade, trade_id)

    async def get_todays_pnl(self) -> Dict[str, Any]:
        """Get today's aggregate P&L."""
        today = _today_str()
        trades = await self.get_trades_by_date(today, limit=500)
        closed = [t for t in trades if t.status == "CLOSED"]
        gross_pnl = sum(t.pnl for t in closed)
        total_fees = sum(t.fees for t in closed) + sum(t.brokerage for t in closed)
        net_pnl = sum(t.net_pnl for t in closed)
        wins = sum(1 for t in closed if t.net_pnl > 0)
        losses = sum(1 for t in closed if t.net_pnl < 0)
        total = len(closed)
        return {
            "date": today,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / total * 100) if total > 0 else 0.0,
            "gross_pnl": round(gross_pnl, 2),
            "total_fees": round(total_fees, 2),
            "net_pnl": round(net_pnl, 2),
            "best_trade": round(max((t.net_pnl for t in closed), default=0), 2),
            "worst_trade": round(min((t.net_pnl for t in closed), default=0), 2),
        }

    # ────────────────────────────────────────
    # SIGNALS
    # ────────────────────────────────────────

    async def create_signal(self, **kwargs) -> Signal:
        data = {
            "id": str(uuid.uuid4()),
            "created_at": _ist_now(),
            "updated_at": _ist_now(),
        }
        if "signal_data" in kwargs and isinstance(kwargs["signal_data"], dict):
            kwargs["signal_data"] = _to_json(kwargs["signal_data"])
        if "risk_gate_results" in kwargs and isinstance(kwargs["risk_gate_results"], dict):
            kwargs["risk_gate_results"] = _to_json(kwargs["risk_gate_results"])
        data.update(kwargs)
        obj = Signal(**data)
        return await self._add_and_flush(obj)

    async def get_signal(self, signal_id: str) -> Optional[Signal]:
        return await self._get_by_id(Signal, signal_id)

    async def get_signals(self, limit: int = 100, offset: int = 0) -> List[Signal]:
        return await self._get_all(Signal, limit, offset)

    async def get_signals_by_status(self, status: str) -> List[Signal]:
        stmt = select(Signal).where(Signal.status == status).order_by(Signal.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_signals_by_symbol(self, symbol: str, limit: int = 50) -> List[Signal]:
        stmt = select(Signal).where(Signal.symbol == symbol).order_by(Signal.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_signals_by_strategy(self, strategy: str, limit: int = 50) -> List[Signal]:
        stmt = select(Signal).where(Signal.strategy == strategy).order_by(Signal.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_todays_signals(self) -> List[Signal]:
        today = _today_str()
        stmt = select(Signal).where(Signal.created_at.startswith(today)).order_by(Signal.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_signal(self, signal_id: str, **kwargs) -> Optional[Signal]:
        obj = await self.get_signal(signal_id)
        if obj is None:
            return None
        for key, value in kwargs.items():
            if key in ("signal_data", "risk_gate_results") and isinstance(value, dict):
                value = _to_json(value)
            if hasattr(obj, key):
                setattr(obj, key, value)
        obj.updated_at = _ist_now()
        await self.session.flush()
        await self.session.commit()
        return obj

    async def delete_signal(self, signal_id: str) -> bool:
        return await self._delete_by_id(Signal, signal_id)

    # ────────────────────────────────────────
    # POSITIONS
    # ────────────────────────────────────────

    async def create_position(self, **kwargs) -> Position:
        data = {
            "id": str(uuid.uuid4()),
            "created_at": _ist_now(),
            "updated_at": _ist_now(),
        }
        if "extra" in kwargs and isinstance(kwargs["extra"], dict):
            kwargs["extra"] = _to_json(kwargs["extra"])
        data.update(kwargs)
        obj = Position(**data)
        return await self._add_and_flush(obj)

    async def get_position(self, position_id: str) -> Optional[Position]:
        return await self._get_by_id(Position, position_id)

    async def get_positions(self, limit: int = 100, offset: int = 0) -> List[Position]:
        return await self._get_all(Position, limit, offset)

    async def get_open_positions(self) -> List[Position]:
        stmt = select(Position).where(Position.status == "OPEN").order_by(Position.entry_time.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_positions_by_symbol(self, symbol: str) -> List[Position]:
        stmt = select(Position).where(Position.symbol == symbol).order_by(Position.entry_time.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_positions_by_strategy(self, strategy: str) -> List[Position]:
        stmt = select(Position).where(Position.strategy == strategy).order_by(Position.entry_time.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_position_count_by_sector(self) -> Dict[str, int]:
        positions = await self.get_open_positions()
        sector_counts: Dict[str, int] = {}
        for pos in positions:
            sector = get_stock_sector(pos.symbol)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        return sector_counts

    async def update_position(self, position_id: str, **kwargs) -> Optional[Position]:
        obj = await self.get_position(position_id)
        if obj is None:
            return None
        for key, value in kwargs.items():
            if key == "extra" and isinstance(value, dict):
                value = _to_json(value)
            if hasattr(obj, key):
                setattr(obj, key, value)
        obj.updated_at = _ist_now()
        await self.session.flush()
        await self.session.commit()
        return obj

    async def delete_position(self, position_id: str) -> bool:
        return await self._delete_by_id(Position, position_id)

    # ────────────────────────────────────────
    # WATCHLIST
    # ────────────────────────────────────────

    async def add_watchlist_item(self, **kwargs) -> WatchlistItem:
        data = {
            "id": str(uuid.uuid4()),
            "added_at": _ist_now(),
            "created_at": _ist_now(),
            "updated_at": _ist_now(),
        }
        if "extra" in kwargs and isinstance(kwargs["extra"], dict):
            kwargs["extra"] = _to_json(kwargs["extra"])
        data.update(kwargs)
        obj = WatchlistItem(**data)
        return await self._add_and_flush(obj)

    async def get_watchlist_item(self, item_id: str) -> Optional[WatchlistItem]:
        return await self._get_by_id(WatchlistItem, item_id)

    async def get_watchlist_item_by_symbol(self, symbol: str) -> Optional[WatchlistItem]:
        stmt = select(WatchlistItem).where(WatchlistItem.symbol == symbol)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_watchlist(self) -> List[WatchlistItem]:
        stmt = select(WatchlistItem).where(WatchlistItem.is_active == True).order_by(WatchlistItem.added_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_watchlist_items(self, limit: int = 100, offset: int = 0) -> List[WatchlistItem]:
        return await self._get_all(WatchlistItem, limit, offset)

    async def update_watchlist_item(self, item_id: str, **kwargs) -> Optional[WatchlistItem]:
        obj = await self.get_watchlist_item(item_id)
        if obj is None:
            return None
        for key, value in kwargs.items():
            if key == "extra" and isinstance(value, dict):
                value = _to_json(value)
            if hasattr(obj, key):
                setattr(obj, key, value)
        obj.updated_at = _ist_now()
        await self.session.flush()
        await self.session.commit()
        return obj

    async def delete_watchlist_item(self, item_id: str) -> bool:
        return await self._delete_by_id(WatchlistItem, item_id)

    async def get_watchlist_count(self) -> int:
        return await self._count(WatchlistItem)

    # ────────────────────────────────────────
    # STRATEGY PERFORMANCE
    # ────────────────────────────────────────

    async def create_strategy_performance(self, strategy: str) -> StrategyPerformance:
        obj = StrategyPerformance(
            id=str(uuid.uuid4()),
            strategy=strategy,
            created_at=_ist_now(),
            updated_at=_ist_now(),
        )
        return await self._add_and_flush(obj)

    async def get_strategy_performance(self, strategy: str) -> Optional[StrategyPerformance]:
        stmt = select(StrategyPerformance).where(StrategyPerformance.strategy == strategy)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_strategy_performance(self) -> List[StrategyPerformance]:
        stmt = select(StrategyPerformance).order_by(StrategyPerformance.strategy)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_strategy_performance(self, strategy: str, **kwargs) -> Optional[StrategyPerformance]:
        obj = await self.get_strategy_performance(strategy)
        if obj is None:
            return None
        for key, value in kwargs.items():
            if key in ("daily_stats", "extra") and isinstance(value, dict):
                value = _to_json(value)
            if hasattr(obj, key):
                setattr(obj, key, value)
        obj.updated_at = _ist_now()
        await self.session.flush()
        await self.session.commit()
        return obj

    async def delete_strategy_performance(self, strategy: str) -> bool:
        obj = await self.get_strategy_performance(strategy)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        await self.session.commit()
        return True

    async def ensure_strategy_performance(self, strategy: str) -> StrategyPerformance:
        obj = await self.get_strategy_performance(strategy)
        if obj is None:
            obj = await self.create_strategy_performance(strategy)
        return obj

    # ────────────────────────────────────────
    # RISK EVENTS
    # ────────────────────────────────────────

    async def create_risk_event(self, **kwargs) -> RiskEvent:
        data = {
            "id": str(uuid.uuid4()),
            "created_at": _ist_now(),
        }
        if "extra" in kwargs and isinstance(kwargs["extra"], dict):
            kwargs["extra"] = _to_json(kwargs["extra"])
        data.update(kwargs)
        obj = RiskEvent(**data)
        return await self._add_and_flush(obj)

    async def get_risk_events(self, limit: int = 100, offset: int = 0) -> List[RiskEvent]:
        stmt = select(RiskEvent).order_by(RiskEvent.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_risk_events_by_severity(self, severity: str) -> List[RiskEvent]:
        stmt = select(RiskEvent).where(RiskEvent.severity == severity).order_by(RiskEvent.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_todays_risk_events(self) -> List[RiskEvent]:
        today = _today_str()
        stmt = select(RiskEvent).where(RiskEvent.created_at.startswith(today)).order_by(RiskEvent.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_risk_event(self, event_id: str) -> bool:
        return await self._delete_by_id(RiskEvent, event_id)

    # ────────────────────────────────────────
    # BROKER CREDENTIALS
    # ────────────────────────────────────────

    async def save_broker_credentials(self, broker_name: str, encrypted_creds: str, **kwargs) -> BrokerCredential:
        existing = await self.get_broker_credentials(broker_name)
        if existing:
            existing.encrypted_credentials = encrypted_creds
            existing.updated_at = _ist_now()
            for k, v in kwargs.items():
                if k == "extra" and isinstance(v, dict):
                    v = _to_json(v)
                if hasattr(existing, k):
                    setattr(existing, k, v)
            await self.session.flush()
            return existing

        data = {
            "id": str(uuid.uuid4()),
            "broker_name": broker_name,
            "encrypted_credentials": encrypted_creds,
            "created_at": _ist_now(),
            "updated_at": _ist_now(),
        }
        if "extra" in kwargs and isinstance(kwargs["extra"], dict):
            kwargs["extra"] = _to_json(kwargs["extra"])
        data.update(kwargs)
        obj = BrokerCredential(**data)
        return await self._add_and_flush(obj)

    async def get_broker_credentials(self, broker_name: str) -> Optional[BrokerCredential]:
        stmt = select(BrokerCredential).where(BrokerCredential.broker_name == broker_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_broker_credentials(self) -> List[BrokerCredential]:
        stmt = select(BrokerCredential).order_by(BrokerCredential.broker_name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_broker_credentials(self, broker_name: str) -> bool:
        stmt = delete(BrokerCredential).where(BrokerCredential.broker_name == broker_name)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    # ────────────────────────────────────────
    # ERROR LOGS
    # ────────────────────────────────────────

    async def create_error_log(self, **kwargs) -> ErrorLog:
        data = {
            "id": str(uuid.uuid4()),
            "created_at": _ist_now(),
            "updated_at": _ist_now(),
        }
        if "context" in kwargs and isinstance(kwargs["context"], dict):
            kwargs["context"] = _to_json(kwargs["context"])
        if "extra" in kwargs and isinstance(kwargs["extra"], dict):
            kwargs["extra"] = _to_json(kwargs["extra"])
        data.update(kwargs)
        obj = ErrorLog(**data)
        return await self._add_and_flush(obj)

    async def get_error_log(self, error_id: str) -> Optional[ErrorLog]:
        return await self._get_by_id(ErrorLog, error_id)

    async def get_error_by_code(self, error_code: str) -> Optional[ErrorLog]:
        stmt = select(ErrorLog).where(ErrorLog.error_code == error_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_errors(
        self,
        resolved: Optional[bool] = None,
        severity: Optional[str] = None,
        error_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ErrorLog]:
        stmt = select(ErrorLog)
        if resolved is not None:
            stmt = stmt.where(ErrorLog.is_resolved == resolved)
        if severity:
            stmt = stmt.where(ErrorLog.severity == severity)
        if error_type:
            stmt = stmt.where(ErrorLog.error_type == error_type)
        stmt = stmt.order_by(ErrorLog.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_errors_count(
        self,
        resolved: Optional[bool] = None,
        severity: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> int:
        stmt = select(func.count()).select_from(ErrorLog)
        if resolved is not None:
            stmt = stmt.where(ErrorLog.is_resolved == resolved)
        if severity:
            stmt = stmt.where(ErrorLog.severity == severity)
        if error_type:
            stmt = stmt.where(ErrorLog.error_type == error_type)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def get_unresolved_errors(self) -> List[ErrorLog]:
        return await self.get_errors(resolved=False, limit=500)

    async def get_error_stats(self) -> Dict[str, Any]:
        total = await self._count(ErrorLog)
        stmt_unresolved = select(func.count()).select_from(ErrorLog).where(ErrorLog.is_resolved == False)
        result_unresolved = await self.session.execute(stmt_unresolved)
        unresolved = result_unresolved.scalar_one() or 0

        stmt_today = select(func.count()).select_from(ErrorLog).where(ErrorLog.created_at.startswith(_today_str()))
        result_today = await self.session.execute(stmt_today)
        today_count = result_today.scalar_one() or 0

        stmt_critical = select(func.count()).select_from(ErrorLog).where(ErrorLog.severity == "critical", ErrorLog.is_resolved == False)
        result_critical = await self.session.execute(stmt_critical)
        critical_unresolved = result_critical.scalar_one() or 0

        # Count by type
        stmt_types = select(ErrorLog.error_type, func.count()).group_by(ErrorLog.error_type)
        result_types = await self.session.execute(stmt_types)
        by_type = dict(result_types.all())

        return {
            "total_errors": total,
            "unresolved": unresolved,
            "today_count": today_count,
            "critical_unresolved": critical_unresolved,
            "by_type": by_type,
        }

    async def resolve_error(self, error_id: str, resolution_note: str = "") -> Optional[ErrorLog]:
        obj = await self.get_error_log(error_id)
        if obj is None:
            return None
        obj.is_resolved = True
        obj.resolved_at = _ist_now()
        obj.resolution_note = resolution_note
        obj.updated_at = _ist_now()
        await self.session.flush()
        return obj

    async def delete_error_log(self, error_id: str) -> bool:
        return await self._delete_by_id(ErrorLog, error_id)

    # ────────────────────────────────────────
    # BACKTEST RUNS
    # ────────────────────────────────────────

    async def create_backtest_run(
        self,
        id: Optional[str] = None,
        strategy: str = "",
        symbol: Optional[str] = None,
        start_date: str = "",
        end_date: str = "",
        timeframe: str = "5min",
        initial_capital: float = 100000.0,
        status: str = "PENDING",
        parameters: Optional[Dict[str, Any]] = None,
        results: Optional[Dict[str, Any]] = None,
        equity_curve: Optional[List[Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> BacktestRun:
        run_id = id or kwargs.pop("run_id", None) or str(uuid.uuid4())
        data = {
            "id": run_id,
            "strategy": strategy,
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "timeframe": timeframe,
            "initial_capital": initial_capital,
            "status": status,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "parameters": _to_json(parameters or {}),
            "results": _to_json(results or {}),
            "equity_curve": _to_json(equity_curve or []),
            "extra": _to_json(extra or {}),
            "created_at": _ist_now(),
            "updated_at": _ist_now(),
        }
        for k, v in kwargs.items():
            if k in ("parameters", "results", "extra") and isinstance(v, dict):
                v = _to_json(v)
            elif k == "equity_curve" and isinstance(v, list):
                v = _to_json(v)
            data[k] = v

        run = BacktestRun(**data)
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_backtest_run(self, run_id: str) -> Optional[BacktestRun]:
        stmt = select(BacktestRun).where(BacktestRun.id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_backtest_runs(
        self, strategy: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[BacktestRun]:
        stmt = select(BacktestRun).order_by(BacktestRun.created_at.desc())
        if strategy:
            stmt = stmt.where(BacktestRun.strategy == strategy)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_backtest_history(self, limit: int = 50) -> List[BacktestRun]:
        """Alias for get_backtest_runs."""
        return await self.get_backtest_runs(limit=limit)

    async def update_backtest_run(self, run_id: str, **kwargs: Any) -> Optional[BacktestRun]:
        obj = await self.get_backtest_run(run_id)
        if obj is None:
            return None
        for key, value in kwargs.items():
            if key in ("parameters", "results", "equity_curve", "extra") and isinstance(value, (dict, list)):
                value = _to_json(value)
            if hasattr(obj, key):
                setattr(obj, key, value)
        obj.updated_at = _ist_now()
        await self.session.flush()
        return obj

    async def delete_backtest_run(self, run_id: str) -> bool:
        stmt = delete(BacktestRun).where(BacktestRun.id == run_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    # ────────────────────────────────────────
    # DAILY SUMMARY
    # ────────────────────────────────────────

    async def create_daily_summary(self, **kwargs) -> DailySummary:
        data = {
            "id": str(uuid.uuid4()),
            "created_at": _ist_now(),
            "updated_at": _ist_now(),
        }
        if "strategies_used" in kwargs and isinstance(kwargs["strategies_used"], list):
            kwargs["strategies_used"] = _to_json(kwargs["strategies_used"])
        if "sector_pnl" in kwargs and isinstance(kwargs["sector_pnl"], dict):
            kwargs["sector_pnl"] = _to_json(kwargs["sector_pnl"])
        if "extra" in kwargs and isinstance(kwargs["extra"], dict):
            kwargs["extra"] = _to_json(kwargs["extra"])
        data.update(kwargs)
        obj = DailySummary(**data)
        return await self._add_and_flush(obj)

    async def get_daily_summary(self, date_str: str) -> Optional[DailySummary]:
        stmt = select(DailySummary).where(DailySummary.date == date_str)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_daily_summary(self) -> Optional[DailySummary]:
        stmt = select(DailySummary).order_by(DailySummary.date.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_daily_summaries(self, limit: int = 30, offset: int = 0) -> List[DailySummary]:
        stmt = select(DailySummary).order_by(DailySummary.date.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_daily_summary(self, date_str: str, **kwargs) -> Optional[DailySummary]:
        obj = await self.get_daily_summary(date_str)
        if obj is None:
            return None
        for key, value in kwargs.items():
            if key in ("strategies_used", "extra") and isinstance(value, (dict, list)):
                value = _to_json(value)
            if key == "sector_pnl" and isinstance(value, dict):
                value = _to_json(value)
            if hasattr(obj, key):
                setattr(obj, key, value)
        obj.updated_at = _ist_now()
        await self.session.flush()
        return obj

    async def delete_daily_summary(self, date_str: str) -> bool:
        stmt = delete(DailySummary).where(DailySummary.date == date_str)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    # ────────────────────────────────────────
    # BULK / AGGREGATE HELPERS
    # ────────────────────────────────────────

    async def get_capital_in_use(self) -> float:
        """Sum of invested_amount for all open positions."""
        positions = await self.get_open_positions()
        return sum(p.invested_amount for p in positions)

    async def get_todays_trade_count(self) -> int:
        """Count of all trades (including open) created today."""
        today = _today_str()
        stmt = select(func.count()).select_from(Trade).where(Trade.entry_time.startswith(today))
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def get_todays_closed_trades(self) -> List[Trade]:
        """Get all closed trades from today."""
        today = _today_str()
        stmt = (
            select(Trade)
            .where(Trade.entry_time.startswith(today), Trade.status == "CLOSED")
            .order_by(Trade.exit_time.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_consecutive_losses(self) -> int:
        """Count consecutive losses from the most recent trades."""
        stmt = select(Trade).where(Trade.status == "CLOSED").order_by(Trade.exit_time.desc()).limit(20)
        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())
        count = 0
        for t in trades:
            if t.net_pnl < 0:
                count += 1
            else:
                break
        return count

    async def get_max_drawdown_pct(self) -> float:
        """Calculate max drawdown percentage from all closed trades."""
        stmt = select(Trade).where(Trade.status == "CLOSED").order_by(Trade.exit_time.asc())
        result = await self.session.execute(stmt)
        trades = list(result.scalars().all())
        if not trades:
            return 0.0
        peak = 100000.0  # Starting capital
        max_dd = 0.0
        running = peak
        for t in trades:
            running += t.net_pnl
            if running > peak:
                peak = running
            dd = (peak - running) / peak * 100 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 2)
