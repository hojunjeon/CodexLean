from __future__ import annotations

import re
from collections import Counter, OrderedDict
from pathlib import PurePath

from ..models import Candidate, CompressionRequest, Profile
from ..textutil import strip_ansi

_KEY_NAMES = {
    "readme.md",
    "agents.md",
    "pyproject.toml",
    "package.json",
    "cargo.toml",
    "go.mod",
    "makefile",
    "dockerfile",
    "compose.yaml",
    "docker-compose.yml",
    ".gitignore",
    "tsconfig.json",
}
_TREE_NODE_RE = re.compile(
    r"^(?P<prefix>(?:(?:│|\|)   |    )*)(?:├── |└── |\|-- |`-- )(?P<name>.+?)\s*$"
)
_TREE_SUMMARY_RE = re.compile(r"^\d+ director(?:y|ies), \d+ files?$", re.IGNORECASE)
_LONG_LISTING_RE = re.compile(
    r"^(?:[-dlcbps][rwxStTs-]{9}[+@.]?|[0-9/\-]{6,}\s+[0-9:]{4,})\s+"
)


def _reconstruct_tree_paths(lines: list[str]) -> list[str] | None:
    """Convert common Unicode/ASCII `tree` output to full relative paths.

    Returning ``None`` is a deliberate fail-safe: a partially understood hierarchy
    is less useful than the exact original, so the caller falls back conservatively.
    """

    nodes: list[tuple[int, str]] = []
    unmatched = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped in {".", "./"} or _TREE_SUMMARY_RE.fullmatch(stripped):
            continue
        match = _TREE_NODE_RE.match(line)
        if not match:
            # The first line is commonly the requested root directory.
            if not nodes and unmatched == 0:
                unmatched += 1
                continue
            unmatched += 1
            continue
        prefix = match.group("prefix")
        nodes.append((len(prefix) // 4, match.group("name")))

    if not nodes or unmatched > max(3, len(nodes) // 10):
        return None

    paths: list[str] = []
    parents: list[str] = []
    for index, (depth, name) in enumerate(nodes):
        if depth > len(parents):
            return None
        parents = parents[:depth]
        parts = [*parents, name]
        paths.append("/".join(parts))
        next_depth = nodes[index + 1][0] if index + 1 < len(nodes) else 0
        if next_depth > depth:
            parents = parts
    return paths


class TreeFilter:
    def compress(self, text: str, request: CompressionRequest, confidence: float) -> Candidate:
        normalized = strip_ansi(text).replace("\r\n", "\n").replace("\r", "\n")
        lines = [line for line in normalized.splitlines() if line.strip()]

        if request.profile is Profile.STRICT or len(lines) < 80:
            from .generic import GenericFilter

            candidate = GenericFilter().compress(normalized, request, confidence)
            candidate.kind = "tree"
            return candidate

        # Long `ls -l`/`dir` records carry permissions, ownership, size, and time.
        # Do not reinterpret them as paths because that would obscure evidence.
        long_rows = sum(bool(_LONG_LISTING_RE.match(line.strip())) for line in lines)
        if long_rows >= max(4, len(lines) // 3):
            from .generic import GenericFilter

            candidate = GenericFilter().compress(normalized, request, confidence)
            candidate.kind = "tree"
            candidate.notes = (*candidate.notes, "long listing protected")
            return candidate

        if any(token in normalized for token in ("├──", "└──", "|-- ", "`-- ")):
            reconstructed = _reconstruct_tree_paths(lines)
            if reconstructed is None:
                from .generic import GenericFilter

                candidate = GenericFilter().compress(normalized, request, confidence)
                candidate.kind = "tree"
                candidate.notes = (*candidate.notes, "unrecognized hierarchy protected")
                return candidate
            cleaned = reconstructed
            hierarchy_note = "tree hierarchy reconstructed"
        else:
            cleaned = [line.strip() for line in lines]
            hierarchy_note = "flat paths grouped"

        by_top: OrderedDict[str, list[str]] = OrderedDict()
        extensions: Counter[str] = Counter()
        key_files: list[str] = []
        for value in cleaned:
            normalized_path = value.replace("\\", "/")
            top = normalized_path.split("/", 1)[0] or "."
            by_top.setdefault(top, []).append(value)
            suffix = PurePath(normalized_path).suffix.lower() or "<none>"
            extensions[suffix] += 1
            if PurePath(normalized_path).name.lower() in _KEY_NAMES:
                key_files.append(value)

        per_group = 12 if request.profile is Profile.SAFE else 5

        def spread(items: list[str], budget: int) -> list[str]:
            if len(items) <= budget:
                return list(items)
            if budget <= 1:
                return [items[0]]
            indices = sorted(
                {round(step * (len(items) - 1) / (budget - 1)) for step in range(budget)}
            )
            return [items[index] for index in indices]

        standalone: list[str] = []
        grouped: OrderedDict[str, list[str]] = OrderedDict()
        for top, items in by_top.items():
            if len(items) == 1 and items[0].replace("\\", "/") == top:
                standalone.append(items[0])
            else:
                grouped[top] = items

        out = [f"Filesystem listing: {len(cleaned)} entries, {len(by_top)} top-level groups"]
        if key_files:
            out.append("Key files:")
            out.extend(f"  {item}" for item in key_files[:40])

        omitted = 0
        if standalone:
            top_budget = 30 if request.profile is Profile.SAFE else 15
            chosen_top = spread(standalone, top_budget)
            # Key top-level files are mandatory even when outside the spread sample.
            chosen_top = list(
                dict.fromkeys([*chosen_top, *(item for item in standalone if item in key_files)])
            )
            chosen_top.sort(key=standalone.index)
            out.append(f"Top-level entries ({len(standalone)}):")
            out.extend(f"  {item}" for item in chosen_top)
            hidden = len(standalone) - len(chosen_top)
            if hidden > 0:
                out.append(f"  … {hidden} more …")
                omitted += hidden

        if grouped:
            out.append("Groups:")
        for top, items in grouped.items():
            nested = [
                item
                for item in items
                if item.replace("\\", "/").rstrip("/") != top.rstrip("/")
            ]
            chosen = spread(nested, per_group)
            out.append(f"- {top}/ ({len(items)})")
            for item in chosen:
                normalized_item = item.replace("\\", "/")
                relative = (
                    normalized_item[len(top) + 1 :]
                    if normalized_item.startswith(top + "/")
                    else normalized_item
                )
                out.append(f"    {relative}")
            hidden = len(items) - len(chosen)
            if hidden > 0:
                out.append(f"    … {hidden} more …")
                omitted += hidden
        out.append(
            "Extensions: "
            + ", ".join(f"{ext}={count}" for ext, count in extensions.most_common(20))
        )

        return Candidate(
            text="\n".join(out),
            kind="tree",
            omitted_lines=omitted,
            protected_lines=tuple(key_files),
            notes=(hierarchy_note, "range-distributed samples", "repeated top prefixes removed", "key-file preservation"),
            confidence=confidence,
        )
