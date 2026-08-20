"""Alert manager – routes alerts to appropriate notification channels.

Central hub that receives typed alerts and dispatches them to Telegram,
WebSocket clients, and log outputs based on alert type and configuration.
"""
import logging
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# Mapping of alert_type -> TelegramBot method name
_TELEGRAM_METHODS = {
    "trade_fill": "send_trade_fill",
    "trade_exit": "send_sl_hit",          # exits route to SL/Target based on data
    "partial_booking": "send_partial_booking",
    "risk_event": "send_risk_alert",
    "error_alert": "send_error_alert",
    "engine_status": "send_message",       # plain text
    "regime_change": "send_message",
    "scan_complete": "send_message",
    "morning_briefing": "send_morning_briefing",
    "eod_report": "send_eod_report",
}


class AlertManager:
    """Route alerts to Telegram and/or WebSocket based on type and config.

    Args:
        telegram_bot: A TelegramBot instance (may have empty token).
        config: Notification config dict, expected to contain a
            ``telegram_enabled`` key (bool).
        ws_manager: Optional WebSocketManager for broadcasting to the
            web frontend.
    """

    def __init__(
        self,
        telegram_bot: Any,
        config: Dict[str, Any],
        ws_manager: Any = None,
    ):
        self.telegram_bot = telegram_bot
        self.config = config
        self.ws_manager = ws_manager
        self._last_alert_time: Dict[str, float] = {}
        self._rate_limit_seconds: float = float(config.get("alert_rate_limit_seconds", 1.0))

    async def route_alert(self, alert_type: str, data: dict) -> bool:
        """Route an alert to all enabled channels with rate-limiting.

        Args:
            alert_type: One of the keys in ``_TELEGRAM_METHODS``.
            data: Payload dict specific to the alert type.

        Returns:
            True if at least one channel accepted the alert.
        """
        sent_any = False
        telegram_enabled = bool(self.config.get("telegram_enabled", False))

        # Check rate limit for repetitive error alerts
        if alert_type == "error_alert":
            err_key = f"{alert_type}:{data.get('error_code', 'generic')}"
            now = time.time()
            if now - self._last_alert_time.get(err_key, 0) < self._rate_limit_seconds:
                logger.debug("Alert rate limited for %s", err_key)
                return False
            self._last_alert_time[err_key] = now

        # ---- Telegram channel ----
        if telegram_enabled and self.telegram_bot is not None:
            sent_telegram = await self._send_telegram(alert_type, data)
            if sent_telegram:
                sent_any = True

        # ---- WebSocket channel (best-effort) ----
        if self.ws_manager is not None:
            sent_ws = await self._send_websocket(alert_type, data)
            if sent_ws:
                sent_any = True

        # ---- Log channel (always) ----
        self._log_alert(alert_type, data)

        return sent_any

    # ------------------------------------------------------------------
    # Internal dispatchers
    # ------------------------------------------------------------------

    async def _send_telegram(self, alert_type: str, data: dict) -> bool:
        """Dispatch to the appropriate TelegramBot method."""
        method_name = _TELEGRAM_METHODS.get(alert_type)
        if method_name is None:
            logger.debug("No Telegram handler for alert type '%s'", alert_type)
            return False

        method = getattr(self.telegram_bot, method_name, None)
        if method is None:
            logger.warning("TelegramBot has no method '%s'", method_name)
            return False

        try:
            if alert_type in ("trade_exit", "trade_fill", "partial_booking"):
                # These methods take structured args, not just a dict.
                # Build a text wrapper when data is plain.
                return await method(data)
            elif alert_type == "morning_briefing":
                watchlist = data.get("watchlist", [])
                regime = data.get("regime", "Unknown")
                vix = float(data.get("vix", 0))
                return await method(watchlist, regime, vix)
            elif alert_type == "eod_report":
                summary = data.get("daily_summary", data)
                trades = data.get("trades", [])
                return await method(summary, trades)
            elif alert_type == "risk_event":
                message = data.get("message", str(data))
                return await method(message)
            elif alert_type == "error_alert":
                return await method(data)
            else:
                # engine_status, regime_change, scan_complete – plain text
                text = data.get("text", str(data))
                return await method(text)
        except Exception as exc:
            logger.error("Telegram send failed for '%s': %s", alert_type, exc)
            return False

    async def _send_websocket(self, alert_type: str, data: dict) -> bool:
        """Broadcast alert payload to all connected WebSocket clients."""
        try:
            payload = {
                "type": alert_type,
                "data": data,
            }
            await self.ws_manager.broadcast(alert_type, payload)
            return True
        except Exception as exc:
            logger.debug("WebSocket broadcast failed for '%s': %s", alert_type, exc)
            return False

    @staticmethod
    def _log_alert(alert_type: str, data: dict) -> None:
        """Write alert to the application logger."""
        if alert_type in ("error_alert", "risk_event"):
            logger.warning("[%s] %s", alert_type, data)
        else:
            logger.info("[%s] %s", alert_type, data)
