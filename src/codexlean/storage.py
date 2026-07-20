from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import time
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import CompressionStats

_SECRET_NAME = (
    r"(?:api[-_]?key|access[-_]?key|access[-_]?token|auth[-_]?token|"
    r"client[-_]?secret|private[-_]?key|secret|token|password|passwd|"
    r"authorization|credential|credentials|database[-_]?url)"
)
_COMMAND_SECRET_FLAG_RE = re.compile(rf"(?i)^(?:--?)?{_SECRET_NAME}$")
_COMMAND_SECRET_ASSIGN_RE = re.compile(
    rf"(?i)(?:^|[\s?&;,=])(?:--?)?{_SECRET_NAME}\s*[:=]"
)
_ARTIFACT_ID_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")


def redact_command(command: tuple[str, ...]) -> tuple[str, ...]:
    """Redact likely credentials from locally stored command metadata.

    The raw command still executes unchanged. Metadata redaction is deliberately
    conservative: an argument containing a secret-shaped assignment is replaced
    in full rather than trying to retain a potentially sensitive suffix.
    """

    redacted: list[str] = []
    redact_next = False
    for token in command:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        if _COMMAND_SECRET_FLAG_RE.fullmatch(token):
            redacted.append(token)
            redact_next = True
            continue
        match = _COMMAND_SECRET_ASSIGN_RE.search(token)
        if match:
            redacted.append("<redacted>")
            # Header-like forms such as `Authorization:` may carry the value in
            # the following argv element. Redact it as well when no value follows.
            if not token[match.end():].strip():
                redact_next = True
            continue
        redacted.append(token)
    return tuple(redacted)


def default_store_path() -> Path:
    override = os.getenv("CODEXLEAN_STORE")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "CodexLean" / "artifacts.sqlite3"
    base = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "codexlean" / "artifacts.sqlite3"


class ArtifactStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_store_path()).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, stat.S_IRWXU)
        except OSError:
            pass
        self._init_db()
        self._expire_default()

    def _expire_default(self) -> None:
        value = os.getenv("CODEXLEAN_RETENTION_DAYS", "7")
        try:
            days = int(value)
        except ValueError:
            days = 7
        if days <= 0:
            return
        cutoff = time.time() - days * 86400
        with self._connect() as conn:
            conn.execute("DELETE FROM artifacts WHERE created_at < ?", (cutoff,))
            conn.execute("DELETE FROM runs WHERE created_at < ?", (cutoff,))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    command_json TEXT NOT NULL,
                    cwd TEXT,
                    exit_code INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    encoding TEXT NOT NULL,
                    payload_zlib BLOB NOT NULL,
                    raw_bytes INTEGER NOT NULL,
                    raw_lines INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    artifact_id TEXT,
                    command_json TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    transformed INTEGER NOT NULL,
                    quality_passed INTEGER NOT NULL,
                    fallback_reason TEXT,
                    raw_bytes INTEGER NOT NULL,
                    compact_bytes INTEGER NOT NULL,
                    raw_lines INTEGER NOT NULL,
                    compact_lines INTEGER NOT NULL,
                    raw_tokens_est INTEGER NOT NULL,
                    compact_tokens_est INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_artifacts_created ON artifacts(created_at);
                """
            )
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    @staticmethod
    def artifact_id(raw: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(raw).hexdigest()
        return digest[:16], digest

    def put(
        self,
        raw: bytes,
        *,
        command: tuple[str, ...],
        cwd: Path | None,
        exit_code: int,
        kind: str,
    ) -> str:
        _, digest = self.artifact_id(raw)
        payload = zlib.compress(raw, level=9)
        with self._connect() as conn:
            # Extend the content-addressed ID only if an extremely unlikely prefix
            # collision exists. Reusing an artifact refreshes its retention timestamp.
            short = digest
            for length in (16, 24, 32, 40, 64):
                candidate = digest[:length]
                row = conn.execute(
                    "SELECT sha256 FROM artifacts WHERE id = ?", (candidate,)
                ).fetchone()
                if row is None or row["sha256"] == digest:
                    short = candidate
                    break
            conn.execute(
                """
                INSERT INTO artifacts
                (id, sha256, created_at, command_json, cwd, exit_code, kind, encoding,
                 payload_zlib, raw_bytes, raw_lines)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    sha256=excluded.sha256,
                    created_at=excluded.created_at,
                    command_json=excluded.command_json,
                    cwd=excluded.cwd,
                    exit_code=excluded.exit_code,
                    kind=excluded.kind,
                    encoding=excluded.encoding,
                    payload_zlib=excluded.payload_zlib,
                    raw_bytes=excluded.raw_bytes,
                    raw_lines=excluded.raw_lines
                """,
                (
                    short,
                    digest,
                    time.time(),
                    json.dumps(redact_command(command), ensure_ascii=False),
                    str(cwd) if cwd else None,
                    exit_code,
                    kind,
                    "bytes+zlib",
                    payload,
                    len(raw),
                    len(raw.splitlines()),
                ),
            )
        return short

    def get(self, artifact_id: str) -> tuple[bytes, dict[str, Any]]:
        if not _ARTIFACT_ID_RE.fullmatch(artifact_id):
            raise KeyError(f"invalid artifact id: {artifact_id}")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE id = ? OR id LIKE ? ORDER BY created_at DESC LIMIT 2",
                (artifact_id, f"{artifact_id}%"),
            ).fetchall()
        if not rows:
            raise KeyError(f"artifact not found: {artifact_id}")
        if len(rows) > 1 and all(row["id"] != artifact_id for row in rows):
            raise KeyError(f"artifact id is ambiguous: {artifact_id}")
        row = next((r for r in rows if r["id"] == artifact_id), rows[0])
        raw = zlib.decompress(row["payload_zlib"])
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row["sha256"]:
            raise RuntimeError(f"artifact integrity check failed: {row['id']}")
        metadata = {k: row[k] for k in row.keys() if k != "payload_zlib"}
        metadata["command"] = tuple(json.loads(metadata.pop("command_json")))
        return raw, metadata

    def record_run(
        self,
        *,
        artifact_id: str | None,
        command: tuple[str, ...],
        kind: str,
        profile: str,
        transformed: bool,
        quality_passed: bool,
        fallback_reason: str | None,
        stats: CompressionStats,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs
                (created_at, artifact_id, command_json, kind, profile, transformed,
                 quality_passed, fallback_reason, raw_bytes, compact_bytes, raw_lines,
                 compact_lines, raw_tokens_est, compact_tokens_est)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    artifact_id,
                    json.dumps(redact_command(command), ensure_ascii=False),
                    kind,
                    profile,
                    int(transformed),
                    int(quality_passed),
                    fallback_reason,
                    stats.raw_bytes,
                    stats.compact_bytes,
                    stats.raw_lines,
                    stats.compact_lines,
                    stats.raw_tokens_est,
                    stats.compact_tokens_est,
                ),
            )

    def stats(self, since_days: int | None = None) -> dict[str, Any]:
        where = ""
        params: tuple[Any, ...] = ()
        if since_days is not None:
            where = "WHERE created_at >= ?"
            params = (time.time() - since_days * 86400,)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS runs,
                       SUM(transformed) AS transformed,
                       SUM(raw_bytes) AS raw_bytes,
                       SUM(compact_bytes) AS compact_bytes,
                       SUM(raw_tokens_est) AS raw_tokens_est,
                       SUM(compact_tokens_est) AS compact_tokens_est,
                       SUM(CASE WHEN quality_passed = 0 THEN 1 ELSE 0 END) AS guard_failures
                FROM runs {where}
                """,
                params,
            ).fetchone()
            by_kind = conn.execute(
                f"""
                SELECT kind, COUNT(*) AS runs, SUM(raw_bytes) AS raw_bytes,
                       SUM(compact_bytes) AS compact_bytes
                FROM runs {where}
                GROUP BY kind ORDER BY (SUM(raw_bytes)-SUM(compact_bytes)) DESC
                """,
                params,
            ).fetchall()
        result = dict(row) if row else {}
        result["by_kind"] = [dict(r) for r in by_kind]
        return result

    def list_artifacts(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, command_json, cwd, exit_code, kind, raw_bytes, raw_lines
                FROM artifacts ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["command"] = tuple(json.loads(item.pop("command_json")))
            result.append(item)
        return result

    def purge(self, older_than_days: int | None = None, all_data: bool = False) -> int:
        with self._connect() as conn:
            if all_data:
                count = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
                conn.execute("DELETE FROM artifacts")
                conn.execute("DELETE FROM runs")
                return int(count)
            if older_than_days is None:
                older_than_days = 7
            cutoff = time.time() - older_than_days * 86400
            count = conn.execute(
                "SELECT COUNT(*) FROM artifacts WHERE created_at < ?", (cutoff,)
            ).fetchone()[0]
            conn.execute("DELETE FROM artifacts WHERE created_at < ?", (cutoff,))
            conn.execute("DELETE FROM runs WHERE created_at < ?", (cutoff,))
            return int(count)
