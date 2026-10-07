"""FFmpeg 정규화와 OpenAI 파일 전사 기반 음성·영상 근거 추출."""

from __future__ import annotations

from dataclasses import dataclass
from io import BufferedReader
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from AI_Engine.file_extraction.models import (
    ExtractionSegment,
    FileExtractionError,
    FileExtractionResult,
    SourceFile,
)


load_dotenv()

FFMPEG_PATHS = (
    Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
    Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
)
FFPROBE_PATHS = tuple(path.with_name("ffprobe.exe") for path in FFMPEG_PATHS)
MEDIA_TIMEOUT_SECONDS = max(30, int(os.getenv("AI_MEDIA_TIMEOUT_SECONDS", "180")))
OPENAI_AUDIO_LIMIT_BYTES = 25 * 1024 * 1024
STT_MODEL = os.getenv("AI_STT_MODEL", "whisper-1").strip() or "whisper-1"


@dataclass(frozen=True)
class MediaCapability:
    ffmpeg: str | None
    ffprobe: str | None
    stt_provider: str
    stt_model: str
    api_key_configured: bool

    @property
    def available(self) -> bool:
        return bool(self.ffmpeg and self.ffprobe and self.api_key_configured)

    def payload(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "ffmpeg": self.ffmpeg,
            "ffprobe": self.ffprobe,
            "stt_provider": self.stt_provider,
            "stt_model": self.stt_model,
            "api_key_configured": self.api_key_configured,
        }


def _command(environment_name: str, binary: str, paths: tuple[Path, ...]) -> str | None:
    configured = os.getenv(environment_name, "").strip()
    if configured:
        return configured if Path(configured).is_file() else None
    discovered = shutil.which(binary)
    if discovered:
        return discovered
    known = next((str(path) for path in paths if path.is_file()), None)
    if known:
        return known
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return None
    winget_root = Path(local_app_data) / "Microsoft" / "WinGet"
    linked = winget_root / "Links" / f"{binary}.exe"
    if linked.is_file():
        return str(linked)
    packages = winget_root / "Packages"
    try:
        candidates = sorted(
            path
            for package in packages.glob("*FFmpeg*")
            for path in package.rglob(f"{binary}.exe")
            if path.is_file()
        )
    except OSError:
        return None
    return str(candidates[-1]) if candidates else None


def get_media_capability() -> MediaCapability:
    return MediaCapability(
        ffmpeg=_command("FFMPEG_CMD", "ffmpeg", FFMPEG_PATHS),
        ffprobe=_command("FFPROBE_CMD", "ffprobe", FFPROBE_PATHS),
        stt_provider="openai",
        stt_model=STT_MODEL,
        api_key_configured=bool(os.getenv("OPENAI_API_KEY", "").strip()),
    )


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=MEDIA_TIMEOUT_SECONDS,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
    except subprocess.TimeoutExpired as error:
        raise FileExtractionError("음성·영상 정규화 시간이 초과되었습니다.") from error
    except OSError as error:
        raise FileExtractionError("FFmpeg 실행에 실패했습니다.") from error


def _probe(ffprobe: str, input_path: Path) -> dict[str, Any]:
    result = _run([
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,codec_name,duration",
        "-of", "json",
        str(input_path),
    ])
    if result.returncode != 0:
        raise FileExtractionError("FFprobe가 음성·영상 컨테이너를 확인하지 못했습니다.")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise FileExtractionError("FFprobe 결과 형식이 올바르지 않습니다.") from error


def _normalise_audio(ffmpeg: str, input_path: Path, output_path: Path) -> None:
    result = _run([
        ffmpeg,
        "-nostdin",
        "-v", "error",
        "-y",
        "-i", str(input_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        str(output_path),
    ])
    if result.returncode != 0 or not output_path.is_file():
        detail = (result.stderr or result.stdout).strip()
        raise FileExtractionError(
            "FFmpeg가 전사용 음성을 만들지 못했습니다."
            + (f" ({detail[:300]})" if detail else "")
        )
    if output_path.stat().st_size > OPENAI_AUDIO_LIMIT_BYTES:
        raise FileExtractionError(
            "정규화된 음성이 전사 API의 25MB 한도를 초과합니다. 구간 분할이 필요합니다."
        )


def _attribute(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _transcribe(audio: BufferedReader, filename: str) -> tuple[str, tuple[ExtractionSegment, ...], dict]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise FileExtractionError("OPENAI_API_KEY가 없어 음성·영상 STT를 실행할 수 없습니다.")
    if STT_MODEL != "whisper-1":
        raise FileExtractionError(
            "현재 타임스탬프 근거 모드는 AI_STT_MODEL=whisper-1만 지원합니다."
        )
    try:
        response = OpenAI(api_key=api_key).audio.transcriptions.create(
            file=(filename, audio, "audio/mpeg"),
            model=STT_MODEL,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    except Exception as error:  # SDK별 HTTP 예외를 공개 계층에서 동일하게 처리한다.
        raise FileExtractionError("OpenAI 음성 전사 요청에 실패했습니다.") from error

    text = str(_attribute(response, "text", "") or "").strip()
    raw_segments = _attribute(response, "segments", ()) or ()
    segments: list[ExtractionSegment] = []
    for item in raw_segments:
        segment_text = str(_attribute(item, "text", "") or "").strip()
        if not segment_text:
            continue
        start = float(_attribute(item, "start", 0.0) or 0.0)
        end = float(_attribute(item, "end", start) or start)
        segments.append(ExtractionSegment(
            text=segment_text,
            locator={
                "start_ms": round(start * 1000),
                "end_ms": round(end * 1000),
            },
            method="stt",
        ))
    if not text:
        text = "\n".join(segment.text for segment in segments).strip()
    if not text:
        raise FileExtractionError("음성에서 전사 가능한 발화를 찾지 못했습니다.")
    if not segments:
        duration = float(_attribute(response, "duration", 0.0) or 0.0)
        segments.append(ExtractionSegment(
            text=text,
            locator={"start_ms": 0, "end_ms": round(duration * 1000)},
            method="stt",
        ))
    return text, tuple(segments), {
        "provider": "openai",
        "model": STT_MODEL,
        "language": _attribute(response, "language"),
    }


def parse_media(file: SourceFile, *, parser_version: str) -> FileExtractionResult:
    capability = get_media_capability()
    if not capability.ffmpeg or not capability.ffprobe:
        raise FileExtractionError("FFmpeg와 FFprobe를 찾을 수 없어 미디어를 처리할 수 없습니다.")
    suffix = Path(file.filename).suffix.casefold() or ".bin"
    with tempfile.TemporaryDirectory(prefix="career-memory-media-") as temporary:
        root = Path(temporary)
        input_path = root / f"input{suffix}"
        output_path = root / "audio.mp3"
        input_path.write_bytes(file.content)
        probe = _probe(capability.ffprobe, input_path)
        streams = probe.get("streams") or []
        if not any(stream.get("codec_type") == "audio" for stream in streams):
            raise FileExtractionError("음성 track이 없는 미디어 파일입니다.")
        duration_seconds = float((probe.get("format") or {}).get("duration") or 0.0)
        _normalise_audio(capability.ffmpeg, input_path, output_path)
        with output_path.open("rb") as audio:
            text, segments, metadata = _transcribe(audio, output_path.name)
    return FileExtractionResult(
        filename=file.filename,
        mime_type=file.mime_type,
        text=text,
        segments=segments,
        extraction_method="stt",
        quality_score=None,
        warnings=(),
        parser_name="openai-stt",
        parser_version=parser_version,
        metadata={
            **metadata,
            "duration_ms": round(duration_seconds * 1000),
            "stream_count": len(streams),
        },
    )


__all__ = [
    "MediaCapability",
    "OPENAI_AUDIO_LIMIT_BYTES",
    "STT_MODEL",
    "get_media_capability",
    "parse_media",
]
