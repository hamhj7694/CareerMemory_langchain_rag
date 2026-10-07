"""첨부 원본을 DB 밖에 보존하는 교체 가능한 로컬 Blob 저장소."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

from AI_Engine.database.connection import PROJECT_ROOT


class BlobStoreError(RuntimeError):
    """원본 저장·조회·삭제가 안전하게 완료되지 않았다."""


def _safe_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return normalized[:100] or "unknown"


def _safe_suffix(filename: str) -> str:
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.casefold()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else ""


@dataclass(frozen=True)
class StoredBlob:
    backend: str
    key: str
    size_bytes: int
    content_hash: str


class LocalBlobStore:
    backend = "local"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self.root / PurePosixPath(key)).resolve()
        if not candidate.is_relative_to(self.root):
            raise BlobStoreError("허용되지 않은 원본 저장 경로입니다.")
        return candidate

    def put(
        self,
        *,
        user_id: str,
        attachment_id: str,
        filename: str,
        content: bytes,
        content_hash: str,
    ) -> StoredBlob:
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != content_hash:
            raise BlobStoreError("저장하려는 원본의 SHA-256 해시가 일치하지 않습니다.")
        user_partition = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
        key = "/".join((
            user_partition,
            content_hash[:2],
            _safe_component(attachment_id),
            f"original{_safe_suffix(filename)}",
        ))
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = target.read_bytes()
            if hashlib.sha256(existing).hexdigest() != content_hash:
                raise BlobStoreError("같은 저장 키에 다른 원본이 존재합니다.")
            return StoredBlob(self.backend, key, len(existing), content_hash)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=".upload-",
                delete=False,
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, target)
        except OSError as error:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise BlobStoreError("첨부 원본을 로컬 저장소에 기록하지 못했습니다.") from error
        return StoredBlob(self.backend, key, len(content), content_hash)

    def read(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as error:
            raise BlobStoreError("저장된 첨부 원본을 읽지 못했습니다.") from error

    def delete(self, key: str) -> None:
        target = self._path(key)
        try:
            target.unlink(missing_ok=True)
        except OSError as error:
            raise BlobStoreError("첨부 원본을 삭제하지 못했습니다.") from error

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


def attachment_storage_root() -> Path:
    configured = os.getenv("ATTACHMENT_STORAGE_ROOT", "").strip()
    return Path(configured) if configured else PROJECT_ROOT / "data" / "uploads"


@lru_cache(maxsize=1)
def get_blob_store() -> LocalBlobStore:
    return LocalBlobStore(attachment_storage_root())


def clear_blob_store_cache() -> None:
    get_blob_store.cache_clear()


def read_attachment_bytes(attachment: object) -> bytes:
    backend = str(getattr(attachment, "storage_backend", "database") or "database")
    key = getattr(attachment, "storage_key", None)
    if backend == "local" and key:
        return get_blob_store().read(str(key))
    content = getattr(attachment, "content", b"")
    if isinstance(content, bytes):
        return content
    return bytes(content or b"")


__all__ = [
    "BlobStoreError",
    "LocalBlobStore",
    "StoredBlob",
    "attachment_storage_root",
    "clear_blob_store_cache",
    "get_blob_store",
    "read_attachment_bytes",
]
