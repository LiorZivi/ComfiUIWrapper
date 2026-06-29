# ComfiUIWrapper — Specification

> Source-of-truth design doc for the project. A fresh build session should read
> this top-to-bottom before writing any code.

## 1. Purpose

ComfiUIWrapper is a **standalone, scriptable tool that runs ComfyUI workflows
headlessly**. Given a prompt (plus optional model/parameters), it selects the
correct pre-authored ComfyUI workflow, runs it against a local, headless ComfyUI
instance on the user's own GPU, and returns the **absolute path to the produced
artifact** (e.g. an `.mp4` video) together with a machine-readable provenance
record.

It exists because some local AI pipelines — notably **LTX-2 audio+video
text-to-video** — are only runnable today through ComfyUI's node graph and model
handling, not through plain `diffusers`. Rather than reimplement those pipelines,
ComfiUIWrapper **drives ComfyUI** behind a small, **typed, stable command-line
contract**, so callers never touch the brittle internals of a node graph.

The tool is **self-contained**: it does not depend on, import, or reference any
other project. It only *follows a generic invocation convention* (Section 4) so
that an external caller can invoke this tool — or any other local-AI execution
tool that follows the same convention — without changing how it builds the
command or parses the result.

## 2. Goals and non-goals

**Goals**
- Run ComfyUI workflows **headless / programmatically** (no browser, no clicking).
- Expose a **small, capability-oriented surface** (e.g. `text_to_video`) with a
  **typed parameter interface** — not a raw "run any graph" passthrough.
- A **deterministic, scriptable CLI contract**: one absolute artifact path on
  stdout (human mode) / one JSON object (`--json`), documented exit codes,
  diagnostics on stderr.
- **Provenance**: every run writes the artifact plus a sidecar JSON capturing
  exactly how it was produced.
- **Self-contained orchestration** of a local ComfyUI: locate, optionally launch,
  submit, monitor, collect, shut down.
- **GPU-free unit tests** by mocking the ComfyUI HTTP/websocket surface.

**Non-goals (v1)**
- No GUI / interactive node editing.
- No training / fine-tuning.
- No general REST passthrough of arbitrary user-supplied graphs (capabilities
  are curated and typed).
- No cloud execution; local GPU only, no CPU fallback for real generation.
- Modalities beyond the first text-to-video slice are **seams, not
  implementations**.

## 3. Architecture

Two layers — a reusable core/runtime plus pluggable capability adapters.

### 3.1 Core / runtime
- **CLI dispatcher** — builds the command grammar (Section 4), registers core
  commands (`doctor`, `capabilities`), and lets each capability adapter
  contribute its own subcommands (so a new capability adds commands without
  touching this module).
- **Backend manager (ComfyUI session)** — locates a ComfyUI install; either
  **attaches** to an already-running server or **launches** one headless;
  performs readiness/health checks; submits prompts to `/prompt`; tracks progress
  via websocket `/ws` and/or polls `/history/{prompt_id}`; collects produced
  files; manages lifecycle (idle reuse, graceful shutdown). **All
  ComfyUI-version-specific quirks live here.**
- **Workflow registry** — keyed by `(capability_id, model_id)`. Each entry points
  to an **API-format workflow template** plus a **parameter binding** (how typed
  inputs map onto specific nodes) and the **expected model files**.
- **Parameter injection** — given typed inputs (prompt, negative, seed, size,
  length, fps, steps, model, …), produce a concrete API-format prompt by setting
  node widget values addressed by **stable role/title bindings** (avoid raw
  numeric node IDs where possible) so injection survives minor graph edits.
- **Artifact + provenance writer** — collision-safe filenames; writes the
  artifact and a sidecar `.json` provenance record.
- **Error taxonomy** — typed errors → documented exit codes (Section 4.3); always
  render an actionable message to stderr, never a raw traceback.
- **Config** — layered: CLI flag > environment (`CUW_*`) > config file > builtin.

### 3.2 Capability adapters
- One adapter per workflow family. v1: **`text_to_video`** backed by the LTX-2
  workflow.
- An adapter declares: its `capability_id`, its `model_id`s (each → a workflow
  template + binding + expected files), the typed parameter schema it accepts,
  and the artifact type it emits (`video/mp4`).
- Adding a capability = a new adapter module + its workflow template; **no core
  changes**.

## 4. Invocation contract (stable, swappable)

The command grammar, stdout discipline, and exit codes below are **the public
contract**. They are intentionally generic and tool-agnostic so a caller can swap
between compatible tools without changing how it builds the command or parses the
result. (The binary *name* is the only thing the caller varies.)

### 4.1 Grammar
```
comfywrap [--version] <command> [options]
```
Global flags (available on every subcommand):
- `--json` — emit exactly one machine-readable JSON object on stdout; all
  diagnostics go to stderr.
- `--config <path>` — explicit config file (else discover `./comfywrap.toml` or
  `./config.toml`).
- `-v, --verbose` — extra diagnostics on stderr.

Core commands:
- `doctor` — verify the execution environment: GPU + CUDA stack, that ComfyUI is
  reachable/launchable, and that required model files are present.
- `capabilities` — list registered capabilities and their models/workflows.

Generation command (capability-contributed):
- `generate "<prompt>" [options]` — run a capability. Shared options mirror a
  common generation surface so callers can swap tools:
  - `--model <id>` — model/workflow variant (e.g. `ltx2-t2v`).
  - `--output-dir <dir>` — directory for outputs.
  - `--seed <int>` — reproducibility seed.
  - `--negative "<text>"` — negative prompt (where supported).
  - Video knobs: `--size WxH` (or `--width`/`--height`), `--length <frames>` (or
    `--seconds`), `--fps <n>`, `--steps <n>`, `--audio/--no-audio`.
  - Additional optional flags are **additive**: a caller using only the shared
    subset is never broken by them.
- `interactive` (optional, later) — a REPL that keeps ComfyUI warm between prompts.

### 4.2 stdout / stderr discipline
- **Human mode:** print each saved artifact's **absolute path**, one per line;
  the **final stdout line is a saved artifact path**. Progress/diagnostics →
  stderr.
- **`--json` mode:** write **exactly one** JSON object to stdout and nothing else:
```json
{
  "capability": "text_to_video",
  "model": "ltx2-t2v",
  "artifacts": [
    { "path": "C:\\...\\<file>.mp4", "type": "video/mp4", "metadata": { } }
  ]
}
```
- `doctor --json` and `capabilities --json` each emit a single object as well.

### 4.3 Exit codes
Codes 0–8 carry conventional, tool-agnostic meanings (a caller can handle them
identically across compatible tools). 9–11 are backend-specific extensions; a
caller that only understands 0–8 treats them as a generic failure.

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Unexpected / internal error |
| 2 | Invalid arguments or parameter values |
| 3 | GPU compute stack unusable (CUDA/torch build mismatch) |
| 4 | No supported GPU detected |
| 5 | Out of (V)RAM during execution |
| 6 | Gated / licensed model or missing token (weights unobtainable) |
| 7 | Network / download failure |
| 8 | Unknown capability / model / workflow id |
| 9 | Execution backend unavailable (ComfyUI failed to start / unreachable) |
| 10 | Workflow execution error (a node failed during the run) |
| 11 | Timeout waiting for completion |

### 4.4 Provenance sidecar
Every artifact gets a `<artifact>.json` sidecar containing at least: prompt,
negative, seed, capability, model/workflow id, resolved parameters, the workflow
template id/version, ComfyUI version, model file names (and, where feasible,
hashes), start/end timestamps, and the output filename. The same record is
embedded as `artifacts[].metadata` in `--json` mode.

## 5. ComfyUI integration details
- **Workflow format:** ComfyUI's `/prompt` endpoint consumes the **API format**
  (the prompt graph), **not** the UI "workflow" JSON. The pre-authored workflow
  must be exported/stored in **API format** as the template. (The source UI
  workflow may contain subgraphs that flatten on export.) Capturing/refreshing
  this template is an explicit setup step (see Appendix A).
- **Submission:** `POST /prompt` with `{prompt, client_id}`; receive a
  `prompt_id`.
- **Progress / completion:** subscribe to websocket `/ws?clientId=...` for
  `executing` / `progress` / `executed` events, and/or poll
  `GET /history/{prompt_id}`.
- **Output collection:** read produced files from the run's results (e.g. the
  `SaveVideo` node output under ComfyUI's `output/` dir); copy/move to
  `--output-dir` with a collision-safe name.
- **Server lifecycle:** discover a configured ComfyUI; if not running and
  auto-launch is enabled, spawn it headless
  (`python main.py --listen 127.0.0.1 --port <p> ...`), wait for readiness
  (`GET /` / `/system_stats`), reuse across requests, and shut down (or leave
  warm) per config.
- **Parameter binding:** address target nodes by a stable key (node `_meta.title`
  / a declared role) captured in the capability's binding map, so prompt/seed/size
  injection survives minor graph edits and re-exports.
- **VRAM:** rely on ComfyUI's own memory management; surface OOM as exit 5.

## 6. First milestone — vertical slice
Deliver, end-to-end, for **`text_to_video` via the LTX-2 workflow**:
1. `doctor` — confirms GPU/CUDA, ComfyUI reachable/launchable, required model
   files present.
2. `capabilities` — lists `text_to_video` and its model(s).
3. `generate "<prompt>" --model ltx2-t2v --seed <n> [--json]` — injects
   prompt+seed into the API-format LTX-2 template, runs it headless, collects the
   `.mp4`, writes the sidecar, and prints the absolute path (or the JSON object).

**Acceptance:** a caller can run `generate ... --json`, parse one object, read
`artifacts[0].path`, and find a playable `.mp4`; exit codes behave per Section
4.3; unit tests pass GPU-free with the ComfyUI surface mocked.

## 7. Configuration
Layered (CLI > `CUW_*` env > config file > builtin). Keys include: ComfyUI
location & launch (path, host, port, extra args, auto-launch on/off, keep-warm
on/off), workflow/model base dir, default output dir, request/run timeouts,
default model. No secrets committed; tokens via environment only.

## 8. Proposed repo layout
```
ComfiUIWrapper/
  pyproject.toml            # console script: comfywrap = "comfywrap.core.cli:main"
  README.md
  spec.md                   # this file
  src/comfywrap/
    core/                   # cli, backend (ComfyUI session), registry, config,
                            # injection, output/provenance, errors, doctor
    capabilities/
      video/
        text_to_video/      # adapter + binding for the LTX-2 workflow
  workflows/                # API-format workflow templates (.json)
  tests/                    # GPU-free unit tests (mock ComfyUI HTTP/ws)
  scripts/                  # bootstrap / dev helpers
  docs/
```

## 9. Tech stack
- Python 3.12, **argparse** (match the contract grammar; no heavy CLI dep),
  `httpx` or `requests` for HTTP, `websocket-client` / `websockets` for progress,
  stdlib `json` / `tomllib` for config. Optional `pydantic` for parameter
  schemas. Packaged with a `pyproject.toml` console script.

## 10. Testing
- **Unit (GPU-free, default):** mock the ComfyUI HTTP/websocket —
  submit → progress → history → output collection; cover injection,
  filename/provenance, error→exit-code mapping, config layering, and the `--json`
  envelope shape.
- **Integration (opt-in):** behind an env flag, run against a real local ComfyUI
  + GPU and assert a real `.mp4` is produced.

## 11. Constraints
- **Self-contained:** do not depend on, import, or reference any other local
  project. Only the invocation *convention* (Section 4) is shared, and it is
  specified here intrinsically.
- Local GPU only; no cloud, no CPU fallback for actual generation.
- Keep ComfyUI-version-specific logic isolated in the backend manager.
- **Scope discipline:** implement only the text-to-video slice first; other
  capabilities are seams.

## 12. Open questions (decide during the build)
- Console-script / binary name (`comfywrap`? `cuwrap`?).
- Auto-launch ComfyUI vs. require an already-running instance for v1.
- How the API-format template is captured (manual export from ComfyUI vs.
  programmatic conversion of the UI workflow).
- Exact typed parameter set for LTX-2 (length/fps/size ranges, audio on/off, LoRA
  toggles) — and which are first-class in v1 vs. fixed to template defaults.

---

## Appendix A — Current environment (target machine)

> Concrete facts for wiring the first slice. These describe the **ComfyUI**
> install on this machine; they are not a dependency on any other project.

- **OS / shell:** Windows, PowerShell (use backslash paths).
- **GPU:** NVIDIA RTX 5090, 32 GB, Blackwell (sm_120 / compute cap 12.0). Any GPU
  code must use a CUDA 12.8+ (cu128) PyTorch build; stock PyPI/cu121 wheels don't
  support sm_120. (ComfyUI's own venv already satisfies this.)
- **ComfyUI Desktop app:** `C:\AI\ComfyUI\resources\ComfyUI` (the app +
  `comfy_extras` core nodes — LTX-2 nodes live in
  `comfy_extras\nodes_lt*.py`, `nodes_video.py`).
- **ComfyUI data root (`base_path`):** `C:\AI\Softwares` — contains `models\`,
  `user\`, `output\`, `custom_nodes\`, and a `.venv\` with `diffusers`. (Set in
  `%APPDATA%\ComfyUI\extra_models_config.yaml`.)
- **Source UI workflow (text-to-video):**
  `C:\AI\Softwares\user\default\workflows\video_ltx2_t2v.json` — a **subgraph**
  workflow named *"Text to Video (LTX 2.0)"*. **Must be exported to API format**
  for `/prompt` (e.g. enable Dev Mode in ComfyUI → *Workflow → Export (API)*), and
  the resulting JSON stored under `workflows/`.
- **Model files the LTX-2 t2v workflow loads** (under `C:\AI\Softwares\models\`):
  | Role | Path |
  |------|------|
  | Diffusion model + video VAE | `models\checkpoints\ltx-2-19b-dev-fp8.safetensors` (~25 GB) |
  | Text encoder (Gemma 3 12B) | `models\text_encoders\gemma_3_12B_it_fp4_mixed.safetensors` (~8.8 GB) |
  | Audio VAE | reuses `models\checkpoints\ltx-2-19b-dev-fp8.safetensors` |
  | Spatial x2 upscaler | `models\latent_upscale_models\ltx-2-spatial-upscaler-x2-1.0.safetensors` (~0.93 GB) |
  | Distilled LoRA | `models\loras\ltx-2-19b-distilled-lora-384.safetensors` (~7.15 GB) |
  | Camera-control LoRA (optional) | `models\loras\ltx-2-19b-lora-camera-control-dolly-left.safetensors` (~0.30 GB) |
- **Generated videos** currently land in `C:\AI\Softwares\output\video\`.
- **All workflow nodes are ComfyUI core** (`comfy_extras`) — no third-party
  custom-node pack is required to run this workflow.
