from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SAFE_KEY = re.compile(r"^[A-Za-z0-9._/\-]+$")


class StorageError(RuntimeError):
    pass


class StorageIntegrityError(StorageError):
    """Stored durable state failed an authenticity/integrity invariant."""


def _norm_key(value: str) -> str:
    key = value.strip().strip("/")
    if not key or len(key) > 900 or ".." in key.split("/") or not _SAFE_KEY.fullmatch(key):
        raise StorageError("Unsafe object-storage key")
    return key


@dataclass(frozen=True, slots=True)
class StorageConfig:
    backend: str
    endpoint_url: str | None
    region: str | None
    bucket: str | None
    access_key_id: str | None
    secret_access_key: str | None
    prefix: str
    force_path_style: bool
    server_side_encryption: str | None


class S3ObjectStore:
    """Small async facade over S3-compatible object storage.

    boto3 is lazy-imported so TitanBox boots normally while storage is disabled.
    All blocking SDK calls run in worker threads instead of Telegram's event loop.
    """

    def __init__(self, config: StorageConfig):
        self.config = config
        self._client: Any | None = None
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.config.backend == "s3"

    def _key(self, raw: str) -> str:
        key = _norm_key(raw)
        prefix = self.config.prefix.strip("/")
        return f"{prefix}/{key}" if prefix else key

    async def _client_async(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._lock:
            if self._client is not None:
                return self._client
            if not self.enabled:
                raise StorageError("Object storage is disabled")
            if not self.config.bucket or not self.config.access_key_id or not self.config.secret_access_key:
                raise StorageError("S3 storage credentials are incomplete")

            def build() -> Any:
                try:
                    import boto3
                    from botocore.config import Config
                except ImportError as exc:  # pragma: no cover - dependency contract
                    raise StorageError("boto3 is required when STORAGE_BACKEND=s3") from exc
                addressing = "path" if self.config.force_path_style else "virtual"
                boto_config = Config(
                    signature_version="s3v4",
                    connect_timeout=5,
                    read_timeout=30,
                    retries={"max_attempts": 4, "mode": "standard"},
                    s3={"addressing_style": addressing},
                )
                return boto3.client(
                    "s3",
                    endpoint_url=self.config.endpoint_url,
                    region_name=self.config.region or "auto",
                    aws_access_key_id=self.config.access_key_id,
                    aws_secret_access_key=self.config.secret_access_key,
                    config=boto_config,
                )

            self._client = await asyncio.to_thread(build)
            return self._client

    async def health(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "ok": True, "backend": "none"}
        started = time.monotonic()
        try:
            client = await self._client_async()
            await asyncio.to_thread(client.list_objects_v2, Bucket=self.config.bucket, MaxKeys=1)
            return {
                "enabled": True,
                "ok": True,
                "backend": "s3",
                "bucket": self.config.bucket,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
            }
        except Exception as exc:
            return {
                "enabled": True,
                "ok": False,
                "backend": "s3",
                "bucket": self.config.bucket,
                "error": f"{type(exc).__name__}: {str(exc)[:180]}",
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
            }

    def _extra_args(self, content_type: str | None = None) -> dict[str, str]:
        result: dict[str, str] = {}
        if content_type:
            result["ContentType"] = content_type
        if self.config.server_side_encryption:
            result["ServerSideEncryption"] = self.config.server_side_encryption
        return result

    async def put_file(self, key: str, path: Path, *, content_type: str | None = None) -> None:
        client = await self._client_async()
        kwargs: dict[str, Any] = {"Bucket": self.config.bucket, "Key": self._key(key)}
        extra = self._extra_args(content_type)
        if extra:
            kwargs["ExtraArgs"] = extra
        await asyncio.to_thread(client.upload_file, str(path), **kwargs)

    async def get_file(self, key: str, destination: Path) -> None:
        client = await self._client_async()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(client.download_file, self.config.bucket, self._key(key), str(destination))
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    async def object_size(self, key: str) -> int:
        """Return remote object size without downloading it."""
        client = await self._client_async()
        response = await asyncio.to_thread(
            client.head_object, Bucket=self.config.bucket, Key=self._key(key)
        )
        size = response.get("ContentLength")
        if not isinstance(size, int) or size < 0:
            raise StorageError("Object storage returned an invalid object size")
        return size

    async def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> None:
        client = await self._client_async()
        kwargs: dict[str, Any] = {
            "Bucket": self.config.bucket,
            "Key": self._key(key),
            "Body": data,
            "ContentType": content_type,
        }
        if self.config.server_side_encryption:
            kwargs["ServerSideEncryption"] = self.config.server_side_encryption
        await asyncio.to_thread(client.put_object, **kwargs)

    async def get_bytes(self, key: str, *, max_bytes: int = 2_000_000) -> bytes:
        client = await self._client_async()

        def read() -> bytes:
            response = client.get_object(Bucket=self.config.bucket, Key=self._key(key))
            body = response["Body"]
            try:
                data = body.read(max_bytes + 1)
            finally:
                close = getattr(body, "close", None)
                if callable(close):
                    close()
            if len(data) > max_bytes:
                raise StorageError("Stored object exceeds configured read limit")
            return data

        return await asyncio.to_thread(read)

    async def list_keys(self, prefix: str, *, limit: int = 1000) -> list[str]:
        client = await self._client_async()
        raw_prefix = prefix.strip()
        trailing_slash = raw_prefix.endswith("/")
        full_prefix = self._key(raw_prefix.rstrip("/")) + ("/" if trailing_slash else "")
        limit = min(max(1, int(limit)), 5000)

        def listing() -> list[str]:
            result: list[str] = []
            token: str | None = None
            while len(result) < limit:
                kwargs: dict[str, Any] = {
                    "Bucket": self.config.bucket,
                    "Prefix": full_prefix,
                    "MaxKeys": min(1000, limit - len(result)),
                }
                if token:
                    kwargs["ContinuationToken"] = token
                response = client.list_objects_v2(**kwargs)
                for item in response.get("Contents", []):
                    key = str(item.get("Key") or "")
                    root_prefix = self.config.prefix.strip("/")
                    if root_prefix and key.startswith(root_prefix + "/"):
                        key = key[len(root_prefix) + 1 :]
                    result.append(key)
                    if len(result) >= limit:
                        break
                if not response.get("IsTruncated") or len(result) >= limit:
                    break
                token = response.get("NextContinuationToken")
                if not token:
                    break
            return result

        return await asyncio.to_thread(listing)

    async def delete_key(self, key: str) -> None:
        client = await self._client_async()
        await asyncio.to_thread(client.delete_object, Bucket=self.config.bucket, Key=self._key(key))


class DurableReleaseStore:
    """Durable, verified release backups over S3-compatible storage.

    A release is uploaded as a *candidate* before local activation. It gets a small
    `.active.json` marker only after runtime health verification succeeds. That two-phase
    protocol prevents a failed candidate from accidentally becoming `/restore ... latest`.
    """

    def __init__(
        self,
        object_store: S3ObjectStore | Any | None,
        *,
        keep_releases: int = 20,
        signing_key: str | None = None,
    ):
        self.store = object_store
        self.keep_releases = min(max(2, int(keep_releases)), 500)
        self._signing_key = signing_key.encode("utf-8") if signing_key else None

    @property
    def enabled(self) -> bool:
        return bool(self.store and self.store.enabled)

    async def health(self) -> dict[str, Any]:
        if not self.enabled or self.store is None:
            return {"enabled": False, "ok": True, "backend": "none"}
        return await self.store.health()

    @staticmethod
    def _safe_project(project: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", project):
            raise StorageError("Invalid project name")
        return project

    @staticmethod
    def _safe_release(release: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,96}", release):
            raise StorageError("Invalid release name")
        return release

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _archive_tree(root: Path, destination: Path) -> int:
        files = 0
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_symlink():
                    raise StorageError("Refusing to persist a release containing symlinks")
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                if ".." in rel.split("/"):
                    raise StorageError("Unsafe release path")
                archive.write(path, rel)
                files += 1
        return files

    @staticmethod
    def _metadata_bytes(metadata: dict[str, Any]) -> bytes:
        return json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _signature(self, payload: dict[str, Any]) -> str | None:
        if self._signing_key is None:
            return None
        unsigned = dict(payload)
        unsigned.pop("signature", None)
        return hmac.new(self._signing_key, self._metadata_bytes(unsigned), hashlib.sha256).hexdigest()

    def _signed(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        signature = self._signature(result)
        if signature is not None:
            result["signature"] = signature
        return result

    def _verify_signature(self, payload: dict[str, Any], *, label: str) -> None:
        if self._signing_key is None:
            return
        supplied = str(payload.get("signature") or "")
        expected = self._signature(payload) or ""
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise StorageIntegrityError(f"{label} signature verification failed")

    async def backup_release(self, project: str, release: str, release_root: Path) -> dict[str, Any]:
        """Upload a verified candidate. Does not mark it as the active durable release."""
        if not self.enabled or self.store is None:
            raise StorageError("Durable release storage is disabled")
        project = self._safe_project(project)
        release = self._safe_release(release)
        if not release_root.is_dir():
            raise StorageError("Release directory is missing")
        with tempfile.TemporaryDirectory(prefix="titanbox-backup-") as temp_dir:
            archive = Path(temp_dir) / f"{release}.zip"
            files = await asyncio.to_thread(self._archive_tree, release_root, archive)
            sha = await asyncio.to_thread(self._sha256, archive)
            size = archive.stat().st_size
            base = f"releases/{project}/{release}"
            metadata: dict[str, Any] = {
                "version": 1,
                "project": project,
                "release": release,
                "sha256": sha,
                "size": size,
                "files": files,
                "state": "candidate",
                "created_at": int(time.time()),
            }
            metadata = self._signed(metadata)
            try:
                await self.store.put_file(base + ".zip", archive, content_type="application/zip")
                await self.store.put_bytes(base + ".json", self._metadata_bytes(metadata), content_type="application/json")
            except Exception:
                await self.abandon_release(project, release)
                raise
            return metadata

    async def promote_release(self, project: str, release: str) -> dict[str, Any]:
        """Commit a candidate after local activation/health verification succeeds."""
        if not self.enabled or self.store is None:
            raise StorageError("Durable release storage is disabled")
        project = self._safe_project(project)
        release = self._safe_release(release)
        base = f"releases/{project}/{release}"
        try:
            raw = await self.store.get_bytes(base + ".json", max_bytes=100_000)
            metadata = json.loads(raw)
        except Exception as exc:
            raise StorageError("Durable candidate metadata is unavailable") from exc
        if not isinstance(metadata, dict) or metadata.get("project") != project or metadata.get("release") != release:
            raise StorageIntegrityError("Durable candidate metadata identity mismatch")
        self._verify_signature(metadata, label="Durable candidate metadata")
        expected = str(metadata.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise StorageIntegrityError("Durable candidate metadata is invalid")
        metadata["state"] = "active"
        metadata["activated_at"] = int(time.time())
        metadata = self._signed(metadata)
        marker = {
            "version": 1,
            "project": project,
            "release": release,
            "sha256": expected,
            "activated_at": metadata["activated_at"],
        }
        marker = self._signed(marker)
        # Metadata first, marker second. `list_releases()` trusts the marker, so a partial
        # promotion never becomes restorable as an active release.
        await self.store.put_bytes(base + ".json", self._metadata_bytes(metadata), content_type="application/json")
        await self.store.put_bytes(base + ".active.json", self._metadata_bytes(marker), content_type="application/json")
        # The signed latest pointer is part of the durable commit. If this write fails,
        # callers that require durability roll the local release back and abandon the remote
        # candidate. Keeping the pointer in the commit avoids a stale-"latest" ambiguity when
        # deterministic idempotency release names are used by the PostgreSQL job queue.
        await self.store.put_bytes(
            f"releases/{project}/latest.json",
            self._metadata_bytes(marker),
            content_type="application/json",
        )
        # Retention cleanup is best-effort *after* the durable commit. A temporary listing
        # failure must not turn an already-committed release into an ambiguous failed commit.
        try:
            await self.prune(project)
        except Exception:
            pass
        return metadata

    async def abandon_release(self, project: str, release: str) -> None:
        if not self.enabled or self.store is None:
            return
        try:
            project = self._safe_project(project)
            release = self._safe_release(release)
        except StorageError:
            return
        base = f"releases/{project}/{release}"
        for suffix in (".active.json", ".json", ".zip"):
            try:
                await self.store.delete_key(base + suffix)
            except Exception:
                pass

    async def prune(self, project: str) -> None:
        if not self.enabled or self.store is None:
            return
        project = self._safe_project(project)
        releases = await self.list_releases(project, limit=500)
        for release in releases[self.keep_releases :]:
            base = f"releases/{project}/{release}"
            for suffix in (".active.json", ".json", ".zip"):
                try:
                    await self.store.delete_key(base + suffix)
                except Exception:
                    # A successful current backup must not fail because old cleanup failed.
                    pass

    async def _active_marker(self, project: str, release: str) -> dict[str, Any]:
        if not self.enabled or self.store is None:
            raise StorageError("Durable release storage is disabled")
        project = self._safe_project(project)
        release = self._safe_release(release)
        try:
            raw = await self.store.get_bytes(
                f"releases/{project}/{release}.active.json", max_bytes=100_000
            )
            marker = json.loads(raw)
        except Exception as exc:
            raise StorageError("Backup is not an active verified release: activation marker is unavailable") from exc
        if not isinstance(marker, dict):
            raise StorageIntegrityError("Backup activation marker is invalid")
        if marker.get("project") != project or marker.get("release") != release:
            raise StorageIntegrityError("Backup activation marker identity mismatch")
        self._verify_signature(marker, label="Backup activation marker")
        checksum = str(marker.get("sha256") or "")
        activated_at = marker.get("activated_at")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum) or not isinstance(activated_at, int):
            raise StorageIntegrityError("Backup activation marker is invalid")
        return marker

    async def list_projects(self, *, limit: int = 100) -> list[str]:
        """Discover project names that have at least one durable active-marker key."""
        if not self.enabled or self.store is None:
            return []
        limit = min(max(1, int(limit)), 500)
        keys = await self.store.list_keys("releases/", limit=min(limit * 20 + 100, 5000))
        projects: set[str] = set()
        for key in keys:
            parts = key.split("/")
            if len(parts) != 3 or parts[0] != "releases" or not parts[2].endswith(".active.json"):
                continue
            project = parts[1]
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", project):
                projects.add(project)
                if len(projects) >= limit:
                    break
        return sorted(projects, key=str.lower)

    async def list_releases(self, project: str, *, limit: int = 100) -> list[str]:
        if not self.enabled or self.store is None:
            return []
        project = self._safe_project(project)
        limit = min(max(1, int(limit)), 500)
        keys = await self.store.list_keys(f"releases/{project}/", limit=min(limit * 5 + 50, 2500))
        prefix = f"releases/{project}/"
        suffix = ".active.json"
        names: set[str] = set()
        for key in keys:
            if not key.startswith(prefix) or not key.endswith(suffix):
                continue
            name = key[len(prefix) : -len(suffix)]
            if "/" not in name and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,96}", name):
                names.add(name)

        # Release names for persistent jobs are deterministic hashes, so lexical sorting is
        # not a chronology. Read the small signed active markers and sort by activated_at.
        # Invalid/tampered markers are deliberately excluded from restore/prune candidates;
        # direct restore still fails closed through download_archive().
        semaphore = asyncio.Semaphore(8)

        async def marker_row(name: str) -> tuple[int, str] | None:
            async with semaphore:
                try:
                    marker = await self._active_marker(project, name)
                except StorageIntegrityError:
                    # Do not silently hide a signed-marker integrity failure from operators.
                    raise
                except Exception:
                    # A disappeared marker can result from concurrent retention/abandon.
                    return None
                return int(marker["activated_at"]), name

        rows = await asyncio.gather(*(marker_row(name) for name in names))
        valid = [row for row in rows if row is not None]
        valid.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [name for _, name in valid[:limit]]

    async def latest_release(self, project: str) -> str | None:
        if not self.enabled or self.store is None:
            return None
        project = self._safe_project(project)
        # Prefer the signed pointer written as the final step of promotion. If a network
        # ambiguity left it pointing at a release that was subsequently abandoned, fall back
        # to signed active-marker chronology and repair the pointer. Integrity failures never
        # fall back silently.
        try:
            raw = await self.store.get_bytes(f"releases/{project}/latest.json", max_bytes=100_000)
            pointer = json.loads(raw)
        except Exception:
            pointer = None

        if pointer is not None:
            if not isinstance(pointer, dict) or pointer.get("project") != project:
                raise StorageIntegrityError("Latest release pointer identity mismatch")
            self._verify_signature(pointer, label="Latest release pointer")
            release = self._safe_release(str(pointer.get("release") or ""))
            try:
                marker = await self._active_marker(project, release)
            except StorageIntegrityError:
                raise
            except StorageError:
                marker = None
            if marker is not None:
                if marker.get("sha256") != pointer.get("sha256"):
                    raise StorageIntegrityError("Latest release pointer checksum mismatch")
                return release

        releases = await self.list_releases(project, limit=1)
        if not releases:
            try:
                await self.store.delete_key(f"releases/{project}/latest.json")
            except Exception:
                pass
            return None
        release = releases[0]
        # Self-heal a missing/stale pointer. Failure is harmless because active markers remain
        # authoritative and will be checked again on the next restore.
        try:
            marker = await self._active_marker(project, release)
            await self.store.put_bytes(
                f"releases/{project}/latest.json",
                self._metadata_bytes(marker),
                content_type="application/json",
            )
        except StorageIntegrityError:
            raise
        except Exception:
            pass
        return release

    async def download_archive(self, project: str, release: str, destination: Path) -> dict[str, Any]:
        if not self.enabled or self.store is None:
            raise StorageError("Durable release storage is disabled")
        project = self._safe_project(project)
        release = self._safe_release(release)
        base = f"releases/{project}/{release}"
        marker = await self._active_marker(project, release)

        metadata_raw = await self.store.get_bytes(base + ".json", max_bytes=100_000)
        metadata = json.loads(metadata_raw)
        if not isinstance(metadata, dict):
            raise StorageIntegrityError("Backup metadata is invalid")
        self._verify_signature(metadata, label="Backup metadata")
        if metadata.get("project") != project or metadata.get("release") != release or metadata.get("state") != "active":
            raise StorageIntegrityError("Backup metadata identity/state mismatch")
        expected = str(metadata.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise StorageIntegrityError("Backup metadata is invalid")
        if str(marker.get("sha256") or "") != expected:
            raise StorageIntegrityError("Backup activation marker checksum mismatch")
        expected_size = metadata.get("size")
        if not isinstance(expected_size, int) or expected_size < 0:
            raise StorageIntegrityError("Backup metadata size is invalid")
        remote_size = getattr(self.store, "object_size", None)
        if callable(remote_size):
            actual_remote_size = await remote_size(base + ".zip")
            if actual_remote_size != expected_size:
                raise StorageIntegrityError("Backup remote object size verification failed")
        await self.store.get_file(base + ".zip", destination)
        if destination.stat().st_size != expected_size:
            destination.unlink(missing_ok=True)
            raise StorageIntegrityError("Backup size verification failed")
        actual = await asyncio.to_thread(self._sha256, destination)
        if actual != expected:
            destination.unlink(missing_ok=True)
            raise StorageIntegrityError("Backup checksum verification failed")
        return metadata
