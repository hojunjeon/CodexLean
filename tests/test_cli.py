import os
import subprocess
import sys
from pathlib import Path


def _env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    return env


def test_run_preserves_wrapped_exit_code_and_recovery(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    store = tmp_path / "store.sqlite3"
    code = (
        "print('header');"
        "[print('noise line') for _ in range(200)];"
        "print('ERROR decisive failure');"
        "raise SystemExit(7)"
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "codexlean",
            "run",
            "--profile",
            "safe",
            "--min-bytes",
            "0",
            "--min-lines",
            "0",
            "--min-savings",
            "0",
            "--store",
            str(store),
            "--",
            sys.executable,
            "-c",
            code,
        ],
        cwd=root,
        env=_env(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 7
    output = proc.stdout.decode()
    assert "ERROR decisive failure" in output
    assert "| exact: codexlean show " in output


def test_filter_small_input_passes_through(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "codexlean", "filter", "--store", str(tmp_path / "s.db")],
        cwd=root,
        env=_env(root),
        input=b"hello\n",
        stdout=subprocess.PIPE,
    )
    assert proc.returncode == 0
    assert proc.stdout == b"hello\n"


def test_signal_exit_uses_posix_shell_convention(tmp_path: Path):
    if os.name == "nt":
        return
    root = Path(__file__).resolve().parents[1]
    code = "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "codexlean",
            "run",
            "--store",
            str(tmp_path / "signal.sqlite3"),
            "--",
            sys.executable,
            "-c",
            code,
        ],
        cwd=root,
        env=_env(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 143


def test_timeout_returns_124_and_keeps_partial_output(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    if os.name == "nt":
        wrapped = [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(4)"]
        timeout = "2.0"
    else:
        wrapped = ["sh", "-c", "printf 'started\n'; sleep 2"]
        timeout = "0.2"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "codexlean",
            "run",
            "--timeout",
            timeout,
            "--store",
            str(tmp_path / "timeout.sqlite3"),
            "--",
            *wrapped,
        ],
        cwd=root,
        env=_env(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 124
    assert b"started" in proc.stdout
    assert b"command timed out" in proc.stdout



def test_zero_tail_returns_empty_and_conflicting_selectors_are_rejected():
    from codexlean.cli import _line_slice, build_parser

    assert _line_slice("one\ntwo\n", None, None, 0) == ""
    parser = build_parser()
    try:
        parser.parse_args(["show", "abcd", "--head", "1", "--tail", "1"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("conflicting retrieval selectors were accepted")
