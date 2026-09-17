from __future__ import annotations

import asyncio
import logging
import shlex
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from titanbox.audit import AuditLog
from titanbox.deploy import DeployError, DeployLimits, DeploymentManager
from titanbox.security import TokenBucket, verify_totp
from titanbox.system_metrics import memory_pressure_pct, snapshot

log = logging.getLogger("titanbox.deploy_admin")


HELP_TEXT = """TitanBox Deploy Admin 🛡️🚀

هذا البوت مخصص للإدارة فقط.

الفحص والأمان:
/whoami — Telegram numeric ID وحالة الصلاحية
/diag — Token/Webhook/Pending updates
/system — RAM/Uptime/Memory pressure
/security — حالة 2FA/Audit/Storage
/infra — فحص Object Storage + Database
/setup — خطوات تفعيل التخزين/DB بدون كشف أسرار
/wake — رابط فحص/إيقاظ الخدمة عند الطلب
/auth 123456 — فتح جلسة 2FA مؤقتة للأوامر الخطرة
/lock — إغلاق جلسة 2FA فوراً
/audit [N] — آخر عمليات الإدارة
/jobs [N] — آخر العمليات الدائمة (إذا PostgreSQL مفعلة)

إدارة المشاريع:
/projects — عرض المشاريع
/use NAME — اختيار مشروع افتراضي
/status [NAME] — حالة المشروع
/files [NAME] [PREFIX] — عرض الملفات
/releases [NAME] — عرض النسخ المحلية
/backups [NAME] — عرض النسخ الدائمة الخارجية
/restore NAME [RELEASE|latest] — استعادة نسخة دائمة بعد التحقق
/restart [NAME] — Restart إذا كان المشروع مربوطاً بالـRunner
/rollback [NAME] [RELEASE] — رجوع لنسخة محلية سابقة

رفع مشروع كامل:
أرسل ZIP واكتب في Caption:
/deploy mybot

تحديث/إضافة ملف واحد:
أرسل الملف واكتب في Caption:
/put mybot path/to/file.py

الوضع الذكي:
/use mybot
ثم أرسل ملفاً بلا Caption؛ إذا كان الاسم فريداً داخل المشروع يتم إنشاء Release جديدة قابلة للـRollback.
"""


class _JobBotProxy:
    """Keep notification failures from replaying an already-committed admin side effect.

    For persistent jobs, Telegram messages are best-effort notifications. File downloads and
    other BotContext operations still propagate errors so the job can retry safely before a
    deployment side effect is committed.
    """

    def __init__(self, bot: Any):
        self._bot = bot
        self.name = getattr(bot, "name", "deploy-admin")

    async def send_message(self, chat_id: int | str, text: str, **extra: Any) -> Any:
        try:
            return await self._bot.send_message(chat_id, text, **extra)
        except Exception as exc:
            log.warning("persistent-job notification failed type=%s", type(exc).__name__)
            return {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._bot, name)


class DeployAdminPlugin:
    def __init__(self) -> None:
        self.manager: DeploymentManager | None = None
        self.audit: AuditLog | None = None
        self.admin_ids: set[int] = set()
        self.max_upload_bytes = 0
        self.active_project: dict[int, str] = {}
        self._op_slots = asyncio.Semaphore(1)
        self._tasks: set[asyncio.Task[None]] = set()
        self.public_base_url: str | None = None
        self.platform = "generic"
        self.storage_persistent = False
        self.require_2fa = False
        self.totp_secret: str | None = None
        self.twofa_session_seconds = 300
        self._auth_until: dict[int, float] = {}
        self._last_totp_counter: dict[int, int] = {}
        self._admin_limiters: dict[int, TokenBucket] = {}
        self.admin_rate_per_minute = 60
        self.admin_rate_burst = 15
        self.control_plane_only = False
        self.max_bots_per_runtime = 0
        self.infrastructure: Any | None = None
        self._bot_context: Any | None = None
        self._job_worker_task: asyncio.Task[None] | None = None
        self._job_wakeup = asyncio.Event()

    def bind_services(self, services: "PluginServices") -> None:
        settings = services.settings
        limits = DeployLimits(
            max_upload_bytes=settings.deploy_max_upload_bytes,
            max_archive_files=settings.deploy_max_archive_files,
            max_extracted_bytes=settings.deploy_max_extracted_bytes,
            keep_releases=settings.deploy_keep_releases,
            stabilize_seconds=float(settings.deploy_stabilize_seconds),
            restart_timeout_seconds=float(settings.deploy_restart_timeout_seconds),
        )
        self.infrastructure = services.infrastructure
        self._bot_context = services.bot_context
        durable_store = getattr(self.infrastructure, "releases", None) if self.infrastructure is not None else None
        self.manager = DeploymentManager(
            settings.deploy_root,
            limits,
            runner=services.runner,
            durable_store=durable_store,
            durability_required=settings.durability_required,
        )
        self.audit = AuditLog(settings.audit_log_path, settings.audit_hmac_key, settings.audit_max_bytes)
        self.admin_ids = settings.deploy_admin_ids()
        self.max_upload_bytes = settings.deploy_max_upload_bytes
        self.public_base_url = settings.public_base_url
        self.platform = settings.platform
        self.storage_persistent = bool(durable_store and durable_store.enabled)
        self.require_2fa = settings.deploy_require_2fa
        self.totp_secret = settings.deploy_totp_secret
        self.twofa_session_seconds = settings.deploy_2fa_session_seconds
        self.admin_rate_per_minute = settings.deploy_admin_rate_per_minute
        self.admin_rate_burst = settings.deploy_admin_rate_burst
        self.control_plane_only = settings.control_plane_only
        self.max_bots_per_runtime = settings.max_bots_per_runtime
        self._op_slots = asyncio.Semaphore(settings.deploy_max_concurrent_ops)

    @property
    def _database(self) -> Any | None:
        return getattr(self.infrastructure, "database", None) if self.infrastructure is not None else None

    @property
    def _persistent_jobs_enabled(self) -> bool:
        database = self._database
        return bool(database is not None and database.enabled)

    async def start(self) -> None:
        if self._persistent_jobs_enabled and self._bot_context is not None and self._job_worker_task is None:
            self._job_worker_task = asyncio.create_task(self._job_worker(), name="deploy-admin:persistent-job-worker")
            self._job_wakeup.set()

    async def _enqueue_job(
        self,
        kind: str,
        unique_key: str,
        payload: dict[str, Any],
        chat_id: int | str,
        bot: "BotContext",
    ) -> bool:
        database = self._database
        if database is None or not database.enabled:
            return False
        job = await database.enqueue_job(unique_key, kind, payload, max_attempts=5)
        self._job_wakeup.set()
        await bot.send_message(
            chat_id,
            f"🧾 تم تثبيت العملية في PostgreSQL قبل التنفيذ — Job #{job.get('id')} ({job.get('state')}).",
        )
        return True

    async def _jobs_status(self, chat_id: int | str, parts: list[str], bot: "BotContext") -> None:
        database = self._database
        if database is None or not database.enabled:
            await bot.send_message(chat_id, "⚪️ Persistent job queue غير مفعلة. فعّل POSTGRES_DSN أولاً.")
            return
        limit = 10
        if len(parts) >= 2:
            try:
                limit = min(max(1, int(parts[1])), 30)
            except ValueError as exc:
                raise DeployError("الاستخدام: /jobs 10") from exc
        jobs = await database.recent_jobs(limit)
        lines: list[str] = []
        for item in jobs:
            err = str(item.get("last_error") or "")
            if len(err) > 80:
                err = err[:77] + "..."
            lines.append(
                f"• #{item.get('id')} {item.get('kind')} — {item.get('state')} "
                f"attempts={item.get('attempts')}/{item.get('max_attempts')}"
                + (f" — {err}" if err else "")
            )
        await self._send_chunks(bot, chat_id, "🧾 Persistent jobs:", lines or ["لا توجد Jobs."])

    async def _job_worker(self) -> None:
        database = self._database
        bot = self._bot_context
        if database is None or not database.enabled or bot is None:
            return
        kinds = ("document", "rollback", "restart", "restore")
        while True:
            try:
                job = await database.claim_job(kinds, lease_seconds=600)
                if job is None:
                    self._job_wakeup.clear()
                    try:
                        await asyncio.wait_for(self._job_wakeup.wait(), timeout=15.0)
                    except TimeoutError:
                        pass
                    continue
                await self._process_job(job, bot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("persistent job worker loop error type=%s", type(exc).__name__)
                await asyncio.sleep(2)

    async def _process_job(self, job: dict[str, Any], bot: "BotContext") -> None:
        database = self._database
        if database is None:
            return
        job_id = int(job.get("id") or 0)
        payload = job.get("payload") or {}
        kind = str(job.get("kind") or "")
        actor_id = payload.get("actor_id")
        chat_id = payload.get("chat_id")
        if not isinstance(actor_id, int) or actor_id not in self.admin_ids or not isinstance(chat_id, (int, str)):
            await database.fail_job(job_id, "admin is no longer authorized", retry=False)
            return
        # Once a persistent job starts mutating deployment state, Telegram notification
        # failures must not cause the whole job to replay. Use a proxy that treats only
        # send_message() as best-effort; download_file/API failures still propagate.
        job_bot = _JobBotProxy(bot)
        try:
            if kind == "document":
                message = payload.get("message")
                if not isinstance(message, dict):
                    raise DeployError("Persistent document job payload is invalid.")
                await self._handle_document(
                    actor_id, chat_id, message, job_bot, preauthorized=True, operation_id=str(job.get("unique_key") or f"job-{job_id}")
                )
            elif kind == "rollback":
                await self._do_rollback(
                    str(payload["project"]),
                    payload.get("release"),
                    chat_id,
                    job_bot,
                    idempotent=True,
                    operation_id=str(job.get("unique_key") or f"job-{job_id}"),
                )
            elif kind == "restart":
                await self._do_restart(str(payload["project"]), chat_id, job_bot)
            elif kind == "restore":
                await self._do_restore(
                    str(payload["project"]),
                    str(payload.get("release") or "latest"),
                    chat_id,
                    job_bot,
                    operation_id=str(job.get("unique_key") or f"job-{job_id}"),
                )
            else:
                raise DeployError("Unknown persistent job kind.")
            await database.complete_job(job_id)
        except DeployError as exc:
            await database.fail_job(job_id, str(exc), retry=False)
            try:
                await bot.send_message(chat_id, f"❌ Job #{job_id} فشل: {exc}")
            except Exception:
                pass
        except Exception as exc:
            attempts = int(job.get("attempts") or 1)
            delay = min(60, 2 ** min(attempts, 5))
            state = await database.fail_job(
                job_id,
                f"{type(exc).__name__}: {str(exc)[:300]}",
                retry=True,
                retry_delay_seconds=delay,
            )
            log.exception("persistent job failed id=%s kind=%s next_state=%s", job_id, kind, state)
            if state == "failed":
                try:
                    await bot.send_message(chat_id, f"❌ Job #{job_id} فشل بعد عدة محاولات. راجع /jobs و /infra.")
                except Exception:
                    pass

    def _limiter(self, user_id: int) -> TokenBucket:
        limiter = self._admin_limiters.get(user_id)
        if limiter is None:
            limiter = TokenBucket(self.admin_rate_per_minute, self.admin_rate_burst)
            self._admin_limiters[user_id] = limiter
        return limiter

    async def _mirror_audit(self, record: dict[str, Any]) -> None:
        database = getattr(self.infrastructure, "database", None) if self.infrastructure is not None else None
        if database is None or not database.enabled:
            return
        try:
            await database.append_audit(record)
        except Exception as exc:
            # Audit mirroring must never break the administrative action that was already
            # locally recorded. /infra will expose DB health separately.
            log.warning("database audit mirror failed type=%s", type(exc).__name__)

    def _audit(
        self,
        action: str,
        actor_id: int | None,
        result: str,
        *,
        project: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if self.audit is None:
            return
        record = self.audit.append(action=action, actor_id=actor_id, result=result, project=project, detail=detail)
        database = getattr(self.infrastructure, "database", None) if self.infrastructure is not None else None
        if database is None or not database.enabled:
            return
        try:
            task = asyncio.create_task(self._mirror_audit(record), name="deploy-admin:audit-mirror")
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _twofa_active(self, user_id: int) -> bool:
        if not self.require_2fa:
            return True
        return time.monotonic() < self._auth_until.get(user_id, 0.0)

    def _require_privileged(self, user_id: int) -> None:
        if not self.require_2fa:
            return
        if not self.totp_secret:
            raise DeployError(
                "2FA مطلوب لكنه غير مضبوط. أضف DEPLOY_TOTP_SECRET في Render قبل تنفيذ أوامر التعديل."
            )
        if not self._twofa_active(user_id):
            raise DeployError("هذا أمر حساس. افتح جلسة حماية أولاً: /auth 123456 ثم أعد الأمر.")

    def _spawn_operation(
        self,
        coroutine: Any,
        chat_id: int | str,
        bot: "BotContext",
        *,
        actor_id: int,
        action: str,
        project: str | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._run_operation(coroutine, chat_id, bot, actor_id=actor_id, action=action, project=project),
            name=f"deploy-admin:{action}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_operation(
        self,
        coroutine: Any,
        chat_id: int | str,
        bot: "BotContext",
        *,
        actor_id: int,
        action: str,
        project: str | None,
    ) -> None:
        try:
            async with self._op_slots:
                await coroutine
            self._audit(action, actor_id, "success", project=project)
        except DeployError as exc:
            self._audit(action, actor_id, "denied_or_failed", project=project, detail={"error": str(exc)[:200]})
            await bot.send_message(chat_id, f"❌ {exc}")
        except asyncio.CancelledError:
            self._audit(action, actor_id, "cancelled", project=project)
            raise
        except Exception as exc:
            self._audit(action, actor_id, "error", project=project, detail={"type": type(exc).__name__})
            log.exception("unexpected background deployment failure action=%s project=%s", action, project)
            await bot.send_message(chat_id, "❌ حدث خطأ داخلي أثناء العملية. لم يتم اعتماد تحديث غير مكتمل.")

    async def close(self) -> None:
        if self._job_worker_task is not None:
            self._job_worker_task.cancel()
            await asyncio.gather(self._job_worker_task, return_exceptions=True)
            self._job_worker_task = None
        if not self._tasks:
            return
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    @staticmethod
    def _actor(update: dict[str, Any]) -> tuple[int | None, int | str | None, dict[str, Any] | None]:
        # Administrative actions intentionally accept only fresh private messages. Edited
        # messages/callbacks cannot mutate an old harmless message into a deployment command.
        message = update.get("message")
        if not isinstance(message, dict):
            return None, None, None
        sender = message.get("from") or {}
        chat = message.get("chat") or {}
        user_id = sender.get("id")
        return (user_id if isinstance(user_id, int) else None, chat.get("id"), message)

    @staticmethod
    def _command_parts(text: str) -> list[str]:
        try:
            parts = shlex.split(text.strip())
        except ValueError:
            return []
        if parts:
            parts[0] = parts[0].split("@", 1)[0].lower()
        return parts

    def _pick_project(self, user_id: int, explicit: str | None = None) -> str:
        assert self.manager is not None
        if explicit:
            project = self.manager.validate_project_name(explicit)
            self.active_project[user_id] = project
            return project
        active = self.active_project.get(user_id)
        if active:
            return active
        projects = self.manager.list_projects()
        if len(projects) == 1:
            project = str(projects[0]["name"])
            self.active_project[user_id] = project
            return project
        raise DeployError("حدد المشروع أولاً: /use PROJECT أو اذكر اسمه مع الأمر.")

    def _canonical_persistent_document(self, user_id: int, message: dict[str, Any]) -> dict[str, Any]:
        """Resolve volatile smart-upload state before persisting a document job.

        A queued job can run after a restart, so it must not depend on the in-memory `/use`
        selection. Persist an explicit `/deploy PROJECT` or `/put PROJECT PATH` operation and
        only the small Telegram file reference fields needed to download it later.
        """
        assert self.manager is not None
        document = message.get("document")
        if not isinstance(document, dict):
            raise DeployError("Telegram document payload is invalid.")
        file_id = document.get("file_id")
        if not isinstance(file_id, str) or not file_id:
            raise DeployError("Telegram document has no file_id.")
        filename = self.manager.safe_filename(str(document.get("file_name") or "upload.bin"))
        declared = document.get("file_size")
        if isinstance(declared, int) and declared > self.max_upload_bytes:
            raise DeployError(f"الملف أكبر من الحد المسموح ({self.max_upload_bytes} bytes).")

        caption = str(message.get("caption") or "").strip()
        parts = self._command_parts(caption) if caption.startswith("/") else []
        if caption.startswith("/") and not parts:
            raise DeployError("Caption غير صالح.")

        if parts:
            if parts[0] == "/deploy":
                if len(parts) != 2:
                    raise DeployError("Caption الصحيح: /deploy PROJECT")
                project = self._pick_project(user_id, parts[1])
                if not filename.lower().endswith(".zip"):
                    raise DeployError("/deploy يحتاج ملف ZIP.")
                canonical_caption = f"/deploy {shlex.quote(project)}"
            elif parts[0] == "/put":
                if len(parts) != 3:
                    raise DeployError("Caption الصحيح: /put PROJECT path/to/file.ext")
                project = self._pick_project(user_id, parts[1])
                target = self.manager.validate_relative_path(parts[2]).as_posix()
                canonical_caption = f"/put {shlex.quote(project)} {shlex.quote(target)}"
            else:
                raise DeployError("Caption الملف الإداري يجب أن يكون /deploy أو /put فقط.")
        else:
            project = self._pick_project(user_id)
            if filename.lower().endswith(".zip"):
                raise DeployError(f"الملف ZIP. للنشر الكامل أعد إرساله مع Caption: /deploy {project}")
            matches = self.manager.find_by_basename(project, filename)
            if len(matches) == 1:
                target = matches[0]
                canonical_caption = f"/put {shlex.quote(project)} {shlex.quote(target)}"
            elif len(matches) > 1:
                choices = "\n".join(f"• {x}" for x in matches)
                raise DeployError(
                    "اسم الملف موجود بأكثر من مكان. أعد إرسال الملف مع المسار الكامل:\n"
                    f"/put {project} path/to/{filename}\n\nالمطابقات:\n{choices}"
                )
            else:
                raise DeployError(
                    f"الملف {filename} جديد وما أگدر أخمن مكانه. أعد إرساله مع Caption:\n"
                    f"/put {project} assets/{filename}"
                )

        safe_document: dict[str, Any] = {"file_id": file_id, "file_name": filename}
        if isinstance(declared, int):
            safe_document["file_size"] = declared
        file_unique_id = document.get("file_unique_id")
        if isinstance(file_unique_id, str) and file_unique_id:
            safe_document["file_unique_id"] = file_unique_id[:200]
        return {"document": safe_document, "caption": canonical_caption}

    def _resolve_rollback_target(self, project: str, release: str | None) -> str:
        """Freeze rollback intent to an explicit release before a persistent job is queued."""
        assert self.manager is not None
        releases = self.manager.release_names(project)
        current = self.manager.current_release_name(project)
        if not releases or current is None:
            raise DeployError("Project has no releases to roll back.")
        if release is not None:
            if release not in releases:
                raise DeployError("Requested release does not exist.")
            if release == current:
                raise DeployError("Requested release is already active.")
            return release
        candidates = [name for name in releases if name != current]
        if not candidates:
            raise DeployError("No previous release exists.")
        return candidates[0]

    async def _resolve_restore_target(self, project: str, release: str) -> str:
        """Freeze `latest` to one exact durable release so retries cannot drift."""
        assert self.manager is not None
        if release not in {"", "latest"}:
            return release
        backups = await self.manager.list_backups(project, limit=1)
        if not backups:
            raise DeployError("No active durable backup exists for this project.")
        return backups[0]

    async def _send_chunks(self, bot: "BotContext", chat_id: int | str, heading: str, lines: list[str]) -> None:
        chunk = heading
        for line in lines:
            candidate = f"{chunk}\n{line}"
            if len(candidate) > 3800:
                await bot.send_message(chat_id, chunk)
                chunk = line
            else:
                chunk = candidate
        if chunk:
            await bot.send_message(chat_id, chunk)

    def _persistence_warning(self) -> str:
        if self.storage_persistent:
            return "\n☁️ Durable release backup: enabled."
        if self.platform == "render":
            return "\n⚠️ Render local storage is ephemeral. Enable S3-compatible durable storage before relying on uploaded releases."
        return ""

    async def _whoami(self, user_id: int, chat_id: int | str, bot: "BotContext") -> None:
        authorized = user_id in self.admin_ids
        status = "✅ مصرح" if authorized else "⛔ غير مصرح بعد"
        text = f"Telegram numeric ID: `{user_id}`\nStatus: {status}\n\n"
        if authorized and self.require_2fa:
            text += f"2FA session: {'✅ مفتوحة' if self._twofa_active(user_id) else '🔒 مقفلة'}\n"
        if not authorized:
            text += (
                "حتى تفعل الإدارة: Render → Environment → "
                f"DEPLOY_ADMIN_TELEGRAM_IDS={user_id} ثم Save/Redeploy.\n"
                "ما تم تنفيذ أي صلاحية إدارية."
            )
        await bot.send_message(chat_id, text, parse_mode="Markdown")

    async def _diag(self, user_id: int, chat_id: int | str, bot: "BotContext") -> None:
        me = await bot.get_me()
        info = await bot.get_webhook_info()
        username = me.get("username") or "-"
        url = info.get("url") or "-"
        pending = info.get("pending_update_count", 0)
        last_error = info.get("last_error_message") or "-"
        expected = f"{self.public_base_url}/telegram/{bot.name}" if self.public_base_url else "غير مكتشف"
        match = "✅" if url == expected else "⚠️"
        await bot.send_message(
            chat_id,
            "🧪 TitanBox diagnostics\n"
            f"Admin ID: {user_id}\n"
            f"Bot: @{username}\n"
            f"Public base URL: {self.public_base_url or '-'}\n"
            f"Expected webhook: {expected}\n"
            f"Telegram webhook: {url} {match}\n"
            f"Pending updates: {pending}\n"
            f"Last Telegram error: {last_error}\n"
            f"2FA: {'required' if self.require_2fa else 'optional/off'}"
            f"{self._persistence_warning()}",
        )

    async def _system(self, chat_id: int | str, bot: "BotContext") -> None:
        data = snapshot()
        pressure = memory_pressure_pct()
        limit = data.get("cgroup_memory_limit_bytes")
        current = data.get("cgroup_memory_current_bytes")
        await bot.send_message(
            chat_id,
            "🖥 TitanBox system\n"
            f"Uptime: {int(float(data['uptime_seconds']))}s\n"
            f"Process peak RSS: {int(data['process_peak_rss_bytes']) // (1024 * 1024)} MiB\n"
            f"Container memory: {int(current) // (1024 * 1024) if isinstance(current, int) else '-'} / "
            f"{int(limit) // (1024 * 1024) if isinstance(limit, int) else '-'} MiB\n"
            f"Memory pressure: {f'{pressure:.1f}%' if pressure is not None else '-'}",
        )

    async def _security(self, user_id: int, chat_id: int | str, bot: "BotContext") -> None:
        audit_ok = self.audit.verify() if self.audit else False
        twofa_configured = bool(self.totp_secret)
        await bot.send_message(
            chat_id,
            "🛡️ Security status\n"
            f"Admin allowlist: ✅ ({len(self.admin_ids)} admin)\n"
            f"2FA required: {'✅' if self.require_2fa else '⚠️ لا'}\n"
            f"2FA secret configured: {'✅' if twofa_configured else '❌'}\n"
            f"Current 2FA session: {'✅ مفتوحة' if self._twofa_active(user_id) else '🔒 مقفلة'}\n"
            f"Audit chain: {'✅ سليمة' if audit_ok else '⚠️ غير متاحة/غير سليمة'}\n"
            f"Persistent deploy storage: {'✅' if self.storage_persistent else '⚠️ لا'}\n"
            f"Control-plane-only: {'✅' if self.control_plane_only else '⚠️ لا'}\n"
            f"Max bots/runtime: {self.max_bots_per_runtime or 'unlimited'}\n"
            "ملاحظة: العزل الأمني التام بين البوتات يحتاج Service/Container مستقل لكل Bot.",
        )

    async def _infra(self, chat_id: int | str, bot: "BotContext") -> None:
        if self.infrastructure is None:
            await bot.send_message(chat_id, "Infrastructure manager غير مربوط.")
            return
        health = await self.infrastructure.health()
        storage = health.get("storage") or {}
        database = health.get("database") or {}

        def line(label: str, value: dict[str, Any]) -> str:
            enabled = bool(value.get("enabled"))
            if not enabled:
                return f"{label}: ⚪️ غير مفعّل"
            state = "✅" if value.get("ok") else "❌"
            latency = value.get("latency_ms")
            suffix = f" — {latency}ms" if latency is not None else ""
            error = str(value.get("error") or "")
            if error:
                error = f" — {error[:120]}"
            return f"{label}: {state}{suffix}{error}"

        await bot.send_message(
            chat_id,
            "🧱 Infrastructure\n"
            + line("Object Storage", storage)
            + "\n"
            + line("PostgreSQL", database)
            + f"\nDurability required: {'✅' if health.get('durability_required') else 'لا'}"
            + f"\nDatabase required: {'✅' if health.get('database_required') else 'لا'}",
        )

    async def _setup_guide(self, chat_id: int | str, bot: "BotContext") -> None:
        storage_enabled = bool(self.infrastructure and getattr(self.infrastructure, "releases", None) and self.infrastructure.releases.enabled)
        database_enabled = bool(self._database and self._database.enabled)
        lines = [
            "🧭 TitanBox setup — بدون عرض أي Secret",
            f"Object Storage: {'✅ مفعّل' if storage_enabled else '⚪️ غير مفعّل'}",
            f"PostgreSQL: {'✅ مفعّل' if database_enabled else '⚪️ غير مفعّل'}",
            f"2FA: {'✅ مطلوب' if self.require_2fa else '⚠️ غير مفروض'}",
            "",
            "للتخزين الدائم أضف في Render Environment:",
            "STORAGE_BACKEND=s3",
            "S3_ENDPOINT_URL / S3_REGION / S3_BUCKET",
            "S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY",
            "ملاحظة: RELEASE_SIGNING_KEY يولده Blueprint تلقائياً.",
            "",
            "لـPostgreSQL أضف:",
            "POSTGRES_DSN=postgresql://...",
            "وعند وجوده TitanBox يجعل DB مطلوبة افتراضياً حتى لا ينفذ إدارة بنصف حالة.",
            "",
            "بعد الحفظ/Redeploy: /infra ثم /security ثم /diag",
            "لا ترسل أي Token/Password/DSN داخل Telegram أو GitHub.",
        ]
        await bot.send_message(chat_id, "\n".join(lines))

    async def _wake(self, chat_id: int | str, bot: "BotContext") -> None:
        if not self.public_base_url:
            await bot.send_message(chat_id, "Public Render URL غير مكتشف.")
            return
        await bot.send_message(
            chat_id,
            "🌤 Wake / cold-start\n"
            f"Wake endpoint: {self.public_base_url}/wakez\n"
            "Telegram webhook نفسه يرسل Incoming HTTP ويوقظ الخدمة عند وصول رسالة.\n"
            "TitanBox لا يرسل self-pings ولا يحاول تجاوز حدود الخطة المجانية.",
        )

    async def _auth(self, user_id: int, chat_id: int | str, parts: list[str], bot: "BotContext") -> None:
        if not self.require_2fa:
            await bot.send_message(chat_id, "ℹ️ 2FA غير مفروض حالياً. فعّله من Render: DEPLOY_REQUIRE_2FA=true.")
            return
        if not self.totp_secret:
            self._audit("2fa_auth", user_id, "misconfigured")
            raise DeployError("DEPLOY_REQUIRE_2FA=true لكن DEPLOY_TOTP_SECRET غير موجود.")
        if len(parts) != 2:
            raise DeployError("الاستخدام: /auth 123456")
        last = self._last_totp_counter.get(user_id)
        counter = verify_totp(self.totp_secret, parts[1], last_counter=last)
        if counter is None:
            self._audit("2fa_auth", user_id, "failed")
            await bot.send_message(chat_id, "❌ كود 2FA غير صحيح/منتهي أو مستخدم سابقاً.")
            return
        self._last_totp_counter[user_id] = counter
        self._auth_until[user_id] = time.monotonic() + self.twofa_session_seconds
        self._audit("2fa_auth", user_id, "success")
        await bot.send_message(chat_id, f"🔓 تم فتح جلسة الأوامر الحساسة لمدة {self.twofa_session_seconds // 60} دقائق.")

    async def _audit_tail(self, chat_id: int | str, parts: list[str], bot: "BotContext") -> None:
        if self.audit is None:
            await bot.send_message(chat_id, "Audit log غير متاح.")
            return
        limit = 10
        if len(parts) >= 2:
            try:
                limit = min(max(1, int(parts[1])), 30)
            except ValueError as exc:
                raise DeployError("الاستخدام: /audit 10") from exc
        records = self.audit.tail(limit)
        lines = []
        for item in records:
            lines.append(
                f"• {item.get('ts')} | {item.get('action')} | {item.get('result')} | "
                f"admin={item.get('actor_id')} | project={item.get('project') or '-'} | mac={str(item.get('mac') or '')[:10]}"
            )
        await self._send_chunks(bot, chat_id, "🧾 Audit log:", lines or ["لا توجد عمليات مسجلة بعد."])

    async def _handle_command(
        self,
        user_id: int,
        chat_id: int | str,
        text: str,
        bot: "BotContext",
        update_id: int,
    ) -> bool:
        assert self.manager is not None
        parts = self._command_parts(text)
        if not parts:
            return False
        command = parts[0]

        if command in {"/start", "/help"}:
            await bot.send_message(chat_id, HELP_TEXT + self._persistence_warning())
            return True
        if command == "/whoami":
            await self._whoami(user_id, chat_id, bot)
            return True
        if command == "/diag":
            await self._diag(user_id, chat_id, bot)
            return True
        if command == "/system":
            await self._system(chat_id, bot)
            return True
        if command == "/security":
            await self._security(user_id, chat_id, bot)
            return True
        if command == "/infra":
            await self._infra(chat_id, bot)
            return True
        if command == "/setup":
            await self._setup_guide(chat_id, bot)
            return True
        if command == "/wake":
            await self._wake(chat_id, bot)
            return True
        if command == "/auth":
            await self._auth(user_id, chat_id, parts, bot)
            return True
        if command == "/lock":
            self._auth_until.pop(user_id, None)
            self._audit("2fa_lock", user_id, "success")
            await bot.send_message(chat_id, "🔒 تم إغلاق جلسة الأوامر الحساسة.")
            return True
        if command == "/audit":
            self._require_privileged(user_id)
            await self._audit_tail(chat_id, parts, bot)
            return True
        if command == "/jobs":
            self._require_privileged(user_id)
            await self._jobs_status(chat_id, parts, bot)
            return True

        if command in {"/projects", "/use", "/status", "/files", "/releases"}:
            self._require_privileged(user_id)

        if command == "/projects":
            local_projects = self.manager.list_projects()
            local = {str(item["name"]): item for item in local_projects}
            durable_names = await self.manager.list_durable_projects()
            names = sorted(set(local) | set(durable_names), key=str.lower)
            if not names:
                await bot.send_message(chat_id, "لا توجد مشاريع بعد. أرسل ZIP مع: /deploy mybot")
                return True
            durable_set = set(durable_names)
            lines = []
            for name in names:
                item = local.get(name)
                current = item.get("current") if item else None
                releases = item.get("releases", 0) if item else 0
                cloud = "yes" if name in durable_set else "no"
                lines.append(f"• {name} — current={current or '-'} — local={releases} — durable={cloud}")
            await self._send_chunks(bot, chat_id, "📦 المشاريع:", lines)
            return True

        if command == "/use":
            if len(parts) != 2:
                raise DeployError("الاستخدام: /use PROJECT")
            project = self.manager.validate_project_name(parts[1])
            self.active_project[user_id] = project
            await bot.send_message(chat_id, f"✅ المشروع النشط: {project}")
            return True

        if command == "/status":
            project = self._pick_project(user_id, parts[1] if len(parts) >= 2 else None)
            project_status = self.manager.status(project)
            backups = await self.manager.list_backups(project, limit=100)
            runner = project_status["runner"]
            runner_text = "غير مربوط بالـRunner"
            if isinstance(runner, dict):
                runner_text = f"running={runner.get('running')} pid={runner.get('pid')} restarts={runner.get('restart_count')}"
            await bot.send_message(
                chat_id,
                f"📦 {project}\nCurrent: {project_status['current'] or '-'}\nLocal releases: {project_status['release_count']}"
                f"\nDurable backups: {len(backups)}\nRunner: {runner_text}",
            )
            return True

        if command == "/files":
            explicit = parts[1] if len(parts) >= 2 else None
            project = self._pick_project(user_id, explicit)
            prefix = parts[2] if len(parts) >= 3 else ""
            files = self.manager.list_files(project, prefix=prefix)
            if not files:
                await bot.send_message(chat_id, "لا توجد ملفات مطابقة.")
            else:
                await self._send_chunks(bot, chat_id, f"📁 {project}:", [f"• {x}" for x in files])
            return True

        if command == "/releases":
            project = self._pick_project(user_id, parts[1] if len(parts) >= 2 else None)
            current = self.manager.current_release_name(project)
            releases = self.manager.release_names(project)
            lines = [f"{'🟢' if x == current else '⚪️'} {x}" for x in releases]
            await self._send_chunks(bot, chat_id, f"🗂 Releases — {project}:", lines or ["لا توجد نسخ."])
            return True

        if command == "/backups":
            self._require_privileged(user_id)
            project = self._pick_project(user_id, parts[1] if len(parts) >= 2 else None)
            backups = await self.manager.list_backups(project)
            lines = [f"☁️ {name}" for name in backups]
            await self._send_chunks(
                bot,
                chat_id,
                f"☁️ Durable backups — {project}:",
                lines or ["لا توجد نسخ دائمة نشطة، أو التخزين الخارجي غير مفعّل."],
            )
            return True

        if command == "/restore":
            self._require_privileged(user_id)
            if len(parts) < 2 or len(parts) > 3:
                raise DeployError("الاستخدام: /restore PROJECT [RELEASE|latest]")
            project = self._pick_project(user_id, parts[1])
            release = parts[2] if len(parts) == 3 else "latest"
            queued_release = await self._resolve_restore_target(project, release) if self._persistent_jobs_enabled else release
            if await self._enqueue_job(
                "restore",
                f"{bot.name}:{update_id}:restore",
                {"actor_id": user_id, "chat_id": chat_id, "project": project, "release": queued_release},
                chat_id,
                bot,
            ):
                return True
            self._spawn_operation(
                self._do_restore(project, release, chat_id, bot),
                chat_id,
                bot,
                actor_id=user_id,
                action="restore_durable",
                project=project,
            )
            return True

        if command == "/rollback":
            self._require_privileged(user_id)
            explicit_project = parts[1] if len(parts) >= 2 else None
            project = self._pick_project(user_id, explicit_project)
            release = parts[2] if len(parts) >= 3 else None
            queued_release = self._resolve_rollback_target(project, release) if self._persistent_jobs_enabled else release
            if await self._enqueue_job(
                "rollback",
                f"{bot.name}:{update_id}:rollback",
                {"actor_id": user_id, "chat_id": chat_id, "project": project, "release": queued_release},
                chat_id,
                bot,
            ):
                return True
            self._spawn_operation(
                self._do_rollback(project, release, chat_id, bot),
                chat_id,
                bot,
                actor_id=user_id,
                action="rollback",
                project=project,
            )
            return True

        if command == "/restart":
            self._require_privileged(user_id)
            project = self._pick_project(user_id, parts[1] if len(parts) >= 2 else None)
            if await self._enqueue_job(
                "restart",
                f"{bot.name}:{update_id}:restart",
                {"actor_id": user_id, "chat_id": chat_id, "project": project},
                chat_id,
                bot,
            ):
                return True
            self._spawn_operation(
                self._do_restart(project, chat_id, bot),
                chat_id,
                bot,
                actor_id=user_id,
                action="restart",
                project=project,
            )
            return True

        return False

    async def _do_restore(
        self,
        project: str,
        release: str,
        chat_id: int | str,
        bot: "BotContext",
        *,
        operation_id: str | None = None,
    ) -> None:
        assert self.manager is not None
        await bot.send_message(chat_id, f"☁️ جاري تنزيل وفحص النسخة الدائمة لـ {project}: {release} ...")
        result = await self.manager.restore_backup(project, release, operation_id=operation_id)
        await bot.send_message(
            chat_id,
            "✅ Durable restore ناجح\n"
            f"Project: {project}\nNew local release: {result.release}\n"
            f"Previous: {result.previous_release or '-'}\nRestarted: {result.restarted}",
        )

    async def _do_rollback(
        self,
        project: str,
        release: str | None,
        chat_id: int | str,
        bot: "BotContext",
        *,
        idempotent: bool = False,
        operation_id: str | None = None,
    ) -> None:
        assert self.manager is not None
        await bot.send_message(chat_id, f"⏪ بدء Rollback لـ {project}...")
        restored_from_durable = False
        try:
            result = await self.manager.rollback(project, release, idempotent=idempotent)
        except DeployError:
            # A Render restart can erase every local release after the rollback job was
            # durably queued. If its frozen target exists in object storage, recover that
            # exact release through the verified restore path instead of losing the job.
            if not operation_id or not release:
                raise
            backups = await self.manager.list_backups(project, limit=100)
            if release not in backups:
                raise
            result = await self.manager.restore_backup(
                project, release, operation_id=operation_id
            )
            restored_from_durable = True
        mode = "Durable restore fallback" if restored_from_durable else "Local rollback"
        await bot.send_message(
            chat_id,
            f"✅ Rollback ناجح\nMode: {mode}\nProject: {project}\nCurrent: {result.release}"
            f"\nPrevious: {result.previous_release or '-'}\nRestarted: {result.restarted}",
        )

    async def _do_restart(self, project: str, chat_id: int | str, bot: "BotContext") -> None:
        assert self.manager is not None
        await bot.send_message(chat_id, f"🔄 بدء Restart لـ {project}...")
        state = await self.manager.restart(project)
        await bot.send_message(chat_id, f"✅ {project} مستقر — pid={state.get('pid')}")

    async def _download_document(self, document: dict[str, Any], bot: "BotContext") -> Path:
        assert self.manager is not None
        file_id = document.get("file_id")
        if not isinstance(file_id, str) or not file_id:
            raise DeployError("Telegram document has no file_id.")
        file_name = self.manager.safe_filename(str(document.get("file_name") or "upload.bin"))
        declared = document.get("file_size")
        if isinstance(declared, int) and declared > self.max_upload_bytes:
            raise DeployError(f"الملف أكبر من الحد المسموح ({self.max_upload_bytes} bytes).")
        temp = self.manager.create_temp_upload(file_name)
        try:
            await bot.download_file(file_id, temp, self.max_upload_bytes)
        except ValueError as exc:
            raise DeployError(str(exc)) from exc
        return temp

    async def _handle_document(
        self,
        user_id: int,
        chat_id: int | str,
        message: dict[str, Any],
        bot: "BotContext",
        *,
        preauthorized: bool = False,
        operation_id: str | None = None,
    ) -> None:
        assert self.manager is not None
        if not preauthorized:
            self._require_privileged(user_id)
        document = message.get("document")
        if not isinstance(document, dict):
            return
        filename = self.manager.safe_filename(str(document.get("file_name") or "upload.bin"))
        caption = str(message.get("caption") or "").strip()
        parts = self._command_parts(caption) if caption.startswith("/") else []

        if parts and parts[0] == "/deploy":
            if len(parts) != 2:
                raise DeployError("Caption الصحيح: /deploy PROJECT")
            project = self._pick_project(user_id, parts[1])
            if not filename.lower().endswith(".zip"):
                raise DeployError("/deploy يحتاج ملف ZIP.")
            await bot.send_message(chat_id, f"⬇️ استلمت {filename}. جاري التنزيل والفحص قبل نشر {project}...")
            temp = await self._download_document(document, bot)
            try:
                result = await self.manager.deploy_zip(project, temp, operation_id=operation_id)
            finally:
                temp.unlink(missing_ok=True)
            self._audit("deploy_zip", user_id, "success", project=project, detail={"release": result.release})
            run_note = (
                "✅ التطبيق أُعيد تشغيله واستقر."
                if result.restarted
                else "ℹ️ تم حفظ وفحص النسخة، لكنها غير مربوطة بالـRunner؛ رفع ZIP وحده لا يشغّل برنامجاً عشوائياً تلقائياً."
            )
            await bot.send_message(
                chat_id,
                "✅ Deployment files accepted\n"
                f"Project: {result.project}\nRelease: {result.release}\n"
                f"Previous: {result.previous_release or '-'}\nRestarted: {result.restarted}\n"
                f"Checks: {', '.join(result.validation)}\n{run_note}" + self._persistence_warning(),
            )
            return

        if parts and parts[0] == "/put":
            if len(parts) != 3:
                raise DeployError("Caption الصحيح: /put PROJECT path/to/file.ext")
            project = self._pick_project(user_id, parts[1])
            target = parts[2]
            await bot.send_message(chat_id, f"🧪 جاري تجهيز تحديث {project}/{target}...")
            temp = await self._download_document(document, bot)
            try:
                result = await self.manager.put_file(project, target, temp, operation_id=operation_id)
            finally:
                temp.unlink(missing_ok=True)
            self._audit(
                "put_file",
                user_id,
                "success",
                project=project,
                detail={"path": target[:200], "release": result.release},
            )
            run_note = "" if result.restarted else "\nℹ️ المشروع غير مربوط بالـRunner، لذلك تم تحديث الملفات فقط."
            await bot.send_message(
                chat_id,
                "✅ تحديث الملف نجح\n"
                f"Project: {project}\nPath: {target}\nRelease: {result.release}\n"
                f"Previous: {result.previous_release or '-'}\nRestarted: {result.restarted}" + run_note + self._persistence_warning(),
            )
            return

        project = self._pick_project(user_id)
        if filename.lower().endswith(".zip"):
            raise DeployError(f"الملف ZIP. للنشر الكامل أعد إرساله مع Caption: /deploy {project}")

        matches = self.manager.find_by_basename(project, filename)
        if len(matches) == 1:
            target = matches[0]
            await bot.send_message(chat_id, f"🎯 لقيت الملف بشكل فريد: {project}/{target}\nجاري التحديث الآمن...")
            temp = await self._download_document(document, bot)
            try:
                result = await self.manager.put_file(project, target, temp, operation_id=operation_id)
            finally:
                temp.unlink(missing_ok=True)
            self._audit(
                "smart_put_file",
                user_id,
                "success",
                project=project,
                detail={"path": target[:200], "release": result.release},
            )
            await bot.send_message(
                chat_id,
                f"✅ تم تحديث {target}\nRelease: {result.release}\nPrevious: {result.previous_release or '-'}\nRestarted: {result.restarted}"
                + self._persistence_warning(),
            )
            return

        if len(matches) > 1:
            choices = "\n".join(f"• {x}" for x in matches)
            raise DeployError(
                "اسم الملف موجود بأكثر من مكان. أعد إرسال الملف مع المسار الكامل:\n"
                f"/put {project} path/to/{filename}\n\nالمطابقات:\n{choices}"
            )

        raise DeployError(
            f"الملف {filename} جديد وما أگدر أخمن مكانه. أعد إرساله مع Caption:\n"
            f"/put {project} assets/{filename}"
        )

    async def handle(self, update: dict[str, Any], bot: "BotContext") -> None:
        if self.manager is None:
            raise RuntimeError("DeployAdminPlugin was not bound to TitanBox services")
        user_id, chat_id, message = self._actor(update)
        if user_id is None or chat_id is None or message is None:
            return
        chat = message.get("chat") or {}
        chat_type = str(chat.get("type") or "")
        if chat_type and chat_type != "private":
            log.warning("ignored deploy admin message outside private chat user_id=%s chat_type=%s", user_id, chat_type)
            return
        text = str(message.get("text") or "").strip()
        if user_id not in self.admin_ids:
            log.warning("rejected deployment bot access user_id=%s", user_id)
            command = self._command_parts(text)[0] if text.startswith("/") and self._command_parts(text) else ""
            if command in {"/start", "/whoami"}:
                await self._whoami(user_id, chat_id, bot)
            else:
                await bot.send_message(
                    chat_id,
                    f"⛔ هذا الحساب غير مصرح للإدارة.\nTelegram ID مالك: {user_id}\nأرسل /whoami للتعليمات.",
                )
            return

        if not await self._limiter(user_id).allow():
            await bot.send_message(chat_id, "⏳ أوامر الإدارة سريعة جداً. انتظر ثواني وحاول مرة ثانية.")
            return

        raw_update_id = update.get("update_id")
        # TelegramHub validates update_id before invoking plugins. The fallback keeps direct
        # unit/plugin integrations backward-compatible; persistent queuing only receives real
        # Telegram IDs in production.
        update_id = raw_update_id if isinstance(raw_update_id, int) else -int(time.time_ns() % 2_000_000_000)
        try:
            if text.startswith("/") and await self._handle_command(user_id, chat_id, text, bot, update_id):
                return
            if isinstance(message.get("document"), dict):
                self._require_privileged(user_id)
                if self._persistent_jobs_enabled:
                    # Resolve `/use` and smart-update filename matching *before* persistence.
                    # A Render sleep/restart can erase in-memory active_project state while the
                    # PostgreSQL job survives; the queued payload therefore contains a fully
                    # explicit deterministic operation.
                    job_message = self._canonical_persistent_document(user_id, message)
                    if await self._enqueue_job(
                        "document",
                        f"{bot.name}:{update_id}:document",
                        {"actor_id": user_id, "chat_id": chat_id, "message": job_message},
                        chat_id,
                        bot,
                    ):
                        return
                self._spawn_operation(
                    self._handle_document(user_id, chat_id, message, bot, preauthorized=True),
                    chat_id,
                    bot,
                    actor_id=user_id,
                    action="document_operation",
                    project=self.active_project.get(user_id),
                )
                return
            if text:
                await bot.send_message(chat_id, "استخدم /help لعرض أوامر الإدارة.")
        except DeployError as exc:
            self._audit("command_denied", user_id, "denied", detail={"error": str(exc)[:200]})
            await bot.send_message(chat_id, f"❌ {exc}")
        except Exception as exc:
            self._audit("admin_internal_error", user_id, "error", detail={"type": type(exc).__name__})
            log.exception("unexpected deploy admin failure user_id=%s", user_id)
            await bot.send_message(chat_id, "❌ حدث خطأ داخلي أثناء العملية. لم يتم اعتماد تحديث غير مكتمل.")


if TYPE_CHECKING:
    from titanbox.telegram import BotContext, PluginServices
