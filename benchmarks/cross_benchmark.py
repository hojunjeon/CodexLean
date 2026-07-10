"""Reproducible 15-case CodexLean ON/OFF output benchmark.

Run after installing the project, preferably with the offline cl100k tokenizer:

    python -m pip install -e '.[benchmark]'
    python benchmarks/cross_benchmark.py
"""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from codexlean import __version__
from codexlean.benchmark import fixtures
from codexlean.engine import CompressionEngine
from codexlean.models import CompressionRequest, Profile
from codexlean.storage import ArtifactStore
from codexlean.textutil import decode
from codexlean.tokens import estimate_tokens, tokenizer_name


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    label_ko: str
    category: str
    text: str
    command: tuple[str, ...]
    exit_code: int
    anchors: tuple[tuple[str, ...], ...]
    exact_visible: bool = False
    sensitive: bool = False


@dataclass(frozen=True, slots=True)
class Row:
    case: str
    label_ko: str
    category: str
    raw_tokens: int
    output_tokens: int
    saved_tokens: int
    savings_pct: float
    transformed: bool
    strict_visible_pass: bool
    exact_available: bool
    artifact_created: bool
    fallback_reason: str | None


def _token_counter() -> tuple[Callable[[str], int], str]:
    """Prefer the exact bundled cl100k encoding when available."""
    try:
        import tiktoken  # type: ignore

        names = set(tiktoken.list_encoding_names())
        for name in ("cl100k_base_offline", "cl100k_base"):
            if name not in names:
                continue
            try:
                encoder = tiktoken.get_encoding(name)
                return (
                    lambda text: len(encoder.encode(text, disallowed_special=())),
                    f"tiktoken:{name}",
                )
            except Exception:
                continue
    except Exception:
        pass
    return estimate_tokens, tokenizer_name()


def _core_cases() -> list[Case]:
    categories = {
        "pytest-pass": ("Pytest 성공", "pytest"),
        "pytest-fail": ("Pytest 실패", "pytest"),
        "logs": ("대량 운영 로그", "log"),
        "json-array": ("대형 JSON 배열", "json"),
        "search": ("대규모 검색 결과", "search"),
        "tree": ("파일 트리", "tree"),
        "generic-progress": ("진행률 로그", "generic"),
        "git-status": ("Git status", "git-status"),
        "git-diff-protected": ("보호된 Git diff", "git-diff"),
        "secret-passthrough": ("민감정보 로그", "log"),
    }
    cases: list[Case] = []
    for fixture in fixtures():
        label, category = categories[fixture.name]
        cases.append(
            Case(
                name=f"CL/{fixture.name}",
                label_ko=label,
                category=category,
                text=fixture.raw.decode("utf-8"),
                command=fixture.command,
                exit_code=fixture.exit_code,
                anchors=tuple((value,) for value in fixture.required),
                exact_visible=fixture.name in {"git-diff-protected", "secret-passthrough"},
                sensitive=fixture.name == "secret-passthrough",
            )
        )
    return cases


def _external_cases() -> list[Case]:
    pytest_log = "\n".join(
        [
            "============================= test session starts =============================",
            "platform win32 -- Python 3.11.9, pytest-8.2.0",
            "collected 184 items",
            *[
                f"tests/test_api.py::{name} PASSED [ {index}%]"
                for index, name in enumerate((f"test_ok_{n}" for n in range(70)), 1)
            ],
            "tests/test_auth.py::test_expired_token_rejected FAILED [ 39%]",
            "________________________________ test_expired_token_rejected ________________________________",
            "E AssertionError: expected 401, got 200",
            "E at tests/test_auth.py:42",
            "FAILED tests/test_auth.py::test_expired_token_rejected - AssertionError: expected 401, got 200",
            "==================== 1 failed, 183 passed in 12.84s ====================",
        ]
    )
    search_output = "\n".join(
        [f"src/module_{i % 7}.py:{10 + i}:def handler_{i}(): return 'ok'" for i in range(80)]
        + [
            "src/auth.py:42:raise AuthError('expired token accepted')",
            "src/auth.py:77:def validate_expiry(token):",
        ]
    )
    json_payload = {
        "status": "partial_failure",
        "request_id": "req_8f3a91c0",
        "items": [
            {"id": i, "name": f"job-{i}", "status": "ok", "duration_ms": 20 + i}
            for i in range(60)
        ]
        + [{"id": 61, "name": "auth-sync", "status": "error", "message": "token expired"}],
        "next_page": None,
    }
    diff = "\n".join(
        [
            "diff --git a/src/auth.py b/src/auth.py",
            "index 1111111..2222222 100644",
            "--- a/src/auth.py",
            "+++ b/src/auth.py",
            "@@ -39,7 +39,9 @@ def validate_expiry(token):",
            "- return token.exp < now",
            "+ if token.exp <= now:",
            "+ raise AuthError('expired token accepted')",
            "+ return True",
            *[f"+ audit_{i} = True" for i in range(60)],
        ]
    )
    answer = (
        "Sure! I'd be happy to help you with that. The reason your React component is "
        "re-rendering is likely because you're creating a new object reference on each "
        "render cycle. When you pass an inline object as a prop, React shallow comparison "
        "sees it as a different object every time, which triggers a re-render. I would "
        "recommend using useMemo to memoize the object."
    )
    return [
        Case(
            "EXT/pytest-failure",
            "외부 Pytest 실패",
            "pytest",
            pytest_log,
            ("pytest",),
            1,
            (
                ("E AssertionError: expected 401, got 200",),
                ("E at tests/test_auth.py:42", "tests/test_auth.py:42"),
                ("FAILED tests/test_auth.py::test_expired_token_rejected",),
                ("1 failed, 183 passed in 12.84s",),
            ),
        ),
        Case(
            "EXT/ripgrep-results",
            "외부 ripgrep 검색 결과",
            "search",
            search_output,
            ("rg", "handler", "src"),
            0,
            (
                ("src/auth.py:42",),
                ("AuthError('expired token accepted')", "AuthError"),
                ("src/auth.py:77",),
                ("validate_expiry",),
            ),
        ),
        Case(
            "EXT/json-api",
            "외부 JSON API 응답",
            "json",
            json.dumps(json_payload, indent=2),
            ("curl", "https://example.invalid/jobs"),
            0,
            (("partial_failure",), ("req_8f3a91c0",), ("auth-sync",), ("token expired",)),
        ),
        Case(
            "EXT/git-diff",
            "외부 Git diff",
            "git-diff",
            diff,
            ("git", "diff"),
            0,
            (
                ("diff --git a/src/auth.py b/src/auth.py",),
                ("@@ -39,7 +39,9 @@ def validate_expiry(token):",),
                ("+ raise AuthError('expired token accepted')",),
                ("+ audit_59 = True",),
            ),
            exact_visible=True,
        ),
        Case(
            "EXT/assistant-answer",
            "짧은 답변",
            "assistant",
            answer,
            (),
            0,
            (
                ("React component",),
                ("new object reference", "new object ref"),
                ("inline object",),
                ("React shallow comparison", "React shallow compare"),
                ("useMemo",),
            ),
        ),
    ]


def run() -> tuple[list[Row], dict[str, object]]:
    count_tokens, counter_name = _token_counter()
    cases = _core_cases() + _external_cases()
    rows: list[Row] = []
    with tempfile.TemporaryDirectory(prefix="codexlean-cross-") as temp_dir:
        store = ArtifactStore(Path(temp_dir) / "artifacts.sqlite3")
        engine = CompressionEngine(store)
        for case in cases:
            result = engine.compress(
                CompressionRequest(
                    raw=case.text.encode("utf-8"),
                    command=case.command,
                    exit_code=case.exit_code,
                    profile=Profile.SAFE,
                    store_original=True,
                )
            )
            output = decode(result.output)
            anchors_ok = all(
                any(alternative.lower() in output.lower() for alternative in alternatives)
                for alternatives in case.anchors
            )
            exact_visible_ok = not case.exact_visible or output == case.text
            sensitive_ok = not case.sensitive or (output == case.text and not result.artifact_id)
            strict_pass = anchors_ok and exact_visible_ok and sensitive_ok and result.quality_passed
            exact_available = output == case.text
            if result.artifact_id:
                raw, _ = store.get(result.artifact_id)
                exact_available = exact_available or raw == case.text.encode("utf-8")
            raw_tokens = count_tokens(case.text)
            output_tokens = count_tokens(output)
            rows.append(
                Row(
                    case=case.name,
                    label_ko=case.label_ko,
                    category=case.category,
                    raw_tokens=raw_tokens,
                    output_tokens=output_tokens,
                    saved_tokens=raw_tokens - output_tokens,
                    savings_pct=round((raw_tokens - output_tokens) * 100 / raw_tokens, 3),
                    transformed=result.transformed,
                    strict_visible_pass=bool(strict_pass),
                    exact_available=bool(exact_available),
                    artifact_created=bool(result.artifact_id),
                    fallback_reason=result.fallback_reason,
                )
            )
    raw_total = sum(row.raw_tokens for row in rows)
    output_total = sum(row.output_tokens for row in rows)
    summary: dict[str, object] = {
        "version": __version__,
        "profile": "safe",
        "token_counter": counter_name,
        "case_count": len(rows),
        "raw_tokens": raw_total,
        "output_tokens": output_total,
        "saved_tokens": raw_total - output_total,
        "savings_pct": round((raw_total - output_total) * 100 / raw_total, 3),
        "transformed_cases": sum(row.transformed for row in rows),
        "strict_visible_passes": sum(row.strict_visible_pass for row in rows),
        "exact_available_cases": sum(row.exact_available for row in rows),
    }
    return rows, summary


def write_outputs(rows: list[Row], summary: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "rows": [asdict(row) for row in rows]}
    (output_dir / "cross_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "cross_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)

    lines = [
        "# CodexLean ON/OFF 교차 벤치마크",
        "",
        f"- 버전: `{summary['version']}` / 프로필: `{summary['profile']}`",
        f"- 토큰 계수기: `{summary['token_counter']}`",
        f"- 합계: **{summary['raw_tokens']:,} → {summary['output_tokens']:,} tokens ({summary['savings_pct']:.1f}% 절감)**",
        f"- 엄격 1차 품질 게이트: **{summary['strict_visible_passes']}/{summary['case_count']}**",
        f"- 정확 원문 가용: **{summary['exact_available_cases']}/{summary['case_count']}**",
        "",
        "| 작업 | OFF | ON | 절감률 | 처리 | 품질 |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.label_ko} | {row.raw_tokens:,} | {row.output_tokens:,} | "
            f"{row.savings_pct:.1f}% | {'압축' if row.transformed else '원문 통과'} | "
            f"{'통과' if row.strict_visible_pass else '실패'} |"
        )
    lines += [
        "",
        "> 이 결과는 정적 명령 출력 압축의 합성 마이크로벤치마크입니다. 실제 Codex 세션의 입력·출력·캐시·재시도 전체 과금 토큰을 뜻하지 않습니다.",
        "",
    ]
    (output_dir / "cross_results.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks"))
    args = parser.parse_args()
    rows, summary = run()
    write_outputs(rows, summary, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["strict_visible_passes"] == summary["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
