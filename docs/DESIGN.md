# CodexLean design

## Objective and boundary

CodexLean minimizes model-facing terminal output while preserving correctness-oriented evidence. It does not rewrite the Codex API request, conversation history, source files, system prompt, or model choice. The optimized boundary is noisy command output plus concise response guidance delivered through a Codex Skill.

The primary invariant is fail-open behavior: a failed detector, filter, quality check, artifact store, or net-savings check returns the exact raw command output.

## Data flow

```text
Codex / user
  -> codexlean run -- <command>
  -> combined stdout+stderr file-backed capture
  -> binary / threshold / probable-secret checks
  -> command + content detector
  -> profile-specific filter
  -> quality guard
  -> prospective rendered-size check
  -> exact local artifact write when omission occurred
  -> compact result + recovery handle
  -> Codex context
```

The child process exit status remains the wrapper exit status. POSIX signals are normalized to `128 + signal`; timeout and interruption use 124 and 130. A temporary file preserves partial output on timeout and avoids maintaining two live in-memory copies while the child runs.

## Why a Skill instead of an API proxy

Codex discovers user and repository skills from `.agents/skills`, with the skill body loaded when selected. The Skill approach leaves authentication, provider traffic, streaming, tool schemas, and multimodal endpoints unchanged. A short managed `AGENTS.md` block makes wrapper use durable without inserting the full Skill instructions into every turn.

The tradeoff is adoption: Codex must select the Skill or follow the `AGENTS.md` rule and invoke the wrapper. There is no undocumented shell hook.

## Detection

The detector combines executable/subcommand signals with output markers. High-confidence routes include:

- test runners: pytest, Jest/Vitest, Cargo test, Go test, Maven/Gradle test, dotnet test
- Git status, diff, and log
- grep/rg search
- find/tree/ls listings
- valid JSON
- log-file commands and severity-dense text

Unknown content uses the generic filter. Selective omission from low-confidence content is rejected unless the transformation itself is deterministic, such as exact duplicate-run collapse or an obvious progress family.

## Filters

### Tests

Passing output keeps the runner preamble, every detected warning, and summaries. Failing output keeps every detected failure/assertion/exception line, source locations, local context windows, and the final summary. The quality guard independently checks every decisive line for non-zero exits.

### Logs

ERROR/FATAL/CRITICAL/PANIC, exceptions, warnings, and nearby context are retained. Repetitive INFO/DEBUG templates are grouped after volatile timestamps, UUIDs, numeric values, and request-like IDs are normalized. Counts remain visible.

### JSON

`strict` removes whitespace only and preserves the parsed data model. `safe`/`max` keep object keys and array boundaries, sample the first/last and critical records, and calculate summaries for broadly present numeric fields. Full JSON remains retrievable whenever items are omitted.

### Search

Results are grouped by file, so repeated path prefixes disappear while each selected location remains exact. Every file name is preserved, sample locations are distributed across the complete match range rather than biased to the head, and every error-like match is retained. Repeated match bodies are defined once in a local template dictionary and referenced by an alias in selected rows. Omitted matches remain in the exact artifact.

### File listings

Common Unicode and ASCII `tree` hierarchies are reconstructed into full relative paths before compression. Flat `find`-style paths are grouped by top-level component; repeated top prefixes are removed; samples are distributed across each group; key project files and extension counts remain visible. Ambiguous hierarchies and long `ls -l` rows fall back conservatively rather than being reinterpreted.

### Git

Canonical `git status` records are grouped by staged/unstaged/untracked state while every changed path and status code remains visible. Help boilerplate is removed. `git diff` is a protected exact-passthrough path, including ANSI-bearing output. `git log` bodies are capped only under the aggressive profile.

### Generic

Exact consecutive duplicates and obvious progress families are collapsed. `max` may retain critical/head/tail windows for recognized repetitive output. Low-confidence selective omission is rejected.

## Quality guard

A candidate is rejected when any condition below holds:

1. A non-zero exit has no recognizable decisive line.
2. Any decisive line from a non-zero exit is absent.
3. A filter-declared critical or protected string is absent.
4. Lines are omitted without an exact-recovery store.
5. Format confidence is below the selective-omission threshold.
6. The candidate becomes empty.
7. The final output, including its retrieval handle, is not strictly smaller.
8. Net reduction is below the configured threshold.

Storage is attempted only after the prospective net-savings gate, preventing artifacts for rejected candidates. A write failure causes exact raw passthrough.

## Artifact store

SQLite stores zlib-compressed raw bytes, complete SHA-256 digests, content-addressed IDs, redacted command metadata, and local run metrics. Retrieval accepts unambiguous ID prefixes and verifies the digest before returning data. Reusing identical content refreshes its retention timestamp. Directories and the database are restricted to the current user where the operating system supports POSIX modes.

Probable credential output is not persisted unless `CODEXLEAN_STORE_SECRETS=1` is set. The heuristic covers common key/token/password assignments, bearer credentials, private-key PEM headers, OpenAI-like key prefixes, GitHub tokens, and AWS access-key IDs. This is a safety heuristic, not a complete secret scanner.

## Profiles and convergence

Development compared three layers:

1. `strict`: deterministic representation changes only.
2. `safe`: recognized-format compression with distributed samples, quality guards, and exact recovery.
3. `max`: smaller first-pass samples for the same recognized formats.

On the bundled aggregate corpus, `safe` reduced exact bytes by 88.0%; `max` reduced 88.8%. The remaining 0.8 percentage-point gain does not justify making `max` the default: exact recovery guarantees availability, but not that an agent will always recognize when it should retrieve omitted context. Further high-volume reduction would require optimizing source-code context, conversation history, model responses, or API-level traffic, all outside this release's compatibility-preserving boundary.
