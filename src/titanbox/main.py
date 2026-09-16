from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from . import __version__
from .auth import admin_guard
from .runner import AppRunner
from .settings import Settings
from .system_metrics import snapshot
from .telegram import TelegramHub

settings = Settings.from_env()
settings.validate()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("titanbox")
runner = AppRunner(settings.apps_config)
hub = TelegramHub(settings, runner=runner)


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("TitanBox starting version=%s", __version__)
    await hub.start()
    if settings.enable_runner:
        await runner.start()
    try:
        yield
    finally:
        if settings.enable_runner:
            await runner.close()
        await hub.close()
        log.info("TitanBox stopped")


app = FastAPI(title="TitanBox", version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan)
admin = admin_guard(settings)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
async def root():
    return {
        "name": "TitanBox",
        "version": __version__,
        "mode": "ultra-light-paas-runtime",
        "bots": len(hub.bots),
        "runner_enabled": settings.enable_runner,
        "terminal_enabled": settings.enable_terminal,
    }


@app.get("/healthz")
async def healthz():
    return {"ok": True, **snapshot()}


@app.get("/readyz")
async def readyz():
    if settings.enable_runner and not runner.started:
        return JSONResponse(status_code=503, content={"ok": False, "reason": "runner_not_started"})
    return {"ok": True, "bots": len(hub.bots)}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    data = snapshot()
    lines = [
        "# HELP titanbox_up Whether the TitanBox process is alive.",
        "# TYPE titanbox_up gauge",
        "titanbox_up 1",
        f"titanbox_process_peak_rss_bytes {data['process_peak_rss_bytes']}",
        f"titanbox_uptime_seconds {data['uptime_seconds']}",
        f"titanbox_bot_count {len(hub.bots)}",
        f"titanbox_webhook_active_handlers {hub.active_handlers}",
        f"titanbox_webhook_handled_total {hub.total_handled}",
        f"titanbox_webhook_rejected_total {hub.total_rejected}",
    ]
    if data["cgroup_memory_current_bytes"] is not None:
        lines.append(f"titanbox_cgroup_memory_current_bytes {data['cgroup_memory_current_bytes']}")
    if data["cgroup_memory_limit_bytes"] is not None:
        lines.append(f"titanbox_cgroup_memory_limit_bytes {data['cgroup_memory_limit_bytes']}")
    return "\n".join(lines) + "\n"


@app.post("/telegram/{bot_name}")
async def telegram_webhook(bot_name: str, request: Request):
    return await hub.handle(bot_name, request)


@app.get("/admin/status", dependencies=[Depends(admin)])
async def admin_status():
    return {
        "system": snapshot(),
        "bots": hub.public_status(),
        "apps": runner.status() if settings.enable_runner else [],
    }


def _state_or_404(name: str):
    if name not in runner.states:
        raise HTTPException(status_code=404, detail="Unknown app")


@app.post("/admin/apps/{name}/start", dependencies=[Depends(admin)])
async def app_start(name: str):
    _state_or_404(name)
    return await runner.start_app(name)


@app.post("/admin/apps/{name}/stop", dependencies=[Depends(admin)])
async def app_stop(name: str):
    _state_or_404(name)
    return await runner.stop_app(name)


@app.post("/admin/apps/{name}/restart", dependencies=[Depends(admin)])
async def app_restart(name: str):
    _state_or_404(name)
    return await runner.restart_app(name)


@app.post("/admin/telegram/register-webhooks", dependencies=[Depends(admin)])
async def register_webhooks():
    if not settings.public_base_url:
        raise HTTPException(status_code=400, detail="PUBLIC_BASE_URL is not set")
    await hub.register_all_webhooks()
    return {"ok": True, "registered": len(hub.bots)}
