import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import get_current_user
from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# In-memory notification history (recent notifications sent via WebSocket/Telegram)
_notification_history: List[Dict[str, Any]] = []
_MAX_HISTORY = 200


def _add_notification_to_history(
    event_type: str,
    message: str,
    severity: str = "info",
    extra: Optional[Dict] = None,
) -> None:
    """Add a notification to the in-memory history."""
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")

    entry = {
        "id": f"notif-{len(_notification_history) + 1}",
        "event_type": event_type,
        "message": message,
        "severity": severity,
        "extra": extra or {},
        "created_at": datetime.now(IST).isoformat(),
    }
    _notification_history.append(entry)

    # Trim to max size
    while len(_notification_history) > _MAX_HISTORY:
        _notification_history.pop(0)


@router.get("/history")
async def get_notification_history(
    event_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    username: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get notification history."""
    try:
        history = list(_notification_history)

        # Filter by event type
        if event_type:
            history = [n for n in history if n.get("event_type") == event_type]

        total = len(history)
        history = history[offset:offset + limit]

        return {
            "notifications": history,
            "total": total,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get notification history: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get notification history: {str(exc)}",
        )


class NotificationSettingsUpdate(BaseModel):
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    sound_enabled: Optional[bool] = None
    desktop_enabled: Optional[bool] = None
    trade_fill_enabled: Optional[bool] = None
    trade_exit_enabled: Optional[bool] = None
    new_opportunity_enabled: Optional[bool] = None
    risk_alert_enabled: Optional[bool] = None
    error_alert_enabled: Optional[bool] = None
    scan_complete_enabled: Optional[bool] = None
    regime_change_enabled: Optional[bool] = None
    partial_booking_enabled: Optional[bool] = None


@router.put("/settings")
async def update_notification_settings(
    body: NotificationSettingsUpdate,
    username: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update notification settings."""
    try:
        update_data = body.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )

        # Separate secrets from non-secrets
        secrets = {}
        non_secrets = {}
        for key, value in update_data.items():
            if "token" in key:
                secrets[key] = value
            else:
                non_secrets[key] = value

        # Update non-secret settings in raw config
        notif_config = settings._raw_config.setdefault("notifications", {})
        notif_config.update(non_secrets)

        # Update secret settings in raw config (will be excluded from GET response)
        if secrets:
            notif_config.update(secrets)

        # Persist updated settings to defaults.yaml
        settings.save()

        return {
            "message": "Notification settings updated",
            "updated_keys": list(update_data.keys()),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update notification settings: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update notification settings: {str(exc)}",
        )


@router.post("/test")
async def send_test_notification(
    username: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """Send a test notification via Telegram."""
    try:
        notif_config = settings.get_notifications_config()
        bot_token = notif_config.get("telegram_bot_token", "")
        chat_id = notif_config.get("telegram_chat_id", "")

        if not bot_token or not chat_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Telegram not configured. Please set telegram_bot_token and telegram_chat_id in settings.",
            )

        # Send test message via Telegram Bot API
        import aiohttp
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": "🔔 UltraBot Web Test Notification\n\nThis is a test message to verify your Telegram integration is working correctly.\n\n- Engine: Online\n- Time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parse_mode": "HTML",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    result_data = await resp.json()
                    _add_notification_to_history(
                        event_type="test",
                        message="Test notification sent successfully",
                        severity="info",
                    )
                    return {
                        "message": "Test notification sent successfully",
                        "telegram_message_id": result_data.get("result", {}).get("message_id"),
                    }
                else:
                    error_text = await resp.text()
                    logger.warning("Telegram API error: %s %s", resp.status, error_text)
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Telegram API returned {resp.status}: {error_text}",
                    )
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="aiohttp not installed. Install with: pip install aiohttp",
        )
    except Exception as exc:
        logger.error("Failed to send test notification: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test notification: {str(exc)}",
        )
