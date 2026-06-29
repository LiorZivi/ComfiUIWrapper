# ComfiUIWrapper — Specification

> Source-of-truth design doc for the project. A fresh build session should read
> this top-to-bottom before writing any code.

## 0. TL;DR (what changed and why)

ComfiUIWrapper is a **thin, typed wrapper that drives the official
[`comfy-cli`](https://github.com/Comfy-Org/comfy-cli)** to run ComfyUI workflows
locally and headlessly. It does **not** re-implement ComfyUI orchestration.

`comfy-cli` (`pip install comfy-cli`, GPL-3.0) already provides the hard parts:
launch/stop a local headless server (`comfy launch --background` / `comfy stop`),
submit a workflow and **auto-convert UI-format JSON → API format**, track progress
over websocket, collect outputs, and emit a structured `--json` envelope with an
error-code → exit-code mapping (`comfy run --wait --local-paths --json`).

So this project is **only** the value that `comfy-cli` does *not* provide:

1. A **typed, capability-oriented surface** (`generate "<prompt>" --model ltx2-t2v
   --seed N --size WxH --length F --fps N …`) instead of "hand-edit a node graph".
2. **Parameter injection** of those typed inputs into the right nodes (by stable
   title/role bindings) of a curated workflow template.
3. A **stable, tool-agnostic CLI/JSON contract** (Section 4) — one JSON object,
   `artifacts[].path`, documented exit codes 0–11 — that a caller codes against
   once and never changes.
4. A **provenance sidecar** per artifact.
5. A capability-specific **`doctor`** (LTX-2 model files present, GPU/CUDA usable,
   `comfy` reachable).

`comfy-cli` is invoked **as a subprocess** (never imported), which both matches the
design philosophy below and keeps this project free of GPL obligations (calling a
GPL program at arm's length over a CLI is mere aggregation, not a derivative work).

## 1. Purpose

ComfiUIWrapper is a **standalone, scriptable tool that produces a local AI artifact
(e.g. an LTX-2 `.mp4`) from typed parameters**, by driving `comfy-cli` against a
local, headless ComfyUI on the user's own GPU. Given a prompt (plus optional
model/parameters) it selects the correct pre-authored workflow, injects the typed
inputs, runs it through `comfy-cli`, and returns the **absolute path to the produced
artifact** together with a machine-readable provenance record.

It exists because some local AI pipelines — notably **LTX-2 audio+video
text-to-video** — are only runnable today through ComfyUI's node graph and model
handling. Rather than make every caller learn ComfyUI node graphs, `comfy-cli`
flags, and per-workflow node IDs, ComfiUIWrapper exposes a **small, typed,
capability surface** behind a **stable command-line contract** (Section 4).

### 1.1 Motivating scenario (the intended caller)

A **backend job listens to an Azure Service Bus queue**. When a message arrives —
carrying a prompt payload plus properties (seed, size, length, fps, audio, …) — the
job must generate an LTX-2 text-to-video clip **locally** on the RTX 5090 and then
upload/settle the result.

> **Out of scope:** the Service Bus listener, message parsing, retry/dead-letter
> policy, upload, and status reporting are **not** part of this project.

ComfiUIWrapper is the **seam** that lets that consumer stay infrastructure-only.
The consumer maps a message to a typed `comfywrap generate … --json` invocation,
runs it as a subprocess, parses one JSON object, reads `artifacts[0].path`, and uses
the **exit code** to decide retry vs. dead-letter. The consumer therefore knows
nothing about ComfyUI, LTX-2 node graphs, or `comfy-cli` quirks — all of that lives
here. (See Section 9 for the integration pattern.)

## 2. Goals and non-goals

**Goals**
- Turn typed parameters into a produced artifact by **driving `comfy-cli`**
  (`comfy launch --background`, `comfy run`, `comfy stop`) — no re-implementation of
  ComfyUI's HTTP/websocket/orchestration.
- Expose a **small, capability-oriented surface** (e.g. `text_to_video`) with a
  **typed parameter interface** — not a raw "run any graph" passthrough.
- A **deterministic, scriptable CLI contract**: one absolute artifact path on
  stdout (human mode) / one JSON object (`--json`), documented exit codes,
  diagnostics on stderr (Section 4).
- **Provenance**: every run writes the artifact plus a sidecar JSON capturing
  exactly how it was produced.
- **Keep-warm throughput**: reuse one background ComfyUI across many `generate`
  calls so model load cost (tens of GB) is paid once, not per message.
- **GPU-free unit tests** by mocking the `comfy` **subprocess** (its stdout `--json`
  envelope + exit codes) — no GPU, no real ComfyUI.

**Non-goals (v1)**
- No GUI / interactive node editing.
- No training / fine-tuning.
- No general passthrough of arbitrary user-supplied graphs (capabilities are
  curated and typed). Driving an arbitrary graph is already `comfy run`'s job.
- No cloud execution; local GPU only, no CPU fallback for real generation. (Note:
  `comfy generate` — comfy-cli's *cloud partner-node* path — is explicitly **not**
  used; it needs an API key + credits and is not local.)
- No re-implementation of anything `comfy-cli` already does (server lifecycle,
  UI→API conversion, websocket tracking, output collection).
- Modalities beyond the first text-to-video slice are **seams, not
  implementations**.

## 3. Architecture

Two layers — a reusable core/runtime plus pluggable capability adapters. The core
delegates all ComfyUI interaction to `comfy-cli`.

### 3.1 Core / runtime
- **CLI dispatcher** — builds the command grammar (Section 4), registers core
  commands (`doctor`, `capabilities`), and lets each capability adapter contribute
  its own subcommands (so a new capability adds commands without touching this
  module).
- **comfy-cli driver** *(replaces the old "backend manager")* — the **single place**
  that shells out to the `comfy` binary. It:
  - ensures a local headless server is available: probe the configured host/port; if
    nothing is listening and auto-launch is enabled, run
    `comfy launch --background -- --listen 127.0.0.1 --port <p>` and wait for ready;
    otherwise **attach** to the running one;
  - submits a prepared workflow with `comfy run <workflow.json> --wait --local-paths
    --json [--timeout <s>]` and reads the single JSON envelope from stdout;
  - extracts produced file paths from the envelope (`data.outputs` / `output` events);
  - manages lifecycle (reuse/keep-warm; optional `comfy stop`);
  - **isolates every `comfy-cli`/ComfyUI-version quirk** here, including the
    envelope/exit-code translation (Section 5).
- **Workflow registry** — keyed by `(capability_id, model_id)`. Each entry points to
  a **workflow template** (preferably **API format** for robust injection — see §5)
  plus a **parameter binding** (how typed inputs map onto specific nodes) and the
  **expected model files**.
- **Parameter injection** — given typed inputs (prompt, negative, seed, size,
  length, fps, steps, model, audio …), produce a concrete prompt JSON by setting
  node widget values addressed by **stable role/title bindings** (avoid raw numeric
  node IDs) so injection survives minor graph edits. The injected JSON is written to
  a temp file and handed to `comfy run`.
- **Artifact + provenance writer** — collision-safe filenames; copies/moves the file
  `comfy run` reports into `--output-dir`; writes a sidecar `.json` provenance record.
- **Error taxonomy** — map `comfy-cli` envelope `error.code` + process exit into the
  typed errors → documented exit codes (Section 4.3); always render an actionable
  message to stderr, never a raw traceback.
- **Config** — layered: CLI flag > environment (`CUW_*`) > config file > builtin.

### 3.2 Capability adapters
- One adapter per workflow family. v1: **`text_to_video`** backed by the LTX-2
  workflow.
- An adapter declares: its `capability_id`, its `model_id`s (each → a workflow
  template + binding + expected files), the typed parameter schema it accepts, and
  the artifact type it emits (`video/mp4`).
- Adding a capability = a new adapter module + its workflow template; **no core
  changes** and **no new ComfyUI/`comfy-cli` glue** (the driver is reused).

## 4. Invocation contract (stable, swappable)

The command grammar, stdout discipline, and exit codes below are **the public
contract**. They are intentionally generic and tool-agnostic so a caller can swap
between compatible tools without changing how it builds the command or parses the
result. (The binary *name* is the only thing the caller varies.) This contract is
deliberately independent of `comfy-cli`'s own envelope — the driver adapts to it.

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
- `doctor` — verify the execution environment: GPU + CUDA stack, that `comfy` is on
  PATH and a local ComfyUI is reachable/launchable, and that the required model files
  are present.
- `capabilities` — list registered capabilities and their models/workflows.

Generation command (capability-contributed):
- `generate "<prompt>" [options]` — run a capability. Shared options mirror a common
  generation surface so callers can swap tools:
  - `--model <id>` — model/workflow variant (e.g. `ltx2-t2v`).
  - `--output-dir <dir>` — directory for outputs.
  - `--seed <int>` — reproducibility seed.
  - `--negative "<text>"` — negative prompt (where supported).
  - Video knobs: `--size WxH` (or `--width`/`--height`), `--length <frames>` (or
    `--seconds`), `--fps <n>`, `--steps <n>`, `--audio/--no-audio`.
  - Additional optional flags are **additive**: a caller using only the shared subset
    is never broken by them.
- `interactive` (optional, later) — a REPL that keeps the background ComfyUI warm
  between prompts.

### 4.2 stdout / stderr discipline
- **Human mode:** print each saved artifact's **absolute path**, one per line; the
  **final stdout line is a saved artifact path**. Progress/diagnostics → stderr
  (including any pass-through of `comfy-cli` progress).
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
identically across compatible tools). 9–11 are backend-specific extensions; a caller
that only understands 0–8 treats them as a generic failure. The driver maps
`comfy-cli`'s envelope/exit onto these (Section 5).

| Code | Meaning | Typical caller action |
|------|---------|-----------------------|
| 0 | Success | settle/complete |
| 1 | Unexpected / internal error | dead-letter (investigate) |
| 2 | Invalid arguments or parameter values | dead-letter (bad message) |
| 3 | GPU compute stack unusable (CUDA/torch build mismatch) | dead-letter / alert |
| 4 | No supported GPU detected | dead-letter / alert |
| 5 | Out of (V)RAM during execution | retry (maybe smaller) |
| 6 | Gated / licensed model or missing token (weights unobtainable) | dead-letter |
| 7 | Network / download failure | retry |
| 8 | Unknown capability / model / workflow id | dead-letter (bad message) |
| 9 | Execution backend unavailable (ComfyUI/`comfy` failed to start / unreachable) | retry |
| 10 | Workflow execution error (a node failed during the run) | dead-letter / retry |
| 11 | Timeout waiting for completion | retry |

### 4.4 Provenance sidecar
Every artifact gets a `<artifact>.json` sidecar containing at least: prompt,
negative, seed, capability, model/workflow id, resolved parameters, the workflow
template id/version, ComfyUI version (as reported by `comfy`), model file names (and,
where feasible, hashes), start/end timestamps, and the output filename. The same
record is embedded as `artifacts[].metadata` in `--json` mode.

## 5. comfy-cli integration details

All ComfyUI interaction goes through the `comfy` binary; nothing in this project
talks to ComfyUI's HTTP/websocket surface directly.

- **Dependency, not import.** `comfy-cli` is a published external tool (PyPI,
  GPL-3.0). It is invoked **only as a subprocess**. This project never `import`s
  `comfy_cli`, so it incurs no GPL obligation and stays independent of any other repo.
- **Server lifecycle.** Discover a configured local ComfyUI. If a server is already
  listening on the configured host/port, **attach**. Otherwise, if auto-launch is on,
  start one headless and in the background:
  `comfy launch --background -- --listen 127.0.0.1 --port <p> [extra args]`, then wait
  for readiness. Reuse it across requests (keep-warm). Shut down via `comfy stop`
  (or leave warm) per config.
- **Workflow format.** ComfyUI's `/prompt` consumes the **API format** graph, not the
  UI "workflow" JSON. `comfy run` **auto-converts UI→API** when handed a UI file, so a
  UI export can work as-is. **However**, for robust title/role-based parameter
  injection this project prefers a **flat API-format template** under `workflows/`
  (subgraph UI JSON is awkward to inject into). The API template can be obtained by
  either: (a) ComfyUI Dev Mode → *Export (API)*, **or** (b) programmatically letting
  `comfy run --print-prompt` convert the UI JSON once and capturing the converted
  prompt as the stored template. Capturing/refreshing the template is an explicit
  one-time setup step (Appendix A).
- **Parameter injection** happens **before** invoking `comfy run`: inject typed
  inputs into the stored API template addressed by stable node `_meta.title` / role,
  write to a temp file, then `comfy run <temp.json> --wait --local-paths --json
  [--timeout <s>]`.
- **Submission / progress / collection.** Handled entirely by `comfy run`. Read the
  single JSON object it prints; success arrives as a final `type:"envelope"` line with
  `ok=true` and `data.outputs` (file paths, thanks to `--local-paths`); progress
  events go to stderr. Move/copy the produced file to `--output-dir` with a
  collision-safe name.
- **Error / exit-code mapping.** Translate `comfy-cli`'s structured failure
  (`ok=false { error.code, error.message, error.hint }`) and process exit onto the
  Section 4.3 taxonomy. Indicative mapping (refine during the build):

  | comfy-cli `error.code` (or signal) | comfywrap exit |
  |---|---|
  | `server_not_running`, `connection_error` | 9 |
  | `ws_timeout` | 11 |
  | `execution_error` (node failed) | 10 (5 if OOM detected in message) |
  | `prompt_rejected` / validation | 2 (or 8 if unknown node/model) |
  | `workflow_not_found`, `workflow_*`, `conversion_*` | 8 / 1 |
  | `cancelled` | 130 → surfaced as failure |
  | success | 0 |

  Always emit an actionable stderr message; never leak a raw traceback or raw
  `comfy-cli` envelope to the caller (the caller parses **our** envelope only).
- **VRAM.** Rely on ComfyUI's own memory management; detect OOM in the failure
  message and surface it as exit 5.

## 6. First milestone — vertical slice

Deliver, end-to-end, for **`text_to_video` via the LTX-2 workflow**:
1. `doctor` — confirms GPU/CUDA, `comfy` on PATH + ComfyUI reachable/launchable, and
   the required LTX-2 model files present.
2. `capabilities` — lists `text_to_video` and its model(s).
3. `generate "<prompt>" --model ltx2-t2v --seed <n> [--json]` — injects prompt+seed
   (and any provided knobs) into the API-format LTX-2 template, runs it via
   `comfy run`, collects the `.mp4`, writes the sidecar, and prints the absolute path
   (or the JSON object).

**Acceptance:** a caller can run `generate … --json`, parse one object, read
`artifacts[0].path`, and find a playable `.mp4`; exit codes behave per Section 4.3;
unit tests pass GPU-free with the `comfy` subprocess mocked.

## 7. Configuration

Layered (CLI > `CUW_*` env > config file > builtin). Keys include: `comfy` binary
location (else assume on PATH), ComfyUI host/port + launch extra args, auto-launch
on/off, keep-warm on/off, workflow/model base dir, default output dir, request/run
timeouts, default model. No secrets committed; tokens via environment only.

## 8. Tech stack

- Python 3.12, **argparse** (match the contract grammar; no heavy CLI dep).
- stdlib **`subprocess`** to drive `comfy`, stdlib **`json`** for the envelope, stdlib
  **`tomllib`** for config. Optional `pydantic` for parameter schemas.
- **No HTTP/websocket client dependency** — `comfy-cli` owns that surface.
- Single external runtime dependency: the **`comfy` CLI** (`pip install comfy-cli`)
  available on PATH. Packaged with a `pyproject.toml` console script
  `comfywrap = "comfywrap.core.cli:main"`.

## 9. Consumer integration (e.g. Azure Service Bus job)

The queue consumer is **out of scope**, but the contract is designed for it. Pattern:

```text
on message:
  req = map(message.body.prompt, message.application_properties)   # seed, size, fps, length, audio…
  run:  comfywrap generate "<prompt>" --model ltx2-t2v \
          --seed <seed> --size <w>x<h> --length <frames> --fps <fps> [--no-audio] \
          --output-dir <staging> --json
  parse exactly one JSON object from stdout → path = artifacts[0].path
  switch exit code:
    0            -> upload(path); complete/settle message
    5, 7, 9, 11  -> abandon -> retry (transient)
    2, 6, 8      -> dead-letter (bad/unsatisfiable message)
    1, 3, 4, 10  -> dead-letter + alert
```

The consumer never touches ComfyUI, the LTX-2 graph, node IDs, or `comfy-cli`. To
keep latency low across many messages, start a background server once
(`comfywrap` auto-launch / keep-warm, or an out-of-band `comfy launch --background`)
so model weights load once and each `generate` reuses the warm server.

## 10. Repo layout

```
ComfiUIWrapper/
  pyproject.toml            # console script: comfywrap = "comfywrap.core.cli:main"
  README.md
  spec.md                   # this file
  src/comfywrap/
    core/                   # cli, comfy_cli driver, registry, config, injection,
                            # output/provenance, errors, doctor
    capabilities/
      video/
        text_to_video/      # adapter + binding for the LTX-2 workflow
  workflows/                # API-format workflow templates (.json)
  tests/                    # GPU-free unit tests (mock the `comfy` subprocess)
  scripts/                  # bootstrap / dev helpers (e.g. capture API template)
  docs/
```

## 11. Testing

- **Unit (GPU-free, default):** mock the **`comfy` subprocess** — feed canned
  `comfy run --json` envelopes (success + each failure `error.code`) and exit codes;
  assert: parameter injection into the template, temp-file handoff, output collection
  + collision-safe naming, provenance contents, **error→exit-code mapping**, config
  layering, and the `--json` envelope shape. No GPU, no real ComfyUI, no network.
- **Integration (opt-in):** behind an env flag, run against a **real local ComfyUI +
  GPU** via real `comfy` and assert a real `.mp4` is produced.

## 12. Constraints

- **Self-contained w.r.t. other repos:** do not depend on, import, or reference any
  other *local project*. The **only** external runtime dependency is the published
  `comfy` CLI, invoked as a subprocess. Only the invocation *convention* (Section 4)
  is shared with callers, and it is specified here intrinsically.
- **Subprocess, never import** `comfy_cli` (keeps the GPL boundary clean — Section 5).
- Local GPU only; no cloud, no CPU fallback for actual generation. Do not use
  `comfy generate` (cloud partner nodes).
- Keep all `comfy-cli`/ComfyUI-version-specific logic isolated in the comfy-cli driver.
- **Scope discipline:** implement only the text-to-video slice first; other
  capabilities are seams.

## 13. Decisions (formerly open questions)

- **Binary / console-script name:** `comfywrap`. Config/env prefix: `CUW_*`.
- **Server start:** auto-launch a **background** ComfyUI via
  `comfy launch --background` when none is reachable, and keep it warm; attach if one
  is already running. Configurable off (require an existing instance).
- **API-format template capture:** prefer a stored flat **API-format** template;
  obtain it via ComfyUI Dev-Mode *Export (API)* **or** programmatically with
  `comfy run --print-prompt` (a `scripts/` helper). This removes the hard manual
  export dependency while keeping injection robust.
- **Engine:** drive the official **`comfy-cli`** as a subprocess (not ComfyScript,
  not raw HTTP, not in-process node execution).
- Still to decide during the build: exact typed LTX-2 parameter set
  (length/fps/size ranges, audio on/off, LoRA toggles) and which are first-class in v1
  vs. fixed to template defaults; the precise `comfy run` flag set and version floor.

---

## Appendix A — Current environment (target machine)

> Concrete facts for wiring the first slice. These describe the **ComfyUI** install on
> this machine; they are not a dependency on any other project.

- **OS / shell:** Windows, PowerShell (use backslash paths).
- **GPU:** NVIDIA RTX 5090, 32 GB, Blackwell (sm_120 / compute cap 12.0). Any GPU code
  must use a CUDA 12.8+ (cu128) PyTorch build; stock PyPI/cu121 wheels don't support
  sm_120. (ComfyUI's own venv already satisfies this.)
- **`comfy-cli`:** `pip install comfy-cli`; the `comfy` binary must be on PATH (or its
  path configured). Used to launch/attach/run/stop the local ComfyUI.
- **ComfyUI Desktop app:** `C:\AI\ComfyUI\resources\ComfyUI` (the app +
  `comfy_extras` core nodes — LTX-2 nodes live in `comfy_extras\nodes_lt*.py`,
  `nodes_video.py`).
- **ComfyUI data root (`base_path`):** `C:\AI\Softwares` — contains `models\`,
  `user\`, `output\`, `custom_nodes\`, and a `.venv\` with `diffusers`. (Set in
  `%APPDATA%\ComfyUI\extra_models_config.yaml`.)
- **Source UI workflow (text-to-video):**
  `C:\AI\Softwares\user\default\workflows\video_ltx2_t2v.json` — a **subgraph**
  workflow named *"Text to Video (LTX 2.0)"*. Convert to an API-format template (Dev
  Mode *Export (API)*, or `comfy run --print-prompt`) and store the result under
  `workflows/`.
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
- **All workflow nodes are ComfyUI core** (`comfy_extras`) — no third-party custom-node
  pack is required to run this workflow.
