# Validation record

Build environment: Python 3.13.5, Linux container, 2026-07-10.

## Automated tests

Command:

```bash
PYTHONPATH=src pytest -q
```

Result before release packaging:

```text
33 passed
```

Covered behavior:

- command/content detection, including build-versus-test discrimination
- SQLite exact byte recovery, hash verification, prefix lookup, and retention refresh
- command metadata credential redaction and invalid artifact-ID rejection
- passing and failing test compression
- every decisive line retained on non-zero exits
- fatal log and traceback retention
- JSON critical-record retention and strict data-model equivalence
- protected Git diff exact passthrough, including ANSI-bearing content
- probable-secret passthrough with no artifact creation for multiple secret forms
- no orphan artifact when the net-savings gate rejects a candidate
- raw fail-open behavior for missing or failing artifact stores
- every changed path/status retained in grouped Git status output
- search grouping, distributed selection, repeated-body aliases, and exact `path:line` preservation for salient errors/symbols
- tree hierarchy reconstruction, key-file retention, and long-listing protection
- project Skill installation idempotence and reversible managed-block removal
- wrapped process exit-code and POSIX signal convention preservation
- timeout code 124 with already-emitted partial output retained
- zero-length tail selection and mutually exclusive retrieval selectors
- bundled benchmark quality gates

## Benchmark

Commands:

```bash
PYTHONPATH=src python3 -m codexlean benchmark --output benchmarks/results.md
PYTHONPATH=src python3 -m codexlean benchmark --output benchmarks/results.json
```

Packaging result:

| Profile | Exact byte saving | Estimated token saving | Quality failures |
|---|---:|---:|---:|
| strict | 8.2% | 9.7% | 0 |
| safe | 88.0% | 87.1% | 0 |
| max | 88.8% | 88.3% | 0 |

The corpus contains 10 synthetic, intentionally noisy fixtures: passing/failing pytest, logs, JSON, search output, a large filesystem listing, progress output, Git status, protected diff, and secret-bearing logs. Quality checks require configured sentinel facts, all detected decisive error lines, expected passthroughs, and byte-for-byte artifact recovery.

The figures describe the included corpus. They are not a guarantee for arbitrary repositories or an end-to-end provider billing reduction. The release benchmark used the bundled `tiktoken:cl100k_base_offline` encoding; exact byte measurements remain independent of the tokenizer.

## Cross benchmark

The expanded ON/OFF suite combines the 10 built-in fixtures with five independently shaped pytest, ripgrep, JSON API, Git diff, and short-response cases. Version 0.1.1 produced 102,489 → 14,723 cl100k tokens (85.6% visible reduction), with 15/15 strict visible gates and 15/15 exact-original availability. See `benchmarks/cross_results.md`.

## Release packaging checks

The release procedure performs the following against the final wheel and ZIP:

1. compile all package modules;
2. rerun all source tests;
3. build the wheel without downloading dependencies;
4. verify that the wheel contains the bundled Skill and `agents/openai.yaml`;
5. install the wheel into a clean virtual environment;
6. install the project-scoped Skill into a temporary repository and run `doctor`;
7. wrap a failing noisy process, verify its exit code and preserved decisive error;
8. retrieve the exact stored output and compare bytes;
9. run the installed benchmark and require zero quality failures;
10. validate the final ZIP and compute SHA-256.

The concrete packaging output is recorded in `RELEASE-VALIDATION.txt`.

## Not executed

An authenticated Codex CLI binary/session was unavailable in the build environment. Therefore this release does not claim:

- provider-reported input/output token A/B measurements;
- task-success non-inferiority on SWE-bench or a private repository corpus;
- Codex desktop/UI behavior;
- Windows-native child-process tests beyond portable Python logic and static installer review.
