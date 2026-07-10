---
name: codexlean
description: Reduce Codex token use in coding tasks without sacrificing correctness. Route large test, build, search, log, JSON, and file-listing output through the reversible `codexlean` CLI; retrieve exact originals when omitted detail can affect a decision. Also keep final responses technically complete and compact.
---

# CodexLean

Apply this workflow throughout coding tasks.

1. Run interactive, binary, already-short, and patch/diff commands normally.
2. For commands likely to emit more than 40 lines, run `codexlean run -- <command>` instead. Typical targets: tests, builds, linters, logs, broad searches, JSON responses, and recursive file listings.
3. Treat every preserved error, warning, path, test name, exit code, and summary as exact evidence.
4. A compressed result includes an artifact ID. Before making a decision that could depend on omitted detail, retrieve only what is needed:
   - full exact output: `codexlean show <id>`
   - matching sections: `codexlean show <id> --grep '<pattern>' --context 4`
   - exact range: `codexlean show <id> --lines START:END`
5. If format detection falls back to raw output, do not try to shorten it manually.
6. Never infer that omitted lines are irrelevant merely because they were omitted. Retrieve them when uncertainty remains.

## Response discipline

Lead with the result. Remove greetings, filler, tool-call narration, and repeated recaps. Keep all material facts, caveats, changed paths, test results, code, commands, identifiers, and exact error strings. Prefer short complete sentences over stylized or ambiguous fragments.

## Safety boundaries

- Do not persist probable credentials; CodexLean intentionally passes such output through unless the user explicitly opts in with `CODEXLEAN_STORE_SECRETS=1`.
- Git diffs are protected and passed through in the default quality-first profiles.
- Preserve the wrapped command's exit status.
- Use `codexlean stats` only for measured local savings; token counts are estimates unless `tiktoken` is installed.
