# ComfiUIWrapper — what it is and how it was built

> A narrative for the human maintainer (you). It explains the project's purpose, the decisions behind it, and exactly how it was implemented and validated.

## 1. What this project is

`comfywrap` (the `comfywrap` CLI in this repo, **ComfiUIWrapper**) is a thin, typed, scriptable command-line tool that turns a prompt + parameters into a locally rendered video — today **LTX-2 text-to-video** — by **driving the official [comfy-cli](https://github.com/Comfy-Org/comfy-cli) as a subprocess**.

The motivating use case: an unattended backend job (e.g. an **Azure Service Bus** consumer) receives a message with a prompt and properties, and needs to render an LTX-2 clip locally on the RTX 5090 and hand back the result. `comfywrap` is the **seam** that job calls, so the messaging worker never has to understand ComfyUI node graphs, model wiring, or comfy-cli quirks. It just runs `comfywrap generate "<prompt>" --json`, parses one JSON object, reads `artifacts[0].path`, and branches on the exit code.

## 2. The key insight: wrap, don't reimplement

The original `spec.md` in this repo described building the whole headless-ComfyUI orchestration from scratch (its own backend manager, websocket tracking, UI→API conversion, output collection). Before writing any of that, we searched for prior art and found that the **official comfy-cli already does all of it** — `comfy run` launches/attaches a headless ComfyUI, **auto-converts UI→API graphs**, tracks progress over websocket, collects outputs, and emits a structured `--json` envelope with an error-code → exit-code mapping.

So the project was re-scoped: `comfywrap` is **not** a ComfyUI engine. It is the ~80% that comfy-cli does *not* provide — a **typed capability surface**, **parameter injection** into a curated workflow template, a **stable result/error contract**, **provenance**, and a capability-specific **doctor**. comfy-cli is the engine; comfywrap is the typed layer on top.

### Subprocess, not import

A deliberate, load-bearing decision: comfywrap **drives comfy-cli as a subprocess and never `import comfy_cli`**. Reasons, in priority order:

1. **Crash isolation** — a CUDA error, OOM, or hung node kills the child process, not the (potentially long-running, unattended) comfywrap worker.
2. **Dependency isolation** — comfywrap is **stdlib-only**; the heavy torch/cu12x GPU stack lives entirely in ComfyUI's own venv and never has to be installable alongside comfywrap.
3. **Stable contract** — we depend on comfy-cli's documented CLI + `--json` envelope, not its private internals.
4. **Clean license boundary** — comfy-cli is GPL-3.0; arm's-length subprocess use keeps comfywrap independent (it's MIT).

A further insight that settled the debate: comfy-cli is *itself* an orchestrator that runs ComfyUI as a **separate server process**, so importing it wouldn't even buy in-process generation — the heavy work is out-of-process either way.

## 3. How it was built: de-risk first

Rather than write code against assumptions, we **proved the hard part on the real machine first**, then built the wrapper around what actually worked.

1. **Environment recon.** Confirmed Python 3.12, the RTX 5090, and that ComfyUI was already running headless on `127.0.0.1:8000` (ComfyUI Desktop, torch 2.8.0+cu129, launched with `--base-directory C:\AI\Softwares`). Installed comfy-cli into a project `.venv`.
2. **Captured the template without running anything.** `comfy run --print-prompt` converts a UI workflow to the flat **API graph** using the live server only for `/object_info`. That gave us `src\comfywrap\data\workflows\ltx2_t2v.api.json` (36 nodes — the source subgraphs flattened) and, crucially, the **real node ids and titles** to bind to. (This is what `scripts\capture_template.py` now automates.)
3. **Discovered the bindings from the real graph.** Inspecting the template revealed: positive prompt = node `92:3`, negative = `92:4` (the two `CLIPTextEncode` nodes share a title, so they're bound by id+role); two `RandomNoise` seeds (`92:67`, `92:11`); size = `EmptyImage 92:89`; length = `92:62`; fps as both int (`92:103`) and float (`92:102`); steps = `92:9`; output = `SaveVideo 75`.
4. **Ran the real workflow end-to-end** through comfy-cli and learned the exact envelope: outputs are reported as `/view?filename&subfolder&type=output` **URLs** (this comfy-cli has **no `--local-paths` flag**, contrary to the original plan), which we resolve to `<comfyui_output_dir>\<subfolder>\ <filename>`. We also captured a real **failure** envelope (`ok:false`, `error.code:"server_not_running"`, process exit 1) to get the error mapping right.

Only then did we write the wrapper — so the code matched reality instead of the plan's assumptions.

## 4. The implementation

Source lives under `src\comfywrap\`, split into a modality-agnostic **core** and a **capability adapter**.

**Core (`src\comfywrap\core\`):**

- `driver.py` — the single module that shells out to `comfy`. It owns server lifecycle (`probe` → attach, else auto-launch a background ComfyUI and wait ready, keep-warm), `comfy run --wait --json`, NDJSON + `envelope/1` parsing, `/view`-URL → absolute-path resolution, and `capture_api_prompt` (`--print-prompt`). **Every comfy-cli quirk is quarantined here.**
- `errors.py` — typed errors with stable exit codes **0–11**, plus `from_comfy_error(...)` mapping comfy-cli's `error.code` (and OOM/gated/network message markers) onto them.
- `config.py` — layered config (CLI > `CUW_*` env > `comfywrap.toml`/`config.toml`
> builtin). Builtin defaults target this workstation (ComfyUI on `:8000`, data
  root `C:\AI\Softwares`) and are fully overridable.
- `injection.py` — `Binding` + `inject(template, values, bindings)` + `write_temp_prompt(...)` (deep-copies the template, sets bound node inputs by role, skips unset values).
- `registry.py` — `(capability_id, model_id)` → `CapabilityEntry`; adapters self-register.
- `output.py` — collision-safe placement + the `<artifact>.json` provenance sidecar.
- `doctor.py` — GPU (nvidia-smi), comfy-cli (+ version), ComfyUI reachability, and LTX-2 model-file presence.
- `cli.py` — argparse dispatcher; global flags work before **or** after the subcommand (a parent parser with `SUPPRESS` defaults); the `--json` envelope and the error→exit-code boundary.

**Capability (`src\comfywrap\capabilities\video\text_to_video\`):** `adapter.py` (declares `text_to_video` / `ltx2-t2v` / `video/mp4`, expected model files, and wires the shared video-param surface), `schema.py` (typed validation), `binding.py` (the role→node map above). It self-registers via the manifest chain `src\comfywrap\capabilities\__init__.py` → `video\__init__.py` → `adapter.py`.

**The contract.** `comfywrap doctor | capabilities | generate`. `generate` exposes the full shared video surface (`--seed`, `--size`/`--width`/`--height`, `--length`/`--seconds`, `--fps`, `--steps`, `--negative`, `--audio`/`--no-audio`); unset knobs keep the template's defaults; `--seed` is randomized + recorded when omitted. `--json` emits exactly one object; the exit code is the authoritative signal. Full detail in `human-docs\skill-invocation.md`.

## 5. Decisions made along the way

- **Default config is machine-specific but overridable** — fastest path to a working tool on your box; every value is settable via `CUW_*` / config file.
- **Dropped the planned `--local-paths`** (this comfy-cli lacks it) — the driver resolves `/view` URLs to absolute paths instead.
- **Removed `/32` size rounding** — the template default 720×1280 is known-good and not a multiple of 32; we pass dimensions through and let ComfyUI validate.
- **`--no-audio` is accepted/recorded but LTX-2 is audio-native** — there's no clean node toggle, so the mp4 still carries audio; documented rather than faked.
- **Keep-warm by attaching to the running ComfyUI on :8000** — never launch a second instance (VRAM).

## 6. Testing & validation

- **34 GPU-free unit tests** (`tests\`) mock the `comfy` subprocess with canned `--json` envelopes and exercise injection (against the *real* template), error→exit-code mapping, the envelope shape, config, schema, and output. They run without a GPU, a real ComfyUI, or network.
- An **opt-in real-GPU integration test** runs only with `CUW_RUN_INTEGRATION=1`.
- **Real end-to-end on the RTX 5090** (the definition of done): a fresh-seed `comfywrap generate` produced a playable `.mp4` in ~104 s, and a second call reused the warm server in **0.37 s** (no model reload). See `human-docs\validation.md` for the measured numbers and sample envelope.

## 7. Where it's headed

More ComfyUI workflows — **video and non-video** — added as self-contained adapters with **no core changes**. The capture→bind→adapter→register recipe is in `agent-memory\adding-a-capability.md`, and the `.github\skills\add-capability` skill walks an agent through it.
