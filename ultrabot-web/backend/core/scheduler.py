"""Market Lifecycle Scheduler for UltraBot.

Orchestrates all Indian market lifecycle events using APScheduler / asyncio cron:
  - 08:45 AM IST: Pre-market initialization & daily counters reset
  - 09:15 AM IST: Market open & scan loop activation
  - 15:15 PM IST: Auto-squareoff warning alert (10 mins to EOD)
  - 15:20 PM IST: Auto-squareoff execution for all MIS positions
  - 15:30 PM IST: Market close & DailySummary persistence
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date, time
from typing import Any, Callable, Dict, Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from scanner.watchlist_builder import WatchlistBuilder

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")



class MarketLifecycleScheduler:
    """Automates Indian stock market (NSE) daily lifecycle routines."""

    def __init__(self, engine: Any, repository_getter: Callable):
        self.engine = engine
        self._get_repo = repository_getter
        self.scheduler = AsyncIOScheduler(timezone=IST)
        self._is_running = False

    def start(self) -> None:
        """Register all daily cron triggers and start scheduler."""
        if self._is_running:
            return

        # 1. Pre-market initialization: 08:45 AM Mon-Fri
        self.scheduler.add_job(
            self.on_pre_market_init,
            CronTrigger(hour=8, minute=45, day_of_week="mon-fri", timezone=IST),
            id="pre_market_init",
            replace_existing=True,
        )

        # 2. Market Open: 09:15 AM Mon-Fri
        self.scheduler.add_job(
            self.on_market_open,
            CronTrigger(hour=9, minute=15, day_of_week="mon-fri", timezone=IST),
            id="market_open",
            replace_existing=True,
        )

        # 3. Squareoff Warning: 15:15 PM Mon-Fri
        self.scheduler.add_job(
            self.on_squareoff_warning,
            CronTrigger(hour=15, minute=15, day_of_week="mon-fri", timezone=IST),
            id="squareoff_warning",
            replace_existing=True,
        )

        # 4. Auto-Squareoff Execution: 15:20 PM Mon-Fri
        self.scheduler.add_job(
            self.on_auto_squareoff,
            CronTrigger(hour=15, minute=20, day_of_week="mon-fri", timezone=IST),
            id="auto_squareoff",
            replace_existing=True,
        )

        # 5. Market Close & Daily Summary: 15:30 PM Mon-Fri
        self.scheduler.add_job(
            self.on_market_close,
            CronTrigger(hour=15, minute=30, day_of_week="mon-fri", timezone=IST),
            id="market_close",
            replace_existing=True,
        )

        self.scheduler.start()
        self._is_running = True
        logger.info("MarketLifecycleScheduler started with 5 scheduled lifecycle jobs (IST)")

    def stop(self) -> None:
        """Stop scheduler."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("MarketLifecycleScheduler stopped")

    def _is_trading_day(self) -> bool:
        """Check if today is a regular NSE trading day."""
        today = datetime.now(IST).date()
        if today.weekday() >= 5:
            return False
        mh = getattr(self.engine, "market_hours", None)
        if mh and hasattr(mh, "is_market_holiday"):
            try:
                res = mh.is_market_holiday(today)
                if isinstance(res, bool):
                    return not res
            except Exception:
                pass
        return True

    # ─────────────────────────────────────────────
    # Lifecycle Handlers
    # ─────────────────────────────────────────────

    async def on_pre_market_init(self) -> None:
        """08:45 AM: Reset daily risk counters, calibrate market parameters,
        and automatically generate and persist the daily Top-10 Watchlist."""
        if not self._is_trading_day():
            logger.info("[08:45 AM IST] Skipping Pre-Market Init: today is an NSE market holiday or weekend.")
            return
        logger.info("[08:45 AM IST] Running Pre-Market Initialization...")
        try:
            # 1. Reset daily risk counters
            daily_mgr = getattr(self.engine, "daily_risk", None) or getattr(self.engine, "daily_risk_manager", None)
            if daily_mgr and hasattr(daily_mgr, "reset_daily"):
                daily_mgr.reset_daily()
                logger.info("Daily risk counters reset for new trading session.")

            # 2. Automated Pre-market Watchlist Generation (Top 10)
            try:
                feed = getattr(self.engine, "feed", None)
                regime = getattr(self.engine, "current_regime", "Sideways") or "Sideways"

                news_items = []
                news_engine = getattr(self.engine, "news_engine", None)
                if news_engine and hasattr(news_engine, "get_recent_news"):
                    try:
                        news_items = news_engine.get_recent_news(limit=20)
                    except Exception:
                        pass

                builder = WatchlistBuilder()
                top_10 = await builder.build_daily_watchlist(
                    feed=feed,
                    news_items=news_items,
                    regime=regime,
                    final_top_n=10,
                )

                # Persist to Watchlist DB table
                persisted_symbols = []
                repo = await self._get_repo()
                try:
                    active_items = await repo.get_active_watchlist()
                    for old_item in active_items:
                        await repo.update_watchlist_item(old_item.id, is_active=False)

                    for item in top_10:
                        sym = item["symbol"]
                        existing = await repo.get_watchlist_item_by_symbol(sym)
                        if existing:
                            await repo.update_watchlist_item(
                                existing.id,
                                name=item.get("name", existing.name),
                                sector=item.get("sector", existing.sector),
                                lot_size=item.get("lot_size", existing.lot_size),
                                is_fno=item.get("is_fno", True),
                                is_active=True,
                                extra=item,
                            )
                        else:
                            await repo.add_watchlist_item(
                                symbol=sym,
                                name=item.get("name", sym),
                                sector=item.get("sector", "Unknown"),
                                lot_size=item.get("lot_size", 1),
                                is_fno=item.get("is_fno", True),
                                is_active=True,
                                extra=item,
                            )
                        persisted_symbols.append(sym)
                finally:
                    if repo is not None and hasattr(repo, "close"):
                        try:
                            res = repo.close()
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception:
                            pass

                logger.info(
                    "[08:45 AM IST] Auto-generated Top 10 Daily Watchlist (Regime=%s): %s",
                    regime, persisted_symbols,
                )

                if hasattr(self.engine, "_broadcast"):
                    await self.engine._broadcast("watchlist", {
                        "type": "daily_watchlist_updated",
                        "timestamp": datetime.now(IST).isoformat(),
                        "regime": regime,
                        "count": len(top_10),
                        "symbols": persisted_symbols,
                        "items": top_10,
                    })

                if hasattr(self.engine, "_route_alert"):
                    await self.engine._route_alert("morning_briefing", {
                        "watchlist": top_10,
                        "regime": regime,
                        "vix": getattr(self.engine, "vix", 15.0),
                    })
            except Exception as wl_exc:
                logger.error("Failed to auto-generate pre-market watchlist: %s", wl_exc, exc_info=True)

            if hasattr(self.engine, "_broadcast"):
                await self.engine._broadcast("market", {
                    "type": "pre_market_initialized",
                    "timestamp": datetime.now(IST).isoformat(),
                    "message": "Daily risk limits reset & Top 10 Watchlist prepared for 09:15 AM market open.",
                })
        except Exception as exc:
            logger.error("Pre-market initialization error: %s", exc, exc_info=True)


    async def on_market_open(self) -> None:
        """09:15 AM: NSE Market Open event."""
        if not self._is_trading_day():
            logger.info("[09:15 AM IST] Skipping Market Open: today is an NSE market holiday or weekend.")
            return
        logger.info("[09:15 AM IST] Market Open - Activating live strategy scanning...")
        try:
            await self.engine._broadcast("market", {
                "type": "market_opened",
                "timestamp": datetime.now(IST).isoformat(),
                "message": "NSE regular trading hours commenced (09:15 - 15:30 IST).",
            })
        except Exception as exc:
            logger.error("Market open notification error: %s", exc)

    async def on_squareoff_warning(self) -> None:
        """15:15 PM: Squareoff Warning Alert (10 mins to EOD auto-squareoff)."""
        if not self._is_trading_day():
            return
        logger.warning("[15:15 PM IST] Intraday auto-squareoff warning (5 minutes remaining).")
        try:
            await self.engine._broadcast("risk_event", {
                "type": "squareoff_warning",
                "timestamp": datetime.now(IST).isoformat(),
                "message": "Intraday (MIS) positions will be auto-squared off at 15:20 PM IST.",
            })
            if hasattr(self.engine, "_route_alert"):
                await self.engine._route_alert("risk_event", {
                    "message": "Intraday (MIS) positions will be auto-squared off at 15:20 PM IST (5 minutes remaining).",
                    "rule": "AUTO_SQUAREOFF_WARNING",
                })
        except Exception as exc:
            logger.error("Squareoff warning error: %s", exc)

    async def on_auto_squareoff(self) -> None:
        """15:20 PM: Force close all open intraday positions."""
        if not self._is_trading_day():
            return
        logger.warning("[15:20 PM IST] Executing Intraday Auto-Squareoff for all open positions...")
        try:
            open_positions = []
            repo = await self._get_repo()
            try:
                open_positions = await repo.get_open_positions()
            finally:
                if repo is not None and hasattr(repo, "close"):
                    try:
                        res = repo.close()
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception:
                        pass

            for pos in open_positions:
                try:
                    # Fetch fresh LTP from feed or broker immediately before calculating square-off P&L
                    fresh_price = None
                    if self.engine and self.engine.feed and hasattr(self.engine.feed, "get_latest_price"):
                        try:
                            fresh_price = await self.engine.feed.get_latest_price(pos.symbol)
                        except Exception as feed_err:
                            logger.warning("Could not fetch fresh feed price for %s auto-squareoff: %s", pos.symbol, feed_err)

                    if not fresh_price and self.engine and self.engine.broker and hasattr(self.engine.broker, "get_latest_price"):
                        try:
                            fresh_price = await self.engine.broker.get_latest_price(pos.symbol)
                        except Exception as broker_err:
                            logger.warning("Could not fetch fresh broker price for %s auto-squareoff: %s", pos.symbol, broker_err)

                    current_price = float(fresh_price) if fresh_price and fresh_price > 0 else (pos.current_price or pos.entry_price)
                    pnl_amount = (current_price - pos.entry_price) * pos.quantity if pos.direction == "LONG" else (pos.entry_price - current_price) * pos.quantity
                    pnl_pct = (pnl_amount / (pos.entry_price * pos.quantity)) * 100 if pos.entry_price > 0 else 0.0

                    await self.engine._close_position(
                        position=pos,
                        exit_price=current_price,
                        close_reason="auto_squareoff",
                        pnl_amount=pnl_amount,
                        pnl_pct=pnl_pct,
                    )
                    logger.info("Auto-squared off position %s (%s) @ INR %.2f", pos.id, pos.symbol, current_price)
                except Exception as pos_err:
                    logger.error("Failed to auto-squareoff position %s: %s", pos.id, pos_err)

            await self.engine._broadcast("market", {
                "type": "auto_squareoff_completed",
                "closed_count": len(open_positions),
                "timestamp": datetime.now(IST).isoformat(),
                "message": f"Successfully auto-squared off {len(open_positions)} open intraday positions.",
            })
        except Exception as exc:
            logger.error("Auto squareoff routine error: %s", exc, exc_info=True)

    async def on_market_close(self) -> None:
        """15:30 PM: Market Close & Save Daily Summary to DB."""
        if not self._is_trading_day():
            return
        logger.info("[15:30 PM IST] Market Close - Generating Daily Summary...")
        try:
            today_str = datetime.now(IST).date().isoformat()
            total_trades = 0
            total_net_pnl = 0.0

            repo = await self._get_repo()
            try:
                todays_trades = await repo.get_todays_closed_trades()
                wins = sum(1 for t in todays_trades if t.net_pnl > 0)
                losses = sum(1 for t in todays_trades if t.net_pnl <= 0)
                total_trades = len(todays_trades)
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
                total_net_pnl = sum(t.net_pnl for t in todays_trades)

                # Persist summary
                await repo.create_daily_summary(
                    date=today_str,
                    total_trades=total_trades,
                    wins=wins,
                    losses=losses,
                    win_rate=win_rate,
                    net_pnl=total_net_pnl,
                    max_drawdown_pct=await repo.get_max_drawdown_pct(),
                )
            finally:
                if repo is not None and hasattr(repo, "close"):
                    try:
                        res = repo.close()
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception:
                        pass
            logger.info("DailySummary saved for %s: %d trades, Net PnL: INR %.2f", today_str, total_trades, total_net_pnl)

            await self.engine._broadcast("market", {
                "type": "market_closed",
                "date": today_str,
                "total_trades": total_trades,
                "net_pnl": total_net_pnl,
                "win_rate": win_rate,
                "timestamp": datetime.now(IST).isoformat(),
            })

            if hasattr(self.engine, "_route_alert"):
                await self.engine._route_alert("eod_report", {
                    "daily_summary": {
                        "date": today_str,
                        "total_trades": total_trades,
                        "wins": wins,
                        "losses": losses,
                        "win_rate": win_rate,
                        "net_pnl": total_net_pnl,
                    },
                    "trades": todays_trades,
                })
        except Exception as exc:
            logger.error("Market close routine error: %s", exc, exc_info=True)
