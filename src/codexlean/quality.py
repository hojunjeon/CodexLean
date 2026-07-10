from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Candidate, CompressionRequest
from .textutil import normalize_line, strip_ansi

_CRITICAL_RE = re.compile(
    r"(?:\b(?:error|fatal|critical|panic|exception|traceback|failed|failure|assert(?:ion)?|segfault|denied|timeout)\b|"
    r"(?:^|\s)(?:E\s+|F\s+)|"
    r"(?:^|\s)(?:[A-Za-z0-9_./\\-]+:\d+(?::\d+)?)|"
    r"(?:exit(?:ed)?\s+(?:code|status)\s*[:=]?\s*[1-9]\d*))",
    re.IGNORECASE,
)
_SECRET_RE = re.compile(
    r"(?:"
    r"(?:api[_-]?key|access[_-]?key|access[_-]?token|auth[_-]?token|"
    r"client[_-]?secret|private[_-]?key|secret|token|password|passwd|"
    r"authorization|credential|database[_-]?url)\s*[:=]\s*\S+"
    r"|\bauthorization\s*:\s*bearer\s+\S+"
    r"|\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b(?:sk|rk)-[A-Za-z0-9_-]{16,}"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GuardDecision:
    passed: bool
    reason: str | None = None


def extract_critical_lines(text: str, exit_code: int) -> tuple[str, ...]:
    lines = []
    for line in text.splitlines():
        normalized = normalize_line(line)
        if _CRITICAL_RE.search(normalized):
            lines.append(normalized)
    if exit_code != 0 and not lines:
        # A failing command with no recognizable decisive line is unsafe to trim.
        return ()
    # Stable order, no duplicates.
    return tuple(dict.fromkeys(lines))


def contains_probable_secret(text: str) -> bool:
    return bool(_SECRET_RE.search(text))


def validate_candidate(
    request: CompressionRequest,
    raw_text: str,
    candidate: Candidate,
    retrieval_available: bool,
) -> GuardDecision:
    compact = strip_ansi(candidate.text)

    if request.exit_code != 0:
        raw_critical = extract_critical_lines(raw_text, request.exit_code)
        if not raw_critical:
            return GuardDecision(False, "non-zero exit without identifiable decisive lines")
        for line in raw_critical:
            if line not in compact:
                return GuardDecision(False, f"critical line omitted: {line[:120]}")

    for line in candidate.critical_lines:
        normalized = normalize_line(line)
        if normalized and normalized not in compact:
            return GuardDecision(False, f"filter-declared critical line omitted: {normalized[:120]}")

    for line in candidate.protected_lines:
        normalized = normalize_line(line)
        if normalized and normalized not in compact:
            return GuardDecision(False, f"protected line omitted: {normalized[:120]}")

    if candidate.omitted_lines > 0 and not retrieval_available:
        return GuardDecision(False, "omission without exact-retrieval store")

    if candidate.confidence < 0.72 and candidate.omitted_lines > 0:
        return GuardDecision(False, "format confidence too low for selective omission")

    if not candidate.text.strip() and raw_text.strip():
        return GuardDecision(False, "candidate became empty")

    return GuardDecision(True)
