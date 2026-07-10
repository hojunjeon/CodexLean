from pathlib import Path

from codexlean.benchmark import fixtures
from codexlean.engine import CompressionEngine
from codexlean.models import CompressionRequest, Profile
from codexlean.quality import extract_critical_lines
from codexlean.storage import ArtifactStore
from codexlean.textutil import decode


def _fixture(name: str):
    return next(item for item in fixtures() if item.name == name)


def _run(tmp_path: Path, name: str, profile: Profile = Profile.SAFE):
    fixture = _fixture(name)
    store = ArtifactStore(tmp_path / f"{name}.sqlite3")
    engine = CompressionEngine(store)
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
    return fixture, store, result


def test_passing_tests_compress_and_restore(tmp_path: Path):
    fixture, store, result = _run(tmp_path, "pytest-pass")
    assert result.transformed
    assert result.artifact_id
    assert result.stats.byte_savings_ratio > 0.5
    output = decode(result.output)
    assert "1200 passed" in output
    assert "DeprecationWarning: legacy_api is deprecated" in output
    restored, _ = store.get(result.artifact_id)
    assert restored == fixture.raw


def test_failing_tests_preserve_all_decisive_lines(tmp_path: Path):
    fixture, store, result = _run(tmp_path, "pytest-fail")
    assert result.transformed
    output = decode(result.output)
    for line in extract_critical_lines(decode(fixture.raw), fixture.exit_code):
        assert line in output
    restored, _ = store.get(result.artifact_id)
    assert restored == fixture.raw


def test_log_preserves_fatal_context(tmp_path: Path):
    _, _, result = _run(tmp_path, "logs")
    assert result.transformed
    output = decode(result.output)
    assert "ERROR payment commit failed order_id=ORD-9917" in output
    assert "SerializationFailure: retry budget exhausted" in output
    assert "CRITICAL order ORD-9917 left in pending state" in output


def test_json_preserves_critical_value(tmp_path: Path):
    _, _, result = _run(tmp_path, "json-array")
    assert result.transformed
    assert "FATAL checksum mismatch for shard-19" in decode(result.output)


def test_git_diff_is_protected(tmp_path: Path):
    fixture, _, result = _run(tmp_path, "git-diff-protected")
    assert not result.transformed
    assert result.output == fixture.raw


def test_probable_secret_is_not_persisted_or_compressed(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CODEXLEAN_STORE_SECRETS", raising=False)
    fixture, store, result = _run(tmp_path, "secret-passthrough")
    assert not result.transformed
    assert result.output == fixture.raw
    assert store.list_artifacts() == []


def test_small_output_passthrough(tmp_path: Path):
    store = ArtifactStore(tmp_path / "small.sqlite3")
    engine = CompressionEngine(store)
    raw = b"ok\n"
    result = engine.compress(CompressionRequest(raw=raw, command=("echo", "ok")))
    assert not result.transformed
    assert result.output == raw


def test_diff_with_ansi_is_still_exact_passthrough(tmp_path: Path):
    raw = b"\x1b[31m-removed\x1b[0m\n\x1b[32m+added\x1b[0m\n"
    store = ArtifactStore(tmp_path / "diff.sqlite3")
    result = CompressionEngine(store).compress(
        CompressionRequest(
            raw=raw,
            command=("git", "diff", "--color=always"),
            profile=Profile.SAFE,
            min_bytes=0,
            min_lines=0,
            min_savings_ratio=0.0,
        )
    )
    assert not result.transformed
    assert result.output == raw
    assert store.list_artifacts() == []


def test_no_store_means_selective_omission_falls_back_to_exact_raw():
    fixture = _fixture("logs")
    result = CompressionEngine(None).compress(
        CompressionRequest(
            raw=fixture.raw,
            command=fixture.command,
            profile=Profile.SAFE,
            min_bytes=0,
            min_lines=0,
            min_savings_ratio=0.0,
        )
    )
    assert not result.transformed
    assert result.output == fixture.raw
    assert result.fallback_reason == "exact-recovery store unavailable"


def test_rejected_candidate_does_not_leave_orphan_artifact(tmp_path: Path):
    fixture = _fixture("pytest-pass")
    store = ArtifactStore(tmp_path / "orphan.sqlite3")
    result = CompressionEngine(store).compress(
        CompressionRequest(
            raw=fixture.raw,
            command=fixture.command,
            profile=Profile.SAFE,
            min_bytes=0,
            min_lines=0,
            min_savings_ratio=0.999,
        )
    )
    assert not result.transformed
    assert store.list_artifacts() == []


def test_store_write_failure_never_hides_raw_output(tmp_path: Path):
    fixture = _fixture("logs")

    class BrokenStore:
        def put(self, *args, **kwargs):
            raise OSError("disk full")

        def record_run(self, *args, **kwargs):
            raise OSError("disk full")

    result = CompressionEngine(BrokenStore()).compress(  # type: ignore[arg-type]
        CompressionRequest(
            raw=fixture.raw,
            command=fixture.command,
            profile=Profile.SAFE,
            min_bytes=0,
            min_lines=0,
            min_savings_ratio=0.0,
        )
    )
    assert not result.transformed
    assert result.output == fixture.raw
    assert result.fallback_reason == "exact-recovery store write failed"


def test_additional_secret_shapes_are_not_persisted(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CODEXLEAN_STORE_SECRETS", raising=False)
    for index, secret_line in enumerate(
        [
            "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz",
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "-----BEGIN PRIVATE KEY-----",
            "github_pat_abcdefghijklmnopqrstuvwxyz123456",
            "AKIAABCDEFGHIJKLMNOP",
        ]
    ):
        raw = (("INFO repeat\n" * 100) + secret_line + "\n").encode()
        store = ArtifactStore(tmp_path / f"secret-{index}.sqlite3")
        result = CompressionEngine(store).compress(
            CompressionRequest(
                raw=raw,
                command=("cat", "log.txt"),
                profile=Profile.SAFE,
                min_bytes=0,
                min_lines=0,
                min_savings_ratio=0.0,
            )
        )
        assert not result.transformed, secret_line
        assert result.output == raw
        assert store.list_artifacts() == []
