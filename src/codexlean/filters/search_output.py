from __future__ import annotations

import re
from collections import Counter, OrderedDict
from dataclasses import dataclass

from ..models import Candidate, CompressionRequest, Profile
from ..textutil import strip_ansi

_MATCH_RE = re.compile(
    r"^(?P<path>.*?)(?P<sep>[:\-])(?P<line>\d+)(?P<sep2>[:\-])(?P<body>.*)$"
)
_CRITICAL_RE = re.compile(
    r"(?:\b(?:fatal|critical|panic|failed|failure|denied|timeout)\b|"
    r"\b[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)\b|\berror\b|\bexception\b)",
    re.IGNORECASE,
)
_SYMBOL_DEFINITION_RE = re.compile(
    r"(?:^|\b)(?:async\s+def|def|class|interface|enum|struct|type|func|fn|impl|"
    r"const|let|var|function)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Match:
    raw: str
    line: str
    separator: str
    body: str

    @property
    def compact(self) -> str:
        # Path is already stated once in the group heading. Removing it from every
        # match preserves location and content while avoiding the dominant repetition.
        return f"{self.line}{self.separator}{self.body}"


class SearchFilter:
    def compress(self, text: str, request: CompressionRequest, confidence: float) -> Candidate:
        normalized = strip_ansi(text).replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.splitlines()

        if request.profile is Profile.STRICT:
            from .generic import GenericFilter

            candidate = GenericFilter().compress(normalized, request, confidence)
            candidate.kind = "search"
            return candidate

        groups: OrderedDict[str, list[Match]] = OrderedDict()
        unparsable: list[str] = []
        for line in lines:
            match = _MATCH_RE.match(line)
            if match:
                groups.setdefault(match.group("path"), []).append(
                    Match(
                        raw=line,
                        line=match.group("line"),
                        separator=match.group("sep2"),
                        body=match.group("body"),
                    )
                )
            else:
                unparsable.append(line)

        if not groups or len(groups) < 2:
            from .generic import GenericFilter

            candidate = GenericFilter().compress(normalized, request, confidence)
            candidate.kind = "search"
            return candidate

        per_file = 6 if request.profile is Profile.SAFE else 3
        out: list[str] = []
        omitted = 0
        protected_paths: list[str] = []
        critical_bodies: list[str] = []
        selected: OrderedDict[str, tuple[list[Match], list[Match]]] = OrderedDict()

        for path, matches in groups.items():
            critical_indices = [
                index for index, item in enumerate(matches) if _CRITICAL_RE.search(item.body)
            ]
            for index in critical_indices:
                critical_bodies.append(matches[index].body)

            # Spread representative matches across the entire file instead of only
            # keeping the first N. This preserves first/last and broad positional
            # coverage with a smaller first-pass view. All critical matches survive.
            if len(matches) <= per_file:
                anchor_indices = list(range(len(matches)))
            elif per_file == 1:
                anchor_indices = [0]
            else:
                anchor_indices = sorted(
                    {
                        round(step * (len(matches) - 1) / (per_file - 1))
                        for step in range(per_file)
                    }
                )
            chosen_indices = list(dict.fromkeys([*critical_indices, *anchor_indices]))
            if len(critical_indices) < per_file and len(chosen_indices) > per_file:
                critical_set = set(critical_indices)
                optional = [i for i in chosen_indices if i not in critical_set]
                chosen_indices = [
                    *critical_indices,
                    *optional[: max(0, per_file - len(critical_indices))],
                ]
            chosen_indices = sorted(dict.fromkeys(chosen_indices))
            selected[path] = (matches, [matches[index] for index in chosen_indices])
            protected_paths.append(path)

        # Repeated match bodies are represented once and referenced by a tiny alias.
        # This is a representation-only reduction: file, line, and selected body
        # information remain recoverable directly from the compact view.
        body_counts = Counter(
            item.body
            for _, chosen in selected.values()
            for item in chosen
            if not _CRITICAL_RE.search(item.body)
        )
        aliases: dict[str, str] = {}
        for body, count in body_counts.items():
            alias = f"@{len(aliases) + 1}"
            original_cost = len(body) * count
            compact_cost = len(alias) * count + len(alias) + len(body) + 4
            if count >= 3 and original_cost - compact_cost >= 24:
                aliases[body] = alias

        if aliases:
            out.append("[match templates]")
            out.extend(f"{alias} = {body}" for body, alias in aliases.items())
            out.append("")

        for path, (matches, chosen) in selected.items():
            out.append(f"## {path} ({len(matches)} matches)")
            for item in chosen:
                rendered_body = aliases.get(item.body, item.body)
                # Error-bearing and symbol-definition matches are likely to be
                # referenced later as an exact ``path:line`` location. Keep their
                # original full line instead of relying only on the group heading.
                # This costs a few tokens but avoids location ambiguity in the safe
                # profile. Routine repetitive matches still benefit from path
                # de-duplication and optional body aliases.
                salient_symbol = len(matches) <= per_file and _SYMBOL_DEFINITION_RE.search(item.body)
                if _CRITICAL_RE.search(item.body) or salient_symbol:
                    out.append(item.raw)
                else:
                    out.append(f"{item.line}{item.separator}{rendered_body}")
            hidden = len(matches) - len(chosen)
            if hidden:
                out.append(f"… {hidden} more matches …")
                omitted += hidden

        if unparsable:
            out.append("\n[unparsed output]")
            cap = 20 if request.profile is Profile.SAFE else 8
            out.extend(unparsable[:cap])
            hidden = max(0, len(unparsable) - cap)
            if hidden:
                out.append(f"… {hidden} more unparsed lines …")
                omitted += hidden

        return Candidate(
            text="\n".join(out),
            kind="search",
            omitted_lines=omitted,
            critical_lines=tuple(dict.fromkeys(critical_bodies)),
            protected_lines=tuple(protected_paths),
            notes=("search results grouped by file", "range-distributed samples", "repeated-body dictionary", "repeated path prefixes removed"),
            confidence=confidence,
        )
