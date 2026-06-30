# Project Spec — ComfiUIWrapper (`comfywrap`)

> **ComfiUIWrapper is a thin, typed, scriptable CLI that turns a prompt +
> parameters into a locally rendered artifact (today: LTX-2 text-to-video) by
> driving [comfy-cli](https://github.com/Comfy-Org/comfy-cli) as a subprocess.**
> It is the unattended, machine-readable front door to ComfyUI workflows — no
> node graph, no clicking, a stable contract a script or agent can depend on.

This is the **forward-looking purpose**. For the original implementation
spec/plan see repo-root `spec.md` and `output\architect\` (historical). For
*how* it's built, see `human-docs\HighLevelArchitecture.md` and
`human-docs\Implementation.md` (human reference).

---

## Why this exists

Some local AI pipelines — notably **LTX-2 audio+video text-to-video** — only run
through ComfyUI's node graph and model handling. comfy-cli already does the hard
ComfyUI work (launch/attach a headless server, convert UI→API graphs, track
progress over websocket, collect outputs, emit a JSON envelope). What it does
**not** give you is a *typed, capability-level* surface, a *stable result/error
contract* a program can rely on, or a *provenance record*.

`comfywrap` is exactly that thin layer: typed params → parameter injection into a
curated workflow template → drive comfy-cli → return the absolute artifact path +
a provenance sidecar, with a documented exit-code taxonomy. **The motivating
caller is an unattended backend job** (e.g. an Azure Service Bus consumer) that
maps a message to a `comfywrap generate … --json` call and branches on the exit
code — knowing nothing about ComfyUI.

## Positioning

| | **comfywrap** | **comfy-cli (`comfy run`)** | **ComfyUI GUI** |
|---|---|---|---|
| Surface | Typed `generate "<prompt>" --seed …` | Generic "run this graph" | Interactive node graph |
| Output | Stable `{capability,model,artifacts[]}` + provenance | `{schema,data.outputs[…]}` | Files in the UI |
| Hides | ComfyUI graph, node ids, comfy-cli quirks | — | — |
| Role | The typed seam a caller codes against | The engine comfywrap drives | Hands-on design |

`comfywrap` **drives** comfy-cli; it does not replace it. comfy-cli is the
engine; comfywrap is the typed "capability + contract + provenance" layer on top.

## What it does today

- **`text_to_video` via LTX-2** (`ltx2-t2v`), implemented under
  `src\comfywrap\capabilities\video\text_to_video\`, backed by the API template
  captured from `C:\AI\Softwares\user\default\workflows\video_ltx2_t2v.json`.
- LTX-2 generates **synchronized audio, including talking characters** — to make a
  character speak, put the line in the prompt (`...saying: "<line>"`); it lip-syncs
  natively. Do not mux external TTS. Details in
  `.github\instructions\capability.instructions.md`.
- Three commands: `doctor`, `capabilities`, `generate`.

## The automation contract (what makes it scriptable) — KEEP STABLE

A caller depends on these; do not churn them:

1. **Grammar:** `comfywrap [--version] [--json] [--config PATH] [-v] <command> [options]`.
   Commands: `doctor`, `capabilities`, `generate "<prompt>" [options]`.
2. **Human mode:** each saved artifact's absolute path on its own line; the
   **final stdout line is an absolute artifact path**. Diagnostics → stderr.
3. **`--json` mode:** exactly **one** JSON object on stdout:
   `{"capability","model","artifacts":[{"path","type","metadata"}]}` on success;
   `{"error":{"code","kind","message","hint","details"}}` on failure. The exit
   code is the authoritative signal.
4. **Exit codes (0–11):** `0` ok · `1` internal · `2` invalid args · `3` GPU
   stack unusable · `4` no GPU · `5` OOM · `6` gated model · `7` network ·
   `8` unknown capability/model · `9` backend unavailable (ComfyUI unreachable) ·
   `10` workflow execution error · `11` timeout.
5. **Provenance** — a `<artifact>.json` sidecar beside every artifact, identical
   to the embedded `artifacts[0].metadata`.
6. **Reproducibility** — same prompt + seed + params reproduces the result; the
   seed is always recorded (random seed chosen and recorded when omitted).

## Design principles

- **Drive comfy-cli as a subprocess; never `import comfy_cli`.** This gives crash
  isolation (a CUDA/segfault kills the child, not the worker), dependency
  isolation (comfywrap is stdlib-only; the heavy torch/cu12x stack stays in
  ComfyUI's venv), and a clean GPL boundary.
- **Modality-agnostic core, pluggable adapters.** The core
  (`src\comfywrap\core`) carries no model/video specifics; capabilities plug in
  via the registry. Future **video and non-video** models slot in with no core
  edits (see `agent-memory\adding-a-capability.md`).
- **Quarantine comfy-cli/ComfyUI quirks in one module:**
  `src\comfywrap\core\driver.py` is the only code that shells out to `comfy`.
- **Stable surface over convenience; provenance everywhere; honest about
  failures** (map comfy-cli `error.code` + exit onto the 0–11 taxonomy; never
  leak a raw traceback or the raw comfy-cli envelope).

## Key environment facts (target workstation)

- **GPU:** RTX 5090 (Blackwell, sm_120). comfywrap itself uses no torch; the
  cu12x stack lives in **ComfyUI's** venv (`C:\AI\Softwares\.venv`).
- **ComfyUI** runs headless on `127.0.0.1:8000` (ComfyUI Desktop), data root
  `C:\AI\Softwares`. comfywrap **attaches** if reachable, else auto-launches and
  keeps warm (so the multi-tens-of-GB model load is paid once).
- **comfy-cli** (`pip install comfy-cli`) provides the `comfy` binary; comfywrap
  resolves it from config / PATH / the active venv.
- `comfy run --json` streams NDJSON then a final `envelope/1`; outputs are
  `/view?filename&subfolder&type` URLs (no `--local-paths` in this version) which
  the driver resolves to absolute local paths under the ComfyUI output dir.

## Non-goals

- No GUI / interactive node editing; no arbitrary user-graph passthrough.
- No cloud / partner-node (paid) generation — local GPU only.
- The Service Bus listener / upload / retry policy is the **caller's** job, not
  this tool's.
- No new capability/modality built without an explicit ask (scope discipline).

## Related docs

Agent-facing (read these):
- `agent-memory\STRUCTURE.md` — the repo's doc layout.
- `agent-memory\adding-a-capability.md` — how to add a model/modality (no core edits).

Human-only — **do NOT read** (navigate the code under `src\comfywrap\` instead):
- `human-docs\HighLevelArchitecture.md` — core + driver + adapters and the flow.
- `human-docs\Implementation.md` — what the project is and how it was built.
- `human-docs\FirstUseAndHowToRunExplanation.md` — install + run your first generation.
- `human-docs\skill-invocation.md` — the exact machine-readable contract + exit codes.
- `human-docs\validation.md` — measured end-to-end results.
