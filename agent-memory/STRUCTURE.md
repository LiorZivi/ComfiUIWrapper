# Repository documentation structure (agent: read this first)

This repo separates **agent-facing** docs from **human-facing** docs. If you are an AI agent working here: **read `agent-memory\`; do NOT spend context reading `human-docs\`.**

## `agent-memory\` — read these (the agent's source of truth)

- `agent-memory\STRUCTURE.md` — this file: the doc layout + what to read.
- `agent-memory\ProjectSpec.md` — the project's purpose and the **stable automation contract** (the `comfywrap` CLI / `--json` envelope / exit codes 0–11) you must preserve.
- `agent-memory\adding-a-capability.md` — the recipe for adding a workflow / model / modality (no core edits).

Plus the always-applied instruction files (loaded automatically by Copilot):

- `.github\copilot-instructions.md` — project-wide rules (architecture summary, the subprocess-not-import rule, comfy-cli/ComfyUI facts, build/test, scope discipline).
- `.github\instructions\capability.instructions.md` — rules for capability adapters under `src\comfywrap\capabilities\`.
- `.github\instructions\docs.instructions.md` — how to write docs.

## `human-docs\` — do NOT read (these are for the human maintainer)

`human-docs\HighLevelArchitecture.md`, `human-docs\Implementation.md`, `human-docs\FirstUseAndHowToRunExplanation.md`, `human-docs\skill-invocation.md`, and `human-docs\validation.md` are narrative / reference / historical material written for a person. **Everything you need to act is in `agent-memory\` + the instruction files above.** For specifics, navigate the **code** directly (grep/glob/read `src\comfywrap\`) rather than these long-form docs.

## Why the split

`agent-memory\` stays small and high-signal so agent context isn't bloated by prose meant for humans. `human-docs\` can be as long and narrative as the maintainer wants. **Keep `agent-memory\` accurate when behavior changes;** the human owns `human-docs\`.

## Where else things live

- Source: `src\comfywrap\` (the `core\` runtime + `capabilities\` adapters).
- Bundled workflow templates: `src\comfywrap\data\workflows\` (loaded at run time); a reference copy also lives at repo-root `workflows\`.
- Tests: `tests\` (GPU-free; `.venv\Scripts\python.exe -m pytest`).
- Template capture helper: `scripts\capture_template.py`.
- Historical plan/spec: repo-root `spec.md` and `output\architect\` (do not treat as current; behavior is the source of truth).
