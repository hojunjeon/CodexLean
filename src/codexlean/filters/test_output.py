from __future__ import annotations

import re

from ..models import Candidate, CompressionRequest, Profile
from ..quality import extract_critical_lines
from ..textutil import (
    collapse_consecutive_duplicates,
    merge_windows,
    render_windows,
    strip_ansi,
)

_FAILURE_RE = re.compile(
    r"(?:\b(?:fail(?:ed|ure|ures)?|error|exception|traceback|panic|assert(?:ion)?)\b|"
    r"^E\s+|^F\s+|^_{2,}\s*.*\s*_{2,}$|^={2,}\s*(?:FAILURES?|ERRORS?)\s*={2,})",
    re.IGNORECASE,
)
_SUMMARY_RE = re.compile(
    r"(?:\b\d+\s+(?:passed|failed|skipped|xfailed|xpassed|warnings?|tests?)\b|"
    r"^(?:test suites|tests|snapshots|time|ran all test suites)\s*:|"
    r"^test result:|^failures:|^successfully ran|^build (?:succeeded|failed)|"
    r"^finished test|^ok\s|^FAIL\s)",
    re.IGNORECASE,
)
_PROGRESS_ONLY_RE = re.compile(r"^[.sFxXEP]+\s*(?:\[[^]]+\])?\s*$")
_LOCATION_RE = re.compile(r"(?:[A-Za-z0-9_.\-/\\]+:\d+(?::\d+)?|-->\s+[^:]+:\d+:\d+)")


class TestFilter:
    def compress(self, text: str, request: CompressionRequest, confidence: float) -> Candidate:
        normalized = strip_ansi(text).replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.splitlines()
        collapsed, duplicate_removed = collapse_consecutive_duplicates(lines)

        # STRICT removes only pure progress streams and exact repeats.
        if request.profile is Profile.STRICT:
            out: list[str] = []
            progress_count = 0
            for line in collapsed:
                if _PROGRESS_ONLY_RE.fullmatch(line.strip()) and len(line.strip()) >= 10:
                    progress_count += len(line.strip())
                    continue
                out.append(line)
            if progress_count:
                out.append(f"… {progress_count} test progress markers collapsed …")
            return Candidate(
                text="\n".join(out),
                kind="test",
                omitted_lines=duplicate_removed + (1 if progress_count else 0),
                critical_lines=extract_critical_lines(normalized, request.exit_code),
                notes=("test progress collapse",),
                confidence=confidence,
            )

        failed = request.exit_code != 0 or any(_FAILURE_RE.search(line) for line in lines)
        summary_indices = [i for i, line in enumerate(lines) if _SUMMARY_RE.search(line.strip())]
        critical_indices = [i for i, line in enumerate(lines) if _FAILURE_RE.search(line)]
        location_indices = [i for i, line in enumerate(lines) if _LOCATION_RE.search(line)]

        if failed:
            # Keep complete local failure context, traceback neighborhoods, locations,
            # command preamble, and runner summary. Guard later verifies every decisive line.
            indices = set(range(min(6, len(lines))))
            indices.update(summary_indices)
            indices.update(critical_indices)
            indices.update(location_indices)
            indices.update(range(max(0, len(lines) - 20), len(lines)))
            radius = 4 if request.profile is Profile.SAFE else 2
            windows = merge_windows(indices, radius=radius, size=len(lines))
            rendered, omitted = render_windows(lines, windows)
            return Candidate(
                text=rendered,
                kind="test",
                omitted_lines=omitted,
                critical_lines=extract_critical_lines(normalized, request.exit_code),
                notes=("failure-focused test output",),
                confidence=confidence,
            )

        # Passing runs: retain environment preamble, warnings, and all summaries.
        warning_indices = [
            i
            for i, line in enumerate(lines)
            if re.search(r"\bwarn(?:ing)?\b|deprecated", line, re.IGNORECASE)
        ]
        indices = set(range(min(5, len(lines))))
        indices.update(summary_indices)
        indices.update(warning_indices)
        indices.update(range(max(0, len(lines) - 12), len(lines)))
        radius = 2 if request.profile is Profile.SAFE else 1
        windows = merge_windows(indices, radius=radius, size=len(lines))
        rendered, omitted = render_windows(lines, windows)
        return Candidate(
            text=rendered,
            kind="test",
            omitted_lines=omitted,
            critical_lines=tuple(lines[i] for i in warning_indices),
            notes=("passing-test summary",),
            confidence=confidence,
        )
