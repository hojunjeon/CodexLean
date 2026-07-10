# CodexLean benchmark

Token counter: `tiktoken:cl100k_base_offline`
Quality failures: **0**

## Aggregate

| Profile | Cases | Transformed | Byte saving | Estimated token saving |
|---|---:|---:|---:|---:|
| strict | 10 | 1 | 8.2% | 9.7% |
| safe | 10 | 8 | 88.0% | 87.1% |
| max | 10 | 8 | 88.8% | 88.3% |

## strict

| Fixture | Kind | Action | Byte saving | Estimated token saving | Quality |
|---|---|---|---:|---:|---|
| pytest-pass | test | passthrough | 0.0% | 0.0% | pass |
| pytest-fail | test | passthrough | 0.0% | 0.0% | pass |
| logs | log | passthrough | 0.0% | 0.0% | pass |
| json-array | json | compressed | 40.2% | 44.0% | pass |
| search | search | passthrough | 0.0% | 0.0% | pass |
| tree | tree | passthrough | 0.0% | 0.0% | pass |
| generic-progress | generic | passthrough | 0.0% | 0.0% | pass |
| git-status | git_status | passthrough | 0.0% | 0.0% | pass |
| git-diff-protected | git_diff | passthrough | 0.0% | 0.0% | pass |
| secret-passthrough | log | passthrough | 0.0% | 0.0% | pass |

## safe

| Fixture | Kind | Action | Byte saving | Estimated token saving | Quality |
|---|---|---|---:|---:|---|
| pytest-pass | test | compressed | 84.7% | 83.6% | pass |
| pytest-fail | test | compressed | 77.8% | 79.1% | pass |
| logs | log | compressed | 95.5% | 95.6% | pass |
| json-array | json | compressed | 96.8% | 97.4% | pass |
| search | search | compressed | 89.7% | 83.7% | pass |
| tree | tree | compressed | 96.9% | 97.0% | pass |
| generic-progress | generic | compressed | 98.3% | 98.2% | pass |
| git-status | git_status | compressed | 31.9% | 23.9% | pass |
| git-diff-protected | git_diff | passthrough | 0.0% | 0.0% | pass |
| secret-passthrough | log | passthrough | 0.0% | 0.0% | pass |

## max

| Fixture | Kind | Action | Byte saving | Estimated token saving | Quality |
|---|---|---|---:|---:|---|
| pytest-pass | test | compressed | 86.3% | 85.2% | pass |
| pytest-fail | test | compressed | 79.7% | 81.1% | pass |
| logs | log | compressed | 96.3% | 96.4% | pass |
| json-array | json | compressed | 96.8% | 97.4% | pass |
| search | search | compressed | 91.8% | 88.5% | pass |
| tree | tree | compressed | 98.0% | 98.0% | pass |
| generic-progress | generic | compressed | 98.3% | 98.2% | pass |
| git-status | git_status | compressed | 31.9% | 23.9% | pass |
| git-diff-protected | git_diff | passthrough | 0.0% | 0.0% | pass |
| secret-passthrough | log | passthrough | 0.0% | 0.0% | pass |

## Interpretation

The token values are exact when `tiktoken` is installed; otherwise they use the documented UTF-8 proxy. Byte reduction is exact. Quality checks require decisive errors, configured sentinel facts, protected diff content, and byte-for-byte artifact recovery.
