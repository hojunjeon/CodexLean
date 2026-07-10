from __future__ import annotations

import re
from collections import OrderedDict

from ..models import Candidate, CompressionRequest, Profile
from ..quality import extract_critical_lines
from ..textutil import (
    collapse_consecutive_duplicates,
    compact_template,
    merge_windows,
    render_windows,
    strip_ansi,
)

_PROGRESS_RE = re.compile(
    r"(?:\b\d{1,3}%\b|\[[#=*>.\- ]{5,}\]|(?:downloading|uploading|building|compiling|processing)\b.*\d)",
    re.IGNORECASE,
)


class GenericFilter:
    def compress(self, text: str, request: CompressionRequest, confidence: float) -> Candidate:
        normalized = strip_ansi(text).replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.splitlines()
        collapsed, removed = collapse_consecutive_duplicates(lines)

        if request.profile is Profile.STRICT:
            return Candidate(
                text="\n".join(collapsed),
                kind="generic",
                omitted_lines=removed,
                critical_lines=extract_critical_lines(normalized, request.exit_code),
                notes=("consecutive duplicate collapse",) if removed else (),
                confidence=confidence,
            )

        # Collapse noisy progress families while preserving the first and final state.
        out: list[str] = []
        progress_groups: OrderedDict[str, list[str]] = OrderedDict()
        progress_positions: dict[str, int] = {}
        for line in collapsed:
            if _PROGRESS_RE.search(line):
                key = compact_template(line)
                progress_groups.setdefault(key, []).append(line)
                if key not in progress_positions:
                    progress_positions[key] = len(out)
                    out.append(line)
                else:
                    out[progress_positions[key]] = progress_groups[key][-1]
            else:
                out.append(line)

        progress_removed = sum(max(0, len(v) - 1) for v in progress_groups.values())
        if progress_removed:
            out.append(f"… {progress_removed} intermediate progress lines collapsed …")

        omitted = removed + progress_removed
        if request.profile is Profile.MAX and len(out) > 120:
            critical = extract_critical_lines(normalized, request.exit_code)
            indices = [
                i
                for i, line in enumerate(out)
                if any(c and c in line for c in critical)
            ]
            indices.extend(range(min(8, len(out))))
            indices.extend(range(max(0, len(out) - 16), len(out)))
            windows = merge_windows(indices, radius=2, size=len(out))
            rendered, additionally_omitted = render_windows(out, windows)
            return Candidate(
                text=rendered,
                kind="generic",
                omitted_lines=omitted + additionally_omitted,
                critical_lines=critical,
                notes=("duplicate/progress collapse", "head-tail critical windowing"),
                confidence=max(confidence, 0.85),
            )

        effective_confidence = 1.0 if removed and not progress_removed else max(confidence, 0.85)
        return Candidate(
            text="\n".join(out),
            kind="generic",
            omitted_lines=omitted,
            critical_lines=extract_critical_lines(normalized, request.exit_code),
            notes=("duplicate/progress collapse",) if omitted else (),
            confidence=effective_confidence,
        )
