import sqlite3
from pathlib import Path

import pytest

from codexlean.storage import ArtifactStore


def test_store_connections_close_after_context(tmp_path: Path):
    store = ArtifactStore(tmp_path / "closed.sqlite3")
    with store._connect() as conn:
        conn.execute("SELECT 1").fetchone()
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_exact_roundtrip_and_prefix_lookup(tmp_path: Path):
    store = ArtifactStore(tmp_path / "store.sqlite3")
    raw = b"first\x00second\nthird\xff"
    artifact_id = store.put(
        raw,
        command=("tool", "--flag"),
        cwd=tmp_path,
        exit_code=7,
        kind="binary",
    )
    restored, metadata = store.get(artifact_id[:8])
    assert restored == raw
    assert metadata["exit_code"] == 7
    assert metadata["command"] == ("tool", "--flag")


def test_command_metadata_redacts_common_secret_forms(tmp_path: Path):
    store = ArtifactStore(tmp_path / "redact.sqlite3")
    artifact_id = store.put(
        b"safe output\n",
        command=(
            "curl",
            "--api-key=top-secret",
            "--token",
            "second-secret",
            "-H",
            "Authorization: Bearer third-secret",
            "https://example.invalid/?access_token=fourth-secret",
        ),
        cwd=tmp_path,
        exit_code=0,
        kind="generic",
    )
    _, metadata = store.get(artifact_id)
    joined = " ".join(metadata["command"])
    assert "top-secret" not in joined
    assert "second-secret" not in joined
    assert "third-secret" not in joined
    assert "fourth-secret" not in joined
    assert "<redacted>" in joined


def test_invalid_artifact_prefix_is_rejected(tmp_path: Path):
    store = ArtifactStore(tmp_path / "store.sqlite3")
    try:
        store.get("%")
    except KeyError as exc:
        assert "invalid artifact id" in str(exc)
    else:
        raise AssertionError("wildcard artifact id was accepted")


def test_reusing_artifact_refreshes_retention_timestamp(tmp_path: Path, monkeypatch):
    import codexlean.storage as storage_module

    store = ArtifactStore(tmp_path / "refresh.sqlite3")
    raw = b"repeatable\n"
    monkeypatch.setattr(storage_module.time, "time", lambda: 1000.0)
    artifact_id = store.put(raw, command=("one",), cwd=tmp_path, exit_code=0, kind="generic")
    monkeypatch.setattr(storage_module.time, "time", lambda: 2000.0)
    second_id = store.put(raw, command=("two",), cwd=tmp_path, exit_code=0, kind="generic")
    _, metadata = store.get(artifact_id)
    assert second_id == artifact_id
    assert metadata["created_at"] == 2000.0
    assert metadata["command"] == ("two",)
