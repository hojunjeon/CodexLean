# Changelog

## 0.2.0 — 2026-07-21

- Added first-class `linux/` and `windows/` platform directories at the repository root; installers moved from `scripts/` to their platform folders.
- Added isolated virtual-environment installers and matching uninstallers that do not modify system Python packages.
- Added Linux installation smoke coverage and a Windows CI lane.
- Fixed Windows timeout termination where `signal.SIGKILL` is unavailable.
- Close every SQLite connection deterministically so Windows can remove temporary benchmark stores.
- Protect unrelated launchers and caller-owned storage-directory permissions.
- Added Skill-drift, checksum, source-distribution, and native installer safety gates to CI.
- Kept one shared Python core to prevent platform implementations from drifting.

## 0.1.1 — 2026-07-10

- Preserved exact `path:line` text for error-bearing matches and salient symbol definitions in grouped search output.
- Added a regression test for the cross-benchmark `src/auth.py:77:def validate_expiry` case; the 15-case strict visible gate now passes 15/15.
- Added offline `cl100k_base` tokenizer support through the optional `benchmark` dependency and corrected tokenizer backend reporting.
- Added Korean public-release documentation, reproducible cross-benchmark data, charts, and GitHub Actions CI.

## 0.1.0 — 2026-07-10

- Added a Codex Skill and managed `AGENTS.md` integration using public `.agents/skills` locations.
- Added reversible command-output compression for tests, logs, JSON, search, filesystem listings, Git status/log, and repetitive generic output.
- Added distributed search/tree sampling, repeated search-body aliases, Git status grouping, and protected exact Git diff passthrough.
- Added zlib/SHA-256 local artifacts, exact/prefix retrieval, range/grep/head/tail views, local statistics, expiration, and purge commands.
- Added fail-open quality guards, probable-secret non-persistence, metadata credential redaction, and no-orphan net-savings handling.
- Preserved wrapped exit codes, POSIX signal conventions, timeout code 124, and partial timeout output.
- Added 32 automated tests and a 10-fixture reproducible benchmark corpus.
