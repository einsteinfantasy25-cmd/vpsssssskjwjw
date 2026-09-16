from __future__ import annotations

import asyncio
import logging
import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Any

from titanbox.deploy import DeployError, DeployLimits, DeploymentManager

log = logging.getLogger("titanbox.deploy_admin")


HELP_TEXT = """TitanBox Deploy Admin 🚀

هذا البوت مخصص للإدارة فقط.

الأوامر:
/projects — عرض المشاريع
/use NAME — اختيار مشروع افتراضي
/status [NAME] — حالة المشروع
/files [NAME] [PREFIX] — عرض الملفات
/releases [NAME] — عرض النسخ
/restart [NAME] — إعادة تشغيل التطبيق إذا كان مربوطاً بالـRunner
/rollback [NAME] [RELEASE] — رجوع للنسخة السابقة أو نسخة محددة

رفع مشروع كامل:
أرسل ZIP واكتب في Caption:
/deploy mybot

تحديث/إضافة ملف واحد:
أرسل الملف واكتب في Caption:
/put mybot path/to/file.py

الوضع الذكي:
/use mybot
بعدها إذا أرسلت ملفاً بدون Caption وكان له اسم فريد داخل المشروع، سيُستبدل تلقائياً داخل Release جديدة قابلة للـRollback.
"""


class DeployAdminPlugin:
    def __init__(self) -> None:
        self.manager: DeploymentManager | None = None
        self.admin_ids: set[int] = set()
        self.max_upload_bytes = 0
        self.active_project: dict[int, str] = {}
        self._op_slots = asyncio.Semaphore(1)
        self._tasks: set[asyncio.Task[None]] = set()

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
        self.manager = DeploymentManager(settings.deploy_root, limits, runner=services.runner)
        self.admin_ids = settings.deploy_admin_ids()
        self.max_upload_bytes = settings.deploy_max_upload_bytes
        self._op_slots = asyncio.Semaphore(settings.deploy_max_concurrent_ops)

    def _spawn_operation(self, coroutine: Any, chat_id: int | str, bot: "BotContext") -> None:
        task = asyncio.create_task(self._run_operation(coroutine, chat_id, bot), name="deploy-admin-operation")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_operation(self, coroutine: Any, chat_id: int | str, bot: "BotContext") -> None:
        try:
            async with self._op_slots:
                await coroutine
        except DeployError as exc:
            await bot.send_message(chat_id, f"❌ {exc}")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("unexpected background deployment failure")
            await bot.send_message(chat_id, "❌ حدث خطأ داخلي أثناء العملية. لم يتم اعتماد تحديث غير مكتمل.")

    async def close(self) -> None:
        if not self._tasks:
            return
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    @staticmethod
    def _actor(update: dict[str, Any]) -> tuple[int | None, int | str | None, dict[str, Any] | None]:
        message = update.get("message") or update.get("edited_message")
        if isinstance(message, dict):
            sender = message.get("from") or {}
            chat = message.get("chat") or {}
            user_id = sender.get("id")
            return (user_id if isinstance(user_id, int) else None, chat.get("id"), message)
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            sender = callback.get("from") or {}
            msg = callback.get("message") or {}
            chat = msg.get("chat") or {}
            user_id = sender.get("id")
            return (user_id if isinstance(user_id, int) else None, chat.get("id"), msg)
        return None, None, None

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

    async def _handle_command(
        self,
        user_id: int,
        chat_id: int | str,
        text: str,
        bot: "BotContext",
    ) -> bool:
        assert self.manager is not None
        parts = self._command_parts(text)
        if not parts:
            return False
        command = parts[0]

        if command in {"/start", "/help"}:
            await bot.send_message(chat_id, HELP_TEXT)
            return True

        if command == "/projects":
            projects = self.manager.list_projects()
            if not projects:
                await bot.send_message(chat_id, "لا توجد مشاريع بعد. أرسل ZIP مع: /deploy mybot")
                return True
            lines = [f"• {x['name']} — current={x['current'] or '-'} — releases={x['releases']}" for x in projects]
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
            status = self.manager.status(project)
            runner = status["runner"]
            runner_text = "غير مربوط بالـRunner"
            if isinstance(runner, dict):
                runner_text = f"running={runner.get('running')} pid={runner.get('pid')} restarts={runner.get('restart_count')}"
            await bot.send_message(
                chat_id,
                f"📦 {project}\nCurrent: {status['current'] or '-'}\nReleases: {status['release_count']}\nRunner: {runner_text}",
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

        if command == "/rollback":
            explicit_project = parts[1] if len(parts) >= 2 else None
            project = self._pick_project(user_id, explicit_project)
            release = parts[2] if len(parts) >= 3 else None
            self._spawn_operation(self._do_rollback(project, release, chat_id, bot), chat_id, bot)
            return True

        if command == "/restart":
            project = self._pick_project(user_id, parts[1] if len(parts) >= 2 else None)
            self._spawn_operation(self._do_restart(project, chat_id, bot), chat_id, bot)
            return True

        return False

    async def _do_rollback(
        self, project: str, release: str | None, chat_id: int | str, bot: "BotContext"
    ) -> None:
        assert self.manager is not None
        await bot.send_message(chat_id, f"⏪ بدء Rollback لـ {project}...")
        result = await self.manager.rollback(project, release)
        await bot.send_message(
            chat_id,
            f"✅ Rollback ناجح\nProject: {project}\nCurrent: {result.release}\nPrevious: {result.previous_release or '-'}\nRestarted: {result.restarted}",
        )

    async def _do_restart(self, project: str, chat_id: int | str, bot: "BotContext") -> None:
        assert self.manager is not None
        await bot.send_message(chat_id, f"🔄 بدء Restart لـ {project}...")
        state = await self.manager.restart(project)
        await bot.send_message(chat_id, f"✅ {project} مستقر — pid={state.get('pid')}")

    async def _download_document(
        self,
        document: dict[str, Any],
        bot: "BotContext",
    ) -> Path:
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
    ) -> None:
        assert self.manager is not None
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
                result = await self.manager.deploy_zip(project, temp)
            finally:
                temp.unlink(missing_ok=True)
            await bot.send_message(
                chat_id,
                "✅ Deployment ناجح\n"
                f"Project: {result.project}\nRelease: {result.release}\n"
                f"Previous: {result.previous_release or '-'}\nRestarted: {result.restarted}\n"
                f"Checks: {', '.join(result.validation)}",
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
                result = await self.manager.put_file(project, target, temp)
            finally:
                temp.unlink(missing_ok=True)
            await bot.send_message(
                chat_id,
                "✅ تحديث الملف نجح\n"
                f"Project: {project}\nPath: {target}\nRelease: {result.release}\n"
                f"Previous: {result.previous_release or '-'}\nRestarted: {result.restarted}",
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
                result = await self.manager.put_file(project, target, temp)
            finally:
                temp.unlink(missing_ok=True)
            await bot.send_message(
                chat_id,
                f"✅ تم تحديث {target}\nRelease: {result.release}\nPrevious: {result.previous_release or '-'}\nRestarted: {result.restarted}",
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
        if user_id not in self.admin_ids:
            log.warning("rejected deployment bot access user_id=%s", user_id)
            return

        try:
            text = str(message.get("text") or "").strip()
            if text.startswith("/") and await self._handle_command(user_id, chat_id, text, bot):
                return
            if isinstance(message.get("document"), dict):
                self._spawn_operation(self._handle_document(user_id, chat_id, message, bot), chat_id, bot)
                return
            if text:
                await bot.send_message(chat_id, "استخدم /help لعرض أوامر الإدارة.")
        except DeployError as exc:
            await bot.send_message(chat_id, f"❌ {exc}")
        except Exception:
            log.exception("unexpected deploy admin failure user_id=%s", user_id)
            await bot.send_message(chat_id, "❌ حدث خطأ داخلي أثناء العملية. لم يتم اعتماد تحديث غير مكتمل.")


if TYPE_CHECKING:
    from titanbox.telegram import BotContext, PluginServices
