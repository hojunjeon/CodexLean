from __future__ import annotations

import re
from collections import OrderedDict

from ..models import Candidate, CompressionRequest, Profile
from ..quality import extract_critical_lines
from ..textutil import compact_template, merge_windows, render_windows, strip_ansi

_LEVEL_RE = re.compile(
    r"\b(?P<level>TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|FATAL|CRITICAL|PANIC)\b",
    re.IGNORECASE,
)
_CRITICAL_LEVELS = {"ERROR", "FATAL", "CRITICAL", "PANIC"}
_WARNING_LEVELS = {"WARN", "WARNING"}


class LogFilter:
    def compress(self, text: str, request: CompressionRequest, confidence: float) -> Candidate:
        normalized = strip_ansi(text).replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.splitlines()

        if request.profile is Profile.STRICT:
            from .generic import GenericFilter

            candidate = GenericFilter().compress(normalized, request, confidence)
            candidate.kind = "log"
            return candidate

        critical_indices: list[int] = []
        warning_indices: list[int] = []
        template_groups: OrderedDict[str, list[tuple[int, str]]] = OrderedDict()

        for i, line in enumerate(lines):
            match = _LEVEL_RE.search(line)
            level = match.group("level").upper() if match else ""
            if level in _CRITICAL_LEVELS or re.search(
                r"\b(?:exception|traceback|segfault|stack trace)\b", line, re.I
            ):
                critical_indices.append(i)
            elif level in _WARNING_LEVELS:
                warning_indices.append(i)
            else:
                template_groups.setdefault(compact_template(line), []).append((i, line))

        indices = set(range(min(5, len(lines))))
        indices.update(range(max(0, len(lines) - 8), len(lines)))
        indices.update(critical_indices)
        indices.update(warning_indices)

        # Keep one representative per INFO/DEBUG template in SAFE, only sizeable
        # families in MAX. Counts are appended so frequency information survives.
        template_summaries: list[str] = []
        for template, items in template_groups.items():
            if not template:
                continue
            if request.profile is Profile.SAFE or len(items) >= 3:
                indices.add(items[0][0])
            if len(items) > 1:
                template_summaries.append(f"×{len(items)} {template}")

        radius = 3 if request.profile is Profile.SAFE else 2
        windows = merge_windows(indices, radius=radius, size=len(lines))
        rendered, omitted = render_windows(lines, windows)
        if template_summaries:
            limit = 40 if request.profile is Profile.SAFE else 20
            rendered += "\n\n[repeated log templates]\n" + "\n".join(template_summaries[:limit])
            if len(template_summaries) > limit:
                rendered += f"\n… {len(template_summaries) - limit} more template groups in artifact …"

        declared_critical = tuple(lines[i] for i in critical_indices + warning_indices)
        return Candidate(
            text=rendered,
            kind="log",
            omitted_lines=omitted,
            critical_lines=declared_critical,
            notes=("severity preservation", "template grouping"),
            confidence=confidence,
        )
