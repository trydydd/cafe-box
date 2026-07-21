"""
main.py — Hearth admin backend entry point.

Start the server:
    HEARTH_SECRET_KEY=<secret> uvicorn main:app

The application is a FastAPI service that exposes:
  GET  /healthz                               → liveness check
  GET  /api/public/services/status            → unauthenticated service list
  POST /api/admin/login                       → issue session cookie
  POST /api/admin/logout                      → clear session cookie
  POST /api/admin/auth/change-password        → change admin password
  POST /api/admin/services/{id}/start         → start service
  POST /api/admin/services/{id}/stop          → stop service
  POST /api/admin/services/{id}/restart       → restart service
  POST /api/admin/upload/{service_id}         → upload content file
  GET  /api/admin/eink/status                 → e-ink display mode
  POST /api/admin/eink/logo                   → show logo on display
  POST /api/admin/eink/blank                  → clear display to white
"""

from fastapi import Depends, FastAPI

from csrf import verify_csrf_token
from routers import auth as auth_router
from routers import eink as eink_router
from routers import public as public_router
from routers import services as services_router
from routers import upload as upload_router

app = FastAPI(title="Hearth Admin API", version="0.1.0")

app.include_router(public_router.router)
app.include_router(auth_router.router)
app.include_router(services_router.router)
app.include_router(upload_router.router)
app.include_router(eink_router.router)


@app.get("/healthz", dependencies=[Depends(verify_csrf_token)])
async def healthz() -> dict:
    """Liveness check — returns HTTP 200 with {"status": "ok"}.

    The CSRF dependency ensures a ``csrf_token`` cookie is issued on the
    first request so that the front-end can include it in subsequent
    state-changing requests.
    """
    return {"status": "ok"}
