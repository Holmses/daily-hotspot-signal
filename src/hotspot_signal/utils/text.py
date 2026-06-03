from __future__ import annotations

from difflib import SequenceMatcher
import re


_PUNCTUATION_RE = re.compile(r"[\s\-_【】\[\]（）()《》<>:：,，.。!！?？/\\|\"'“”‘’]+")


def normalize_title(title: str) -> str:
    lowered = title.lower().strip()
    return _PUNCTUATION_RE.sub("", lowered)


def contains_any(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    return [keyword for keyword in keywords if keyword and keyword.lower() in lowered]


def title_similarity(left: str, right: str) -> float:
    left_norm = normalize_title(left)
    right_norm = normalize_title(right)
    if not left_norm or not right_norm:
        return 0.0
    direct = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_grams = _char_grams(left_norm)
    right_grams = _char_grams(right_norm)
    if not left_grams or not right_grams:
        return direct
    jaccard = len(left_grams & right_grams) / len(left_grams | right_grams)
    return max(direct, jaccard)


def _char_grams(text: str, size: int = 2) -> set[str]:
    if len(text) <= size:
        return {text}
    return {text[index : index + size] for index in range(0, len(text) - size + 1)}


def compact_reason_list(values: list[str], limit: int = 4) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result
