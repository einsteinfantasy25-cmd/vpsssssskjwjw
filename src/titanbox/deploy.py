from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class DeployError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeployResult:
    project: str
    release: str
    previous_release: str | None
    restarted: bool
    rolled_back: bool
    validation: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "release": self.release,
            "previous_release": self.previous_release,
            "restarted": self.restarted,
            "rolled_back": self.rolled_back,
            "validation": list(self.validation),
        }


@dataclass(frozen=True, slots=True)
class DeployLimits:
    max_upload_bytes: int
    max_archive_files: int
    max_extracted_bytes: int
    keep_releases: int
    stabilize_seconds: float
    restart_timeout_seconds: float


class DeploymentManager:
    """Transactional, release-based deployment manager for admin-owned projects."""

    def __init__(self, root: Path, limits: DeployLimits, runner: Any | None = None):
        self.root = root.resolve()
        self.projects_root = self.root / "projects"
        self.tmp_root = self.root / "tmp"
        self.limits = limits
        self.runner = runner
        self._locks: dict[str, asyncio.Lock] = {}
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_workdirs()

    def _cleanup_stale_workdirs(self) -> None:
        for project in self.projects_root.iterdir():
            if not project.is_dir():
                continue
            for path in project.glob(".staging-*"):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
        for path in self.tmp_root.glob("upload-*"):
            path.unlink(missing_ok=True)

    def _lock(self, project: str) -> asyncio.Lock:
        return self._locks.setdefault(project, asyncio.Lock())

    @staticmethod
    def validate_project_name(name: str) -> str:
        value = name.strip()
        if not PROJECT_RE.fullmatch(value):
            raise DeployError("Invalid project name. Use letters, numbers, dot, dash, underscore; max 64 chars.")
        return value

    @staticmethod
    def validate_relative_path(raw: str) -> PurePosixPath:
        value = raw.strip().replace("\\", "/")
        if not value or "\x00" in value or len(value) > 240:
            raise DeployError("Invalid target path.")
        if value.startswith("./") or "//" in value:
            raise DeployError("Target path contains an ambiguous path segment.")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise DeployError("Target path must stay inside the project and cannot contain '..'.")
        return path

    @staticmethod
    def safe_filename(raw: str) -> str:
        if not raw or "\x00" in raw:
            raise DeployError("Invalid filename.")
        name = Path(raw).name
        if name in {"", ".", ".."} or len(name) > 180:
            raise DeployError("Invalid filename.")
        if any(ord(ch) < 32 for ch in name):
            raise DeployError("Filename contains control characters.")
        return name

    def project_dir(self, project: str) -> Path:
        return self.projects_root / self.validate_project_name(project)

    def releases_dir(self, project: str) -> Path:
        return self.project_dir(project) / "releases"

    def current_link(self, project: str) -> Path:
        return self.project_dir(project) / "current"

    def current_release_name(self, project: str) -> str | None:
        link = self.current_link(project)
        if not link.is_symlink():
            return None
        target = os.readlink(link)
        return Path(target).name

    def current_release_path(self, project: str) -> Path | None:
        release = self.current_release_name(project)
        if release is None:
            return None
        path = (self.releases_dir(project) / release).resolve()
        root = self.releases_dir(project).resolve()
        if path.parent != root:
            raise DeployError("Current release pointer is invalid.")
        if not path.is_dir():
            return None
        return path

    def list_projects(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not self.projects_root.exists():
            return items
        for child in sorted(self.projects_root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir() or not PROJECT_RE.fullmatch(child.name):
                continue
            releases = child / "releases"
            count = sum(1 for p in releases.iterdir() if p.is_dir()) if releases.exists() else 0
            items.append({"name": child.name, "current": self.current_release_name(child.name), "releases": count})
        return items

    def list_files(self, project: str, prefix: str = "", limit: int = 120) -> list[str]:
        current = self.current_release_path(project)
        if current is None:
            raise DeployError("Project has no active release.")
        prefix_norm = prefix.strip().replace("\\", "/")
        results: list[str] = []
        for path in sorted(current.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(current).as_posix()
            if prefix_norm and not rel.startswith(prefix_norm):
                continue
            results.append(rel)
            if len(results) >= limit:
                break
        return results

    def find_by_basename(self, project: str, filename: str, limit: int = 10) -> list[str]:
        current = self.current_release_path(project)
        if current is None:
            return []
        name = self.safe_filename(filename)
        results: list[str] = []
        for path in current.rglob(name):
            if path.is_file() and path.name == name:
                results.append(path.relative_to(current).as_posix())
                if len(results) >= limit:
                    break
        return sorted(results)

    def release_names(self, project: str) -> list[str]:
        releases = self.releases_dir(project)
        if not releases.exists():
            return []
        entries = [p for p in releases.iterdir() if p.is_dir() and not p.name.startswith(".")]
        entries.sort(key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
        return [p.name for p in entries]

    def status(self, project: str) -> dict[str, Any]:
        project = self.validate_project_name(project)
        current = self.current_release_name(project)
        app_status = None
        if self.runner is not None and project in getattr(self.runner, "states", {}):
            app_status = self.runner.states[project].as_dict()
        return {
            "project": project,
            "current": current,
            "release_count": len(self.release_names(project)),
            "runner": app_status,
        }

    def _new_release_name(self, source_path: Path | None = None) -> str:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        entropy = f"{time.time_ns()}:{os.getpid()}".encode()
        if source_path and source_path.exists() and source_path.is_file():
            try:
                with source_path.open("rb") as handle:
                    entropy += handle.read(65536)
            except OSError:
                pass
        suffix = hashlib.sha256(entropy).hexdigest()[:8]
        return f"{stamp}-{suffix}"

    @staticmethod
    def _copy_with_hardlink(src: str, dst: str) -> str:
        try:
            os.link(src, dst)
            return dst
        except OSError:
            return shutil.copy2(src, dst)

    def _clone_release(self, source: Path, destination: Path) -> None:
        shutil.copytree(
            source,
            destination,
            symlinks=True,
            copy_function=self._copy_with_hardlink,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )

    def _zip_member_path(self, name: str) -> PurePosixPath:
        if not name or "\x00" in name:
            raise DeployError("Archive contains an invalid path.")
        normalized = name.replace("\\", "/")
        if normalized.startswith("./") or "//" in normalized:
            raise DeployError(f"Unsafe archive path: {name!r}")
        path = PurePosixPath(normalized)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise DeployError(f"Unsafe archive path: {name!r}")
        if len(normalized) > 512:
            raise DeployError("Archive path is too long.")
        return path

    def _safe_extract_zip(self, archive: Path, destination: Path) -> None:
        try:
            zf = zipfile.ZipFile(archive)
        except (zipfile.BadZipFile, OSError) as exc:
            raise DeployError("The uploaded ZIP is not valid.") from exc

        with zf:
            infos = zf.infolist()
            if len(infos) > self.limits.max_archive_files:
                raise DeployError(f"Archive has too many entries ({len(infos)}).")
            total = sum(max(0, info.file_size) for info in infos)
            if total > self.limits.max_extracted_bytes:
                raise DeployError("Archive expands beyond the configured safety limit.")

            members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for info in infos:
                rel = self._zip_member_path(info.filename.rstrip("/")) if not info.is_dir() else self._zip_member_path(info.filename.rstrip("/"))
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise DeployError("Archive symlinks are not allowed.")
                members.append((info, rel))

            destination.mkdir(parents=True, exist_ok=False)
            total_written = 0
            for info, rel in members:
                target = destination.joinpath(*rel.parts)
                target_parent = target.parent.resolve()
                dest_resolved = destination.resolve()
                if target_parent != dest_resolved and dest_resolved not in target_parent.parents:
                    raise DeployError("Archive attempted to escape the staging directory.")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with zf.open(info, "r") as source, target.open("wb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        total_written += len(chunk)
                        if written > info.file_size + 1024:
                            raise DeployError("Archive member exceeded its declared size.")
                        if total_written > self.limits.max_extracted_bytes:
                            raise DeployError("Archive exceeded extracted-size limit while unpacking.")
                        output.write(chunk)

        self._flatten_single_root(destination)

    @staticmethod
    def _flatten_single_root(destination: Path) -> None:
        macos = destination / "__MACOSX"
        if macos.exists():
            shutil.rmtree(macos, ignore_errors=True)
        entries = list(destination.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            return
        inner = entries[0]
        temp = destination.parent / f"{destination.name}.flatten"
        inner.rename(temp)
        destination.rmdir()
        temp.rename(destination)

    @staticmethod
    def _tree_digest(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = path.relative_to(root).as_posix().encode("utf-8")
            digest.update(len(rel).to_bytes(4, "big"))
            digest.update(rel)
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
        return digest.hexdigest()

    def _validate_tree(self, root: Path) -> tuple[str, ...]:
        checks: list[str] = []
        file_count = 0
        total_bytes = 0
        for path in root.rglob("*"):
            if path.is_symlink():
                raise DeployError(f"Symlink is not allowed in release: {path.relative_to(root)}")
            if not path.is_file():
                continue
            file_count += 1
            total_bytes += path.stat().st_size
            if file_count > self.limits.max_archive_files:
                raise DeployError("Release has too many files.")
            if total_bytes > self.limits.max_extracted_bytes:
                raise DeployError("Release exceeds configured size limit.")

            suffix = path.suffix.lower()
            try:
                if suffix == ".py":
                    source = path.read_text(encoding="utf-8")
                    compile(source, str(path), "exec", dont_inherit=True)
                elif suffix == ".json" and path.stat().st_size <= 4 * 1024 * 1024:
                    with path.open("r", encoding="utf-8") as handle:
                        json.load(handle)
                elif suffix == ".toml" and path.stat().st_size <= 4 * 1024 * 1024:
                    with path.open("rb") as handle:
                        tomllib.load(handle)
            except (SyntaxError, ValueError, UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
                rel = path.relative_to(root).as_posix()
                raise DeployError(f"Validation failed for {rel}: {exc}") from exc
        checks.append(f"files:{file_count}")
        checks.append(f"bytes:{total_bytes}")
        checks.append("python/json/toml:ok")
        checks.append(f"sha256:{self._tree_digest(root)}")
        return tuple(checks)

    def _activate_release(self, project: str, release: str) -> str | None:
        project_dir = self.project_dir(project)
        link = self.current_link(project)
        previous = self.current_release_name(project)
        tmp_link = project_dir / f".current-{os.getpid()}-{time.time_ns()}"
        relative_target = Path("releases") / release
        os.symlink(relative_target.as_posix(), tmp_link)
        os.replace(tmp_link, link)
        return previous

    async def _restart_and_verify(self, project: str) -> bool:
        if self.runner is None or project not in getattr(self.runner, "states", {}):
            return False
        await self.runner.restart_app(project)
        healthy = await self.runner.wait_healthy(
            project,
            grace_seconds=self.limits.stabilize_seconds,
            timeout_seconds=self.limits.restart_timeout_seconds,
        )
        if not healthy:
            raise DeployError("Updated app did not become stable after restart.")
        return True

    async def _finalize_release(self, project: str, release: str, validation: tuple[str, ...]) -> DeployResult:
        previous = self._activate_release(project, release)
        restarted = False
        try:
            restarted = await self._restart_and_verify(project)
        except Exception as exc:
            if previous is not None:
                self._activate_release(project, previous)
                try:
                    await self._restart_and_verify(project)
                except Exception:
                    pass
            raise DeployError(f"Activation failed and previous release was restored: {exc}") from exc

        self._prune_releases(project, protect={release, previous} if previous else {release})
        return DeployResult(
            project=project,
            release=release,
            previous_release=previous,
            restarted=restarted,
            rolled_back=False,
            validation=validation,
        )

    def _prune_releases(self, project: str, protect: set[str | None]) -> None:
        keep = max(2, self.limits.keep_releases)
        releases = self.release_names(project)
        survivors = 0
        for release in releases:
            if release in protect or survivors < keep:
                survivors += 1
                continue
            shutil.rmtree(self.releases_dir(project) / release, ignore_errors=True)

    async def deploy_zip(self, project: str, archive: Path) -> DeployResult:
        project = self.validate_project_name(project)
        if archive.stat().st_size > self.limits.max_upload_bytes:
            raise DeployError("Upload exceeds configured size limit.")
        async with self._lock(project):
            project_dir = self.project_dir(project)
            releases = self.releases_dir(project)
            releases.mkdir(parents=True, exist_ok=True)
            release = self._new_release_name(archive)
            staging = project_dir / f".staging-{release}"
            final = releases / release
            try:
                await asyncio.to_thread(self._safe_extract_zip, archive, staging)
                validation = await asyncio.to_thread(self._validate_tree, staging)
                os.replace(staging, final)
                return await self._finalize_release(project, release, validation)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                if final.exists() and self.current_release_name(project) != release:
                    shutil.rmtree(final, ignore_errors=True)
                raise

    async def put_file(self, project: str, relative_path: str, uploaded: Path) -> DeployResult:
        project = self.validate_project_name(project)
        rel = self.validate_relative_path(relative_path)
        if uploaded.stat().st_size > self.limits.max_upload_bytes:
            raise DeployError("Upload exceeds configured size limit.")
        async with self._lock(project):
            current = self.current_release_path(project)
            if current is None:
                raise DeployError("Project does not exist yet. Deploy a ZIP first.")
            releases = self.releases_dir(project)
            release = self._new_release_name(uploaded)
            staging = self.project_dir(project) / f".staging-{release}"
            final = releases / release
            try:
                await asyncio.to_thread(self._clone_release, current, staging)
                target = staging.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                previous_mode: int | None = None
                if target.exists() or target.is_symlink():
                    if target.is_dir():
                        raise DeployError("Target path is a directory.")
                    previous_mode = stat.S_IMODE(target.stat().st_mode)
                    target.unlink()
                await asyncio.to_thread(shutil.copy2, uploaded, target)
                if previous_mode is not None:
                    target.chmod(previous_mode)
                validation = await asyncio.to_thread(self._validate_tree, staging)
                os.replace(staging, final)
                return await self._finalize_release(project, release, validation)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                if final.exists() and self.current_release_name(project) != release:
                    shutil.rmtree(final, ignore_errors=True)
                raise

    async def rollback(self, project: str, release: str | None = None) -> DeployResult:
        project = self.validate_project_name(project)
        async with self._lock(project):
            current = self.current_release_name(project)
            releases = self.release_names(project)
            if not releases or current is None:
                raise DeployError("Project has no releases to roll back.")
            if release is None:
                candidates = [name for name in releases if name != current]
                if not candidates:
                    raise DeployError("No previous release exists.")
                release = candidates[0]
            if release not in releases:
                raise DeployError("Requested release does not exist.")
            if release == current:
                raise DeployError("Requested release is already active.")
            self._activate_release(project, release)
            restarted = False
            try:
                restarted = await self._restart_and_verify(project)
            except Exception as exc:
                self._activate_release(project, current)
                try:
                    await self._restart_and_verify(project)
                except Exception:
                    pass
                raise DeployError(f"Rollback target failed; original release restored: {exc}") from exc
            return DeployResult(
                project=project,
                release=release,
                previous_release=current,
                restarted=restarted,
                rolled_back=True,
                validation=("rollback:ok",),
            )

    async def restart(self, project: str) -> dict[str, Any]:
        project = self.validate_project_name(project)
        if self.runner is None or project not in getattr(self.runner, "states", {}):
            raise DeployError("Project is not configured in the Legacy Runner.")
        await self.runner.restart_app(project)
        healthy = await self.runner.wait_healthy(
            project,
            grace_seconds=self.limits.stabilize_seconds,
            timeout_seconds=self.limits.restart_timeout_seconds,
        )
        if not healthy:
            raise DeployError("App failed to stabilize after restart.")
        return self.runner.states[project].as_dict()

    def create_temp_upload(self, filename: str) -> Path:
        name = self.safe_filename(filename)
        fd, path = tempfile.mkstemp(prefix="upload-", suffix=f"-{name}", dir=self.tmp_root)
        os.close(fd)
        return Path(path)
