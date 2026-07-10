from __future__ import annotations

import re
from collections.abc import Iterable

ANSI_RE = re.compile(
    r"(?:\x1B[@-_][0-?]*[ -/]*[@-~])|(?:\x1B\][^\x07]*(?:\x07|\x1B\\))"
)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TIMESTAMP_RE = re.compile(
    r"(?:\b\d{4}-\d{2}-\d{2}[T ][0-9:.+\-Z]+\b)|(?:\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b)"
)
HEX_ID_RE = re.compile(r"\b(?:0x)?[0-9a-fA-F]{8,}\b")
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
NUMBER_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?(?![A-Za-z_])")


def decode(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


def encode(text: str) -> bytes:
    return text.encode("utf-8", "surrogateescape")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def normalize_line(line: str) -> str:
    return strip_ansi(line).rstrip("\r\n")


def visible_lines(text: str) -> list[str]:
    return [normalize_line(line) for line in text.splitlines()]


def is_binary(raw: bytes) -> bool:
    if not raw:
        return False
    if b"\x00" in raw:
        return True
    sample = raw[:8192]
    controls = sum(1 for b in sample if b < 9 or (13 < b < 32))
    return controls / max(1, len(sample)) > 0.03


def compact_template(line: str) -> str:
    """Normalize volatile values for grouping repeated log templates."""

    value = strip_ansi(line).strip()
    value = UUID_RE.sub("<uuid>", value)
    value = TIMESTAMP_RE.sub("<time>", value)
    value = HEX_ID_RE.sub("<id>", value)
    value = NUMBER_RE.sub("<n>", value)
    return value


def merge_windows(indices: Iterable[int], radius: int, size: int) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    for idx in sorted(set(indices)):
        start = max(0, idx - radius)
        end = min(size, idx + radius + 1)
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))
    return windows


def render_windows(lines: list[str], windows: list[tuple[int, int]]) -> tuple[str, int]:
    if not windows:
        return "", len(lines)
    out: list[str] = []
    cursor = 0
    omitted = 0
    for start, end in windows:
        if start > cursor:
            gap = start - cursor
            omitted += gap
            out.append(f"… {gap} lines omitted …")
        out.extend(lines[start:end])
        cursor = end
    if cursor < len(lines):
        gap = len(lines) - cursor
        omitted += gap
        out.append(f"… {gap} lines omitted …")
    return "\n".join(out), omitted


def collapse_consecutive_duplicates(lines: list[str]) -> tuple[list[str], int]:
    if not lines:
        return [], 0
    out: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        j = i + 1
        while j < len(lines) and lines[j] == line:
            j += 1
        count = j - i
        out.append(line)
        if count > 1:
            out.append(f"… previous line repeated {count - 1} more times …")
            removed += count - 1
        i = j
    return out, removed
