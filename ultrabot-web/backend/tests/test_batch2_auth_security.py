import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException
from api.dependencies import get_current_user, create_access_token
from api.routes.auth import revoke_token
from api.routes.risk import update_risk_limits, RiskLimitsUpdate
from api.websocket import websocket_endpoint
from config.settings import settings


@pytest.mark.asyncio
async def test_rest_token_revocation_enforcement():
    token = create_access_token({"sub": "admin_revoked_subject"})

    # Valid token works
    user = await get_current_user(token)
    assert user == "admin_revoked_subject"

    # Revoke token
    revoke_token(token)

    # Now get_current_user must reject with 401
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_websocket_mandatory_auth():
    ws_mock = AsyncMock()
    ws_mock.close = AsyncMock()

    # 1. Reject missing token
    await websocket_endpoint(ws_mock, token=None)
    ws_mock.close.assert_called_with(code=1008, reason="Authentication token required")

    # 2. Reject invalid token
    ws_mock.close.reset_mock()
    await websocket_endpoint(ws_mock, token="invalid-token-string")
    ws_mock.close.assert_called_with(code=1008, reason="Invalid token")

    # 3. Reject revoked token
    revoked = create_access_token({"sub": "ws_revoked_subject"})
    revoke_token(revoked)
    ws_mock.close.reset_mock()
    await websocket_endpoint(ws_mock, token=revoked)
    ws_mock.close.assert_called_with(code=1008, reason="Token revoked")


@pytest.mark.asyncio
async def test_risk_limits_update_section_routing(monkeypatch):
    body = RiskLimitsUpdate(
        kelly_max_fraction=0.08,
        hard_risk_pct=1.5,
        max_position_size_pct=10.0,
        vix_high_threshold=22.0,
    )

    from config.settings import Settings
    monkeypatch.setattr(Settings, "save", lambda self: True)
    res = await update_risk_limits(body=body, username="admin")
    assert res["message"] == "Risk limits updated successfully"

    # Verify position sizing config was updated
    pos_cfg = settings._raw_config.get("position_sizing", {})
    assert pos_cfg.get("kelly_max_fraction") == 0.08
    assert pos_cfg.get("hard_risk_pct") == 1.5

    # Verify risk config and key aliases
    risk_cfg = settings._raw_config.get("risk", {})
    assert risk_cfg.get("max_per_position_pct") == 10.0
    assert risk_cfg.get("vix_threshold") == 22.0

    # Verify capital config
    cap_cfg = settings._raw_config.get("capital", {})
    assert cap_cfg.get("max_per_position_pct") == 10.0
