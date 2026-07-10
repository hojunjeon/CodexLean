from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .engine import CompressionEngine
from .models import CompressionRequest, Profile
from .quality import extract_critical_lines
from .storage import ArtifactStore
from .textutil import decode
from .tokens import tokenizer_name


@dataclass(frozen=True, slots=True)
class Fixture:
    name: str
    raw: bytes
    command: tuple[str, ...]
    exit_code: int
    required: tuple[str, ...] = ()
    expect_passthrough: bool = False


def _pytest_pass() -> str:
    lines = [
        "============================= test session starts =============================",
        "platform linux -- Python 3.13.5, pytest-8.4.0",
        "rootdir: /work/project",
        "collected 1200 items",
        "",
    ]
    for group in range(120):
        lines.append(f"tests/test_module_{group:03d}.py ..........                         [{group + 1:3d}/120]")
    lines += [
        "",
        "============================= warnings summary =============================",
        "tests/test_legacy.py:18: DeprecationWarning: legacy_api is deprecated",
        "================ 1200 passed, 1 warning in 18.42s =================",
    ]
    return "\n".join(lines) + "\n"


def _pytest_fail() -> str:
    lines = [
        "============================= test session starts =============================",
        "platform linux -- Python 3.13.5, pytest-8.4.0",
        "rootdir: /work/project",
        "collected 802 items",
    ]
    lines += [f"tests/test_ok_{i:03d}.py .........." for i in range(180)]
    lines += [
        "tests/test_auth.py ....F.",
        "",
        "=================================== FAILURES ===================================",
        "________________________ test_expired_token_rejected ________________________",
        "",
        "    def test_expired_token_rejected():",
        "        response = client.get('/private', headers={'Authorization': expired})",
        ">       assert response.status_code == 401",
        "E       assert 200 == 401",
        "E        +  where 200 = <Response [200 OK]>.status_code",
        "",
        "tests/test_auth.py:219: AssertionError",
        "=========================== short test summary info ============================",
        "FAILED tests/test_auth.py::test_expired_token_rejected - assert 200 == 401",
        "======================== 1 failed, 801 passed in 9.31s ========================",
    ]
    return "\n".join(lines) + "\n"


def _logs() -> str:
    lines: list[str] = []
    for i in range(1000):
        lines.append(
            f"2026-07-10T12:{i // 60:02d}:{i % 60:02d}.000Z INFO request completed request_id={i:08x} status=200 latency_ms={20 + i % 13}"
        )
        if i in {211, 587}:
            lines.append(
                f"2026-07-10T12:{i // 60:02d}:{i % 60:02d}.100Z WARNING cache nearing capacity shard={i % 8} used=91%"
            )
        if i == 673:
            lines.extend(
                [
                    "2026-07-10T12:11:13.200Z ERROR payment commit failed order_id=ORD-9917",
                    "Traceback (most recent call last):",
                    "  File \"payments/commit.py\", line 88, in commit",
                    "    raise SerializationFailure('retry budget exhausted')",
                    "SerializationFailure: retry budget exhausted",
                    "2026-07-10T12:11:13.201Z CRITICAL order ORD-9917 left in pending state",
                ]
            )
    return "\n".join(lines) + "\n"


def _json_array() -> str:
    items = []
    for i in range(500):
        item = {
            "id": i,
            "service": f"worker-{i % 12}",
            "status": "ok",
            "latency_ms": 10 + (i % 41),
            "attempt": 1,
        }
        if i == 367:
            item.update(
                {
                    "status": "failed",
                    "error": "FATAL checksum mismatch for shard-19",
                    "attempt": 4,
                }
            )
        items.append(item)
    return json.dumps({"results": items, "next_cursor": None}, indent=2) + "\n"


def _search() -> str:
    lines = []
    for file_index in range(60):
        for match in range(14):
            body = f"register_handler(route_{match}, middleware=auth_guard)"
            if file_index == 41 and match == 9:
                body = "raise RuntimeError('FATAL route table corruption')"
            lines.append(f"src/module_{file_index:02d}.py:{match * 7 + 3}:{body}")
    return "\n".join(lines) + "\n"


def _tree() -> str:
    lines = ["."]
    lines += ["README.md", "AGENTS.md", "pyproject.toml", "src", "tests"]
    for package in range(50):
        for file_index in range(20):
            lines.append(f"src/pkg_{package:02d}/module_{file_index:02d}.py")
    for file_index in range(300):
        lines.append(f"tests/integration/test_case_{file_index:03d}.py")
    return "\n".join(lines) + "\n"


def _generic() -> str:
    lines = ["Preparing build environment"]
    for i in range(400):
        lines.append(f"Building dependency graph [{i / 4:.0f}%] package={i % 7}")
    lines += ["Linking binary"] * 120
    lines += ["Build completed successfully", "Output: dist/app"]
    return "\n".join(lines) + "\n"


def _git_status() -> str:
    lines = [
        "On branch feature/token-guard",
        "Your branch is ahead of 'origin/feature/token-guard' by 2 commits.",
        "  (use \"git push\" to publish your local commits)",
        "",
        "Changes not staged for commit:",
        "  (use \"git add <file>...\" to update what will be committed)",
        "  (use \"git restore <file>...\" to discard changes in working directory)",
    ]
    lines += [f"\tmodified:   src/module_{i:03d}.py" for i in range(80)]
    lines += ["", "Untracked files:", "  (use \"git add <file>...\" to include in what will be committed)"]
    lines += [f"\tnew_file_{i:03d}.txt" for i in range(20)]
    lines += ["", "no changes added to commit (use \"git add\" and/or \"git commit -a\")"]
    return "\n".join(lines) + "\n"


def _git_diff() -> str:
    lines = []
    for i in range(80):
        lines += [
            f"diff --git a/src/f{i}.py b/src/f{i}.py",
            f"index 1111111..2222222 100644",
            f"--- a/src/f{i}.py",
            f"+++ b/src/f{i}.py",
            "@@ -1,4 +1,4 @@",
            " def value():",
            f"-    return {i}",
            f"+    return {i + 1}",
            "",
        ]
    return "\n".join(lines)


def _secret_log() -> str:
    return (
        "INFO starting deployment\n" * 100
        + "authorization: Bearer should-not-be-persisted\n"
        + "INFO deployment complete\n" * 100
    )


def fixtures() -> list[Fixture]:
    return [
        Fixture(
            "pytest-pass",
            _pytest_pass().encode(),
            ("pytest", "-q"),
            0,
            required=("1200 passed", "DeprecationWarning: legacy_api is deprecated"),
        ),
        Fixture(
            "pytest-fail",
            _pytest_fail().encode(),
            ("pytest", "-q"),
            1,
            required=(
                "E       assert 200 == 401",
                "tests/test_auth.py:219: AssertionError",
                "FAILED tests/test_auth.py::test_expired_token_rejected",
            ),
        ),
        Fixture(
            "logs",
            _logs().encode(),
            ("tail", "-n", "2000", "service.log"),
            0,
            required=(
                "ERROR payment commit failed order_id=ORD-9917",
                "SerializationFailure: retry budget exhausted",
                "CRITICAL order ORD-9917 left in pending state",
            ),
        ),
        Fixture(
            "json-array",
            _json_array().encode(),
            ("curl", "http://localhost/results"),
            0,
            required=("FATAL checksum mismatch for shard-19",),
        ),
        Fixture(
            "search",
            _search().encode(),
            ("rg", "register_handler", "src"),
            0,
            required=("FATAL route table corruption", "src/module_41.py"),
        ),
        Fixture(
            "tree",
            _tree().encode(),
            ("find", ".", "-type", "f"),
            0,
            required=("README.md", "AGENTS.md", "pyproject.toml"),
        ),
        Fixture(
            "generic-progress",
            _generic().encode(),
            ("custom-build",),
            0,
            required=("Build completed successfully", "Output: dist/app"),
        ),
        Fixture(
            "git-status",
            _git_status().encode(),
            ("git", "status"),
            0,
            required=("src/module_079.py", "new_file_019.txt"),
        ),
        Fixture(
            "git-diff-protected",
            _git_diff().encode(),
            ("git", "diff"),
            0,
            required=("+    return 80",),
            expect_passthrough=True,
        ),
        Fixture(
            "secret-passthrough",
            _secret_log().encode(),
            ("cat", "deploy.log"),
            0,
            required=("authorization: Bearer should-not-be-persisted",),
            expect_passthrough=True,
        ),
    ]


def run_benchmark(profiles: Iterable[str] | None = None) -> dict:
    selected = [Profile(value) for value in (profiles or [p.value for p in Profile])]
    report: dict = {
        "tool": "codexlean",
        "version": "0.1.1",
        "token_counter": tokenizer_name(),
        "profiles": {},
        "quality_failures": 0,
    }
    quality_failures: list[dict] = []

    for profile in selected:
        with tempfile.TemporaryDirectory(prefix="codexlean-bench-") as temp:
            store = ArtifactStore(Path(temp) / "artifacts.sqlite3")
            engine = CompressionEngine(store)
            rows = []
            aggregate_raw_bytes = aggregate_compact_bytes = 0
            aggregate_raw_tokens = aggregate_compact_tokens = 0
            transformed_count = 0

            for fixture in fixtures():
                result = engine.compress(
                    CompressionRequest(
                        raw=fixture.raw,
                        command=fixture.command,
                        exit_code=fixture.exit_code,
                        profile=profile,
                        min_bytes=0,
                        min_lines=0,
                        min_savings_ratio=0.0,
                    )
                )
                output = decode(result.output)
                checks: list[tuple[str, bool]] = []
                for required in fixture.required:
                    checks.append((f"required:{required}", required in output))

                if fixture.exit_code != 0:
                    for critical in extract_critical_lines(decode(fixture.raw), fixture.exit_code):
                        checks.append((f"critical:{critical[:80]}", critical in output))

                if result.transformed:
                    checks.append(("artifact-id", result.artifact_id is not None))
                    if result.artifact_id:
                        restored, _ = store.get(result.artifact_id)
                        checks.append(("exact-recovery", restored == fixture.raw))
                if fixture.expect_passthrough:
                    checks.append(("expected-passthrough", not result.transformed))

                failed_checks = [name for name, passed in checks if not passed]
                if failed_checks:
                    quality_failures.append(
                        {
                            "profile": profile.value,
                            "fixture": fixture.name,
                            "checks": failed_checks,
                        }
                    )

                stats = result.stats
                aggregate_raw_bytes += stats.raw_bytes
                aggregate_compact_bytes += stats.compact_bytes
                aggregate_raw_tokens += stats.raw_tokens_est
                aggregate_compact_tokens += stats.compact_tokens_est
                transformed_count += int(result.transformed)
                rows.append(
                    {
                        "fixture": fixture.name,
                        "kind": result.kind,
                        "transformed": result.transformed,
                        "fallback_reason": result.fallback_reason,
                        "raw_bytes": stats.raw_bytes,
                        "compact_bytes": stats.compact_bytes,
                        "byte_savings_ratio": stats.byte_savings_ratio,
                        "raw_tokens_est": stats.raw_tokens_est,
                        "compact_tokens_est": stats.compact_tokens_est,
                        "token_savings_ratio_est": stats.token_savings_ratio_est,
                        "quality_passed": not failed_checks,
                    }
                )

            report["profiles"][profile.value] = {
                "fixtures": rows,
                "summary": {
                    "cases": len(rows),
                    "transformed": transformed_count,
                    "raw_bytes": aggregate_raw_bytes,
                    "compact_bytes": aggregate_compact_bytes,
                    "byte_savings_ratio": (
                        (aggregate_raw_bytes - aggregate_compact_bytes) / aggregate_raw_bytes
                        if aggregate_raw_bytes
                        else 0.0
                    ),
                    "raw_tokens_est": aggregate_raw_tokens,
                    "compact_tokens_est": aggregate_compact_tokens,
                    "token_savings_ratio_est": (
                        (aggregate_raw_tokens - aggregate_compact_tokens) / aggregate_raw_tokens
                        if aggregate_raw_tokens
                        else 0.0
                    ),
                },
            }

    report["quality_failures"] = len(quality_failures)
    report["quality_failure_details"] = quality_failures
    return report


def _markdown(report: dict) -> str:
    lines = [
        "# CodexLean benchmark",
        "",
        f"Token counter: `{report['token_counter']}`",
        f"Quality failures: **{report['quality_failures']}**",
        "",
        "## Aggregate",
        "",
        "| Profile | Cases | Transformed | Byte saving | Estimated token saving |",
        "|---|---:|---:|---:|---:|",
    ]
    for profile, data in report["profiles"].items():
        summary = data["summary"]
        lines.append(
            f"| {profile} | {summary['cases']} | {summary['transformed']} | "
            f"{summary['byte_savings_ratio']:.1%} | {summary['token_savings_ratio_est']:.1%} |"
        )
    for profile, data in report["profiles"].items():
        lines += [
            "",
            f"## {profile}",
            "",
            "| Fixture | Kind | Action | Byte saving | Estimated token saving | Quality |",
            "|---|---|---|---:|---:|---|",
        ]
        for row in data["fixtures"]:
            action = "compressed" if row["transformed"] else "passthrough"
            lines.append(
                f"| {row['fixture']} | {row['kind']} | {action} | "
                f"{row['byte_savings_ratio']:.1%} | {row['token_savings_ratio_est']:.1%} | "
                f"{'pass' if row['quality_passed'] else 'FAIL'} |"
            )
    if report["quality_failure_details"]:
        lines += ["", "## Quality failures", "", "```json"]
        lines.append(json.dumps(report["quality_failure_details"], ensure_ascii=False, indent=2))
        lines.append("```")
    lines += [
        "",
        "## Interpretation",
        "",
        "The token values are exact when `tiktoken` is installed; otherwise they use the documented UTF-8 proxy. "
        "Byte reduction is exact. Quality checks require decisive errors, configured sentinel facts, protected diff content, and byte-for-byte artifact recovery.",
        "",
    ]
    return "\n".join(lines)


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    else:
        path.write_text(_markdown(report), "utf-8")
