"""파일 추출 계층이 공유하는 입력·결과 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


class FileInputError(ValueError):
    """파일 형식, 크기 또는 컨테이너가 허용 정책에 맞지 않는다."""


class FileExtractionError(RuntimeError):
    """허용된 파일이지만 근거 텍스트를 안전하게 추출하지 못했다."""


@dataclass(frozen=True)
class SourceFile:
    filename: str
    mime_type: str
    content: bytes


@dataclass(frozen=True)
class ExtractionSegment:
    text: str
    locator: dict[str, Any] = field(default_factory=dict)
    method: Literal["native", "ocr", "hybrid", "converted", "stt"] = "native"
    confidence: float | None = None


@dataclass(frozen=True)
class FileExtractionResult:
    """원문까지 역추적할 수 있는 파일별 결정론적 추출 결과."""

    filename: str
    mime_type: str
    text: str
    segments: tuple[ExtractionSegment, ...] = ()
    extraction_method: Literal[
        "native", "ocr", "hybrid", "converted", "stt"
    ] = "native"
    quality_score: float | None = None
    warnings: tuple[str, ...] = ()
    parser_name: str = "unknown"
    parser_version: str = "career-file-parser-v2"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_partial(self) -> bool:
        return bool(self.warnings) or (
            self.quality_score is not None and self.quality_score < 0.65
        )

    def metadata_payload(self) -> dict[str, Any]:
        return {
            "extraction_method": self.extraction_method,
            "quality_score": self.quality_score,
            "warnings": list(self.warnings),
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "segments": [
                {
                    "locator": segment.locator,
                    "method": segment.method,
                    "confidence": segment.confidence,
                    "text_length": len(segment.text),
                }
                for segment in self.segments
            ],
            **self.metadata,
        }


__all__ = [
    "ExtractionSegment",
    "FileExtractionError",
    "FileExtractionResult",
    "FileInputError",
    "SourceFile",
]
