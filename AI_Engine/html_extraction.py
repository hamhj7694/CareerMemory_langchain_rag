"""HTML 원본에서 사용자에게 보이는 본문과 이미지 후보를 결정적으로 추출한다."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import json
import re
from typing import Any


BLOCK_TAGS = frozenset({
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl",
    "dt", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5",
    "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
})
IGNORED_TAGS = frozenset({
    "canvas", "iframe", "noscript", "object", "style", "svg", "template",
})
JSON_SCRIPT_TYPES = frozenset({
    "application/json",
    "application/ld+json",
})
MAX_JSON_TEXT_ITEMS = 500
MAX_IMAGE_SOURCES = 30
VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})


@dataclass(frozen=True)
class HtmlExtraction:
    text: str
    title: str
    image_sources: tuple[str, ...]
    structured_text_count: int = 0


def decode_html_bytes(content: bytes) -> str:
    """BOM과 meta charset을 우선 확인하고 안전한 대체 디코딩을 적용한다."""

    head = content[:4096]
    declared = re.search(
        br"(?:charset\s*=\s*['\"]?)([A-Za-z0-9._-]+)",
        head,
        flags=re.IGNORECASE,
    )
    encodings = []
    if declared:
        encodings.append(declared.group(1).decode("ascii", errors="ignore"))
    encodings.extend(("utf-8-sig", "utf-8", "utf-16", "cp949"))
    for encoding in dict.fromkeys(encodings):
        try:
            return content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


def _style_is_hidden(style: str) -> bool:
    compact = re.sub(r"\s+", "", style).casefold()
    return "display:none" in compact or "visibility:hidden" in compact


def _normalize_lines(parts: list[str]) -> list[str]:
    text = "".join(parts).replace("\u00a0", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines: list[str] = []
    seen_adjacent = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        if line == seen_adjacent:
            continue
        lines.append(line)
        seen_adjacent = line
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _json_text_values(value: Any, result: list[str]) -> None:
    if len(result) >= MAX_JSON_TEXT_ITEMS:
        return
    if isinstance(value, dict):
        for item in value.values():
            _json_text_values(item, result)
    elif isinstance(value, list):
        for item in value:
            _json_text_values(item, result)
    elif isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        if (
            2 <= len(normalized) <= 5_000
            and not normalized.startswith(("http://", "https://", "data:"))
            and not re.fullmatch(r"[A-Za-z0-9_-]{20,}", normalized)
        ):
            result.append(normalized)


class _VisibleHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.image_sources: list[str] = []
        self.skip_depth = 0
        self.hidden_depth = 0
        self.hidden_stack: list[bool] = []
        self.in_title = False
        self.json_script_depth = 0
        self.json_script_parts: list[str] = []
        self.structured_texts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        attributes = {key.casefold(): value or "" for key, value in attrs}
        if tag in IGNORED_TAGS:
            self.skip_depth += 1
            return
        if tag == "script":
            script_type = attributes.get("type", "").split(";", 1)[0].strip().casefold()
            if script_type in JSON_SCRIPT_TYPES or attributes.get("id", "") == "__NEXT_DATA__":
                self.json_script_depth += 1
                self.json_script_parts = []
            else:
                self.skip_depth += 1
            return
        hidden = (
            "hidden" in attributes
            or attributes.get("aria-hidden", "").casefold() == "true"
            or _style_is_hidden(attributes.get("style", ""))
        )
        if tag not in VOID_TAGS:
            self.hidden_stack.append(hidden)
            if hidden:
                self.hidden_depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
                or ""
            ).casefold()
            if key in {"description", "og:title", "og:description", "twitter:title", "twitter:description"}:
                content = attributes.get("content", "").strip()
                if content:
                    self.parts.extend(("\n", content, "\n"))
        if tag == "img" and len(self.image_sources) < MAX_IMAGE_SOURCES:
            source = (
                attributes.get("src")
                or attributes.get("data-src")
                or attributes.get("data-original")
            ).strip()
            if source and source not in self.image_sources:
                self.image_sources.append(source)
            alt = attributes.get("alt", "").strip()
            if alt:
                self.parts.extend(("\n", alt, "\n"))
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in IGNORED_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == "script":
            if self.json_script_depth:
                payload = "".join(self.json_script_parts).strip()
                self.json_script_depth = max(0, self.json_script_depth - 1)
                self.json_script_parts = []
                if payload:
                    try:
                        values: list[str] = []
                        _json_text_values(json.loads(payload), values)
                        self.structured_texts.extend(values)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
            else:
                self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == "title":
            self.in_title = False
        if tag not in VOID_TAGS and self.hidden_stack:
            was_hidden = self.hidden_stack.pop()
            if was_hidden:
                self.hidden_depth = max(0, self.hidden_depth - 1)
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.json_script_depth:
            self.json_script_parts.append(data)
            return
        if self.skip_depth or self.hidden_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        if data.strip():
            self.parts.append(data)


def extract_html(content: bytes | str) -> HtmlExtraction:
    source = decode_html_bytes(content) if isinstance(content, bytes) else content
    parser = _VisibleHtmlParser()
    parser.feed(source)
    parser.close()

    visible_lines = _normalize_lines(parser.parts)
    visible_normalized = {" ".join(line.split()).casefold() for line in visible_lines if line}
    structured_lines = []
    for value in parser.structured_texts:
        normalized = " ".join(value.split()).casefold()
        if normalized and normalized not in visible_normalized:
            structured_lines.append(value)
            visible_normalized.add(normalized)
    if structured_lines:
        if visible_lines:
            visible_lines.extend(("", "[페이지 구조화 데이터]"))
        visible_lines.extend(structured_lines)

    return HtmlExtraction(
        text="\n".join(visible_lines).strip(),
        title=" ".join(" ".join(parser.title_parts).split()).strip(),
        image_sources=tuple(parser.image_sources),
        structured_text_count=len(structured_lines),
    )


__all__ = ["HtmlExtraction", "decode_html_bytes", "extract_html"]
