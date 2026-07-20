from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import __version__
from .engine import CompressionEngine
from .installer import doctor as run_doctor
from .installer import install as install_codex
from .installer import uninstall as uninstall_codex
from .models import CompressionRequest, Profile
from .storage import ArtifactStore, default_store_path
from .textutil import decode
from .tokens import tokenizer_name


def _profile(value: str) -> Profile:
    try:
        return Profile(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def _percent(value: str) -> float:
    parsed = _non_negative_float(value)
    if parsed > 100:
        raise argparse.ArgumentTypeError("must be between 0 and 100")
    return parsed


def _store(value: str | None) -> ArtifactStore:
    path = Path(value).expanduser() if value else None
    return ArtifactStore(path)


def _engine(args: argparse.Namespace) -> CompressionEngine:
    try:
        return CompressionEngine(_store(getattr(args, "store", None)))
    except Exception:
        # The wrapper must remain fail-open: with no recovery store, any selective
        # omission is rejected by the engine and the exact raw output is emitted.
        return CompressionEngine(None)


def _portable_exit_code(returncode: int) -> int:
    if returncode < 0 and os.name != "nt":
        return 128 + abs(returncode)
    return returncode


def _request(
    args: argparse.Namespace,
    raw: bytes,
    command: tuple[str, ...],
    exit_code: int,
    cwd: Path | None,
) -> CompressionRequest:
    return CompressionRequest(
        raw=raw,
        command=command,
        exit_code=exit_code,
        cwd=cwd,
        profile=args.profile,
        kind_hint=getattr(args, "kind", None),
        min_bytes=args.min_bytes,
        min_lines=args.min_lines,
        min_savings_ratio=args.min_savings / 100.0,
        store_original=not args.no_store_original,
    )


def _stop_process(
    process: subprocess.Popen[bytes], signum: int, *, force: bool = False
) -> None:
    try:
        if os.name != "nt":
            os.killpg(process.pid, signum)
        elif force:
            process.kill()
        else:
            process.terminate()
    except (OSError, ProcessLookupError):
        pass


def cmd_run(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("codexlean: no command after --", file=sys.stderr)
        return 2
    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else Path.cwd()

    try:
        # A file-backed capture preserves output already emitted when a timeout
        # occurs. It also avoids holding two in-memory copies while the child runs.
        with tempfile.TemporaryFile() as capture:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=capture,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
                start_new_session=(os.name != "nt"),
            )
            timeout_note: bytes | None = None
            try:
                returncode = process.wait(timeout=args.timeout)
                exit_code = _portable_exit_code(returncode)
            except subprocess.TimeoutExpired:
                _stop_process(process, signal.SIGTERM)
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    _stop_process(
                        process,
                        signal.SIGKILL if os.name != "nt" else signal.SIGTERM,
                        force=True,
                    )
                    process.wait()
                exit_code = 124
                timeout_note = f"codexlean: command timed out after {args.timeout}s".encode()
            except KeyboardInterrupt:
                _stop_process(process, signal.SIGINT)
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    _stop_process(
                        process,
                        signal.SIGKILL if os.name != "nt" else signal.SIGTERM,
                        force=True,
                    )
                    process.wait()
                exit_code = 130
                timeout_note = b"codexlean: interrupted"

            capture.seek(0)
            raw = capture.read()
            if timeout_note is not None:
                if raw and not raw.endswith(b"\n"):
                    raw += b"\n"
                raw += timeout_note + b"\n"
    except FileNotFoundError:
        print(f"codexlean: command not found: {command[0]}", file=sys.stderr)
        return 127
    except PermissionError:
        print(f"codexlean: permission denied: {command[0]}", file=sys.stderr)
        return 126
    except OSError as exc:
        print(f"codexlean: cannot execute {command[0]}: {exc}", file=sys.stderr)
        return 126

    result = _engine(args).compress(
        _request(args, raw, tuple(command), exit_code, cwd)
    )
    sys.stdout.buffer.write(result.output)
    sys.stdout.buffer.flush()
    return exit_code


def cmd_filter(args: argparse.Namespace) -> int:
    raw = sys.stdin.buffer.read()
    command = tuple(shlex.split(args.command_text)) if args.command_text else ()
    result = _engine(args).compress(
        _request(args, raw, command, args.exit_code, Path.cwd())
    )
    sys.stdout.buffer.write(result.output)
    return _portable_exit_code(args.exit_code)


def _line_slice(text: str, spec: str | None, head: int | None, tail: int | None) -> str:
    lines = text.splitlines()
    if spec:
        match = re.fullmatch(r"(?:(\d+))?:(?:(\d+))?", spec)
        if not match:
            raise ValueError("--lines must use START:END (1-based, inclusive)")
        start = int(match.group(1) or 1)
        end = int(match.group(2) or len(lines))
        return "\n".join(lines[max(0, start - 1):max(0, end)])
    if head is not None:
        return "\n".join(lines[:head])
    if tail is not None:
        return "" if tail == 0 else "\n".join(lines[-tail:])
    return text


def _grep(text: str, pattern: str, context: int, fixed: bool) -> str:
    lines = text.splitlines()
    try:
        matcher = (
            (lambda line: pattern in line)
            if fixed
            else (lambda line: re.search(pattern, line) is not None)
        )
        hits = [i for i, line in enumerate(lines) if matcher(line)]
    except re.error as exc:
        raise ValueError(f"invalid regular expression: {exc}") from exc
    selected: list[str] = []
    last = -2
    for index in hits:
        start = max(0, index - context)
        end = min(len(lines), index + context + 1)
        if start > last + 1 and selected:
            selected.append("--")
        selected.extend(f"{i + 1}:{lines[i]}" for i in range(max(start, last + 1), end))
        last = end - 1
    return "\n".join(selected)


def cmd_show(args: argparse.Namespace) -> int:
    try:
        store = _store(args.store)
        raw, metadata = store.get(args.artifact_id)
    except Exception as exc:
        print(f"codexlean: {exc}", file=sys.stderr)
        return 1
    if args.metadata:
        print(json.dumps(metadata, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.raw and not any([args.lines, args.head, args.tail, args.grep]):
        sys.stdout.buffer.write(raw)
        return 0
    text = decode(raw)
    try:
        if args.grep:
            output = _grep(text, args.grep, args.context, args.fixed)
        else:
            output = _line_slice(text, args.lines, args.head, args.tail)
    except ValueError as exc:
        print(f"codexlean: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(output)
    if output and not output.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    try:
        store = _store(args.store)
        items = store.list_artifacts(args.limit)
    except Exception as exc:
        print(f"codexlean: artifact store unavailable: {exc}", file=sys.stderr)
        return 1
    for item in items:
        command = " ".join(shlex.quote(v) for v in item["command"])
        created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item["created_at"]))
        print(
            f"{item['id']}  {created}  {item['kind']:<10} exit={item['exit_code']:<3} "
            f"{item['raw_lines']:>6} lines  {command}"
        )
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    try:
        store = _store(args.store)
        data = store.stats(args.days)
    except Exception as exc:
        print(f"codexlean: artifact store unavailable: {exc}", file=sys.stderr)
        return 1
    if args.json:
        data["tokenizer"] = tokenizer_name()
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    raw_bytes = int(data.get("raw_bytes") or 0)
    compact_bytes = int(data.get("compact_bytes") or 0)
    raw_tokens = int(data.get("raw_tokens_est") or 0)
    compact_tokens = int(data.get("compact_tokens_est") or 0)
    byte_ratio = (raw_bytes - compact_bytes) / raw_bytes if raw_bytes else 0.0
    token_ratio = (raw_tokens - compact_tokens) / raw_tokens if raw_tokens else 0.0
    print(f"Runs: {int(data.get('runs') or 0)}")
    print(f"Compressed: {int(data.get('transformed') or 0)}")
    print(f"Bytes: {raw_bytes:,} -> {compact_bytes:,} ({byte_ratio:.1%} saved)")
    print(
        f"Estimated tokens: {raw_tokens:,} -> {compact_tokens:,} "
        f"({token_ratio:.1%} saved; {tokenizer_name()})"
    )
    print(f"Quality-guard fallbacks: {int(data.get('guard_failures') or 0)}")
    if data.get("by_kind"):
        print("\nBy kind:")
        for row in data["by_kind"]:
            raw = int(row["raw_bytes"] or 0)
            compact = int(row["compact_bytes"] or 0)
            ratio = (raw - compact) / raw if raw else 0.0
            print(f"  {row['kind']:<12} {row['runs']:>4} runs  {ratio:>6.1%} saved")
    return 0


def cmd_purge(args: argparse.Namespace) -> int:
    try:
        store = _store(args.store)
        count = store.purge(older_than_days=args.older_than, all_data=args.all)
    except Exception as exc:
        print(f"codexlean: artifact store unavailable: {exc}", file=sys.stderr)
        return 1
    print(f"Purged {count} artifacts")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    result = install_codex(
        args.scope,
        Path(args.project).expanduser() if args.project else None,
        add_agents=not args.no_agents,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Restart Codex, then use `$codexlean` or let the skill trigger implicitly.")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    result = uninstall_codex(
        args.scope, Path(args.project).expanduser() if args.project else None
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = run_doctor(
        args.scope, Path(args.project).expanduser() if args.project else None
    )
    failed = False
    for label, passed, detail in checks:
        mark = "OK" if passed else "FAIL"
        print(f"[{mark}] {label}: {detail}")
        failed = failed or not passed
    print(f"[INFO] artifact store: {default_store_path()}")
    print(f"[INFO] token counter: {tokenizer_name()}")
    return 1 if failed else 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from .benchmark import run_benchmark, write_report

    report = run_benchmark(profiles=args.profiles)
    if args.output:
        path = Path(args.output)
        write_report(report, path)
        print(path)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["quality_failures"] == 0 else 1


def _add_compression_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", type=_profile, default=Profile.SAFE, choices=list(Profile))
    parser.add_argument("--kind", help="Force content kind")
    parser.add_argument("--min-bytes", type=_non_negative_int, default=2048)
    parser.add_argument("--min-lines", type=_non_negative_int, default=40)
    parser.add_argument(
        "--min-savings",
        type=_percent,
        default=8.0,
        help="Minimum net byte savings percent (0-100)",
    )
    parser.add_argument("--store", help="Artifact SQLite path")
    parser.add_argument("--no-store-original", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codexlean")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    run = sub.add_parser("run", help="Run a command and compact its combined output")
    _add_compression_options(run)
    run.add_argument("--cwd")
    run.add_argument("--timeout", type=_non_negative_float)
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(func=cmd_run)

    filt = sub.add_parser("filter", help="Compact stdin")
    _add_compression_options(filt)
    filt.add_argument("--command", dest="command_text", help="Original command for format detection")
    filt.add_argument("--exit-code", type=int, default=0)
    filt.set_defaults(func=cmd_filter)

    show = sub.add_parser("show", help="Retrieve an exact stored output")
    show.add_argument("artifact_id")
    show.add_argument("--store")
    show.add_argument("--raw", action="store_true")
    show.add_argument("--metadata", action="store_true")
    selector = show.add_mutually_exclusive_group()
    selector.add_argument("--lines", help="1-based inclusive START:END")
    selector.add_argument("--head", type=_non_negative_int)
    selector.add_argument("--tail", type=_non_negative_int)
    selector.add_argument("--grep")
    show.add_argument("--fixed", action="store_true")
    show.add_argument("--context", type=_non_negative_int, default=2)
    show.set_defaults(func=cmd_show)

    listing = sub.add_parser("list", help="List stored outputs")
    listing.add_argument("--store")
    listing.add_argument("--limit", type=_non_negative_int, default=20)
    listing.set_defaults(func=cmd_list)

    stats = sub.add_parser("stats", help="Show local savings analytics")
    stats.add_argument("--store")
    stats.add_argument("--days", type=_non_negative_int)
    stats.add_argument("--json", action="store_true")
    stats.set_defaults(func=cmd_stats)

    purge = sub.add_parser("purge", help="Delete old exact-output artifacts")
    purge.add_argument("--store")
    purge.add_argument("--older-than", type=_non_negative_int, default=7)
    purge.add_argument("--all", action="store_true")
    purge.set_defaults(func=cmd_purge)

    install_parser = sub.add_parser("install", help="Install the Codex skill and guidance")
    install_parser.add_argument("--scope", choices=["user", "project"], default="user")
    install_parser.add_argument("--project")
    install_parser.add_argument("--no-agents", action="store_true")
    install_parser.set_defaults(func=cmd_install)

    uninstall_parser = sub.add_parser("uninstall", help="Remove CodexLean integration")
    uninstall_parser.add_argument("--scope", choices=["user", "project"], default="user")
    uninstall_parser.add_argument("--project")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    doctor = sub.add_parser("doctor", help="Check installation")
    doctor.add_argument("--scope", choices=["user", "project"], default="user")
    doctor.add_argument("--project")
    doctor.set_defaults(func=cmd_doctor)

    benchmark = sub.add_parser("benchmark", help="Run bundled compression/quality benchmark")
    benchmark.add_argument(
        "--profiles", nargs="+", choices=[p.value for p in Profile], default=[p.value for p in Profile]
    )
    benchmark.add_argument("--output")
    benchmark.set_defaults(func=cmd_benchmark)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
