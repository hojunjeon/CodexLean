from __future__ import annotations

import re
from collections import OrderedDict

from ..models import Candidate, CompressionRequest, Profile
from ..textutil import collapse_consecutive_duplicates, strip_ansi

_REGULAR_PATH_RE = re.compile(
    r"^\s*(?P<state>modified|deleted|new file|renamed|copied|typechange|both modified):\s+(?P<path>.+)$",
    re.IGNORECASE,
)
_PORCELAIN_RE = re.compile(r"^(?P<xy>[ MADRCU?!]{2}|\?\?)\s+(?P<path>.+)$")
_STATE_RE = re.compile(
    r"(?:rebase in progress|merge in progress|cherry-pick|revert in progress|bisecting|unmerged paths)",
    re.IGNORECASE,
)
_HELP_RE = re.compile(r"^\s*\(use \"git .+\".*\)\s*$", re.IGNORECASE)

_STATE_CODE = {
    "modified": "M",
    "deleted": "D",
    "new file": "A",
    "renamed": "R",
    "copied": "C",
    "typechange": "T",
    "both modified": "U",
}


class GitStatusFilter:
    def compress(self, text: str, request: CompressionRequest, confidence: float) -> Candidate:
        normalized = strip_ansi(text).replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.splitlines()

        if request.profile is Profile.STRICT:
            collapsed, removed = collapse_consecutive_duplicates(lines)
            return Candidate(
                text="\n".join(collapsed),
                kind="git_status",
                omitted_lines=removed,
                notes=("exact duplicate collapse",),
                confidence=confidence,
            )

        metadata: list[str] = []
        groups: OrderedDict[str, list[str]] = OrderedDict()
        protected: list[str] = []
        removed = 0
        section = ""

        def add_group(label: str, path: str) -> None:
            groups.setdefault(label, []).append(path)
            protected.extend((label, path))

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()
            if not stripped:
                removed += 1
                continue
            if _HELP_RE.match(line) or lower.startswith("no changes added to commit"):
                removed += 1
                continue
            if lower.startswith("on branch "):
                branch = stripped[len("On branch "):]
                metadata.append(f"branch {branch}")
                protected.append(branch)
                continue
            if lower.startswith("your branch "):
                metadata.append(stripped)
                protected.append(stripped)
                continue
            if lower.startswith("changes to be committed"):
                section = "staged"
                removed += 1
                continue
            if lower.startswith("changes not staged"):
                section = "unstaged"
                removed += 1
                continue
            if lower.startswith("untracked files"):
                section = "untracked"
                removed += 1
                continue
            if lower.startswith("unmerged paths"):
                section = "unmerged"
                metadata.append(stripped)
                protected.append(stripped)
                continue
            if _STATE_RE.search(line):
                metadata.append(stripped)
                protected.append(stripped)
                continue

            porcelain = _PORCELAIN_RE.match(line)
            if porcelain and not line.startswith("\t"):
                xy = porcelain.group("xy")
                display_xy = "".join(char if char != " " else "." for char in xy)
                add_group(f"porcelain {display_xy}", porcelain.group("path"))
                continue

            regular = _REGULAR_PATH_RE.match(line)
            if regular:
                state = regular.group("state").lower()
                path = regular.group("path")
                add_group(f"{section or 'changed'} {_STATE_CODE.get(state, state)}", path)
                continue

            # Regular `git status` lists untracked paths as indented bare names.
            if section == "untracked" and (line.startswith("\t") or line.startswith("  ")):
                add_group("untracked", stripped)
                continue

            if lower in {"nothing to commit, working tree clean", "working tree clean"}:
                metadata.append(stripped)
                protected.append(stripped)
                continue

            # Unknown status metadata is retained rather than guessed away.
            metadata.append(stripped)

        out = list(metadata)
        for label, paths in groups.items():
            out.append(f"[{label}] {len(paths)}")
            out.extend(f"  {path}" for path in paths)
        if removed:
            out.append(f"… {removed} boilerplate/blank lines removed …")
        return Candidate(
            text="\n".join(out),
            kind="git_status",
            omitted_lines=removed,
            protected_lines=tuple(dict.fromkeys(protected)),
            notes=("grouped canonical git status", "all paths and states preserved"),
            confidence=confidence,
        )


class GitDiffFilter:
    def compress(self, text: str, request: CompressionRequest, confidence: float) -> Candidate:
        # Diffs are protected by default. Removing unchanged context can alter how a
        # coding model interprets a patch, so the quality-first path returns it intact.
        return Candidate(
            text=text,
            kind="git_diff",
            omitted_lines=0,
            notes=("protected diff passthrough",),
            confidence=1.0,
        )


class GitLogFilter:
    def compress(self, text: str, request: CompressionRequest, confidence: float) -> Candidate:
        normalized = strip_ansi(text).replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.splitlines()
        if request.profile is not Profile.MAX:
            collapsed, removed = collapse_consecutive_duplicates(lines)
            return Candidate(
                text="\n".join(collapsed),
                kind="git_log",
                omitted_lines=removed,
                notes=("duplicate collapse only",),
                confidence=confidence,
            )
        # MAX keeps commit headers and subjects, omitting long bodies.
        keep: list[str] = []
        omitted = 0
        in_body = False
        body_kept = 0
        for line in lines:
            if line.startswith("commit "):
                in_body = False
                body_kept = 0
                keep.append(line)
            elif re.match(r"^(Author|Date|Merge):", line):
                keep.append(line)
            elif not line.strip():
                if keep and keep[-1].strip():
                    keep.append("")
                in_body = True
            elif in_body and body_kept < 2:
                keep.append(line)
                body_kept += 1
            elif in_body:
                omitted += 1
            else:
                keep.append(line)
        if omitted:
            keep.append(f"… {omitted} commit-body lines omitted …")
        return Candidate(
            text="\n".join(keep),
            kind="git_log",
            omitted_lines=omitted,
            notes=("commit body cap",),
            confidence=confidence,
        )
