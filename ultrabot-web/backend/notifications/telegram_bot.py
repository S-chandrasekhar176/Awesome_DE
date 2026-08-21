"""Telegram bot integration for UltraBot Web notifications.

Sends trade fills, partial bookings, stop loss hits, target hits,
risk warnings, engine status changes, error alerts, morning briefings, and EOD reports
via the Telegram Bot API with HTML sanitization.
"""
import html
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
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
        self.bot_token = str(bot_token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self._timeout = 10.0

    def update_credentials(self, bot_token: str, chat_id: str) -> None:
        """Update Telegram credentials dynamically."""
        self.bot_token = str(bot_token or "").strip()
        self.chat_id = str(chat_id or "").strip()

    # ------------------------------------------------------------------
    # Core send
    # ------------------------------------------------------------------

    async def send_message(self, text: str) -> bool:
        """POST a text message to the configured Telegram chat.

        Returns True on success, False on any failure or missing token.
        """
        if not self.bot_token or not self.chat_id:
            logger.debug("Telegram credentials not configured – message skipped.")
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
    # 1. Trade Executed (Fill)
    # ------------------------------------------------------------------

    async def send_trade_fill(self, trade: Union[dict, Any]) -> bool:
        """Send a formatted trade executed / filled notification."""
        if isinstance(trade, dict):
            symbol = _esc(trade.get("symbol", "?"))
            direction = _esc(trade.get("direction", "?"))
            strategy = _esc(trade.get("strategy", ""))
            entry_price = float(trade.get("entry_price") or trade.get("filled_price") or 0.0)
            qty = int(trade.get("qty") or trade.get("quantity") or 0)
            sl = float(trade.get("sl") or trade.get("stop_loss") or 0.0)
            target = float(trade.get("target") or trade.get("target_price") or 0.0)
            fees = float(trade.get("fees") or 0.0)
            option_type = _esc(trade.get("option_type", ""))
            strike = _esc(trade.get("strike", ""))
        else:
            symbol = _esc(getattr(trade, "symbol", "?"))
            direction = _esc(getattr(trade, "direction", "?"))
            strategy = _esc(getattr(trade, "strategy", ""))
            entry_price = float(getattr(trade, "entry_price", 0.0) or 0.0)
            qty = int(getattr(trade, "quantity", 0) or getattr(trade, "qty", 0) or 0)
            sl = float(getattr(trade, "stop_loss", 0.0) or 0.0)
            target = float(getattr(trade, "target", 0.0) or 0.0)
            fees = float(getattr(trade, "fees", 0.0) or 0.0)
            option_type = ""
            strike = ""

        direction_emoji = "🟢" if "LONG" in direction.upper() or "BUY" in direction.upper() else "🔴"
        label = f"{option_type} {strike}" if option_type and strike else symbol
        invested = entry_price * qty

        lines = [
            f"{direction_emoji} <b>TRADE EXECUTED</b>",
            "",
            f"<b>Symbol:</b> {symbol} ({label})",
            f"<b>Direction:</b> {direction} | <b>Strategy:</b> {strategy}",
            f"<b>Entry Price:</b> {entry_price:.2f} x {qty} qty = {format_currency(invested)}",
            f"<b>Stop Loss:</b> {sl:.2f}  |  <b>Target:</b> {target:.2f}",
        ]
        if fees > 0:
            lines.append(f"<b>Estimated Fees:</b> {format_currency(fees)}")
        lines.append(f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S IST')}")

        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # 2. Partial Booking
    # ------------------------------------------------------------------

    async def send_partial_booking(
        self,
        position_or_data: Union[dict, Any],
        level: Optional[str] = None,
        qty: Optional[int] = None,
        price: Optional[float] = None,
    ) -> bool:
        """Send a partial booking profit-lock notification."""
        if isinstance(position_or_data, dict):
            symbol = _esc(position_or_data.get("symbol", "?"))
            direction = _esc(position_or_data.get("direction", "?"))
            entry_price = float(position_or_data.get("entry_price", 0.0) or 0.0)
            lvl_str = _esc(level or position_or_data.get("stage_name") or position_or_data.get("level") or "T1")
            booked_qty = int(qty if qty is not None else position_or_data.get("booked_qty") or position_or_data.get("qty") or 0)
            booked_price = float(price if price is not None else position_or_data.get("booked_price") or position_or_data.get("price") or 0.0)
            remaining_qty = int(position_or_data.get("remaining_qty", 0))
            pnl = float(position_or_data.get("pnl", 0.0))
        else:
            symbol = _esc(getattr(position_or_data, "symbol", "?"))
            direction = _esc(getattr(position_or_data, "direction", "?"))
            entry_price = float(getattr(position_or_data, "entry_price", 0.0) or 0.0)
            total_qty = int(getattr(position_or_data, "quantity", 0) or getattr(position_or_data, "qty", 0) or 0)
            lvl_str = _esc(level or "T1")
            booked_qty = min(int(qty or 0), total_qty) if qty else total_qty
            booked_price = float(price or 0.0)
            remaining_qty = max(0, total_qty - booked_qty)
            if entry_price > 0 and booked_price > 0:
                if "LONG" in direction.upper() or "BUY" in direction.upper():
                    pnl = (booked_price - entry_price) * booked_qty
                else:
                    pnl = (entry_price - booked_price) * booked_qty
            else:
                pnl = 0.0

        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        lines = [
            f"📦 <b>PARTIAL BOOKING – {lvl_str.upper()}</b>",
            "",
            f"<b>Symbol:</b> {symbol}  |  <b>Direction:</b> {direction}",
            f"<b>Booked:</b> {booked_qty} qty @ ₹{booked_price:.2f}",
            f"{pnl_emoji} <b>Realized P&amp;L:</b> {format_currency(pnl, show_sign=True)}",
            f"<b>Remaining:</b> {remaining_qty} qty (Entry: ₹{entry_price:.2f})",
            f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S IST')}",
        ]
        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # 3. Stop Loss Hit
    # ------------------------------------------------------------------

    async def send_sl_hit(self, trade: Union[dict, Any]) -> bool:
        """Send a stop-loss hit notification."""
        if isinstance(trade, dict):
            symbol = _esc(trade.get("symbol", "?"))
            direction = _esc(trade.get("direction", "?"))
            entry_price = float(trade.get("entry_price", 0.0) or 0.0)
            exit_price = float(trade.get("exit_price", 0.0) or 0.0)
            qty = int(trade.get("quantity") or trade.get("qty") or 1)
            strategy = _esc(trade.get("strategy", ""))
            pnl = float(trade.get("net_pnl") if trade.get("net_pnl") is not None else trade.get("pnl", 0.0))
            pnl_pct = float(trade.get("pnl_pct", 0.0))
        else:
            symbol = _esc(getattr(trade, "symbol", "?"))
            direction = _esc(getattr(trade, "direction", "?"))
            entry_price = float(getattr(trade, "entry_price", 0.0) or 0.0)
            exit_price = float(getattr(trade, "exit_price", 0.0) or 0.0)
            qty = int(getattr(trade, "quantity", 1) or getattr(trade, "qty", 1) or 1)
            strategy = _esc(getattr(trade, "strategy", ""))
            pnl = float(getattr(trade, "net_pnl", 0.0) or getattr(trade, "pnl", 0.0) or 0.0)
            pnl_pct = 0.0

        if pnl_pct == 0.0 and entry_price > 0 and qty > 0:
            invested = entry_price * qty
            pnl_pct = (pnl / invested) * 100

        lines = [
            f"⛔ <b>STOP LOSS HIT</b>",
            "",
            f"<b>Symbol:</b> {symbol}  |  <b>Direction:</b> {direction}",
            f"<b>Strategy:</b> {strategy}",
            f"<b>Entry:</b> ₹{entry_price:.2f} → <b>Exit:</b> ₹{exit_price:.2f}",
            f"🔴 <b>P&amp;L:</b> {format_currency(pnl, show_sign=True)} ({format_pct(pnl_pct)})",
            f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S IST')}",
        ]
        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # 4. Target Hit
    # ------------------------------------------------------------------

    async def send_target_hit(self, trade: Union[dict, Any]) -> bool:
        """Send a target hit notification."""
        if isinstance(trade, dict):
            symbol = _esc(trade.get("symbol", "?"))
            direction = _esc(trade.get("direction", "?"))
            entry_price = float(trade.get("entry_price", 0.0) or 0.0)
            exit_price = float(trade.get("exit_price", 0.0) or 0.0)
            target = float(trade.get("target", 0.0) or 0.0)
            qty = int(trade.get("quantity") or trade.get("qty") or 1)
            strategy = _esc(trade.get("strategy", ""))
            pnl = float(trade.get("net_pnl") if trade.get("net_pnl") is not None else trade.get("pnl", 0.0))
            pnl_pct = float(trade.get("pnl_pct", 0.0))
        else:
            symbol = _esc(getattr(trade, "symbol", "?"))
            direction = _esc(getattr(trade, "direction", "?"))
            entry_price = float(getattr(trade, "entry_price", 0.0) or 0.0)
            exit_price = float(getattr(trade, "exit_price", 0.0) or 0.0)
            target = float(getattr(trade, "target", 0.0) or 0.0)
            qty = int(getattr(trade, "quantity", 1) or getattr(trade, "qty", 1) or 1)
            strategy = _esc(getattr(trade, "strategy", ""))
            pnl = float(getattr(trade, "net_pnl", 0.0) or getattr(trade, "pnl", 0.0) or 0.0)
            pnl_pct = 0.0

        if pnl_pct == 0.0 and entry_price > 0 and qty > 0:
            invested = entry_price * qty
            pnl_pct = (pnl / invested) * 100

        lines = [
            f"🎯 <b>TARGET HIT</b>",
            "",
            f"<b>Symbol:</b> {symbol}  |  <b>Direction:</b> {direction}",
            f"<b>Strategy:</b> {strategy}",
            f"<b>Entry:</b> ₹{entry_price:.2f} → <b>Exit:</b> ₹{exit_price:.2f} (Target: ₹{target:.2f})",
            f"🟢 <b>P&amp;L:</b> {format_currency(pnl, show_sign=True)} ({format_pct(pnl_pct)})",
            f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S IST')}",
        ]
        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # 5. Risk Limit Warning
    # ------------------------------------------------------------------

    async def send_risk_alert(self, message: Union[str, dict], level: str = "WARNING") -> bool:
        """Send a risk warning alert."""
        if isinstance(message, dict):
            msg_text = _esc(message.get("message") or message.get("text") or str(message))
            rule_name = _esc(message.get("rule") or message.get("gate") or "")
        else:
            msg_text = _esc(message)
            rule_name = ""

        lines = [
            f"⚠️ <b>RISK LIMIT WARNING</b>",
            "",
            f"{msg_text}",
        ]
        if rule_name:
            lines.append(f"<b>Triggered Rule:</b> {rule_name}")
        lines.append(f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S IST')}")
        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # 6. Engine Status Change
    # ------------------------------------------------------------------

    async def send_engine_status(
        self,
        state: str,
        mode: str = "",
        broker: str = "",
        details: str = "",
    ) -> bool:
        """Send an engine lifecycle status change notification."""
        st_upper = state.upper()
        if st_upper in ("RUNNING", "STARTED"):
            emoji = "🟢"
            status_text = "ENGINE STARTED"
        elif st_upper in ("PAUSED", "PAUSING"):
            emoji = "🟡"
            status_text = "ENGINE PAUSED"
        elif st_upper in ("STOPPED", "STOPPING"):
            emoji = "🔴"
            status_text = "ENGINE STOPPED"
        elif st_upper in ("ERROR", "CRASHED"):
            emoji = "🚨"
            status_text = "ENGINE RUNTIME ERROR"
        else:
            emoji = "⚡"
            status_text = f"ENGINE STATUS: {st_upper}"

        lines = [
            f"{emoji} <b>{status_text}</b>",
            "",
            f"<b>State:</b> {st_upper}",
        ]
        if mode:
            lines.append(f"<b>Mode:</b> {_esc(mode.upper())}")
        if broker:
            lines.append(f"<b>Broker:</b> {_esc(broker)}")
        if details:
            lines.append(f"<b>Info:</b> {_esc(details)}")
        lines.append(f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S IST')}")

        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # 7. Error Alert
    # ------------------------------------------------------------------

    async def send_error_alert(self, error: Union[dict, str]) -> bool:
        """Send a critical system or runtime error alert."""
        if isinstance(error, str):
            error = {"what_happened": error, "error_type": "SystemError", "severity": "error"}

        error_type = _esc(error.get("error_type", "SystemError"))
        severity = _esc(error.get("severity", "error"))
        error_code = _esc(error.get("error_code", ""))
        what = _esc(error.get("what_happened") or error.get("message") or "")
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
            "",
        ]
        if error_code:
            lines.append(f"<b>Code:</b> {error_code}")
        if what:
            lines.append(f"<b>What:</b> {what}")
        if why:
            lines.append(f"<b>Why:</b> {why}")
        if how:
            lines.append(f"<b>Fix:</b> {how}")
        if context and isinstance(context, dict):
            ctx_str = "\n".join(f"  • {_esc(k)}: {_esc(v)}" for k, v in list(context.items())[:5])
            lines.append(f"<b>Context:</b>\n{ctx_str}")
        lines.append(f"<b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S IST')}")

        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # 8. EOD Report
    # ------------------------------------------------------------------

    async def send_eod_report(self, daily_summary: dict, trades: Optional[list] = None) -> bool:
        """Send end-of-day summary report."""
        trades = trades or []
        today_str = _esc(daily_summary.get("date") or datetime.now(IST).strftime("%d-%b-%Y"))
        net_pnl = float(daily_summary.get("net_pnl", 0.0))
        gross_pnl = float(daily_summary.get("gross_pnl", 0.0) or daily_summary.get("pnl", net_pnl))
        total_fees = float(daily_summary.get("total_fees", 0.0) or daily_summary.get("fees", 0.0))
        total_trades = int(daily_summary.get("total_trades", len(trades)))
        wins = int(daily_summary.get("wins", sum(1 for t in trades if getattr(t, "net_pnl", getattr(t, "pnl", 0)) > 0 if not isinstance(t, dict)) if trades else 0))
        losses = int(daily_summary.get("losses", total_trades - wins))
        win_rate = float(daily_summary.get("win_rate", ((wins / total_trades) * 100 if total_trades > 0 else 0.0)))
        best_trade = float(daily_summary.get("best_trade", 0.0))
        worst_trade = float(daily_summary.get("worst_trade", 0.0))

        pnl_emoji = "🟢" if net_pnl >= 0 else "🔴"

        lines = [
            f"📊 <b>EOD PERFORMANCE REPORT – {today_str}</b>",
            "",
            f"{pnl_emoji} <b>Net P&amp;L:</b> {format_currency(net_pnl, show_sign=True)}",
            f"   Gross P&amp;L: {format_currency(gross_pnl, show_sign=True)}  |  Total Fees: {format_currency(total_fees)}",
            "",
            f"<b>Total Trades:</b> {total_trades}  (✅ Wins: {wins}  ❌ Losses: {losses})",
            f"<b>Win Rate:</b> {win_rate:.1f}%",
        ]
        if best_trade != 0.0 or worst_trade != 0.0:
            lines.append(f"<b>Best Trade:</b> {format_currency(best_trade, show_sign=True)}  |  <b>Worst Trade:</b> {format_currency(worst_trade, show_sign=True)}")

        if trades:
            lines.append("")
            lines.append("<b>Trade Breakdown:</b>")
            for t in trades[:15]:
                if isinstance(t, dict):
                    sym = _esc(t.get("symbol", "?"))
                    t_pnl = float(t.get("net_pnl", t.get("pnl", 0.0)))
                    strat = _esc(t.get("strategy", ""))
                    status = _esc(t.get("status", ""))
                    direction = _esc(t.get("direction", ""))
                else:
                    sym = _esc(getattr(t, "symbol", "?"))
                    t_pnl = float(getattr(t, "net_pnl", getattr(t, "pnl", 0.0)))
                    strat = _esc(getattr(t, "strategy", ""))
                    status = _esc(getattr(t, "status", ""))
                    direction = _esc(getattr(t, "direction", ""))
                p_emoji = "🟢" if t_pnl >= 0 else "🔴"
                lines.append(f"  • {sym} {direction} [{strat}] → {p_emoji} {format_currency(t_pnl, show_sign=True)}")

        lines.append("")
        lines.append("<i>Trading session closed. Have a great evening!</i>")
        return await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # Morning Briefing
    # ------------------------------------------------------------------

    async def send_morning_briefing(self, watchlist: list, regime: str, vix: float) -> bool:
        """Send the morning briefing with watchlist, regime, and India VIX."""
        now = datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")

        lines = [
            f"🌅 <b>MORNING BRIEFING – {now}</b>",
            "",
            f"<b>Market Regime:</b> {_esc(regime)}",
            f"<b>India VIX:</b> {vix:.2f}",
            "",
            f"<b>Top Watchlist ({len(watchlist)} stocks):</b>",
        ]

        for item in watchlist[:15]:
            if isinstance(item, dict):
                sym = _esc(item.get("symbol", str(item)))
                reason = _esc(item.get("reason", ""))
                if reason:
                    lines.append(f"  • {sym} – {reason}")
                else:
                    lines.append(f"  • {sym}")
            else:
                lines.append(f"  • {_esc(item)}")

        lines.append("")
        lines.append("<i>UltraBot scan cycle active. Good luck!</i>")
        return await self.send_message("\n".join(lines))
