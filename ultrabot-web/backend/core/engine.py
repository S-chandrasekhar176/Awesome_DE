"""UltraBotEngine – main orchestrator for the trading system.

The engine coordinates market hours checks, feed updates, strategy scanning,
risk gating, position sizing, opportunity creation, trade execution,
position management (SL/target/partial bookings), and WebSocket broadcasting.

Strategies are loaded from ``strategies.registry`` when available.  If that
module hasn't been built yet the engine still runs – it simply won't generate
signals.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from core.engine_state import EngineState, EngineMode
from core.market_hours import MarketHours
from options.option_chain import OptionChainFetcher
from options.strike_selector import StrikeSelector
from options.liquidity_filter import LiquidityFilter
from options.options_risk import OptionsRiskChecker
from options.greeks import GreeksCalculator
from utils.market_utils import get_stock_sector

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


# Try to import strategy registry – graceful fallback if not yet built
try:
    from strategies.registry import StrategyRegistry
    _STRATEGIES_AVAILABLE = True
    logger.info("Strategy registry loaded successfully")
except ImportError:
    _STRATEGIES_AVAILABLE = False
    logger.warning("strategies.registry not available – engine will run without signal generation")
    class StrategyRegistry:
        def __init__(self):
            self._strategies = {}
        def get_all(self):
            return self._strategies
        def get(self, name):
            return None
        def discover(self):
            pass


class UltraBotEngine:
    """The brain of UltraBot. Orchestrates all subsystems."""

    def __init__(
        self,
        config,
        repository_getter: Callable,
        error_engine,
        risk_engine,
        position_sizer,
        partial_booker,
        daily_risk_manager,
        broker_factory,
        feed_manager,
        session_manager,
        market_hours: Optional[MarketHours] = None,
        ws_manager=None,
        strategy_registry=None,
        adaptive_manager=None,
        regime_detector=None,
        performance_tracker=None,
        kronos_scanner=None,
        alert_manager=None,
    ):
        self.config = config
        self._repo_getter = repository_getter
        self.error_engine = error_engine
        self.risk_engine = risk_engine
        self.position_sizer = position_sizer
        self.partial_booker = partial_booker
        self.daily_risk = daily_risk_manager
        self.broker_factory = broker_factory
        self.feed_manager = feed_manager
        self.session_manager = session_manager
        self.market_hours = market_hours or MarketHours()
        self.ws_manager = ws_manager
        self.alert_manager = alert_manager
        self.strategy_registry = strategy_registry
        self.adaptive_manager = adaptive_manager
        self.regime_detector = regime_detector
        self.performance_tracker = performance_tracker
        self.kronos_scanner = kronos_scanner

        # Engine state
        self.state = EngineState.STOPPED
        self.mode: Optional[str] = None
        self.broker = None
        self.broker_name: str = "paper"
        self.feed = None
        self.session_id: Optional[str] = None
        self.initial_capital: Optional[float] = None
        self.pending_opportunities: Dict[str, dict] = {}  # opportunity_id -> opportunity data
        self.invalidated_opportunities: Dict[str, dict] = {}  # opportunity_id -> expired/invalidated data
        self._opportunities_lock: asyncio.Lock = asyncio.Lock()
        self._main_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        self.current_regime: str = "Sideways"
        self.vix: float = 15.0
        self.nifty_price: float = 0.0
        self.nifty_change: float = 0.0
        self._prev_nifty_close: float = 0.0
        self.banknifty_price: float = 0.0
        self.active_strategies: List[str] = []
        self._scan_count: int = 0
        self._symbols_scanned_count: int = 0
        self._signals_generated: int = 0
        self._signals_passed_count: int = 0
        self._signals_rejected_count: int = 0
        self._rejections_by_gate: Dict[str, int] = {}
        self._rejections_by_strategy: Dict[str, int] = {}
        self._recent_scan_telemetry: List[Dict[str, Any]] = []
        self._trades_executed: int = 0
        self._errors_count: int = 0

    async def _route_alert(self, alert_type: str, data: Any) -> None:
        """Route an alert through the alert_manager to Telegram / WS / Logs."""
        if self.alert_manager is not None:
            try:
                await self.alert_manager.route_alert(alert_type, data)
            except Exception as alert_err:
                logger.error("Failed to route alert '%s': %s", alert_type, alert_err)

    # ------------------------------------------------------------------
    # Repository accessor
    # ------------------------------------------------------------------

    async def _get_repo(self):
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

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    async def start(
        self,
        mode: str = "paper",
        broker_name: str = "paper",
        strategy_names: Optional[List[str]] = None,
        initial_capital: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Start the trading engine.

        Args:
            mode: 'paper' or 'live'.
            broker_name: Broker identifier.
            strategy_names: Optional list of specific strategies to activate.
                             If None, uses regime-based activation from config.
            initial_capital: Starting capital. Defaults to config value.

        Returns:
            Dict with session_id and status.
        """
        if self.state not in (EngineState.STOPPED, EngineState.ERROR):
            return {"status": "already_running", "state": self.state.value}

        self.state = EngineState.STARTING
        await self._broadcast("engine", {"type": "engine_state_change", "state": self.state.value})

        try:
            # Validate mode
            if mode not in ("paper", "live"):
                mode = "paper"
            self.mode = mode
            self.broker_name = broker_name or "paper"

            # Capital
            capital_config = self.config.get_capital_config()
            self.initial_capital = initial_capital or capital_config.get("virtual_capital", 100000)

            # Create broker
            broker_config = self.config.get_broker_config(broker_name)
            self.broker = self.broker_factory.create(broker_name, mode=mode, **(broker_config or {}))

            # Authenticate
            if hasattr(self.broker, "authenticate"):
                try:
                    await self.broker.authenticate()
                    logger.info("Broker '%s' authenticated successfully", broker_name)
                except Exception as auth_exc:
                    logger.error("Broker '%s' authentication failed: %s", broker_name, auth_exc, exc_info=True)
                    raise

            # Connect feed
            if self.feed_manager is not None:
                self.feed = self.feed_manager
                if hasattr(self.feed_manager, "connect"):
                    try:
                        await self.feed_manager.connect()
                        logger.info("Feed manager connected")
                    except Exception as feed_exc:
                        logger.error("Feed manager connection failed: %s", feed_exc, exc_info=True)
                        raise

            # Create session
            self.session_id = await self.session_manager.create_session(
                mode=mode,
                broker=broker_name,
                initial_capital=self.initial_capital,
            )

            # Recover state if resuming a previous session
            active_session = await self.session_manager.get_active_session()
            if active_session and active_session.get("session_id") != self.session_id:
                try:
                    recovered = await self.session_manager.recover_state(
                        active_session["session_id"]
                    )
                    self.current_regime = recovered.get("current_regime", "Sideways")
                    self.vix = recovered.get("vix", 15.0)
                    self.nifty_price = recovered.get("nifty_price", 0.0)
                    self.active_strategies = recovered.get("active_strategies", [])
                    logger.info(
                        "Recovered state from previous session: regime=%s, vix=%.1f",
                        self.current_regime, self.vix,
                    )
                except Exception as exc:
                    logger.warning("Could not recover previous session state: %s", exc)

            # Initialize active strategies
            if strategy_names:
                self.active_strategies = list(strategy_names)
            elif not self.active_strategies:
                activation_config = self.config.get_strategy_activation(self.current_regime)
                self.active_strategies = list(activation_config.get("active", []))
                logger.info(
                    "Activated strategies for regime '%s': %s",
                    self.current_regime,
                    self.active_strategies,
                )

            # Reset counters
            self._scan_count = 0
            self._signals_generated = 0
            self._trades_executed = 0
            self._errors_count = 0
            self._start_time = datetime.now(IST)
            self.pending_opportunities = {}

            # Set running
            self.state = EngineState.RUNNING
            await self._broadcast("engine", {
                "type": "engine_state_change",
                "state": self.state.value,
                "session_id": self.session_id,
                "mode": self.mode,
            })
            await self._route_alert("engine_status", {
                "state": "running",
                "mode": mode,
                "broker": broker_name,
                "details": f"Session {self.session_id[:8]} started with {len(self.active_strategies)} active strategies ({self.current_regime} regime)",
            })

            # Start main loop as background task
            self._main_task = asyncio.create_task(self._main_loop())
            logger.info(
                "Engine started: mode=%s, broker=%s, session=%s, strategies=%s",
                mode,
                broker_name,
                self.session_id,
                self.active_strategies,
            )

            return {
                "status": "started",
                "session_id": self.session_id,
                "mode": mode,
                "broker": broker_name,
                "regime": self.current_regime,
                "strategies": self.active_strategies,
            }

        except Exception as exc:
            self.state = EngineState.ERROR
            await self.error_engine.handle_error(
                exc,
                context={"action": "engine_start", "mode": mode, "broker": broker_name},
                session_id=self.session_id,
            )
            await self._broadcast("engine", {"type": "engine_state_change", "state": "error"})
            await self._route_alert("engine_status", {
                "state": "error",
                "mode": mode,
                "broker": broker_name,
                "details": f"Engine failed to start: {exc}",
            })
            self._errors_count += 1
            logger.error("Engine start failed: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    async def stop(self) -> Dict[str, Any]:
        """Gracefully stop the engine.

        Saves state, cancels the main loop, disconnects broker/feed,
        and closes the session.
        """
        if self.state == EngineState.STOPPED:
            return {"status": "already_stopped"}

        logger.info("Engine stopping...")
        prev_state = self.state.value

        try:
            # Cancel main loop
            if self._main_task is not None and not self._main_task.done():
                self._main_task.cancel()
                try:
                    await self._main_task
                except asyncio.CancelledError:
                    pass
                self._main_task = None

            # Save state before shutting down
            if self.session_id:
                try:
                    await self.session_manager.save_state(self.session_id, self)
                except Exception as exc:
                    logger.warning("Failed to save session state on stop: %s", exc)

            # Close positions via broker if live mode
            final_capital = self.initial_capital or 0
            if self.broker is not None:
                try:
                    # Get current capital / P&L
                    if hasattr(self.broker, "get_balance"):
                        balance = await self.broker.get_balance()
                        if isinstance(balance, (int, float)):
                            final_capital = balance
                        elif isinstance(balance, dict):
                            final_capital = balance.get("available_cash", balance.get("net", self.initial_capital or 0))

                    # Disconnect broker
                    if hasattr(self.broker, "disconnect"):
                        await self.broker.disconnect()
                except Exception as exc:
                    logger.warning("Error during broker shutdown: %s", exc)

            # Disconnect feed
            if self.feed is not None and hasattr(self.feed, "disconnect"):
                try:
                    await self.feed.disconnect()
                except Exception as exc:
                    logger.warning("Error during feed disconnect: %s", exc)
                self.feed = None

            # Close session
            if self.session_id:
                try:
                    await self.session_manager.close_session(
                        self.session_id,
                        final_capital=final_capital,
                        status="stopped",
                    )
                except Exception as exc:
                    logger.warning("Failed to close session: %s", exc)

            self.state = EngineState.STOPPED
            self.broker = None

            await self._broadcast("engine", {
                "type": "engine_state_change",
                "state": self.state.value,
                "previous_state": prev_state,
            })
            await self._route_alert("engine_status", {
                "state": "stopped",
                "mode": self.mode or "",
                "broker": self.broker_name or "",
                "details": f"Trades executed: {self._trades_executed}, Scans completed: {self._scan_count}",
            })

            logger.info(
                "Engine stopped. Scans: %d, Signals: %d, Trades: %d, Errors: %d",
                self._scan_count, self._signals_generated, self._trades_executed, self._errors_count,
            )
            return {"status": "stopped", "final_capital": round(final_capital, 2)}

        except Exception as exc:
            self.state = EngineState.ERROR
            await self.error_engine.handle_error(
                exc,
                context={"action": "engine_stop", "previous_state": prev_state},
                session_id=self.session_id,
            )
            await self._route_alert("engine_status", {
                "state": "error",
                "mode": self.mode or "",
                "broker": self.broker_name or "",
                "details": f"Engine error on stop: {exc}",
            })
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Pause / Resume
    # ------------------------------------------------------------------

    async def pause(self) -> Dict[str, Any]:
        """Pause the engine scanning loop. Position management continues."""
        if self.state != EngineState.RUNNING:
            return {"status": "not_running", "state": self.state.value}

        self.state = EngineState.PAUSED
        await self._broadcast("engine", {"type": "engine_state_change", "state": "paused"})
        await self._route_alert("engine_status", {
            "state": "paused",
            "mode": self.mode or "",
            "broker": self.broker_name or "",
            "details": "Engine paused by user. Position risk management is still active.",
        })
        logger.info("Engine paused")
        return {"status": "paused"}

    async def resume(self) -> Dict[str, Any]:
        """Resume the engine scanning loop."""
        if self.state != EngineState.PAUSED:
            return {"status": "not_paused", "state": self.state.value}

        self.state = EngineState.RUNNING
        await self._broadcast("engine", {"type": "engine_state_change", "state": "running"})
        await self._route_alert("engine_status", {
            "state": "running",
            "mode": self.mode or "",
            "broker": self.broker_name or "",
            "details": "Engine scanning resumed.",
        })
        logger.info("Engine resumed")
        return {"status": "running"}

    # ------------------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------------------

    async def _main_loop(self) -> None:
        """Core scanning loop. Runs while state is RUNNING or PAUSED.

        Each iteration:
        1. Check market open / session
        2. Update position prices
        3. Check partial bookings & trailing SLs on open positions
        4. Check daily risk status
        5. If market open AND trade window AND not paused AND risk OK:
           a. Fetch watchlist
           b. Run strategy scans per symbol
           c. Run risk gates on signals
           d. Calculate position size
           e. Create opportunity, push to WS
        6. Sleep for scan_interval
        """
        scan_interval = self.config.get_engine_config().get("scan_interval_seconds", 180)
        max_retries = self.config.get_engine_config().get("max_scan_retries", 10)
        retry_count = 0
        _last_success_time = datetime.now(IST)
        _RETRY_RESET_SECONDS = 300  # Reset retry counter after 5 min of uptime

        while self.state in (EngineState.RUNNING, EngineState.PAUSED, EngineState.SCANNING):
            iteration_start = datetime.now(IST)

            try:
                # --- Step 1: Market check ---
                market_status = self.market_hours.get_market_status()
                await self._broadcast("market", {
                    "type": "market_status",
                    "is_open": market_status["is_open"],
                    "session": market_status["session"],
                })

                # --- Step 2: Update position prices ---
                try:
                    await self._update_position_prices()
                except Exception as pos_price_exc:
                    logger.warning("Could not update position prices: %s", pos_price_exc, exc_info=True)
                    self._errors_count += 1

                # --- Step 3: Manage open positions (SL, target, partial bookings, trailing SL) ---
                try:
                    await self._manage_all_positions()
                except Exception as manage_exc:
                    logger.warning("Could not manage positions: %s", manage_exc, exc_info=True)
                    self._errors_count += 1

                # --- Step 3b: Validate pending opportunities against live prices & TTL ---
                try:
                    await self._validate_pending_opportunities()
                except Exception as validate_exc:
                    logger.warning("Could not validate pending opportunities: %s", validate_exc, exc_info=True)
                    self._errors_count += 1

                # --- Step 4: Check daily risk ---
                risk_ok = False
                can_trade = False
                try:
                    risk_status = await self.daily_risk.get_daily_risk_status()
                    risk_ok = risk_status.can_take_new_trades

                    await self._broadcast("risk", {
                        "type": "daily_risk_update",
                        "can_take_new_trades": risk_ok,
                        "block_reason": risk_status.block_reason,
                        "net_pnl": risk_status.net_pnl,
                        "open_positions": risk_status.open_positions,
                        "consecutive_losses": risk_status.consecutive_losses,
                    })
                except Exception as risk_exc:
                    risk_ok = False
                    logger.error("Could not check daily risk (failing closed): %s", risk_exc, exc_info=True)
                    self._errors_count += 1

                # --- Steps 5+: Only scan if conditions are met ---
                can_trade = (
                    self.state == EngineState.RUNNING
                    and market_status["is_open"]
                    and self.market_hours.is_new_trade_window()
                    and risk_ok
                )

                if can_trade:
                    self.state = EngineState.SCANNING
                    await self._broadcast("engine", {"type": "engine_state_change", "state": "scanning"})

                    try:
                        await self._scan_watchlist()
                    except Exception as scan_exc:
                        logger.error("Watchlist scan error: %s", scan_exc, exc_info=True)
                        try:
                            await self.error_engine.handle_error(
                                scan_exc,
                                context={"action": "watchlist_scan"},
                                session_id=self.session_id,
                            )
                        except Exception:
                            logger.debug("Failed to report watchlist scan error to error engine")
                        self._errors_count += 1
                    finally:
                        if self.state == EngineState.SCANNING:
                            self.state = EngineState.RUNNING

                    self._scan_count += 1

                # Auto-save state periodically (every 10 scans or iterations)
                if self.session_id and (self._scan_count > 0 and self._scan_count % 10 == 0):
                    try:
                        await self.session_manager.save_state(self.session_id, self)
                    except Exception as save_exc:
                        logger.warning("Periodic state save failed: %s", save_exc, exc_info=True)

                # Reset consecutive failure counter on successful cycle
                retry_count = 0
                _last_success_time = datetime.now(IST)

            except asyncio.CancelledError:
                logger.info("Main loop cancelled")
                return
            except Exception as loop_exc:
                retry_count += 1
                self._errors_count += 1
                logger.error("Main loop error (attempt %d/%d): %s", retry_count, max_retries, loop_exc, exc_info=True)

                # Protect error reporting — it must never crash the loop
                try:
                    await self.error_engine.handle_error(
                        loop_exc,
                        context={"action": "main_loop", "attempt": retry_count},
                        session_id=self.session_id,
                    )
                except Exception as err_exc:
                    logger.debug("Failed to report main loop error to error engine: %s", err_exc)

                # Reset retry counter if engine has been running long enough
                # (prevents transient blips from accumulating over hours)
                elapsed_since_success = (datetime.now(IST) - _last_success_time).total_seconds()
                if elapsed_since_success > _RETRY_RESET_SECONDS and retry_count < max_retries:
                    logger.info(
                        "Resetting retry counter (was %d) — engine ran successfully for %.0fs before this error",
                        retry_count, elapsed_since_success,
                    )
                    retry_count = 1
                    _last_success_time = datetime.now(IST)

                if retry_count >= max_retries:
                    logger.critical("Max retries (%d) exceeded, stopping engine", max_retries)
                    self.state = EngineState.ERROR
                    try:
                        await self._broadcast("engine", {"type": "engine_state_change", "state": "error"})
                    except Exception:
                        pass
                    return

            # Sleep for scan interval (cancellable)
            try:
                await asyncio.sleep(scan_interval)
            except asyncio.CancelledError:
                logger.info("Main loop sleep cancelled")
                return

        logger.info("Main loop exited (state=%s)", self.state.value)

    # ------------------------------------------------------------------
    # Scanning & Telemetry
    # ------------------------------------------------------------------

    def _record_telemetry_event(
        self,
        symbol: str,
        strategy: str,
        status: str,
        direction: str = "—",
        price: float = 0.0,
        confidence: float = 0.0,
        gate: Optional[str] = None,
        reason: str = "",
    ) -> None:
        """Record a scan telemetry event and broadcast it via WebSocket in real-time."""
        event = {
            "time": datetime.now(IST).strftime("%H:%M:%S"),
            "symbol": symbol,
            "strategy": strategy,
            "status": status,
            "direction": direction,
            "price": round(float(price or 0.0), 2),
            "confidence": round(float(confidence or 0.0), 3),
            "gate": gate or ("ALL_GATES_PASSED" if status == "PASSED" else "—"),
            "reason": reason or ("Passed" if status == "PASSED" else "No setup trigger"),
        }
        self._recent_scan_telemetry.append(event)
        if len(self._recent_scan_telemetry) > 100:
            self._recent_scan_telemetry.pop(0)

        # Broadcast individual event for real-time WebSocket subscribers
        try:
            loop = asyncio.get_running_loop()
            if loop and loop.is_running():
                task = loop.create_task(self._broadcast("telemetry", {
                    "type": "scan_telemetry_event",
                    "event": event,
                }))
                # Attach done callback to catch and log task errors
                def _log_broadcast_err(t: asyncio.Task) -> None:
                    try:
                        if not t.cancelled() and t.exception():
                            logger.debug("Telemetry broadcast error: %s", t.exception())
                    except Exception:
                        pass
                task.add_done_callback(_log_broadcast_err)
        except Exception as exc:
            logger.debug("Failed to schedule telemetry broadcast: %s", exc)

    def get_scan_telemetry(self) -> Dict[str, Any]:
        """Return aggregated scan metrics and recent scan events with explicit idle status."""
        market_status = self.market_hours.get_market_status() if hasattr(self, "market_hours") else {"is_open": True, "session": "regular"}
        is_market_open = market_status.get("is_open", True)
        is_trade_win = self.market_hours.is_new_trade_window() if hasattr(self, "market_hours") else True

        scanning_status = "scanning_active"
        idle_reason = ""

        if self.state == EngineState.STOPPED:
            scanning_status = "engine_stopped"
            idle_reason = "Engine is stopped — click Start Engine to activate scanning."
        elif self.state == EngineState.PAUSED:
            scanning_status = "paused"
            idle_reason = "Engine is paused — resume engine to continue scanning."
        elif not is_market_open:
            scanning_status = "market_closed"
            session = market_status.get("session", "closed")
            idle_reason = f"Market is closed ({session}). Live scanner automatically resumes during market hours (09:15-15:30 IST)."
        elif not is_trade_win:
            scanning_status = "outside_trade_window"
            idle_reason = "Scanner idle — outside trade window (09:15-15:15 IST). New trade entries are blocked during initial market opening and closing rush."
        elif hasattr(self, "daily_risk") and self.daily_risk is not None:
            risk_state = getattr(self.daily_risk, "_state", None)
            if risk_state and getattr(risk_state, "block_reason", None):
                scanning_status = "risk_blocked"
                idle_reason = f"Scanner idle — blocked by daily risk limits: {risk_state.block_reason}"

        return {
            "total_scans": self._scan_count,
            "symbols_scanned": self._symbols_scanned_count,
            "signals_generated": self._signals_generated,
            "signals_passed": self._signals_passed_count,
            "signals_rejected": self._signals_rejected_count,
            "rejections_by_gate": dict(self._rejections_by_gate),
            "rejections_by_strategy": dict(self._rejections_by_strategy),
            "active_strategies": list(self.active_strategies),
            "broker": self.broker_name or "paper",
            "mode": self.mode or "paper",
            "state": self.state.value,
            "scanning_status": scanning_status,
            "idle_reason": idle_reason,
            "recent_events": list(self._recent_scan_telemetry[-50:]),
        }

    async def _scan_watchlist(self) -> None:
        """Fetch watchlist and run strategy scans for each symbol."""
        async with self._repo_context() as repo:
            watchlist_items = await repo.get_active_watchlist()

            if not watchlist_items:
                logger.debug("Watchlist is empty, skipping scan")
                self._record_telemetry_event(
                    symbol="WATCHLIST",
                    strategy="ALL",
                    status="NO_SETUP",
                    reason="Watchlist empty (populated automatically at pre-market or via manual watchlist)",
                )
                return

            if not _STRATEGIES_AVAILABLE:
                logger.debug("No strategy registry available, skipping signal generation")
                return

            if not self.active_strategies:
                logger.debug("No active strategies, skipping scan")
                return

            self._symbols_scanned_count += len(watchlist_items)

            # Get current VIX and regime from feed/broker if available
            await self._update_market_context()

            # Prune any stale or invalidated opportunities before watchlist iteration
            await self._validate_pending_opportunities()

            for item in watchlist_items:
                symbol = item.symbol

                # Check if symbol already has a pending opportunity
                has_pending = any(
                    opp.get("symbol") == symbol
                    for opp in self.pending_opportunities.values()
                )
                if has_pending:
                    logger.debug("Skipping %s: pending opportunity exists", symbol)
                    self._record_telemetry_event(
                        symbol=symbol,
                        strategy="ALL",
                        status="REJECTED",
                        gate="PendingOpportunity",
                        reason=f"Pending opportunity already exists for {symbol}",
                    )
                    continue

                try:
                    await self._scan_symbol(symbol, repo)
                except Exception as sym_exc:
                    logger.warning("Error scanning %s: %s", symbol, sym_exc)
                    self._errors_count += 1
                    await self.error_engine.handle_error(
                        sym_exc,
                        context={"action": "scan_symbol", "symbol": symbol},
                        session_id=self.session_id,
                    )

            # Broadcast telemetry update to WebSocket subscribers
            try:
                await self._broadcast("telemetry", {
                    "type": "scan_telemetry",
                    "telemetry": self.get_scan_telemetry(),
                })
            except Exception:
                pass

    async def _scan_symbol(self, symbol: str, repo) -> None:
        """Run all active strategies on a single symbol."""
        # Fetch candles from feed
        candles = []
        if self.feed is not None and hasattr(self.feed, "get_candles"):
            try:
                candles = await self.feed.get_candles(symbol, timeframe="5m", count=100)
            except TypeError:
                candles = await self.feed.get_candles(symbol, timeframe="5min", limit=100)
        elif self.broker is not None and hasattr(self.broker, "get_candles"):
            try:
                candles = await self.broker.get_candles(symbol, timeframe="5m", count=100)
            except TypeError:
                candles = await self.broker.get_candles(symbol, timeframe="5min", limit=100)

        if not candles or len(candles) < 20:
            logger.debug("Insufficient candles for %s: %d", symbol, len(candles) if candles else 0)
            self._record_telemetry_event(
                symbol=symbol,
                strategy="ALL",
                status="NO_SETUP",
                reason=f"Insufficient candles ({len(candles) if candles else 0}/20)",
            )
            return

        # Get current price
        current_price = 0.0
        if candles:
            last_candle = candles[-1]
            if isinstance(last_candle, dict):
                current_price = last_candle.get("close", 0)
            else:
                current_price = getattr(last_candle, "close", 0)

        if current_price <= 0:
            return

        # Run each active strategy
        for strategy_name in self.active_strategies:
            try:
                signal = await self._execute_strategy_scan(
                    symbol=symbol,
                    candles=candles,
                    strategy_name=strategy_name,
                    regime=self.current_regime,
                    vix=self.vix,
                )

                if signal is None:
                    self._record_telemetry_event(
                        symbol=symbol,
                        strategy=strategy_name,
                        status="NO_SETUP",
                        price=current_price,
                        reason="Strategy entry criteria not met",
                    )
                    continue

                self._signals_generated += 1
                logger.info(
                    "Signal from %s on %s: %s @ %.2f (conf=%.2f)",
                    strategy_name, symbol, signal.get("direction", "?"),
                    signal.get("entry_price", 0), signal.get("confidence", 0),
                )

                # Run risk gates
                risk_result = await self._run_risk_gates(signal, symbol, current_price)
                if not risk_result.get("passed", False):
                    self._signals_rejected_count += 1
                    block_gate = risk_result.get("blocked_by") or risk_result.get("block_reason") or "RiskGate"
                    reason_msg = risk_result.get("block_reason") or f"Blocked by {block_gate}"
                    self._rejections_by_gate[block_gate] = self._rejections_by_gate.get(block_gate, 0) + 1
                    self._rejections_by_strategy[strategy_name] = self._rejections_by_strategy.get(strategy_name, 0) + 1
                    self._record_telemetry_event(
                        symbol=symbol,
                        strategy=strategy_name,
                        status="REJECTED",
                        direction=signal.get("direction", "—"),
                        price=current_price,
                        confidence=float(signal.get("confidence", 0.0)),
                        gate=block_gate,
                        reason=reason_msg,
                    )
                    logger.info(
                        "Signal from %s on %s blocked by risk: %s",
                        strategy_name, symbol, reason_msg,
                    )
                    continue

                self._signals_passed_count += 1
                self._record_telemetry_event(
                    symbol=symbol,
                    strategy=strategy_name,
                    status="PASSED",
                    direction=signal.get("direction", "—"),
                    price=current_price,
                    confidence=float(signal.get("confidence", 0.0)),
                    gate="ALL_GATES_PASSED",
                    reason="Passed all risk gates - opportunity created",
                )

                # Calculate position size
                sizing = await self._calculate_position_size(signal, current_price)

                # Save signal to DB
                sig_obj = await repo.create_signal(
                    symbol=symbol,
                    direction=signal.get("direction", "LONG"),
                    strategy=strategy_name,
                    confidence=signal.get("confidence", 0),
                    entry_price=signal.get("entry_price", current_price),
                    stop_loss=signal.get("stop_loss", 0),
                    target=signal.get("target", 0),
                    status="pending",
                    signal_data=signal,
                    risk_gate_results=risk_result.get("all_gates", []),
                    session_id=self.session_id,
                )
                sig_id = sig_obj.id if sig_obj and hasattr(sig_obj, "id") else str(uuid.uuid4())

                # Build opportunity
                opportunity = self._build_opportunity(
                    signal, strategy_name, symbol, current_price, sizing, risk_result, signal_id=sig_id
                )

                # Store in pending
                opp_id = opportunity["id"]
                async with self._opportunities_lock:
                    self.pending_opportunities[opp_id] = opportunity

                # Push to WebSocket
                await self._broadcast("opportunity", {
                    "type": "new_opportunity",
                    "opportunity": opportunity,
                })

            except Exception as strat_exc:
                logger.warning(
                    "Error running strategy %s on %s: %s",
                    strategy_name, symbol, strat_exc,
                )

    async def _execute_strategy_scan(
        self,
        symbol: str,
        candles: list,
        strategy_name: str,
        regime: str,
        vix: float,
    ) -> Optional[dict]:
        """Execute a strategy's scan method on incoming candle data."""
        if not hasattr(self, "strategy_registry") or not self.strategy_registry:
            return None
        strat = self.strategy_registry.get(strategy_name)
        if not strat:
            return None

        try:
            import inspect
            import pandas as pd

            if isinstance(candles, list):
                df_candles = pd.DataFrame(candles)
                rename_map = {}
                for col in df_candles.columns:
                    if str(col).lower() in ["open", "high", "low", "close", "volume", "timestamp", "datetime", "date"]:
                        rename_map[col] = str(col).lower()
                if rename_map:
                    df_candles.rename(columns=rename_map, inplace=True)
            elif isinstance(candles, pd.DataFrame):
                df_candles = candles
            else:
                df_candles = pd.DataFrame()

            res = None
            if hasattr(strat, "scan"):
                if inspect.iscoroutinefunction(strat.scan):
                    res = await strat.scan(symbol=symbol, candles=df_candles, regime=regime, vix=vix)
                else:
                    res = strat.scan(symbol=symbol, candles=df_candles, regime=regime, vix=vix)
            elif hasattr(strat, "generate_signals"):
                if inspect.iscoroutinefunction(strat.generate_signals):
                    res = await strat.generate_signals(candles=df_candles, symbol=symbol)
                else:
                    res = strat.generate_signals(candles=df_candles, symbol=symbol)

            if res and isinstance(res, list) and len(res) > 0:
                res = res[0]
            if res and isinstance(res, dict):
                res.setdefault("strategy", strategy_name)
                res.setdefault("symbol", symbol)
                return res
        except Exception as scan_err:
            logger.warning("Strategy %s scan exception on %s: %s", strategy_name, symbol, scan_err, exc_info=True)
        return None

    # ------------------------------------------------------------------
    # Risk Gates
    # ------------------------------------------------------------------

    async def _build_risk_context(self, signal: dict, symbol: str, current_price: float) -> dict:
        """Assemble all 12+ context parameters required by Risk Gates G1-G16."""
        open_positions = []
        async with self._repo_context() as repo:
            open_positions = await repo.get_open_positions()

        # Group positions by sector for G2 / G6
        positions_by_sector: Dict[str, int] = {}
        for pos in open_positions:
            sec = get_stock_sector(pos.symbol)
            positions_by_sector[sec] = positions_by_sector.get(sec, 0) + 1

        daily_status = self.daily_risk.check_daily_limits() if self.daily_risk else None
        daily_loss = abs(daily_status.net_pnl) if daily_status and daily_status.net_pnl < 0 else 0.0
        daily_pnl = float(daily_status.net_pnl) if daily_status else -daily_loss
        daily_trades = daily_status.total_trades if daily_status else 0
        consecutive_losses = daily_status.consecutive_losses if daily_status else 0

        margin_avail = float(self.initial_capital or 100000.0)
        if self.broker and hasattr(self.broker, "get_margins"):
            try:
                margins = await self.broker.get_margins()
                margin_avail = float(margins.get("available_cash", margin_avail))
            except Exception:
                pass

        total_cap = float(self.initial_capital or 100000.0)
        drawdown_pct = (daily_loss / total_cap) * 100.0 if total_cap > 0 else 0.0
        open_syms = [pos.symbol for pos in open_positions]
        return {
            "symbol": symbol,
            "current_price": current_price,
            "ltp": current_price,
            "broker_ltp": current_price,
            "vix": self.vix,
            "india_vix": self.vix,
            "regime": self.current_regime,
            "open_positions": len(open_positions),
            "open_positions_count": len(open_positions),
            "open_position_symbols": open_syms,
            "open_positions_list": open_syms,
            "positions_by_sector": positions_by_sector,
            "daily_loss": daily_loss,
            "daily_loss_rupees": daily_loss,
            "daily_pnl": daily_pnl,
            "daily_trades": daily_trades,
            "daily_trade_count": daily_trades,
            "consecutive_losses": consecutive_losses,
            "current_drawdown_pct": drawdown_pct,
            "capital": total_cap,
            "total_capital": total_cap,
            "margin_available": margin_avail,
            "available_capital": margin_avail,
            "available_margin": margin_avail,
            "session_id": self.session_id,
            "current_time": datetime.now(IST),
            "time_of_day": datetime.now(IST).strftime("%H:%M"),
        }

    async def _run_risk_gates(self, signal: dict, symbol: str, current_price: float) -> dict:
        """Run all risk gates on a signal.

        Returns dict with: passed, all_gates, blocked_by, block_reason, severity,
        reduced_size, notes.
        """
        try:
            context = await self._build_risk_context(signal, symbol, current_price)
            risk_result = await self.risk_engine.evaluate(
                signal=signal,
                symbol=symbol,
                current_price=current_price,
                context=context,
                session_id=self.session_id,
            )
            if hasattr(risk_result, "model_dump"):
                return risk_result.model_dump()
            if isinstance(risk_result, dict):
                return risk_result
            return {"passed": False, "block_reason": "Unknown risk result type", "all_gates": []}
        except Exception as exc:
            logger.error("Risk gate evaluation failed: %s", exc)
            return {"passed": False, "block_reason": f"Risk engine error: {exc}", "all_gates": [], "severity": "error"}

    # ------------------------------------------------------------------
    # Position Sizing
    # ------------------------------------------------------------------

    async def _calculate_position_size(self, signal: dict, current_price: float) -> dict:
        """Calculate position size for a signal."""
        try:
            res = self.position_sizer.calculate(
                signal=signal,
                context={
                    "current_price": current_price,
                    "regime": self.current_regime,
                    "vix": self.vix,
                    "session_id": self.session_id,
                    "available_capital": getattr(self, "available_capital", self.initial_capital or 100000.0),
                },
                current_price=current_price,
                regime=self.current_regime,
                vix=self.vix,
                session_id=self.session_id,
            )
            if asyncio.iscoroutine(res):
                res = await res
            if hasattr(res, "model_dump"):
                return res.model_dump()
            if isinstance(res, dict):
                return res
            return {"quantity": 0, "position_size": 0, "method": "unknown"}
        except Exception as exc:
            logger.error("Position sizing failed: %s", exc)
            return {"quantity": 0, "position_size": 0, "method": "error", "notes": str(exc)}

    # ------------------------------------------------------------------
    # Continuous Opportunity Validation
    # ------------------------------------------------------------------

    async def _validate_pending_opportunities(self) -> None:
        """Validate pending opportunities continuously against live price action and TTL.
        
        Prunes opportunities if:
        1. Target reached before entry (move finished — prevents buying top / selling bottom)
        2. Stop-loss breached before entry (support broken — setup failed)
        3. Price drift exceeds maximum slippage tolerance (unfavorable Risk-Reward)
        4. Setup timeout expired (momentum setup older than TTL, e.g. 15 minutes)
        """
        async with self._opportunities_lock:
            if not self.pending_opportunities:
                return
            items_snapshot = list(self.pending_opportunities.items())

        now = datetime.now(IST)
        risk_config = self.config.get_risk_config() if hasattr(self.config, "get_risk_config") else {}
        mismatch_threshold = risk_config.get("price_mismatch_threshold_pct", 0.6)
        ttl_seconds = risk_config.get("opportunity_ttl_seconds", risk_config.get("opportunity_ttl_minutes", 2) * 60)

        invalidated_items: List[tuple] = []

        # Check 0: Market Hours Check — If market closed, all intraday pending setups expire
        if self.market_hours and not self.market_hours.is_market_open():
            for opp_id, _ in items_snapshot:
                invalidated_items.append((
                    opp_id,
                    "MARKET_SESSION_CLOSED",
                    "Market session is closed (09:15 - 15:30 IST) — Intraday setup expired with market close to prevent overnight risk"
                ))

        for opp_id, opp in items_snapshot:
            if any(item[0] == opp_id for item in invalidated_items):
                continue

            symbol = opp.get("symbol", "")
            direction = opp.get("direction", "BUY").upper()
            strategy = opp.get("strategy", "")
            entry_price = float(opp.get("entry_price", 0.0))
            stop_loss = float(opp.get("stop_loss", 0.0))
            target = float(opp.get("target", 0.0))
            created_at_str = opp.get("created_at")

            # Check 1: TTL Expiry (Momentum window)
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    age_seconds = (now - created_at).total_seconds()
                    if age_seconds > ttl_seconds:
                        invalidated_items.append((
                            opp_id,
                            "SETUP_TIMEOUT_EXPIRED",
                            f"Opportunity expired after {int(ttl_seconds)}s without execution (momentum window closed)"
                        ))
                        continue
                except Exception:
                    pass

            # Check 2: Live Price Query
            current_price = 0.0
            if self.feed is not None and hasattr(self.feed, "get_latest_price"):
                try:
                    current_price = await self.feed.get_latest_price(symbol)
                except Exception:
                    current_price = 0.0

            if current_price <= 0 and self.broker is not None and hasattr(self.broker, "get_latest_price"):
                try:
                    current_price = await self.broker.get_latest_price(symbol)
                except Exception:
                    current_price = 0.0

            if current_price <= 0:
                continue

            # Update live metrics
            opp["current_price"] = current_price
            price_mismatch_pct = abs(current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
            opp["price_mismatch_pct"] = round(price_mismatch_pct, 2)

            # Check 3: Target Hit / Move Already Completed (Chasing Block)
            if direction in ("BUY", "LONG"):
                if target > 0 and current_price >= target:
                    invalidated_items.append((
                        opp_id,
                        "TARGET_ACHIEVED_BEFORE_ENTRY",
                        f"Target ₹{target:.2f} reached before entry (LTP: ₹{current_price:.2f}). Move finished — invalidated to prevent buying top."
                    ))
                    continue
                elif stop_loss > 0 and current_price <= stop_loss:
                    invalidated_items.append((
                        opp_id,
                        "STOP_LOSS_BREACHED",
                        f"Stop loss ₹{stop_loss:.2f} breached before entry (LTP: ₹{current_price:.2f}). Setup invalidated to prevent buying falling knife."
                    ))
                    continue
                elif target > 0 and stop_loss > 0:
                    remaining_gain = target - current_price
                    remaining_risk = current_price - stop_loss
                    if remaining_gain > 0 and remaining_risk > 0:
                        live_rr = remaining_gain / remaining_risk
                        if live_rr < 0.8:
                            invalidated_items.append((
                                opp_id,
                                "UNFAVORABLE_RISK_REWARD",
                                f"Risk-Reward deteriorated to 1:{live_rr:.2f} (LTP ₹{current_price:.2f} moved too close to target). Profit potential exhausted."
                            ))
                            continue
            elif direction in ("SELL", "SHORT"):
                if target > 0 and current_price <= target:
                    invalidated_items.append((
                        opp_id,
                        "TARGET_ACHIEVED_BEFORE_ENTRY",
                        f"Target ₹{target:.2f} reached before entry (LTP: ₹{current_price:.2f}). Move finished — invalidated to prevent selling bottom."
                    ))
                    continue
                elif stop_loss > 0 and current_price >= stop_loss:
                    invalidated_items.append((
                        opp_id,
                        "STOP_LOSS_BREACHED",
                        f"Stop loss ₹{stop_loss:.2f} breached before entry (LTP: ₹{current_price:.2f}). Setup invalidated."
                    ))
                    continue
                elif target > 0 and stop_loss > 0:
                    remaining_gain = current_price - target
                    remaining_risk = stop_loss - current_price
                    if remaining_gain > 0 and remaining_risk > 0:
                        live_rr = remaining_gain / remaining_risk
                        if live_rr < 0.8:
                            invalidated_items.append((
                                opp_id,
                                "UNFAVORABLE_RISK_REWARD",
                                f"Risk-Reward deteriorated to 1:{live_rr:.2f} (LTP ₹{current_price:.2f} moved too close to target). Profit potential exhausted."
                            ))
                            continue

            # Check 4: Market Regime / Strategy Compatibility Check
            if self.current_regime and hasattr(self.config, "get_strategy_activation"):
                regime_cfg = self.config.get_strategy_activation(self.current_regime)
                paused_strategies = regime_cfg.get("paused", [])
                if strategy and strategy in paused_strategies:
                    invalidated_items.append((
                        opp_id,
                        "REGIME_TREND_SHIFT",
                        f"Market regime shifted to {self.current_regime}; strategy '{strategy}' paused. Setup invalidated to protect capital."
                    ))
                    continue

            # Check 5: Price Drift Slippage Tolerance
            if price_mismatch_pct > mismatch_threshold * 1.5:
                invalidated_items.append((
                    opp_id,
                    "PRICE_DRIFT_EXCEEDED",
                    f"Price drifted {price_mismatch_pct:.2f}% from entry ₹{entry_price:.2f} (exceeds {mismatch_threshold * 1.5:.2f}% limit)."
                ))
                continue

        # Prune and notify
        if invalidated_items:
            async with self._repo_context() as repo:
                for opp_id, reason_code, reason_desc in invalidated_items:
                    async with self._opportunities_lock:
                        opp = self.pending_opportunities.pop(opp_id, None)
                        if not opp:
                            continue

                        opp["status"] = "expired"
                        opp["invalidation_code"] = reason_code
                        opp["invalidation_reason"] = reason_desc
                        opp["invalidated_at"] = now.isoformat()

                        self.invalidated_opportunities[opp_id] = opp
                        if len(self.invalidated_opportunities) > 50:
                            oldest_key = next(iter(self.invalidated_opportunities))
                            self.invalidated_opportunities.pop(oldest_key, None)

                    logger.info(
                        "Invalidated opportunity %s (%s): %s - %s",
                        opp_id, opp.get("symbol"), reason_code, reason_desc
                    )

                    await self._broadcast("opportunity", {
                        "type": "opportunity_invalidated",
                        "opportunity_id": opp_id,
                        "symbol": opp.get("symbol"),
                        "reason_code": reason_code,
                        "reason": reason_desc,
                        "invalidated_at": now.isoformat(),
                    })

                    if repo is not None and opp.get("signal_id"):
                        try:
                            await repo.update_signal(
                                opp.get("signal_id"),
                                status="EXPIRED",
                                notes=reason_desc
                            )
                        except Exception as sig_err:
                            logger.warning("Could not update signal status in DB for %s: %s", opp.get("signal_id"), sig_err, exc_info=True)

    # ------------------------------------------------------------------
    # Build Opportunity
    # ------------------------------------------------------------------

    def _build_opportunity(
        self,
        signal: dict,
        strategy_name: str,
        symbol: str,
        current_price: float,
        sizing: dict,
        risk_result: dict,
        signal_id: Optional[str] = None,
    ) -> dict:
        """Build a full opportunity dict from signal + risk + sizing."""
        entry_price = signal.get("entry_price", current_price)
        stop_loss = signal.get("stop_loss", 0)
        target = signal.get("target", 0)

        # Calculate risk/reward
        sl_distance = entry_price - stop_loss if signal.get("direction") == "LONG" else stop_loss - entry_price
        sl_distance = abs(sl_distance)
        target_distance = target - entry_price if signal.get("direction") == "LONG" else entry_price - target
        target_distance = abs(target_distance)
        risk_reward = round(target_distance / sl_distance, 2) if sl_distance > 0 else 0.0

        # Price mismatch check
        price_mismatch_pct = abs(current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0

        # Partial booking levels
        booking_levels = []
        if self.partial_booker is not None:
            try:
                booking_config = self.config.get_partial_booking_config()
                booking_levels = self.partial_booker.get_booking_levels(
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    target=target,
                    direction=signal.get("direction", "LONG"),
                    config=booking_config,
                )
                if hasattr(booking_levels, "model_dump"):
                    booking_levels = booking_levels.model_dump().get("levels", [])
                elif isinstance(booking_levels, list):
                    pass
                else:
                    booking_levels = []
            except Exception:
                booking_levels = []

        opportunity_id = str(uuid.uuid4())
        created_dt = datetime.now(IST)

        # Standardize 1-5 Conviction Score
        raw_conf = float(signal.get("confidence", 0.6) or 0.6)
        rr_bonus = 0.05 if risk_reward >= 2.0 else 0.0
        all_gates = risk_result.get("all_gates", [])
        passed_gates = sum(1 for g in all_gates if (isinstance(g, dict) and g.get("passed", False)) or (hasattr(g, "passed") and getattr(g, "passed", False)))
        gate_ratio = (passed_gates / len(all_gates)) if all_gates else 1.0
        
        composite_score = min(1.0, max(0.0, raw_conf * 0.7 + (gate_ratio * 0.2) + rr_bonus))
        conviction_stars = max(1, min(5, int(round(1 + 4 * composite_score))))
        
        conviction_labels = {
            1: "1 Star - Low Conviction",
            2: "2 Stars - Moderate Setup",
            3: "3 Stars - Standard Setup",
            4: "4 Stars - High Probability",
            5: "5 Stars - A+ Institutional Grade",
        }
        conviction_label = conviction_labels.get(conviction_stars, "3 Stars - Standard Setup")

        resolved_signal_id = signal_id or signal.get("signal_id") or str(uuid.uuid4())

        return {
            "id": opportunity_id,
            "signal_id": resolved_signal_id,
            "created_at": created_dt.isoformat(),
            "created_at_time": created_dt.strftime("%I:%M:%S %p"),
            "symbol": symbol,
            "name": signal.get("name", ""),
            "direction": signal.get("direction", "LONG"),
            "strategy": strategy_name,
            "confidence": signal.get("confidence", 0),
            "conviction_score": conviction_stars,
            "conviction_stars": conviction_stars,
            "conviction_label": conviction_label,
            "composite_score": round(composite_score * 100, 1),
            "conviction_breakdown": {
                "technical_confidence": round(raw_conf * 100, 1),
                "risk_gates_passed": f"{passed_gates}/{len(all_gates)}",
                "risk_reward": risk_reward,
                "composite_score": round(composite_score * 100, 1),
            },
            "entry_price": entry_price,
            "current_price": current_price,
            "stop_loss": stop_loss,
            "target": target,
            "risk_reward": risk_reward,
            "sl_distance_pct": round(sl_distance / entry_price * 100, 2) if entry_price > 0 else 0,
            "target_pct": round(target_distance / entry_price * 100, 2) if entry_price > 0 else 0,
            "price_mismatch_pct": round(price_mismatch_pct, 2),
            "quantity": sizing.get("quantity", 0),
            "position_size": sizing.get("position_size", 0),
            "position_size_pct": sizing.get("position_size_pct", 0),
            "risk_amount": sizing.get("risk_amount", 0),
            "sizing_method": sizing.get("method", ""),
            "capital_required": sizing.get("position_size", 0),
            "kelly_fraction": sizing.get("adjusted_fraction", sizing.get("kelly_fraction")),
            "volatility_tier": sizing.get("volatility_tier", ""),
            "drawdown_tier": sizing.get("drawdown_tier", ""),
            "confidence_tier": sizing.get("confidence_tier", ""),
            "is_equity": signal.get("is_equity", True),
            "lot_size": signal.get("lot_size"),
            "expiry_date": signal.get("expiry_date"),
            "strike": signal.get("strike"),
            "option_type": signal.get("option_type"),
            "is_reduced_size": sizing.get("reduced_size", risk_result.get("reduced_size", False)),
            "risk_gate_passed": risk_result.get("passed", True),
            "risk_gates": risk_result.get("all_gates", []),
            "vix": self.vix,
            "regime": self.current_regime,
            "booking_levels": booking_levels,
            "signal_data": signal,
            "kronos_score": signal.get("kronos_score"),
            "win_rate": signal.get("win_rate"),
            "avg_rr": signal.get("avg_rr"),
            "notes": risk_result.get("notes", ""),
        }

    # ------------------------------------------------------------------
    # Confirm / Skip Opportunity
    # ------------------------------------------------------------------

    async def confirm_opportunity(self, opportunity_id: str, segment: str = "EQ") -> Dict[str, Any]:
        """User confirms an opportunity – execute the trade.

        Args:
            opportunity_id: The pending opportunity ID.
            segment: Market segment ('EQ', 'FNO', etc.).

        Returns:
            Dict with trade details.
        """
        async with self._opportunities_lock:
            opportunity = self.pending_opportunities.pop(opportunity_id, None)
        if opportunity is None:
            return {"status": "not_found", "error": f"Opportunity {opportunity_id} not in pending list"}

        # --- TTL Expiry Check ---
        created_at_str = opportunity.get("created_at")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
                age_seconds = (datetime.now(IST) - created_at).total_seconds()
                risk_config = self.config.get_risk_config() if hasattr(self.config, "get_risk_config") else {}
                ttl_seconds = risk_config.get("opportunity_ttl_seconds", 120)
                if age_seconds > ttl_seconds:
                    return {
                        "status": "rejected",
                        "reason": f"Opportunity expired after {int(ttl_seconds)}s (momentum window closed). Execution aborted to prevent stale trade.",
                    }
            except Exception:
                pass

        symbol = opportunity["symbol"]
        direction = opportunity["direction"]
        entry_price = opportunity["entry_price"]
        quantity = opportunity["quantity"]
        stop_loss = opportunity["stop_loss"]
        target = opportunity["target"]
        strategy = opportunity["strategy"]

        # --- Re-verify risk gates ---
        current_price = entry_price
        if self.feed is not None and hasattr(self.feed, "get_latest_price"):
            try:
                current_price = await self.feed.get_latest_price(symbol)
            except Exception:
                pass
        elif self.broker is not None and hasattr(self.broker, "get_latest_price"):
            try:
                current_price = await self.broker.get_latest_price(symbol)
            except Exception:
                pass

        # --- Target hit or SL breached pre-execution check ---
        dir_upper = direction.upper()
        if dir_upper in ("BUY", "LONG"):
            if target > 0 and current_price >= target:
                return {
                    "status": "rejected",
                    "reason": f"Target ₹{target:.2f} reached before execution (LTP: ₹{current_price:.2f}). Move finished — trade rejected to prevent buying top.",
                    "current_price": current_price,
                    "target": target,
                }
            if stop_loss > 0 and current_price <= stop_loss:
                return {
                    "status": "rejected",
                    "reason": f"Stop loss ₹{stop_loss:.2f} breached (LTP: ₹{current_price:.2f}). Setup invalidated.",
                    "current_price": current_price,
                    "stop_loss": stop_loss,
                }
        elif dir_upper in ("SELL", "SHORT"):
            if target > 0 and current_price <= target:
                return {
                    "status": "rejected",
                    "reason": f"Target ₹{target:.2f} reached before execution (LTP: ₹{current_price:.2f}). Move finished — trade rejected to prevent selling bottom.",
                    "current_price": current_price,
                    "target": target,
                }
            if stop_loss > 0 and current_price >= stop_loss:
                return {
                    "status": "rejected",
                    "reason": f"Stop loss ₹{stop_loss:.2f} breached (LTP: ₹{current_price:.2f}). Setup invalidated.",
                    "current_price": current_price,
                    "stop_loss": stop_loss,
                }

        # --- Price mismatch re-check ---
        price_mismatch_pct = abs(current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
        risk_config = self.config.get_risk_config()
        mismatch_threshold = risk_config.get("price_mismatch_threshold_pct", 0.5)

        if price_mismatch_pct > mismatch_threshold:
            return {
                "status": "rejected",
                "reason": f"Price mismatch too large: {price_mismatch_pct:.2f}% > {mismatch_threshold}%",
                "current_price": current_price,
                "original_entry": entry_price,
            }

        # --- Re-run risk gates ---
        signal_data = opportunity.get("signal_data", opportunity)
        signal_data["entry_price"] = current_price

        risk_result = await self._run_risk_gates(signal_data, symbol, current_price)
        if not risk_result.get("passed", False):
            return {
                "status": "rejected",
                "reason": risk_result.get("block_reason", "Risk gates failed on re-check"),
                "risk_gates": risk_result.get("all_gates", []),
            }

        # --- Recalculate position size with current price ---
        sizing = await self._calculate_position_size(signal_data, current_price)
        quantity = sizing.get("quantity", quantity)
        if quantity <= 0:
            return {"status": "rejected", "reason": "Position size calculated as 0"}

        # --- FNO Options Execution Branch ---
        trade_symbol = symbol
        trade_price = current_price
        trade_quantity = quantity
        trade_direction = direction
        option_metadata = {}

        if segment == "FNO":
            try:
                chain_fetcher = OptionChainFetcher(broker=self.broker)
                chain_data = await chain_fetcher.fetch_option_chain(symbol)

                strike_selector = StrikeSelector()
                strike_info = strike_selector.select_strike(
                    symbol=symbol,
                    direction=direction,
                    entry_price=current_price,
                    sl=stop_loss,
                    target=target,
                    vix=self.vix,
                    option_chain=chain_data,
                )

                option_type = strike_info.get("option_type", "CE")
                selected_strike = strike_info.get("strike", current_price)
                lot_size = strike_info.get("lot_size", 1) or 1
                premium = strike_info.get("premium") or (current_price * 0.012)
                option_symbol = strike_info.get("option_symbol", "")

                if not option_symbol:
                    # Fallback standard Fyers option symbol format: NSE:{SYMBOL}{YYMMM}{STRIKE}{CE/PE}
                    exp_tag = chain_data.get("expiry") or datetime.now(IST).strftime("%y%b").upper()
                    clean_sym = symbol.upper().replace(" ", "").replace("_", "")
                    option_symbol = f"NSE:{clean_sym}{exp_tag}{int(selected_strike)}{option_type}"

                # 1. Hard Liquidity Gate
                matched_contract = None
                if chain_data:
                    side_contracts = chain_data.get("calls", []) if option_type == "CE" else chain_data.get("puts", [])
                    for c in side_contracts:
                        if c.get("symbol") == option_symbol or abs(float(c.get("strike", 0)) - selected_strike) < 0.1:
                            matched_contract = c
                            break

                if matched_contract:
                    liquidity_filter = LiquidityFilter()
                    liq_passed, liq_msg = liquidity_filter.validate_strike_liquidity(matched_contract)
                    if not liq_passed:
                        return {
                            "status": "rejected",
                            "reason": f"Options Liquidity Gate failed: {liq_msg}",
                            "symbol": symbol,
                            "option_symbol": option_symbol,
                        }

                # 2. Options-Specific Capital & Risk Gate
                options_risk = OptionsRiskChecker()
                total_cap = float(self.initial_capital or 100000.0)
                risk_check = options_risk.check_capital_limits(
                    entry_price=current_price,
                    lot_size=lot_size,
                    premium=premium,
                    total_capital=total_cap,
                )
                if not risk_check.get("passed", False):
                    return {
                        "status": "rejected",
                        "reason": f"Options Risk Gate failed: {', '.join(risk_check.get('reasons', []))}",
                        "risk_details": risk_check,
                    }

                # 3. Greeks Calculation
                greeks_calc = GreeksCalculator()
                greeks = greeks_calc.all_greeks(
                    S=current_price,
                    K=selected_strike,
                    T=30.0 / 365.0,
                    sigma=strike_info.get("iv", 0.18) or 0.18,
                    option_type=option_type,
                )

                trade_symbol = option_symbol
                trade_price = premium
                trade_quantity = lot_size
                trade_direction = "BUY"  # Directional options buying (Long CE for BUY, Long PE for SELL)

                option_metadata = {
                    "segment": "FNO",
                    "underlying_symbol": symbol,
                    "option_symbol": option_symbol,
                    "strike": selected_strike,
                    "option_type": option_type,
                    "expiry": chain_data.get("expiry", ""),
                    "premium": premium,
                    "iv": strike_info.get("iv") or greeks.get("iv"),
                    "delta": greeks.get("delta"),
                    "gamma": greeks.get("gamma"),
                    "theta": greeks.get("theta"),
                    "vega": greeks.get("vega"),
                    "lot_size": lot_size,
                }
                logger.info(
                    "Resolved FNO Option Contract: %s @ ₹%.2f (Lot: %d, Delta: %.2f, Expiry: %s)",
                    option_symbol, premium, lot_size, greeks.get("delta", 0), chain_data.get("expiry", ""),
                )
            except Exception as fno_err:
                logger.error("Failed to resolve FNO options pipeline: %s", fno_err, exc_info=True)
                return {"status": "error", "error": f"FNO options resolution failed: {str(fno_err)}"}

        # --- Execute order via broker ---
        trade_id = str(uuid.uuid4())
        order_result = {}
        try:
            if self.broker is not None and hasattr(self.broker, "place_order"):
                order_result = await self.broker.place_order(
                    symbol=trade_symbol,
                    direction=trade_direction,
                    quantity=trade_quantity,
                    price=trade_price,
                    order_type="MARKET",
                    segment=segment,
                    stop_loss=stop_loss,
                    target=target,
                )
            else:
                # Paper simulation
                order_result = {
                    "order_id": f"PAPER-{trade_id[:8]}",
                    "status": "FILLED",
                    "filled_price": trade_price,
                    "filled_quantity": trade_quantity,
                }
        except Exception as order_exc:
            await self.error_engine.handle_error(
                order_exc,
                context={"action": "place_order", "symbol": trade_symbol, "direction": trade_direction, "quantity": trade_quantity},
                session_id=self.session_id,
            )
            self._errors_count += 1
            return {"status": "order_failed", "error": str(order_exc)}

        # --- Determine fill price ---
        filled_price = trade_price
        filled_qty = trade_quantity
        order_status = "OPEN"
        broker_order_id = ""

        if isinstance(order_result, dict):
            broker_order_id = order_result.get("order_id", "")
            if order_result.get("filled_price"):
                filled_price = order_result["filled_price"]
            if order_result.get("filled_quantity"):
                filled_qty = order_result["filled_quantity"]
            if order_result.get("status") == "FILLED":
                order_status = "OPEN"  # Position is now open

        invested_amount = filled_price * filled_qty
        sl_distance = abs(filled_price - stop_loss)
        target_distance = abs(target - filled_price)

        # --- Save trade and position to DB ---
        async with self._repo_context() as repo:
            # Fees calculation
            fees_config = self.config.get_fees_config()
            brokerage = float(fees_config.get("brokerage_per_order", 20))
            ex_rate = float(fees_config.get("exchange_txn_pct", 0.0000345))
            exchange_txn = invested_amount * (ex_rate if ex_rate < 0.001 else ex_rate / 100)
            stt_rate = float(fees_config.get("stt_intraday_sell_pct", 0.00025))
            stt = invested_amount * (stt_rate if stt_rate < 0.001 else stt_rate / 100)
            sebi_rate = float(fees_config.get("sebi_fee_pct", 0.000001))
            sebi_fee = invested_amount * (sebi_rate if sebi_rate < 0.0001 else sebi_rate / 100)
            stamp_rate = float(fees_config.get("stamp_duty_pct", 0.00003))
            stamp_duty = invested_amount * (stamp_rate if stamp_rate < 0.001 else stamp_rate / 100)
            gst_rate = float(fees_config.get("gst_pct", 0.18))
            gst_mult = gst_rate if gst_rate <= 1.0 else gst_rate / 100
            gst = (brokerage + exchange_txn + stt + sebi_fee + stamp_duty) * gst_mult
            total_fees = round(brokerage + exchange_txn + stt + sebi_fee + stamp_duty + gst, 2)

            trade_extra = {
                "opportunity_id": opportunity_id,
                "broker_order_id": broker_order_id,
                "sizing_method": opportunity.get("sizing_method", ""),
                "regime": self.current_regime,
                "vix": self.vix,
                "kronos_score": opportunity.get("kronos_score"),
            }
            trade_extra.update(option_metadata)

            trade = await repo.create_trade(
                id=trade_id,
                symbol=trade_symbol,
                direction=trade_direction,
                strategy=strategy,
                entry_price=filled_price,
                exit_price=0,
                quantity=filled_qty,
                invested_amount=round(invested_amount, 2),
                stop_loss=stop_loss,
                target=target,
                status=order_status,
                session_id=self.session_id,
                signal_confidence=opportunity.get("confidence", 0),
                risk_reward=opportunity.get("risk_reward", 0),
                brokerage=brokerage,
                fees=total_fees,
                net_pnl=0,
                pnl=0,
                tags=[strategy, segment],
                extra=trade_extra,
            )

            # --- Create position ---
            position_extra = {
                "opportunity_id": opportunity_id,
                "broker_order_id": broker_order_id,
                "booking_levels": opportunity.get("booking_levels", []),
                "strategy": strategy,
                "session_id": self.session_id,
            }
            position_extra.update(option_metadata)

            await repo.create_position(
                trade_id=trade_id,
                symbol=trade_symbol,
                direction=trade_direction,
                strategy=strategy,
                entry_price=filled_price,
                quantity=filled_qty,
                invested_amount=round(invested_amount, 2),
                stop_loss=stop_loss,
                target=target,
                current_price=filled_price,
                status="OPEN",
                session_id=self.session_id,
                extra=position_extra,
            )

        self._trades_executed += 1


        # --- Broadcast & Telegram trade fill ---
        trade_payload = {
            "type": "trade_fill",
            "trade_id": trade_id,
            "symbol": symbol,
            "direction": direction,
            "quantity": filled_qty,
            "filled_price": filled_price,
            "entry_price": filled_price,
            "invested_amount": round(invested_amount, 2),
            "stop_loss": stop_loss,
            "target": target,
            "strategy": strategy,
            "broker_order_id": broker_order_id,
            "fees": total_fees,
        }
        await self._broadcast("trade", trade_payload)
        await self._route_alert("trade_fill", trade_payload)

        logger.info(
            "Trade executed: %s %s x%d @ %.2f (SL=%.2f, T=%.2f) [%s]",
            direction, symbol, filled_qty, filled_price, stop_loss, target, strategy,
        )

        return {
            "status": "filled",
            "trade_id": trade_id,
            "symbol": symbol,
            "direction": direction,
            "quantity": filled_qty,
            "filled_price": filled_price,
            "invested_amount": round(invested_amount, 2),
            "stop_loss": stop_loss,
            "target": target,
            "strategy": strategy,
            "broker_order_id": broker_order_id,
            "fees": total_fees,
        }

    async def skip_opportunity(self, opportunity_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """User skips an opportunity."""
        async with self._opportunities_lock:
            opportunity = self.pending_opportunities.pop(opportunity_id, None)
        if opportunity is None:
            return {"status": "not_found", "error": f"Opportunity {opportunity_id} not in pending list"}

        symbol = opportunity.get("symbol", "")
        strategy = opportunity.get("strategy", "")
        skip_reason = reason or "User skipped"

        # Update signal status in DB
        try:
            signal_id = opportunity.get("signal_id")
            if signal_id:
                async with self._repo_context() as repo:
                    await repo.update_signal(signal_id, status="skipped")
        except Exception as exc:
            logger.debug("Could not update signal status: %s", exc)

        await self._broadcast("opportunity", {
            "type": "opportunity_skipped",
            "opportunity_id": opportunity_id,
            "symbol": symbol,
            "strategy": strategy,
            "reason": skip_reason,
        })

        logger.info("Opportunity %s (%s %s) skipped: %s", opportunity_id, symbol, strategy, skip_reason)
        return {"status": "skipped", "opportunity_id": opportunity_id, "reason": skip_reason}

    # ------------------------------------------------------------------
    # Position Management
    # ------------------------------------------------------------------

    async def _manage_all_positions(self) -> None:
        """Manage all open positions: update prices, check SL/target/partial bookings."""
        async with self._repo_context() as repo:
            positions = await repo.get_open_positions()

            for position in positions:
                try:
                    await self._manage_position(position, repo)
                except Exception as pos_exc:
                    logger.error("Error managing position %s: %s", position.id, pos_exc)
                    await self.error_engine.handle_error(
                        pos_exc,
                        context={"action": "manage_position", "position_id": position.id, "symbol": position.symbol},
                        session_id=self.session_id,
                    )

    async def _manage_position(self, position, repo=None) -> None:
        """Manage a single open position: check SL hit, target hit, partial bookings.

        Args:
            position: A Position ORM object from the repository.
            repo: Optional Repository instance to reuse.
        """
        # Get latest price
        current_price = 0.0
        if self.feed is not None and hasattr(self.feed, "get_latest_price"):
            try:
                current_price = await self.feed.get_latest_price(position.symbol)
            except Exception:
                pass
        if current_price <= 0 and self.broker is not None and hasattr(self.broker, "get_latest_price"):
            try:
                current_price = await self.broker.get_latest_price(position.symbol)
            except Exception:
                pass
        if current_price <= 0:
            current_price = position.current_price or position.entry_price

        # Update current price on position
        if repo is not None:
            await repo.update_position(position.id, current_price=current_price)
        else:
            async with self._repo_context() as r:
                await r.update_position(position.id, current_price=current_price)

        entry = position.entry_price
        sl = position.stop_loss
        target = position.target
        direction = position.direction
        quantity = position.quantity

        # Calculate current P&L
        if direction == "LONG":
            pnl_pct = (current_price - entry) / entry * 100 if entry > 0 else 0
            pnl_amount = (current_price - entry) * quantity
            sl_hit = current_price <= sl
            target_hit = current_price >= target
        else:  # SHORT
            pnl_pct = (entry - current_price) / entry * 100 if entry > 0 else 0
            pnl_amount = (entry - current_price) * quantity
            sl_hit = current_price >= sl
            target_hit = current_price <= target

        # --- Stop Loss Hit ---
        if sl_hit and sl > 0:
            await self._close_position(
                position=position,
                exit_price=current_price,
                close_reason="stop_loss",
                pnl_amount=pnl_amount,
                pnl_pct=pnl_pct,
            )
            return

        # --- Target Hit ---
        if target_hit and target > 0:
            await self._close_position(
                position=position,
                exit_price=current_price,
                close_reason="target",
                pnl_amount=pnl_amount,
                pnl_pct=pnl_pct,
            )
            return

        # --- EOD Auto Square-off (Safe Exit Time / Market Close) ---
        if self.market_hours is not None and self.market_hours.is_safe_exit_time():
            logger.info("Auto square-off triggered for %s at safe exit time", position.symbol)
            await self._close_position(
                position=position,
                exit_price=current_price,
                close_reason="auto_squareoff",
                pnl_amount=pnl_amount,
                pnl_pct=pnl_pct,
            )
            return

        # --- Partial Booking Check ---
        if self.partial_booker is not None:
            try:
                booking_result = self.partial_booker.check_partial_booking(
                    current_price=current_price,
                    entry_price=entry,
                    stop_loss=sl,
                    target=target,
                    direction=direction,
                    position=position,
                )

                if hasattr(booking_result, "model_dump"):
                    booking_data = booking_result.model_dump()
                elif isinstance(booking_result, dict):
                    booking_data = booking_result
                else:
                    booking_data = {}

                # Execute partial booking if a new level is triggered
                if booking_data.get("triggered_level"):
                    await self._execute_partial_booking(
                        position=position,
                        booking_data=booking_data,
                        current_price=current_price,
                    )

                # Update trailing / breakeven SL if active or level 1+ triggered
                new_sl = booking_data.get("current_trailing_sl")
                if new_sl:
                    async def _update_sl_on_repo(r):
                        if direction == "LONG" and new_sl > sl:
                            await r.update_position(position.id, stop_loss=round(new_sl, 2), extra=getattr(position, "extra", None))
                            await r.update_trade(position.trade_id, stop_loss=round(new_sl, 2))
                            logger.info(
                                "Trailing SL updated for %s: %.2f -> %.2f (Level %s)",
                                position.symbol, sl, new_sl, booking_data.get("current_level"),
                            )
                        elif direction == "SHORT":
                            entry_p = float(getattr(position, "entry_price", None) or getattr(position, "price", 0.0) or 0.0)
                            should_update = (sl > 0 and new_sl < sl) or (sl == 0 and entry_p > 0 and new_sl < entry_p)
                            if should_update:
                                await r.update_position(position.id, stop_loss=round(new_sl, 2), extra=getattr(position, "extra", None))
                                await r.update_trade(position.trade_id, stop_loss=round(new_sl, 2))
                                logger.info(
                                    "Trailing SL updated for %s: %.2f -> %.2f (Level %s)",
                                    position.symbol, sl, new_sl, booking_data.get("current_level"),
                                )

                    if repo is not None:
                        await _update_sl_on_repo(repo)
                    else:
                        async with self._repo_context() as active_repo:
                            await _update_sl_on_repo(active_repo)

            except Exception as pb_exc:
                logger.warning("Partial booking check error for %s: %s", position.symbol, pb_exc, exc_info=True)

    async def _execute_partial_booking(
        self,
        position,
        booking_data: dict,
        current_price: float,
    ) -> None:
        """Execute a partial book exit for a position."""
        level = booking_data.get("triggered_level", 0)
        book_qty = booking_data.get("book_qty", 0)
        remaining_qty = booking_data.get("remaining_qty", 0)

        if book_qty <= 0:
            return

        symbol = position.symbol
        direction = position.direction

        # Execute partial exit via broker
        try:
            if self.broker is not None and hasattr(self.broker, "place_order"):
                exit_direction = "SELL" if direction == "LONG" else "BUY"
                await self.broker.place_order(
                    symbol=symbol,
                    direction=exit_direction,
                    quantity=book_qty,
                    price=current_price,
                    order_type="MARKET",
                )
        except Exception as exc:
            logger.error("Partial booking order failed for %s: %s", symbol, exc)
            await self.error_engine.handle_error(
                exc,
                context={"action": "partial_booking", "symbol": symbol, "level": level, "qty": book_qty},
                session_id=self.session_id,
            )
            return

        # Calculate P&L for partial exit
        entry = position.entry_price
        if direction == "LONG":
            pnl_amount = (current_price - entry) * book_qty
            buy_p, sell_p = entry, current_price
        else:
            pnl_amount = (entry - current_price) * book_qty
            buy_p, sell_p = current_price, entry

        fees_config = self.config.get_fees_config() if hasattr(self.config, "get_fees_config") else {}
        brokerage = float(fees_config.get("brokerage_per_order", 20.0))
        from fees.nse_fee_calculator import NSEFeeCalculator
        fee_calc = NSEFeeCalculator(brokerage_per_order=brokerage)
        fee_res = fee_calc.calculate_equity_intraday(buy_price=buy_p, sell_price=sell_p, quantity=int(book_qty), brokerage_per_order=brokerage)
        partial_fees = float(fee_res.get("total", 0.0))
        net_partial_pnl = round(pnl_amount - partial_fees, 2)

        # Update position quantity and persist extra
        extra_data = getattr(position, "extra", {}) or {}
        if isinstance(extra_data, dict):
            extra_data["partial_realized_pnl"] = extra_data.get("partial_realized_pnl", 0.0) + net_partial_pnl
            extra_data["partial_fees"] = extra_data.get("partial_fees", 0.0) + partial_fees

        async with self._repo_context() as repo:
            await repo.update_position(
                position.id,
                quantity=remaining_qty,
                current_price=current_price,
                extra=extra_data,
            )

        # If fully exited, close the position
        if remaining_qty <= 0:
            await self._close_position(
                position=position,
                exit_price=current_price,
                close_reason="partial_complete",
                pnl_amount=pnl_amount,
            )

        # --- Broadcast & Telegram Partial Booking ---
        partial_payload = {
            "type": "partial_book",
            "position_id": position.id,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry,
            "level": level,
            "stage_name": booking_data.get("stage_name") or f"T{level}",
            "booked_qty": book_qty,
            "remaining_qty": remaining_qty,
            "booked_price": current_price,
            "pnl": round(pnl_amount, 2),
            "net_pnl": net_partial_pnl,
        }
        await self._broadcast("trade", partial_payload)
        await self._route_alert("partial_booking", partial_payload)

        logger.info(
            "Partial book L%d (%s) for %s: %d @ %.2f (P&L: %.2f, remaining: %d)",
            level, booking_data.get("stage_name", ""), symbol, book_qty, current_price, pnl_amount, remaining_qty,
        )


    async def _close_position(
        self,
        position,
        exit_price: float,
        close_reason: str,
        pnl_amount: float = 0,
        pnl_pct: float = 0,
    ) -> None:
        """Close a position and update the corresponding trade."""
        # Execute exit order via broker
        exit_success = True
        exit_err_msg = None
        try:
            if self.broker is not None and hasattr(self.broker, "place_order"):
                exit_direction = "SELL" if position.direction == "LONG" else "BUY"
                order_res = await self.broker.place_order(
                    symbol=position.symbol,
                    direction=exit_direction,
                    quantity=position.quantity,
                    price=exit_price,
                    order_type="MARKET",
                )
                if isinstance(order_res, dict):
                    status = str(order_res.get("status", "")).upper()
                    if status in ("REJECTED", "CANCELLED", "FAILED"):
                        exit_success = False
                        exit_err_msg = order_res.get("message") or order_res.get("error") or f"Broker order returned status: {status}"
        except Exception as exc:
            exit_success = False
            exit_err_msg = str(exc)
            logger.error("Exit order failed for %s: %s", position.symbol, exc, exc_info=True)
            await self.error_engine.handle_error(
                exc,
                context={"action": "close_position", "symbol": position.symbol, "reason": close_reason},
                session_id=self.session_id,
            )

        if not exit_success:
            self._errors_count += 1
            logger.critical(
                "CRITICAL: Failed to execute exit order for position %s (%s): %s. Position kept OPEN with status EXIT_FAILED.",
                position.id, position.symbol, exit_err_msg
            )
            async with self._repo_context() as repo:
                await repo.update_position(
                    position.id,
                    status="EXIT_FAILED",
                )
                await repo.update_trade(
                    position.trade_id,
                    status="EXIT_FAILED",
                )
            await self._broadcast("trade", {
                "type": "position_exit_failed",
                "position_id": position.id,
                "trade_id": position.trade_id,
                "symbol": position.symbol,
                "error": exit_err_msg,
                "close_reason": close_reason,
            })
            await self._route_alert("error", {
                "message": f"CRITICAL: Position exit failed for {position.symbol}. Position status set to EXIT_FAILED: {exit_err_msg}",
                "rule": "EXIT_ORDER_FAILED",
            })
            return

        # Calculate fees for exit using NSEFeeCalculator
        fees_config = self.config.get_fees_config() if hasattr(self.config, "get_fees_config") else {}
        brokerage = float(fees_config.get("brokerage_per_order", 20.0))
        from fees.nse_fee_calculator import NSEFeeCalculator
        fee_calc = NSEFeeCalculator(brokerage_per_order=brokerage)

        buy_price = position.entry_price if position.direction == "LONG" else exit_price
        sell_price = exit_price if position.direction == "LONG" else position.entry_price
        fee_breakdown = fee_calc.calculate_equity_intraday(
            buy_price=buy_price,
            sell_price=sell_price,
            quantity=int(position.quantity),
            brokerage_per_order=brokerage,
        )
        exit_fees = float(fee_breakdown.get("total", 0.0))

        async with self._repo_context() as repo:
            # Get entry fees from trade
            entry_fees = 0
            trade = await repo.get_trade(position.trade_id)
            if trade:
                entry_fees = trade.fees or 0

            total_fees = entry_fees + exit_fees
            net_pnl = round(pnl_amount - total_fees, 2)

            # Update trade
            await repo.update_trade(
                position.trade_id,
                exit_price=exit_price,
                exit_time=datetime.now(IST).isoformat(),
                status="CLOSED",
                pnl=round(pnl_amount, 2),
                fees=total_fees,
                net_pnl=net_pnl,
            )

            # Update position
            await repo.update_position(
                position.id,
                current_price=exit_price,
                status="CLOSED",
            )

        # Update daily risk tracker if present
        if self.daily_risk is not None and hasattr(self.daily_risk, "record_trade"):
            try:
                self.daily_risk.record_trade(pnl=net_pnl)
                daily_status = self.daily_risk.check_daily_limits()
                if daily_status and not getattr(daily_status, "can_trade", True):
                    await self._route_alert("risk_event", {
                        "message": f"Daily risk threshold exceeded ({getattr(daily_status, 'reason', 'Daily limit reached')}).",
                        "rule": "DAILY_RISK_LIMIT",
                    })
            except Exception as dr_err:
                logger.debug("Daily risk recording note: %s", dr_err)

        close_payload = {
            "type": "position_closed",
            "position_id": position.id,
            "trade_id": position.trade_id,
            "symbol": position.symbol,
            "direction": position.direction,
            "strategy": getattr(position, "strategy", ""),
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "target": getattr(position, "target", 0.0),
            "stop_loss": getattr(position, "stop_loss", 0.0),
            "quantity": position.quantity,
            "pnl": round(pnl_amount, 2),
            "net_pnl": net_pnl,
            "pnl_pct": pnl_pct,
            "fees": total_fees,
            "close_reason": close_reason,
        }
        await self._broadcast("trade", close_payload)

        # Dispatch specific Telegram alert based on exit condition
        reason_lower = close_reason.lower()
        if "stop" in reason_lower or "sl" in reason_lower:
            await self._route_alert("stop_loss_hit", close_payload)
        elif "target" in reason_lower:
            await self._route_alert("target_hit", close_payload)
        else:
            await self._route_alert("position_closed", close_payload)

        logger.info(
            "Position closed: %s %s x%d | Entry: %.2f -> Exit: %.2f | P&L: %.2f (Net: %.2f) | Reason: %s",
            position.direction, position.symbol, position.quantity,
            position.entry_price, exit_price, pnl_amount, net_pnl, close_reason,
        )

    # ------------------------------------------------------------------
    # Market Context
    # ------------------------------------------------------------------

    async def _update_market_context(self) -> None:
        """Update VIX, nifty price, nifty change, banknifty, and regime from feed/broker."""
        prev_nifty = self.nifty_price

        # Get Nifty price — prefer feed, fallback to broker with sanity range 15000–28000
        nifty_fetched = None
        for nifty_sym in ("NIFTY", "NIFTY 50", "NSE:NIFTY50-INDEX"):
            if self.feed is not None and hasattr(self.feed, "get_latest_price"):
                try:
                    p = await self.feed.get_latest_price(nifty_sym)
                    if p and p > 0:
                        nifty_fetched = float(p)
                        break
                except Exception:
                    pass
            if self.broker is not None and hasattr(self.broker, "get_latest_price"):
                try:
                    p = await self.broker.get_latest_price(nifty_sym)
                    if p and p > 0:
                        nifty_fetched = float(p)
                        break
                except Exception:
                    pass

        if nifty_fetched is not None:
            if 15000.0 <= nifty_fetched <= 28000.0:
                self.nifty_price = nifty_fetched
            else:
                logger.warning(
                    "NIFTY price %.2f outside sanity range [15000, 28000], retaining previous valid price %.2f",
                    nifty_fetched, self.nifty_price,
                )

        # Compute nifty_change percentage
        if self.nifty_price > 0:
            # Try to get previous close for accurate change
            if self._prev_nifty_close <= 0:
                # First run: try to fetch previous close from broker
                if self.broker is not None and hasattr(self.broker, "get_previous_close"):
                    try:
                        pc = await self.broker.get_previous_close("NIFTY 50")
                        if pc and 15000.0 <= pc <= 28000.0:
                            self._prev_nifty_close = pc
                    except Exception:
                        pass
                # Second fallback: try to fetch from feed daily candles
                if self._prev_nifty_close <= 0 and self.feed is not None and hasattr(self.feed, "get_candles"):
                    try:
                        candles = await self.feed.get_candles("^NSEI", "1d", 2)
                        if candles is not None and len(candles) >= 2:
                            c_close = float(candles.iloc[-2]["close"])
                            if 15000.0 <= c_close <= 28000.0:
                                self._prev_nifty_close = c_close
                    except Exception:
                        pass
                # Third fallback: use first observed price as baseline
                if self._prev_nifty_close <= 0 and prev_nifty > 0:
                    self._prev_nifty_close = prev_nifty
                elif self._prev_nifty_close <= 0:
                    self._prev_nifty_close = self.nifty_price

            if self._prev_nifty_close > 0:
                self.nifty_change = round(
                    ((self.nifty_price - self._prev_nifty_close) / self._prev_nifty_close) * 100, 2
                )

        # Get BankNifty price — prefer feed, fallback to broker with sanity range 35000–55000
        banknifty_fetched = None
        for bn_sym in ("BANKNIFTY", "NIFTY BANK", "NSE:NIFTYBANK-INDEX"):
            if self.feed is not None and hasattr(self.feed, "get_latest_price"):
                try:
                    p = await self.feed.get_latest_price(bn_sym)
                    if p and p > 0:
                        banknifty_fetched = float(p)
                        break
                except Exception:
                    pass
            if self.broker is not None and hasattr(self.broker, "get_latest_price"):
                try:
                    p = await self.broker.get_latest_price(bn_sym)
                    if p and p > 0:
                        banknifty_fetched = float(p)
                        break
                except Exception:
                    pass

        if banknifty_fetched is not None:
            if 35000.0 <= banknifty_fetched <= 55000.0:
                self.banknifty_price = banknifty_fetched
            else:
                logger.warning(
                    "BANKNIFTY price %.2f outside sanity range [35000, 55000], retaining previous valid price %.2f",
                    banknifty_fetched, self.banknifty_price,
                )

        # Get VIX — prefer feed, fallback to broker
        for vix_sym in ("INDIAVIX", "INDIA VIX", "NSE:INDIAVIX-INDEX"):
            if self.feed is not None and hasattr(self.feed, "get_latest_price"):
                try:
                    v = await self.feed.get_latest_price(vix_sym)
                    if v and v > 0:
                        self.vix = v
                        break
                except Exception:
                    pass
            if self.broker is not None and hasattr(self.broker, "get_latest_price"):
                try:
                    v = await self.broker.get_latest_price(vix_sym)
                    if v and v > 0:
                        self.vix = v
                        break
                except Exception:
                    pass
        if self.vix <= 0:
            self.vix = 15.0  # fallback default

        # Update regime (simplified: based on VIX and Nifty change)
        # Full regime classification will be in a dedicated module
        self._update_regime_simple()

    def _update_regime_simple(self) -> None:
        """Simplified regime classification based on VIX.

        Proper regime detection (AD ratio, Nifty 5-day change) will be
        in a dedicated regime module. This provides a basic fallback.
        """
        regime_config = self.config.get_regime_config()
        high_vix = regime_config.get("high_vix_threshold", 22)

        if self.vix >= high_vix:
            new_regime = "Volatile"
        elif self.vix >= 18:
            new_regime = "Bear"
        else:
            new_regime = "Bull"

        if new_regime != self.current_regime:
            old_regime = self.current_regime
            self.current_regime = new_regime

            # Update active strategies for new regime
            activation = self.config.get_strategy_activation(new_regime)
            self.active_strategies = activation.get("active", [])

            logger.info(
                "Regime changed: %s -> %s (VIX=%.1f, strategies=%s)",
                old_regime, new_regime, self.vix, self.active_strategies,
            )

    async def _update_position_prices(self) -> None:
        """Update current_price for all open positions."""
        async with self._repo_context() as repo:
            positions = await repo.get_open_positions()

            for pos in positions:
                price = 0.0
                if self.feed is not None and hasattr(self.feed, "get_latest_price"):
                    try:
                        price = await self.feed.get_latest_price(pos.symbol)
                    except Exception:
                        pass
                if price <= 0 and self.broker is not None and hasattr(self.broker, "get_latest_price"):
                    try:
                        price = await self.broker.get_latest_price(pos.symbol)
                    except Exception:
                        pass
                if price > 0:
                    await repo.update_position(pos.id, current_price=price)

    # ------------------------------------------------------------------
    # Status & Dashboard
    # ------------------------------------------------------------------

    async def get_status(self) -> dict:
        """Get full engine status."""
        market_status = self.market_hours.get_market_status()
        uptime_seconds = 0
        if self._start_time:
            uptime_seconds = (datetime.now(IST) - self._start_time).total_seconds()

        # Get daily P&L
        pnl_data = {"net_pnl": 0, "total_trades": 0, "wins": 0, "losses": 0}
        try:
            async with self._repo_context() as repo:
                pnl_data = await repo.get_todays_pnl()
        except Exception:
            pass

        # Get risk status
        risk_summary = {}
        try:
            risk_status = await self.daily_risk.get_daily_risk_status()
            if hasattr(risk_status, "model_dump"):
                risk_summary = risk_status.model_dump()
            elif isinstance(risk_status, dict):
                risk_summary = risk_status
        except Exception:
            pass

        return {
            "state": self.state.value,
            "mode": self.mode,
            "broker": self.broker_name or "paper",
            "session_id": self.session_id,
            "regime": self.current_regime,
            "vix": self.vix,
            "nifty_price": self.nifty_price,
            "market": market_status,
            "active_strategies": self.active_strategies,
            "pending_opportunities": len(self.pending_opportunities),
            "scans_completed": self._scan_count,
            "symbols_scanned": self._symbols_scanned_count,
            "signals_generated": self._signals_generated,
            "signals_passed": self._signals_passed_count,
            "signals_rejected": self._signals_rejected_count,
            "rejections_by_gate": dict(self._rejections_by_gate),
            "rejections_by_strategy": dict(self._rejections_by_strategy),
            "trades_executed": self._trades_executed,
            "errors_count": self._errors_count,
            "uptime_seconds": round(uptime_seconds, 1),
            "daily_pnl": pnl_data,
            "risk": risk_summary,
            "initial_capital": self.initial_capital,
        }

    async def get_dashboard_data(self) -> dict:
        """Get aggregated dashboard data."""
        positions_data = []
        total_invested = 0
        total_unrealized_pnl = 0
        trades_data = []
        pnl_data = {"net_pnl": 0, "total_trades": 0, "wins": 0, "losses": 0}

        async with self._repo_context() as repo:
            # Today's P&L
            pnl_data = await repo.get_todays_pnl()

            # Open positions
            open_positions = await repo.get_open_positions()

            for pos in open_positions:
                entry = pos.entry_price or 0
                current = pos.current_price or pos.entry_price or 0
                qty = pos.quantity or 0
                invested = entry * qty
                unrealized = 0
                if pos.direction == "LONG":
                    unrealized = (current - entry) * qty
                else:
                    unrealized = (entry - current) * qty

                positions_data.append({
                    "position_id": pos.id,
                    "trade_id": pos.trade_id,
                    "symbol": pos.symbol,
                    "direction": pos.direction,
                    "strategy": pos.strategy,
                    "entry_price": entry,
                    "current_price": current,
                    "quantity": qty,
                    "invested_amount": round(invested, 2),
                    "unrealized_pnl": round(unrealized, 2),
                    "unrealized_pnl_pct": round(unrealized / invested * 100, 2) if invested > 0 else 0,
                    "stop_loss": pos.stop_loss,
                    "target": pos.target,
                })
                total_invested += invested
                total_unrealized_pnl += unrealized

            # Today's trades
            todays_trades = await repo.get_todays_trades()
            for t in todays_trades:
                trades_data.append({
                    "trade_id": t.id,
                    "symbol": t.symbol,
                "direction": t.direction,
                "strategy": t.strategy,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "status": t.status,
                "pnl": t.pnl,
                "net_pnl": t.net_pnl,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
            })

        # Risk state
        risk_state = {}
        try:
            risk_status = await self.daily_risk.get_daily_risk_status()
            if hasattr(risk_status, "model_dump"):
                risk_state = risk_status.model_dump()
            elif isinstance(risk_status, dict):
                risk_state = risk_status
        except Exception:
            pass

        # Market status
        market_status = self.market_hours.get_market_status()

        # Pending opportunities
        async with self._opportunities_lock:
            pending = list(self.pending_opportunities.values())

        # Engine status
        uptime_seconds = 0
        if self._start_time:
            uptime_seconds = (datetime.now(IST) - self._start_time).total_seconds()

        # Capital metrics
        cap_cfg = self.config.get_capital_config() if hasattr(self.config, "get_capital_config") else {}
        total_capital = float(self.initial_capital or cap_cfg.get("virtual_capital", 100000.0) or 100000.0)
        capital_available = max(0.0, total_capital - total_invested)
        capital_usage_pct = round((total_invested / total_capital * 100.0), 2) if total_capital > 0 else 0.0

        return {
            "engine": {
                "state": self.state.value,
                "mode": self.mode,
                "broker": self.broker_name or "paper",
                "session_id": self.session_id,
                "uptime_seconds": round(uptime_seconds, 1),
                "scans_completed": self._scan_count,
                "symbols_scanned": self._symbols_scanned_count,
                "signals_generated": self._signals_generated,
                "signals_passed": self._signals_passed_count,
                "signals_rejected": self._signals_rejected_count,
                "rejections_by_gate": dict(self._rejections_by_gate),
                "rejections_by_strategy": dict(self._rejections_by_strategy),
                "trades_executed": self._trades_executed,
                "errors_count": self._errors_count,
            },
            "market": market_status,
            "regime": self.current_regime if hasattr(self, "current_regime") and self.current_regime else "Sideways",
            "regime_confidence": getattr(self, "regime_confidence", 78),
            "vix": getattr(self, "vix", 15.5) or 15.5,
            "nifty_price": getattr(self, "nifty_price", 24856.50) or 24856.50,
            "nifty_change": getattr(self, "nifty_change", 0.45),
            "active_strategies": getattr(self, "active_strategies", []),
            "capital": {
                "total": total_capital,
                "invested": round(total_invested, 2),
                "available": round(capital_available, 2),
                "usage_pct": capital_usage_pct,
                "unrealized_pnl": round(total_unrealized_pnl, 2),
            },
            "daily_pnl": pnl_data,
            "risk": risk_state,
            "open_positions": positions_data,
            "open_position_count": len(open_positions),
            "todays_trades": trades_data,
            "pending_opportunities": pending,
            "pending_opportunity_count": len(pending),
            "timestamp": datetime.now(IST).isoformat(),
        }

    # ------------------------------------------------------------------
    # WebSocket Broadcast
    # ------------------------------------------------------------------

    async def _broadcast(self, channel: str, data: dict) -> None:
        """Send data via WebSocket manager if available.

        Args:
            channel: Channel name (e.g. 'engine', 'trade', 'opportunity', 'risk').
            data: Payload dict to send.
        """
        if self.ws_manager is None:
            return

        try:
            if hasattr(self.ws_manager, "broadcast"):
                await self.ws_manager.broadcast(channel, data)
            elif callable(self.ws_manager):
                result = self.ws_manager(channel, data)
                if asyncio.iscoroutine(result):
                    await result
        except Exception as ws_exc:
            logger.warning("WebSocket broadcast failed on channel '%s': %s", channel, ws_exc, exc_info=True)
