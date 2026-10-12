"""공개 URL을 안전하게 수집해 기존 Attachment/Evidence 파이프라인으로 연결한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import ipaddress
import json
import mimetypes
import os
from pathlib import PurePosixPath
import re
import shutil
import socket
import subprocess
from typing import Callable, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from sqlalchemy.orm import Session

from AI_Engine.attachment_service import attachment_service
from AI_Engine.blob_store import BlobStoreError
from AI_Engine.database.connection import PROJECT_ROOT
from AI_Engine.file_extraction import FileInputError, MAX_FILE_BYTES
from AI_Engine.html_extraction import extract_html


WEB_FETCH_TIMEOUT_SECONDS = max(3.0, float(os.getenv("WEB_FETCH_TIMEOUT_SECONDS", "15")))
WEB_FETCH_MAX_BYTES = min(
    MAX_FILE_BYTES,
    max(1, int(os.getenv("WEB_FETCH_MAX_MIB", "15"))) * 1024 * 1024,
)
WEB_MAX_URLS_PER_INPUT = max(1, min(10, int(os.getenv("WEB_MAX_URLS_PER_INPUT", "5"))))
WEB_MAX_REDIRECTS = max(0, min(10, int(os.getenv("WEB_MAX_REDIRECTS", "5"))))
WEB_RENDER_MIN_TEXT = max(100, int(os.getenv("WEB_RENDER_MIN_TEXT", "500")))
WEB_IMAGE_OCR_TEXT_THRESHOLD = max(
    0,
    int(os.getenv("WEB_IMAGE_OCR_TEXT_THRESHOLD", "700")),
)
WEB_MAX_EMBEDDED_IMAGES = max(
    0,
    min(5, int(os.getenv("WEB_MAX_EMBEDDED_IMAGES", "2"))),
)
USER_AGENT = os.getenv(
    "WEB_FETCH_USER_AGENT",
    "CareerMemory/1.0 (+user-requested public page reader)",
).strip()

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", flags=re.IGNORECASE)
TRAILING_URL_PUNCTUATION = ".,;:!?。，、；：！？'\""
HTML_MIME_TYPES = frozenset({"text/html", "application/xhtml+xml"})
PLAIN_TEXT_MIME_TYPES = frozenset({
    "application/json", "application/ld+json", "application/xml", "text/xml",
    "text/csv",
})
BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost")
CHALLENGE_MARKERS = (
    "access denied",
    "captcha",
    "verify you are human",
    "checking your browser",
    "cloudflare ray id",
    "로그인이 필요",
    "로그인하세요",
)


class WebContentError(ValueError):
    """사용자 URL을 안전하게 읽거나 파싱할 수 없을 때 발생한다."""


@dataclass(frozen=True)
class WebFetchResult:
    requested_url: str
    final_url: str
    filename: str
    mime_type: str
    content: bytes
    status_code: int
    title: str = ""
    render_mode: str = "http"
    image_candidates: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class WebIngestionResult:
    attachment_ids: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def extract_http_urls(*texts: str | None, max_count: int = WEB_MAX_URLS_PER_INPUT) -> list[str]:
    """입력 순서를 유지하면서 http(s) URL만 중복 없이 찾는다."""

    result: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in URL_PATTERN.finditer(text):
            candidate = match.group(0).rstrip(TRAILING_URL_PUNCTUATION)
            while candidate.endswith(")") and candidate.count("(") < candidate.count(")"):
                candidate = candidate[:-1]
            while candidate.endswith("]") and candidate.count("[") < candidate.count("]"):
                candidate = candidate[:-1]
            normalized = normalize_public_url(candidate)
            if normalized not in result:
                result.append(normalized)
            if len(result) >= max_count:
                return result
    return result


def normalize_public_url(value: str) -> str:
    raw = value.strip()
    if len(raw) > 2_048:
        raise WebContentError("링크 주소가 너무 깁니다.")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as error:
        raise WebContentError("링크 주소 형식을 확인해 주세요.") from error
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise WebContentError("http:// 또는 https://로 시작하는 공개 링크만 읽을 수 있습니다.")
    if parsed.username or parsed.password:
        raise WebContentError("아이디나 비밀번호가 포함된 링크는 읽을 수 없습니다.")
    if port is not None and port not in {80, 443}:
        raise WebContentError("웹 링크는 기본 HTTP/HTTPS 포트만 사용할 수 있습니다.")
    host = parsed.hostname.encode("idna").decode("ascii").casefold().rstrip(".")
    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme.casefold(), netloc, parsed.path or "/", parsed.query, ""))


def validate_public_url(
    value: str,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> str:
    """SSRF 방지를 위해 목적지의 모든 DNS 결과가 공인 주소인지 확인한다."""

    normalized = normalize_public_url(value)
    parsed = urlsplit(normalized)
    host = parsed.hostname or ""
    lowered = host.casefold().rstrip(".")
    if lowered == "localhost" or lowered.endswith(BLOCKED_HOST_SUFFIXES):
        raise WebContentError("내부 네트워크나 이 컴퓨터의 주소는 읽을 수 없습니다.")
    try:
        direct_ip = ipaddress.ip_address(lowered)
        addresses = [direct_ip]
    except ValueError:
        try:
            resolved = resolver(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except OSError as error:
            raise WebContentError("링크의 서버 주소를 찾지 못했습니다.") from error
        addresses = []
        for item in resolved:
            try:
                addresses.append(ipaddress.ip_address(item[4][0]))
            except (IndexError, ValueError):
                continue
    if not addresses or any(not address.is_global for address in addresses):
        raise WebContentError("공개 인터넷 페이지가 아닌 주소는 읽을 수 없습니다.")
    return normalized


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, validator: Callable[[str], str]) -> None:
        super().__init__()
        self.validator = validator
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        self.redirect_count += 1
        if self.redirect_count > WEB_MAX_REDIRECTS:
            raise WebContentError("링크가 너무 여러 번 다른 주소로 이동합니다.")
        safe_url = self.validator(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


def _response_mime(content_type: str, content: bytes, final_url: str) -> str:
    declared = content_type.split(";", 1)[0].strip().casefold()
    sample = content[:512].lstrip().lower()
    if declared in HTML_MIME_TYPES or sample.startswith((b"<!doctype html", b"<html")):
        return "text/html"
    if declared.startswith("text/") or declared in PLAIN_TEXT_MIME_TYPES:
        return "text/plain"
    if declared:
        return declared
    guessed, _ = mimetypes.guess_type(urlsplit(final_url).path)
    return guessed or "application/octet-stream"


def _safe_filename(final_url: str, mime_type: str, title: str = "") -> str:
    parsed = urlsplit(final_url)
    raw_name = unquote(PurePosixPath(parsed.path).name)
    stem = title.strip() or PurePosixPath(raw_name).stem or parsed.hostname or "web-page"
    stem = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "-", stem).strip(" .-")[:120]
    suffix = {
        "text/html": ".html",
        "text/plain": ".txt",
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }.get(mime_type)
    if suffix is None:
        suffix = PurePosixPath(raw_name).suffix.casefold() or mimetypes.guess_extension(mime_type) or ".bin"
    return f"{stem or 'web-page'}{suffix}"


def _browser_render_enabled() -> bool:
    configured = os.getenv("WEB_BROWSER_RENDER_ENABLED", "auto").strip().casefold()
    if configured in {"0", "false", "no", "off"}:
        return False
    if configured in {"1", "true", "yes", "on"}:
        return True
    return shutil.which("node") is not None and (
        PROJECT_ROOT / "scripts" / "render-public-page.mjs"
    ).is_file()


def render_public_page(url: str) -> tuple[str, str, str] | None:
    """Playwright가 준비된 환경에서 공개 JS 페이지의 최종 DOM을 가져온다."""

    if not _browser_render_enabled():
        return None
    node = shutil.which("node")
    script = PROJECT_ROOT / "scripts" / "render-public-page.mjs"
    if node is None or not script.is_file():
        return None
    try:
        completed = subprocess.run(
            [node, str(script), url],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=max(10.0, WEB_FETCH_TIMEOUT_SECONDS + 10.0),
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        payload = json.loads(completed.stdout)
        html = str(payload.get("html") or "")
        final_url = validate_public_url(str(payload.get("url") or url))
        title = str(payload.get("title") or "").strip()
    except (json.JSONDecodeError, TypeError, WebContentError):
        return None
    if not html or len(html.encode("utf-8")) > WEB_FETCH_MAX_BYTES:
        return None
    return html, final_url, title


def fetch_public_url(url: str) -> WebFetchResult:
    """프록시·인증 우회 없이 공개 URL 하나를 제한된 크기로 읽는다."""

    requested_url = validate_public_url(url)
    redirect_handler = _SafeRedirectHandler(validate_public_url)
    opener = build_opener(ProxyHandler({}), redirect_handler)
    request = Request(
        requested_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf,image/*,text/plain;q=0.9,*/*;q=0.5",
            "Accept-Encoding": "identity",
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=WEB_FETCH_TIMEOUT_SECONDS) as response:
            final_url = validate_public_url(response.geturl())
            status_code = int(getattr(response, "status", 200) or 200)
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > WEB_FETCH_MAX_BYTES:
                raise WebContentError("링크의 자료가 너무 커서 읽을 수 없습니다.")
            content = response.read(WEB_FETCH_MAX_BYTES + 1)
            if len(content) > WEB_FETCH_MAX_BYTES:
                raise WebContentError("링크의 자료가 너무 커서 읽을 수 없습니다.")
            content_type = response.headers.get("Content-Type", "")
    except WebContentError:
        raise
    except HTTPError as error:
        if error.code in {401, 403}:
            detail = "로그인이나 접근 권한이 필요한 페이지는 읽을 수 없습니다."
        elif error.code == 404:
            detail = "링크의 페이지를 찾지 못했습니다."
        elif error.code == 429:
            detail = "사이트가 잠시 접근을 제한했습니다. 잠시 후 다시 시도해 주세요."
        else:
            detail = f"링크의 페이지를 열지 못했습니다. (HTTP {error.code})"
        raise WebContentError(detail) from error
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise WebContentError("링크의 페이지에 연결하지 못했습니다.") from error
    if not content:
        raise WebContentError("링크의 페이지 내용이 비어 있습니다.")

    mime_type = _response_mime(content_type, content, final_url)
    title = ""
    image_candidates: tuple[str, ...] = ()
    render_mode = "http"
    warnings: list[str] = []
    if mime_type == "text/html":
        extracted = extract_html(content)
        title = extracted.title
        image_candidates = extracted.image_sources
        compact_length = len(re.sub(r"\s+", "", extracted.text))
        force_dynamic = (urlsplit(final_url).hostname or "").casefold().endswith(
            ("notion.site", "notion.so", "notion.com")
        )
        if compact_length < WEB_RENDER_MIN_TEXT or force_dynamic:
            rendered = render_public_page(final_url)
            if rendered is not None:
                rendered_html, rendered_url, rendered_title = rendered
                rendered_content = rendered_html.encode("utf-8")
                rendered_extraction = extract_html(rendered_content)
                if len(re.sub(r"\s+", "", rendered_extraction.text)) > compact_length:
                    content = rendered_content
                    final_url = rendered_url
                    title = rendered_title or rendered_extraction.title or title
                    image_candidates = rendered_extraction.image_sources
                    extracted = rendered_extraction
                    compact_length = len(re.sub(r"\s+", "", extracted.text))
                    render_mode = "browser"
            elif force_dynamic:
                warnings.append("공개 Notion 페이지의 동적 렌더링을 사용할 수 없어 정적 HTML만 읽었습니다.")
        lowered = extracted.text.casefold()
        if compact_length < 1_500 and any(marker in lowered for marker in CHALLENGE_MARKERS):
            raise WebContentError("사이트의 로그인 또는 사람 확인 화면 때문에 본문을 읽지 못했습니다.")
        if compact_length < 20 and not image_candidates:
            raise WebContentError("페이지에서 읽을 수 있는 본문을 찾지 못했습니다.")

    return WebFetchResult(
        requested_url=requested_url,
        final_url=final_url,
        filename=_safe_filename(final_url, mime_type, title),
        mime_type=mime_type,
        content=content,
        status_code=status_code,
        title=title,
        render_mode=render_mode,
        image_candidates=image_candidates,
        warnings=tuple(warnings),
    )


class WebContentService:
    def __init__(
        self,
        *,
        fetcher: Callable[[str], WebFetchResult] = fetch_public_url,
    ) -> None:
        self.fetcher = fetcher

    def ingest(
        self,
        database: Session,
        *,
        user_id: str,
        texts: Sequence[str | None] = (),
        urls: Sequence[str] = (),
        existing_attachment_ids: Sequence[str] = (),
        max_attachments: int = 10,
    ) -> WebIngestionResult:
        requested_urls = extract_http_urls(*texts, *urls)
        if not requested_urls:
            return WebIngestionResult()
        available = max(0, max_attachments - len(set(existing_attachment_ids)))
        if available <= 0:
            raise WebContentError("링크 자료를 추가하려면 첨부 파일을 10개 이하로 줄여 주세요.")

        attachment_ids: list[str] = []
        ingested_urls: list[str] = []
        warnings: list[str] = []
        visited = set(requested_urls)
        for requested_url in requested_urls:
            if len(attachment_ids) >= available:
                raise WebContentError("링크와 파일을 합쳐 최대 10개까지 읽을 수 있습니다.")
            fetched = self.fetcher(requested_url)
            attachment = self._store_fetch(database, user_id=user_id, fetched=fetched)
            if attachment.id not in attachment_ids and attachment.id not in existing_attachment_ids:
                attachment_ids.append(attachment.id)
            ingested_urls.append(fetched.final_url)
            warnings.extend(fetched.warnings)

            extracted_length = len(re.sub(r"\s+", "", attachment.extracted_text or ""))
            if (
                fetched.mime_type != "text/html"
                or extracted_length >= WEB_IMAGE_OCR_TEXT_THRESHOLD
                or not WEB_MAX_EMBEDDED_IMAGES
            ):
                continue
            child_ids: list[str] = []
            for source in fetched.image_candidates:
                if len(child_ids) >= WEB_MAX_EMBEDDED_IMAGES or len(attachment_ids) >= available:
                    break
                image_url = urljoin(fetched.final_url, source)
                if image_url in visited or not image_url.startswith(("http://", "https://")):
                    continue
                visited.add(image_url)
                try:
                    child = self.fetcher(image_url)
                    if not child.mime_type.startswith("image/"):
                        continue
                    child_attachment = self._store_fetch(
                        database,
                        user_id=user_id,
                        fetched=child,
                        parent_url=fetched.final_url,
                    )
                except WebContentError as error:
                    warnings.append(f"페이지 이미지 OCR 생략: {error}")
                    continue
                if (
                    child_attachment.id not in attachment_ids
                    and child_attachment.id not in existing_attachment_ids
                ):
                    attachment_ids.append(child_attachment.id)
                if child_attachment.original_attachment_id is None:
                    child_attachment.original_attachment_id = attachment.id
                    database.commit()
                child_ids.append(child_attachment.id)
            if child_ids:
                metadata = dict(attachment.extraction_metadata or {})
                metadata["embedded_ocr_attachment_ids"] = child_ids
                attachment.extraction_metadata = metadata
                database.commit()
            elif extracted_length < 80 and fetched.image_candidates:
                raise WebContentError(
                    "페이지 본문이 이미지로만 구성되어 있지만 이미지의 글자를 읽지 못했습니다."
                )

        return WebIngestionResult(
            attachment_ids=tuple(attachment_ids),
            urls=tuple(ingested_urls),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _store_fetch(
        database: Session,
        *,
        user_id: str,
        fetched: WebFetchResult,
        parent_url: str | None = None,
    ):
        try:
            ingested = attachment_service.ingest(
                database,
                user_id=user_id,
                filename=fetched.filename,
                mime_type=fetched.mime_type,
                content=fetched.content,
            )
            if ingested.job is not None and ingested.job.status == "queued":
                attachment_service.process_job(database, ingested.job.id)
            database.refresh(ingested.attachment)
        except (FileInputError, BlobStoreError, OSError) as error:
            raise WebContentError(str(error)) from error
        attachment = ingested.attachment
        if attachment.parse_status not in {"ready", "partial"}:
            raise WebContentError(
                attachment.parse_error
                or "링크에서 가져온 자료의 내용을 읽지 못했습니다."
            )
        metadata = dict(attachment.extraction_metadata or {})
        web_sources = list(metadata.get("web_sources") or [])
        source_metadata = {
            "requested_url": fetched.requested_url,
            "final_url": fetched.final_url,
            "http_status": fetched.status_code,
            "render_mode": fetched.render_mode,
            "title": fetched.title,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        if parent_url:
            source_metadata["parent_url"] = parent_url
        if not any(item.get("final_url") == fetched.final_url for item in web_sources):
            web_sources.append(source_metadata)
        metadata.update({
            "source_type": "web_url",
            "web_sources": web_sources,
        })
        attachment.extraction_metadata = metadata
        database.commit()
        database.refresh(attachment)
        return attachment


web_content_service = WebContentService()


def merge_attachment_ids(*groups: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in group if item))


__all__ = [
    "WebContentError",
    "WebContentService",
    "WebFetchResult",
    "WebIngestionResult",
    "extract_http_urls",
    "fetch_public_url",
    "merge_attachment_ids",
    "normalize_public_url",
    "render_public_page",
    "validate_public_url",
    "web_content_service",
]
