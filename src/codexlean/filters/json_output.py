from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from ..models import Candidate, CompressionRequest, Profile
from ..textutil import strip_ansi

_CRITICAL_VALUE_RE = re.compile(
    r"\b(?:error|fatal|critical|panic|exception|failed|failure|denied|timeout)\b",
    re.IGNORECASE,
)
_STRONG_CRITICAL_KEYS = {
    "error",
    "errors",
    "exception",
    "fatal",
    "failed",
    "failure",
    "exit_code",
}
_STATUS_KEYS = {"status", "state", "result", "code", "message", "reason"}


def _contains_critical(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_CRITICAL_VALUE_RE.search(value))
    if isinstance(value, dict):
        for key, child in value.items():
            key_lower = str(key).lower()
            if key_lower in _STRONG_CRITICAL_KEYS:
                if isinstance(child, bool):
                    if child:
                        return True
                elif child not in (None, "", 0, [], {}):
                    return True
            if key_lower in _STATUS_KEYS and isinstance(child, str) and _CRITICAL_VALUE_RE.search(child):
                return True
            if key_lower == "exit_code" and isinstance(child, int) and child != 0:
                return True
            if _contains_critical(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_critical(v) for v in value)
    return False


def _critical_strings(value: Any, output: list[str]) -> None:
    if isinstance(value, str) and _CRITICAL_VALUE_RE.search(value):
        output.append(value)
    elif isinstance(value, dict):
        for key, child in value.items():
            key_lower = str(key).lower()
            if isinstance(child, (str, int, float, bool)):
                if key_lower in _STRONG_CRITICAL_KEYS and child not in (None, "", 0, False):
                    output.append(str(child))
                elif key_lower in _STATUS_KEYS and isinstance(child, str) and _CRITICAL_VALUE_RE.search(child):
                    output.append(child)
                elif key_lower == "exit_code" and isinstance(child, int) and child != 0:
                    output.append(str(child))
            _critical_strings(child, output)
    elif isinstance(value, list):
        for child in value:
            _critical_strings(child, output)


def _numeric_summary(items: list[Any]) -> dict[str, dict[str, float]]:
    keys: Counter[str] = Counter()
    for item in items:
        if isinstance(item, dict):
            for key, value in item.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    keys[str(key)] += 1
    result: dict[str, dict[str, float]] = {}
    for key, count in keys.items():
        if count < max(3, len(items) // 3):
            continue
        values = [
            float(item[key])
            for item in items
            if isinstance(item, dict)
            and key in item
            and isinstance(item[key], (int, float))
            and not isinstance(item[key], bool)
        ]
        if values:
            result[key] = {
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
            }
    return result


def _compress_value(value: Any, profile: Profile, depth: int = 0) -> tuple[Any, int]:
    if depth > 8:
        return {"_codexlean": "nested value available in artifact"}, 1
    if isinstance(value, list):
        cap = 12 if profile is Profile.SAFE else 6
        if len(value) <= cap:
            out = []
            omitted = 0
            for child in value:
                compact, child_omitted = _compress_value(child, profile, depth + 1)
                out.append(compact)
                omitted += child_omitted
            return out, omitted

        selected_indices: list[int] = list(range(min(3, len(value))))
        selected_indices += list(range(max(0, len(value) - 2), len(value)))
        selected_indices += [i for i, child in enumerate(value) if _contains_critical(child)]
        selected_indices = sorted(dict.fromkeys(selected_indices))
        if len(selected_indices) > cap:
            critical_indices = [i for i in selected_indices if _contains_critical(value[i])]
            remaining = [i for i in selected_indices if i not in critical_indices]
            selected_indices = sorted((critical_indices + remaining)[:cap])

        samples = []
        omitted = len(value) - len(selected_indices)
        for index in selected_indices:
            compact, child_omitted = _compress_value(value[index], profile, depth + 1)
            samples.append({"_index": index, "value": compact})
            omitted += child_omitted
        summary: dict[str, Any] = {
            "_codexlean_array": {
                "total_items": len(value),
                "sampled_items": len(selected_indices),
                "samples": samples,
            }
        }
        numeric = _numeric_summary(value)
        if numeric:
            summary["_codexlean_array"]["numeric_fields"] = numeric
        return summary, omitted

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        omitted = 0
        for key, child in value.items():
            compact, child_omitted = _compress_value(child, profile, depth + 1)
            out[str(key)] = compact
            omitted += child_omitted
        return out, omitted

    return value, 0


class JsonFilter:
    def compress(self, text: str, request: CompressionRequest, confidence: float) -> Candidate:
        normalized = strip_ansi(text)
        try:
            value = json.loads(normalized)
        except Exception:
            from .generic import GenericFilter

            candidate = GenericFilter().compress(normalized, request, confidence)
            candidate.kind = "json"
            return candidate

        if request.profile is Profile.STRICT:
            # Whitespace-only minification is lossless at the JSON data-model level.
            compact = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            return Candidate(
                text=compact,
                kind="json",
                omitted_lines=0,
                notes=("JSON whitespace minification",),
                confidence=confidence,
            )

        compressed, omitted = _compress_value(value, request.profile)
        rendered = json.dumps(compressed, ensure_ascii=False, indent=2, sort_keys=False)
        critical: list[str] = []
        _critical_strings(value, critical)
        return Candidate(
            text=rendered,
            kind="json",
            omitted_lines=omitted,
            critical_lines=tuple(dict.fromkeys(critical)),
            notes=("JSON structural sampling", "critical-value preservation"),
            confidence=confidence,
        )
