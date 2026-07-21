"""
routers/eink.py — E-ink display control endpoints for the Hearth admin backend.

GET  /api/admin/eink/status   → {enabled, mode}  (session required)
POST /api/admin/eink/logo     → show logo + URL   (session + CSRF required)
POST /api/admin/eink/blank    → clear to white    (session + CSRF required)

The display has two systemd oneshot units:
  hearth-eink.service       — renders the Hearth logo and box URL
  hearth-eink-blank.service — sends an all-white frame to clear the screen

Switching modes stops the outgoing unit and restarts the incoming one so that
only one unit is ever active at a time, keeping status reporting unambiguous.
"""

import subprocess

from fastapi import APIRouter, Depends, HTTPException

from csrf import verify_csrf_token
from session import require_session

_LOGO_UNIT  = "hearth-eink.service"
_BLANK_UNIT = "hearth-eink-blank.service"

router = APIRouter(
    prefix="/api/admin/eink",
    dependencies=[Depends(require_session)],
)


def _unit_active(unit: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_systemctl(action: str, unit: str) -> None:
    result = subprocess.run(
        ["sudo", "systemctl", action, unit],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=result.stderr or f"systemctl {action} {unit} failed",
        )


@router.get("/status")
async def eink_status():
    """Return whether e-ink is enabled in config and the current display mode.

    Response shape::

        {"enabled": true, "mode": "logo"}

    ``mode`` is one of ``"logo"``, ``"blank"``, or ``"off"`` (neither unit active).
    """
    try:
        from config import load_config as _load_config
        cfg = _load_config(None)
    except FileNotFoundError:
        cfg = {}

    enabled: bool = cfg.get("eink", {}).get("enabled", False)

    if _unit_active(_BLANK_UNIT):
        mode = "blank"
    elif _unit_active(_LOGO_UNIT):
        mode = "logo"
    else:
        mode = "off"

    return {"enabled": enabled, "mode": mode}


@router.post("/logo", dependencies=[Depends(verify_csrf_token)])
async def eink_show_logo():
    """Render the Hearth logo and box URL on the e-ink display."""
    _run_systemctl("stop", _BLANK_UNIT)
    _run_systemctl("restart", _LOGO_UNIT)
    return {"mode": "logo"}


@router.post("/blank", dependencies=[Depends(verify_csrf_token)])
async def eink_show_blank():
    """Clear the e-ink display to all white."""
    _run_systemctl("stop", _LOGO_UNIT)
    _run_systemctl("restart", _BLANK_UNIT)
    return {"mode": "blank"}
