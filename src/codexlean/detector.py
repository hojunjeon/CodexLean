from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass

from .textutil import strip_ansi


@dataclass(frozen=True, slots=True)
class Detection:
    kind: str
    confidence: float
    reason: str


_TEST_COMMANDS = {
    "pytest",
    "py.test",
    "jest",
    "vitest",
    "mocha",
    "rspec",
    "cargo",
    "go",
    "gradle",
    "gradlew",
    "mvn",
    "dotnet",
}
_SEARCH_COMMANDS = {"rg", "grep", "egrep", "fgrep", "ack", "ag"}
_TREE_COMMANDS = {"tree", "find", "fd", "ls", "dir"}


def _basename(value: str) -> str:
    return value.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()


def _command_words(command: tuple[str, ...]) -> list[str]:
    if len(command) == 1:
        try:
            return shlex.split(command[0])
        except ValueError:
            return list(command)
    return list(command)


def detect_kind(command: tuple[str, ...], text: str, hint: str | None = None) -> Detection:
    if hint:
        return Detection(hint, 1.0, "explicit hint")

    words = _command_words(command)
    base = _basename(words[0]) if words else ""
    lower_words = [w.lower() for w in words]
    sample = strip_ansi(text[:80_000])
    low = sample.lower()

    if base == "git" or (base in {"hub", "gh"} and "diff" in lower_words):
        if "status" in lower_words:
            return Detection("git_status", 0.99, "git status command")
        if "diff" in lower_words or sample.startswith("diff --git "):
            return Detection("git_diff", 0.99, "git diff command")
        if "log" in lower_words:
            return Detection("git_log", 0.96, "git log command")

    if base in _TEST_COMMANDS:
        if base == "cargo" and not any(w in {"test", "nextest"} for w in lower_words[1:]):
            pass
        elif base == "go" and "test" not in lower_words[1:]:
            pass
        elif base == "dotnet" and "test" not in lower_words[1:]:
            pass
        elif base in {"gradle", "gradlew", "mvn"} and not any("test" in w for w in lower_words[1:]):
            pass
        else:
            return Detection("test", 0.98, "test command")

    if base in {"npm", "pnpm", "yarn", "bun"}:
        arguments = lower_words[1:]
        explicit_test = bool(arguments) and arguments[0] == "test"
        test_script = any(
            word in {"test", "jest", "vitest", "mocha"}
            or word.startswith("test:")
            for word in arguments
        )
        if (explicit_test or test_script) and (
            "test" in low or "passed" in low or "failed" in low
        ):
            return Detection("test", 0.94, "package test output")

    if base in _SEARCH_COMMANDS:
        return Detection("search", 0.96, "search command")

    if base in _TREE_COMMANDS:
        # `tail service.log` / `cat app.log` are logs, not filesystem listings.
        if base in {"tail", "head", "cat"} or any(w.lower().endswith((".log", ".out")) for w in words[1:]):
            return Detection("log", 0.92, "log file command")
        return Detection("tree", 0.9, "filesystem listing command")

    if base in {"tail", "head", "cat", "journalctl", "dmesg", "kubectl", "docker"} and (
        any(w.lower().endswith((".log", ".out")) for w in words[1:])
        or " logs" in " " + " ".join(lower_words)
        or base in {"journalctl", "dmesg"}
    ):
        return Detection("log", 0.92, "log command")

    stripped = sample.lstrip()
    if stripped[:1] in {"{", "["}:
        try:
            json.loads(text)
            return Detection("json", 0.99, "valid JSON")
        except Exception:
            pass

    if sample.startswith("diff --git ") or re.search(r"^@@ .* @@", sample, re.MULTILINE):
        return Detection("git_diff", 0.96, "diff markers")

    test_markers = (
        "short test summary info",
        "test suites:",
        "tests:",
        "failures",
        "collected ",
        "test result:",
        "ran all test suites",
    )
    if sum(marker in low for marker in test_markers) >= 2:
        return Detection("test", 0.86, "test markers")

    log_lines = sample.splitlines()
    severity_hits = sum(
        bool(re.search(r"\b(?:trace|debug|info|warn(?:ing)?|error|fatal|critical|panic)\b", line, re.I))
        for line in log_lines[:1000]
    )
    if severity_hits >= max(8, len(log_lines[:1000]) // 8):
        return Detection("log", 0.82, "log severity density")

    return Detection("generic", 0.55, "no strong format match")
