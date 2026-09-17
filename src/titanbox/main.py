from __future__ import annotations

import html
import logging

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from . import __version__
from .auth import admin_guard, secure_equal
from .runner import AppRunner
from .security import configure_logging
from .settings import Settings
from .system_metrics import snapshot
from .telegram import TelegramHub

settings = Settings.from_env()
settings.validate()
configure_logging(settings.log_level, extra_secrets=settings.known_secret_values())
log = logging.getLogger("titanbox")
runner = AppRunner(settings.apps_config)
hub = TelegramHub(settings, runner=runner)


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info(
        "TitanBox starting version=%s platform=%s public_url=%s",
        __version__,
        settings.platform,
        settings.public_base_url,
    )
    if settings.enable_runner:
        await runner.start()
    await hub.start()
    for warning in settings.setup_warnings():
        log.warning("setup warning: %s", warning)
    try:
        yield
    finally:
        await hub.close()
        if settings.enable_runner:
            await runner.close()
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
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
    )
    if settings.public_base_url and settings.public_base_url.startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if "server" in response.headers:
        del response.headers["server"]
    return response


def _safe(value: object) -> str:
    return html.escape(str(value), quote=True)


def _dashboard_html() -> str:
    warnings = settings.setup_warnings()
    states = hub.public_status(detailed=settings.public_status_details)
    if settings.public_status_details and states:
        rows_parts: list[str] = []
        for item in states:
            issue = item.get("startup_error") or item.get("last_webhook_error") or "-"
            rows_parts.append(
                "<tr>"
                f"<td>{_safe(item['name'])}</td>"
                f"<td>{'✅' if item['loaded'] else '❌'}</td>"
                f"<td>{'✅' if item['ready'] else '⚠️'}</td>"
                f"<td>{_safe(item.get('username') or '-')}</td>"
                f"<td>{_safe(issue)}</td>"
                "</tr>"
            )
        rows = "".join(rows_parts)
    elif states:
        rows = '<tr><td colspan="5">🔒 تفاصيل البوتات مخفية افتراضياً. استخدم Admin Bot أو Render logs.</td></tr>'
    else:
        rows = '<tr><td colspan="5">لا توجد بوتات محمّلة بعد.</td></tr>'
    if settings.public_status_details:
        warning_html = "".join(f"<li>{_safe(x)}</li>" for x in warnings) or "<li>لا توجد تحذيرات إعداد حالياً.</li>"
    else:
        warning_html = f"<li>عدد تنبيهات الإعداد: {len(warnings)} — التفاصيل مخفية.</li>"
    base = settings.public_base_url or "غير مكتشف"
    return f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TitanBox {__version__}</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;max-width:980px;margin:40px auto;padding:0 18px;background:#0b1020;color:#e9eefc}}
.card{{background:#151c32;border:1px solid #2a3559;border-radius:16px;padding:18px;margin:14px 0}}a{{color:#8fc7ff}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid #2a3559;text-align:right}}code{{direction:ltr;display:inline-block;background:#090d18;padding:3px 6px;border-radius:6px}}
.ok{{font-size:1.15rem}} .muted{{color:#aab5d6}}
</style></head><body>
<h1>🛡️ TitanBox <span class="muted">v{__version__}</span></h1>
<div class="card ok">✅ السيرفر شغال. هذه لوحة حالة عامة؛ التفاصيل الحساسة مخفية افتراضياً.</div>
<div class="card"><b>Platform:</b> {_safe(settings.platform)}<br><b>Public URL:</b> <code>{_safe(base)}</code><br><b>Configured bots:</b> {hub.configured_count}<br><b>Loaded bots:</b> {len(hub.bots)}</div>
<div class="card"><h3>حالة البوتات</h3><table><tr><th>الاسم</th><th>Loaded</th><th>Ready</th><th>Username</th><th>الحالة</th></tr>{rows}</table></div>
<div class="card"><h3>تنبيهات الإعداد</h3><ul>{warning_html}</ul></div>
<div class="card"><h3>روابط الفحص</h3><p><a href="/setup">/setup — خطوات الإعداد</a></p><p><a href="/status">/status — حالة عامة</a></p><p><a href="/healthz">/healthz — حياة السيرفر</a></p><p><a href="/readyz">/readyz — جاهزية البوتات</a></p></div>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(_dashboard_html())


@app.get("/setup", response_class=HTMLResponse)
async def setup_page():
    admin_ids = settings.deploy_admin_ids()
    current = "مضبوط" if admin_ids else "غير مضبوط بعد"
    base = settings.public_base_url or "غير مكتشف"
    body = f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TitanBox Setup</title>
<style>body{{font-family:system-ui;max-width:900px;margin:40px auto;padding:0 18px;line-height:1.8}}code,pre{{direction:ltr;background:#f3f4f7;padding:4px 7px;border-radius:6px;overflow:auto}}</style></head><body>
<h1>إعداد TitanBox v{__version__}</h1>
<p><b>الرابط المكتشف:</b> <code>{_safe(base)}</code></p>
<p><b>Admin IDs الحالية:</b> <code>{_safe(current)}</code></p>
<ol>
<li>Render → Environment: ضع Token الحقيقي داخل <code>DEPLOY_BOT_TOKEN</code>.</li>
<li>Webhook يسجل تلقائياً ويُراقب ذاتياً بواسطة Watchdog.</li>
<li>في Telegram أرسل <code>/start</code> ثم ضع رقمك داخل <code>DEPLOY_ADMIN_TELEGRAM_IDS</code>.</li>
<li>للإنتاج فعّل <code>DEPLOY_REQUIRE_2FA=true</code> وضع Base32 secret داخل <code>DEPLOY_TOTP_SECRET</code>.</li>
<li>استخدم <code>/security</code> و<code>/diag</code> للتأكد من الحماية والـWebhook.</li>
</ol>
<p><b>مهم:</b> Render Free filesystem مؤقت. GitHub/DB/Object Storage تبقى مصادر البيانات الدائمة.</p>
<p><b>العزل:</b> Ultra Mode يوفر عزل موارد منطقي فقط؛ العزل الأمني التام يحتاج Service/Container منفصل لكل Bot.</p>
<p><a href="/">← الرجوع</a></p></body></html>"""
    return HTMLResponse(body)


@app.get("/status")
async def public_status():
    return {
        "name": "TitanBox",
        "version": __version__,
        "platform": settings.platform,
        "configured_bots": hub.configured_count,
        "loaded_bots": len(hub.bots),
        "bots_ready": hub.all_ready(),
        "bots": hub.public_status(detailed=True) if settings.public_status_details else [],
        "runner_enabled": settings.enable_runner,
        "terminal_enabled": settings.enable_terminal,
        "warning_count": len(settings.setup_warnings()),
    }


@app.get("/healthz")
async def healthz():
    # Keep the public health probe intentionally minimal. Detailed process/container metrics are
    # available through the protected metrics/admin surfaces and /system in Deploy Admin.
    return {"ok": True, "version": __version__}


@app.get("/readyz")
async def readyz():
    reasons: list[str] = []
    if settings.enable_runner and not runner.started:
        reasons.append("runner_not_started")
    if not hub.all_ready():
        reasons.append("one_or_more_bots_not_ready")
    content = {
        "ok": not reasons,
        "bots": len(hub.bots),
        "configured_bots": hub.configured_count,
        "reasons": reasons,
        "bot_status": hub.public_status(detailed=True) if settings.public_status_details else [],
    }
    if reasons:
        return JSONResponse(status_code=503, content=content)
    return content


def _metrics_auth(authorization: str | None) -> None:
    if settings.metrics_public:
        return
    if not settings.admin_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secure_equal(token, settings.admin_token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics(authorization: str | None = Header(default=None)):
    _metrics_auth(authorization)
    data = snapshot()
    lines = [
        "# HELP titanbox_up Whether the TitanBox process is alive.",
        "# TYPE titanbox_up gauge",
        "titanbox_up 1",
        f"titanbox_process_peak_rss_bytes {data['process_peak_rss_bytes']}",
        f"titanbox_uptime_seconds {data['uptime_seconds']}",
        f"titanbox_bot_count {len(hub.bots)}",
        f"titanbox_bot_configured_count {hub.configured_count}",
        f"titanbox_bot_ready {1 if hub.all_ready() else 0}",
        f"titanbox_webhook_active_handlers {hub.active_handlers}",
        f"titanbox_webhook_handled_total {hub.total_handled}",
        f"titanbox_webhook_rejected_total {hub.total_rejected}",
    ]
    for item in hub.public_status(detailed=True):
        name = str(item["name"]).replace('"', "")
        lines.append(f'titanbox_bot_active_handlers{{bot="{name}"}} {item["active_handlers"]}')
        lines.append(f'titanbox_bot_handled_total{{bot="{name}"}} {item["total_handled"]}')
        lines.append(f'titanbox_bot_rejected_total{{bot="{name}"}} {item["total_rejected"]}')
        lines.append(f'titanbox_bot_circuit_open{{bot="{name}"}} {1 if item["circuit_open"] else 0}')
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
        "settings_warnings": settings.setup_warnings(),
        "bots": hub.public_status(detailed=True),
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
        raise HTTPException(status_code=400, detail="No public base URL could be detected")
    results = await hub.register_all_webhooks()
    return {"ok": hub.all_ready(), "results": results}


@app.post("/admin/telegram/{name}/refresh", dependencies=[Depends(admin)])
async def refresh_webhook(name: str):
    try:
        result = await hub.refresh_webhook_info(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result
