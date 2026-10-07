"""레거시 문서 변환 실행기 탐지와 격리된 subprocess 호출."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from AI_Engine.file_extraction.detection import (
    DOC_MIME,
    HWP_MIME,
    PPT_MIME,
)
from AI_Engine.file_extraction.models import FileExtractionError, SourceFile


CONVERSION_TIMEOUT_SECONDS = max(
    15,
    int(os.getenv("AI_DOCUMENT_CONVERSION_TIMEOUT_SECONDS", "90")),
)
LIBREOFFICE_PATHS = (
    Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
    Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
)
HWPX_CONVERTER_PATHS = (
    Path(r"C:\Program Files (x86)\Hnc\Hwp80\HwpToHwpx.exe"),
    Path(r"C:\Program Files\Hnc\Office\HOffice120\Bin\HwpToHwpx.exe"),
)


@dataclass(frozen=True)
class ToolCapability:
    name: str
    available: bool
    command: str | None
    error: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "command": self.command,
            "error": self.error,
        }


def _resolve_command(environment_name: str, binary: str, paths: tuple[Path, ...]) -> str | None:
    configured = os.getenv(environment_name, "").strip()
    if configured:
        return configured if Path(configured).is_file() else None
    discovered = shutil.which(binary)
    if discovered:
        return discovered
    return next((str(path) for path in paths if path.is_file()), None)


def get_libreoffice_capability() -> ToolCapability:
    command = _resolve_command("LIBREOFFICE_CMD", "soffice", LIBREOFFICE_PATHS)
    return ToolCapability(
        name="libreoffice",
        available=command is not None,
        command=command,
        error=None if command else "LibreOffice headless 변환기를 찾을 수 없습니다.",
    )


def get_hwpx_converter_capability() -> ToolCapability:
    command = _resolve_command(
        "HWPX_CONVERTER_CMD",
        "HwpToHwpx",
        HWPX_CONVERTER_PATHS,
    )
    return ToolCapability(
        name="hwp-to-hwpx",
        available=command is not None,
        command=command,
        error=None if command else "한컴 HWP→HWPX 변환기를 찾을 수 없습니다.",
    )


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CONVERSION_TIMEOUT_SECONDS,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
    except subprocess.TimeoutExpired as error:
        raise FileExtractionError("레거시 문서 변환 시간이 초과되었습니다.") from error
    except OSError as error:
        raise FileExtractionError("레거시 문서 변환기를 실행하지 못했습니다.") from error


def convert_legacy_document(file: SourceFile) -> SourceFile:
    if file.mime_type == HWP_MIME:
        return _convert_hwp(file)
    if file.mime_type not in {DOC_MIME, PPT_MIME}:
        raise FileExtractionError("변환 대상 레거시 문서 형식이 아닙니다.")
    capability = get_libreoffice_capability()
    if not capability.available or not capability.command:
        raise FileExtractionError(capability.error or "LibreOffice를 사용할 수 없습니다.")
    output_extension = ".docx" if file.mime_type == DOC_MIME else ".pptx"
    output_filter = "docx" if file.mime_type == DOC_MIME else "pptx"
    with tempfile.TemporaryDirectory(prefix="career-memory-office-") as temporary:
        root = Path(temporary)
        input_path = root / f"input{Path(file.filename).suffix.casefold()}"
        output_dir = root / "output"
        profile_dir = root / "profile"
        output_dir.mkdir()
        profile_dir.mkdir()
        input_path.write_bytes(file.content)
        result = _run([
            capability.command,
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--convert-to",
            output_filter,
            "--outdir",
            str(output_dir),
            str(input_path),
        ], cwd=root)
        converted = next(output_dir.glob(f"*{output_extension}"), None)
        if result.returncode != 0 or converted is None:
            detail = (result.stderr or result.stdout).strip()
            raise FileExtractionError(
                f"LibreOffice가 {file.filename} 변환에 실패했습니다."
                + (f" ({detail[:300]})" if detail else "")
            )
        return SourceFile(
            filename=f"{Path(file.filename).stem}{output_extension}",
            mime_type="",
            content=converted.read_bytes(),
        )


def _convert_hwp(file: SourceFile) -> SourceFile:
    capability = get_hwpx_converter_capability()
    if not capability.available or not capability.command:
        raise FileExtractionError(capability.error or "HWP 변환기를 사용할 수 없습니다.")
    with tempfile.TemporaryDirectory(prefix="career-memory-hwp-") as temporary:
        root = Path(temporary)
        input_path = root / "input.hwp"
        output_dir = root / "output"
        output_dir.mkdir()
        input_path.write_bytes(file.content)
        result = _run(
            [capability.command, str(input_path), str(output_dir)],
            cwd=root,
        )
        converted = next(output_dir.rglob("*.hwpx"), None)
        if result.returncode != 0 or converted is None:
            detail = (result.stderr or result.stdout).strip()
            raise FileExtractionError(
                "한컴 변환기가 HWP를 HWPX로 변환하지 못했습니다."
                + (f" ({detail[:300]})" if detail else "")
            )
        return SourceFile(
            filename=f"{Path(file.filename).stem}.hwpx",
            mime_type="",
            content=converted.read_bytes(),
        )


__all__ = [
    "CONVERSION_TIMEOUT_SECONDS",
    "ToolCapability",
    "convert_legacy_document",
    "get_hwpx_converter_capability",
    "get_libreoffice_capability",
]
