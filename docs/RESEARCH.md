# Research notes

Accessed 2026-07-10.

## Caveman

- Repository: https://github.com/JuliusBrussee/caveman
- License: MIT
- Relevant pattern: shorten model-facing prose while preserving code blocks, commands, API names, paths, and exact errors.
- Adopted: professional compact response discipline in the Codex Skill.
- Not adopted: deliberately ungrammatical “caveman” voice. It can reduce readability and is not needed for most of the technical savings.

## RTK (Rust Token Killer)

- Repository: https://github.com/rtk-ai/rtk
- License: Apache-2.0
- Relevant patterns: command-specific filters, wrapped exit-code preservation, real fixtures, snapshot/quality tests, and raw-output recovery hints for capped lists.
- Adopted: command-aware routing, combined output filtering, recovery handle, exit status propagation, and fixture-based tests.
- Not adopted: source code or binary bundling. CodexLean is a standalone standard-library Python implementation.

## Headroom

- Repository: https://github.com/headroomlabs-ai/headroom
- License: Apache-2.0
- Relevant patterns: content routing and Compress–Cache–Retrieve with on-demand originals.
- Adopted: local reversible artifact store, content classifier, critical-value preservation, and retrieval commands.
- Not adopted: API proxy, ML compression model, image routing, semantic cache, or MCP server. These add dependencies and compatibility surfaces beyond the quality-first Codex CLI scope.

## OpenAI Codex integration

- Skills: https://developers.openai.com/codex/skills
- AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- Relevant behavior: Codex discovers user skills at `$HOME/.agents/skills` and repository skills under `.agents/skills`; full Skill instructions load progressively when selected. `AGENTS.md` provides durable project/user guidance.
- Adopted: official Skill directory plus a small managed `AGENTS.md` block. No undocumented hook or traffic interception.

## Other considered techniques

- Whole conversation compaction: outside the supported local tool-output boundary.
- AST source compression: disabled because omitted function bodies can alter coding decisions.
- Diff context stripping: disabled in quality-first profiles.
- Smaller-model routing: not implemented because model equivalence requires a separate task benchmark.
- Prompt/API proxying: avoided to preserve authentication, streaming, tool schema, and multimodal compatibility.
