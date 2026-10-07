"""파일 추출 정답 세트에서 재사용하는 품질 KPI 계산기."""

from __future__ import annotations

import re


def _edit_distance(expected: list[str], actual: list[str]) -> int:
    previous = list(range(len(actual) + 1))
    for row, expected_item in enumerate(expected, start=1):
        current = [row]
        for column, actual_item in enumerate(actual, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (expected_item != actual_item),
            ))
        previous = current
    return previous[-1]


def character_error_rate(expected: str, actual: str) -> float:
    expected_chars = list(expected)
    if not expected_chars:
        return 0.0 if not actual else 1.0
    return _edit_distance(expected_chars, list(actual)) / len(expected_chars)


def word_error_rate(expected: str, actual: str) -> float:
    expected_words = expected.split()
    if not expected_words:
        return 0.0 if not actual.split() else 1.0
    return _edit_distance(expected_words, actual.split()) / len(expected_words)


def numeric_token_recall(expected: str, actual: str) -> float:
    pattern = re.compile(r"(?:\d+(?:[.,]\d+)?%?|\d+\s*[~～-]\s*\d+\s*년)")
    expected_tokens = pattern.findall(expected)
    if not expected_tokens:
        return 1.0
    actual_tokens = set(pattern.findall(actual))
    return sum(token in actual_tokens for token in expected_tokens) / len(expected_tokens)


__all__ = ["character_error_rate", "numeric_token_recall", "word_error_rate"]
