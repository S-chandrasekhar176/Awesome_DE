"""Telegram bot integration for UltraBot Web notifications.

Sends trade fills, risk alerts, error alerts, morning briefings, and EOD reports
via the Telegram Bot API with HTML sanitization.
"""
import html
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import httpx

from utils.formatters import format_currency, format_pct

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


def _esc(val: Any) -> str:
    """Sanitize variable strings for HTML parsing mode in Telegram."""
    if val is None:
        return ""
    return html.escape(str(val))


class TelegramBot:
    """Send notifications via Telegram Bot API.

    If bot_token is empty, all send methods log a warning and return False
    without crashing. This makes the bot safe to use even when no token is
    configured (e.g. during development).
    """

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._timeout = 10.0

    # ------------------------------------------------------------------
    # Core send
    # ------------------------------------------------------------------

    async def send_message(self, text: str) -> bool:
        """POST a text message to the configured Telegram chat.

        Returns True on success, False on any failure or missing token.
        """
        if not self.bot_token:
            logger.warning("Telegram bot_token is empty – message not sent.")
            return False

        url = _TELEGRAM_API_BASE.format(token=self.bot_token)
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                body = resp.json()
                if not body.get("ok"):
                    logger.error("Telegram API error: %s", body.get("description"))
                    return False
                return True
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Trade fill
    # ------------------------------------------------------------------

    async def send_trade_fill(self, trade: dict) -> bool:
        """Send a formatted trade fill notification."""
        symbol = _esc(trade.get("symbol", "?"))
        direction = _esc(trade.get("direction", "?"))
        strategy = _esc(trade.get("strategy", ""))
        entry_price = float(trade.get("entry_price") or 0)
        qty = int(trade.get("qty") or trade.get("quantity") or 0)
        sl = float(trade.get("sl") or trade.get("stop_loss") or 0)
        target = float(trade.get("target") or trade.get("target_price") or 0)
        lot_size = int(trade.get("lot_size") or 1)
        option_type = _esc(trade.get("option_type", ""))
        strike = _esc(trade.get("strike", ""))

        direction_emoji = "🟢" if "LONG" in direction.upper() or "BUY" in direction.upper() else "🔴"
        label = f"{option_type} {strike}" if option_type and strike else symbol

        invested = entry_price * qty * lot_size

        lines = [
            f"{direction_emoji} <b>TRADE FILLED</b>",
            f"",  
            f"<b>Symbol:</b> {symbol} ({label})",
            f"<b>Direction:</b> {direction}",
            f"<b>Strategy:</b> {strategy}",
            f"<b>Entry:</b> {entry_price:.2f} x {qty} lots = {format_currency(invested)}",
            f"<b>SL:</b> {sl:.2f}  |  <b>Target:</b> {target:.2f}",
            f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S')}",
        ]
        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # Partial booking
    # ------------------------------------------------------------------

    async def send_partial_booking(self, position, level: str, qty: int, price: float) -> bool:
        """Send a partial booking notification."""
        symbol = _esc(getattr(position, "symbol", "?"))
        direction = _esc(getattr(position, "direction", "?"))
        entry_price = float(getattr(position, "entry_price", 0) or 0)
        total_qty = int(getattr(position, "quantity", None) or getattr(position, "qty", 0) or 0)

        booked_qty = min(qty, total_qty)
        remaining = total_qty - booked_qty

        if entry_price > 0 and price > 0:
            if "LONG" in direction.upper() or "BUY" in direction.upper():
                pnl = (price - entry_price) * booked_qty
            else:
                pnl = (entry_price - price) * booked_qty
        else:
            pnl = 0.0

        lines = [
            f"📦 <b>PARTIAL BOOK – {_esc(level.upper())}</b>",
            f"",
            f"<b>Symbol:</b> {symbol}  |  <b>Direction:</b> {direction}",
            f"<b>Booked:</b> {booked_qty} lots @ {price:.2f}",
            f"<b>P&amp;L:</b> {format_currency(pnl, show_sign=True)}",
            f"<b>Remaining:</b> {remaining} lots @ entry {entry_price:.2f}",
            f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S')}",
        ]
        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # SL / Target hit
    # ------------------------------------------------------------------

    async def send_sl_hit(self, trade: dict) -> bool:
        """Send a stop-loss hit notification."""
        symbol = _esc(trade.get("symbol", "?"))
        direction = _esc(trade.get("direction", "?"))
        entry_price = float(trade.get("entry_price", 0))
        exit_price = float(trade.get("exit_price", 0))
        qty = int(trade.get("qty", 0))
        lot_size = int(trade.get("lot_size", 1))
        strategy = _esc(trade.get("strategy", ""))

        if "LONG" in direction.upper() or "BUY" in direction.upper():
            pnl = (exit_price - entry_price) * qty * lot_size
        else:
            pnl = (entry_price - exit_price) * qty * lot_size

        pnl_pct = ((pnl) / (entry_price * qty * lot_size) * 100) if entry_price * qty * lot_size > 0 else 0

        lines = [
            f"⛔ <b>SL HIT</b>",
            f"",
            f"<b>Symbol:</b> {symbol}  |  <b>Direction:</b> {direction}",
            f"<b>Strategy:</b> {strategy}",
            f"<b>Entry:</b> {entry_price:.2f} → <b>Exit:</b> {exit_price:.2f}",
            f"<b>P&amp;L:</b> {format_currency(pnl, show_sign=True)} ({format_pct(pnl_pct)})",
            f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S')}",
        ]
        return await self.send_message("\n".join(lines))

    async def send_target_hit(self, trade: dict) -> bool:
        """Send a target hit notification."""
        symbol = _esc(trade.get("symbol", "?"))
        direction = _esc(trade.get("direction", "?"))
        entry_price = float(trade.get("entry_price", 0))
        exit_price = float(trade.get("exit_price", 0))
        target = float(trade.get("target", 0))
        qty = int(trade.get("qty", 0))
        lot_size = int(trade.get("lot_size", 1))
        strategy = _esc(trade.get("strategy", ""))

        if "LONG" in direction.upper() or "BUY" in direction.upper():
            pnl = (exit_price - entry_price) * qty * lot_size
        else:
            pnl = (entry_price - exit_price) * qty * lot_size

        pnl_pct = ((pnl) / (entry_price * qty * lot_size) * 100) if entry_price * qty * lot_size > 0 else 0

        lines = [
            f"🎯 <b>TARGET HIT</b>",
            f"",
            f"<b>Symbol:</b> {symbol}  |  <b>Direction:</b> {direction}",
            f"<b>Strategy:</b> {strategy}",
            f"<b>Entry:</b> {entry_price:.2f} → <b>Exit:</b> {exit_price:.2f} (Target: {target:.2f})",
            f"<b>P&amp;L:</b> {format_currency(pnl, show_sign=True)} ({format_pct(pnl_pct)})",
            f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S')}",
        ]
        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # Morning briefing
    # ------------------------------------------------------------------

    async def send_morning_briefing(self, watchlist: list, regime: str, vix: float) -> bool:
        """Send the morning briefing with watchlist, regime, and VIX."""
        now = datetime.now(IST).strftime("%d-%b-%Y %H:%M")

        lines = [
            f"🌅 <b>MORNING BRIEFING</b>  –  {now}",
            f"",
            f"<b>Regime:</b> {_esc(regime)}",
            f"<b>India VIX:</b> {vix:.2f}",
            f"",
            f"<b>Watchlist ({len(watchlist)} stocks):</b>",
        ]

        for item in watchlist[:30]:
            if isinstance(item, dict):
                sym = _esc(item.get("symbol", str(item)))
                reason = _esc(item.get("reason", ""))
                if reason:
                    lines.append(f"  • {sym} – {reason}")
                else:
                    lines.append(f"  • {sym}")
            else:
                lines.append(f"  • {_esc(item)}")

        lines.append(f"")
        lines.append(f"<i>Engine starting scan cycle...</i>")
        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # EOD report
    # ------------------------------------------------------------------

    async def send_eod_report(self, daily_summary: dict, trades: list) -> bool:
        """Send end-of-day report."""
        today_str = _esc(daily_summary.get("date", ""))
        net_pnl = float(daily_summary.get("net_pnl", 0))
        gross_pnl = float(daily_summary.get("gross_pnl", 0))
        total_fees = float(daily_summary.get("total_fees", 0))
        total_trades = int(daily_summary.get("total_trades", 0))
        wins = int(daily_summary.get("wins", 0))
        losses = int(daily_summary.get("losses", 0))
        win_rate = float(daily_summary.get("win_rate", 0))
        best_trade = float(daily_summary.get("best_trade", 0))
        worst_trade = float(daily_summary.get("worst_trade", 0))

        pnl_emoji = "🟢" if net_pnl >= 0 else "🔴"

        lines = [
            f"📊 <b>EOD REPORT – {today_str}</b>",
            f"",
            f"{pnl_emoji} <b>Net P&amp;L:</b> {format_currency(net_pnl, show_sign=True)}",
            f"   Gross: {format_currency(gross_pnl, show_sign=True)}  |  Fees: {format_currency(total_fees)}",
            f"",
            f"<b>Trades:</b> {total_trades}  (W: {wins}  L: {losses})",
            f"<b>Win Rate:</b> {win_rate:.1f}%",
            f"<b>Best:</b> {format_currency(best_trade, show_sign=True)}  |  <b>Worst:</b> {format_currency(worst_trade, show_sign=True)}",
            f"",
        ]

        if trades:
            lines.append(f"<b>Trade Details:</b>")
            for t in trades[:15]:
                if isinstance(t, dict):
                    sym = _esc(t.get("symbol", "?"))
                    t_pnl = float(t.get("net_pnl", t.get("pnl", 0)))
                    strat = _esc(t.get("strategy", ""))
                    status = _esc(t.get("status", ""))
                    direction = _esc(t.get("direction", ""))
                    lines.append(
                        f"  {sym} {direction} {strat} → {format_currency(t_pnl, show_sign=True)} [{status}]"
                    )
                else:
                    # SQLAlchemy model object
                    sym = _esc(getattr(t, "symbol", "?"))
                    t_pnl = float(getattr(t, "net_pnl", 0))
                    strat = _esc(getattr(t, "strategy", ""))
                    status = _esc(getattr(t, "status", ""))
                    direction = _esc(getattr(t, "direction", ""))
                    lines.append(
                        f"  {sym} {direction} {strat} → {format_currency(t_pnl, show_sign=True)} [{status}]"
                    )

        lines.append(f"")
        lines.append(f"<i>Session ended. See you tomorrow!</i>")
        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # Error alert
    # ------------------------------------------------------------------

    async def send_error_alert(self, error: dict) -> bool:
        """Send a critical error alert."""
        error_type = _esc(error.get("error_type", "UnknownError"))
        severity = _esc(error.get("severity", "error"))
        what = _esc(error.get("what_happened", ""))
        why = _esc(error.get("why_happened", ""))
        how = _esc(error.get("how_to_fix", ""))
        context = error.get("context", {})

        severity_emoji = {
            "critical": "🚨",
            "error": "❌",
            "warning": "⚠️",
            "info": "ℹ️",
        }.get(severity.lower(), "❌")

        lines = [
            f"{severity_emoji} <b>{error_type}</b> [{severity.upper()}]",
            f"",
            f"<b>What:</b> {what}",
        ]
        if why:
            lines.append(f"<b>Why:</b> {why}")
        if how:
            lines.append(f"<b>Fix:</b> {how}")
        if context and isinstance(context, dict):
            ctx_str = "\n".join(f"  • {_esc(k)}: {_esc(v)}" for k, v in list(context.items())[:5])
            lines.append(f"<b>Context:</b>\n{ctx_str}")
        lines.append(f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S')}")

        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # Risk alert
    # ------------------------------------------------------------------

    async def send_risk_alert(self, message: str) -> bool:
        """Send a risk warning alert."""
        lines = [
            f"⚠️ <b>RISK ALERT</b>",
            f"",
            f"{_esc(message)}",
            f"",
            f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S')}",
        ]
        return await self.send_message("\n".join(lines))
