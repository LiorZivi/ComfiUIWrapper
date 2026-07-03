# First use & how to run

> Human guide. A practical, start-to-finish walkthrough of installing `comfywrap` and running your first generation. For *what it is and how it was built* see `human-docs\Implementation.md`; for the exact machine contract see `human-docs\skill-invocation.md`.

## 0. What you'll do

Install `comfywrap` into a virtualenv, run `comfywrap doctor` to confirm the environment, then `comfywrap generate "<prompt>"` to render an LTX-2 video. The tool **drives comfy-cli**, which talks to a **headless ComfyUI** — so ComfyUI must be runnable on this machine (it already is on the target workstation).

## 1. Prerequisites

- **Python 3.12** (`python --version`).
- **comfy-cli** — provides the `comfy` binary that comfywrap shells out to.
- **A ComfyUI install with the LTX-2 models** — on this workstation, ComfyUI Desktop runs headless on `127.0.0.1:8000` with its data root at `C:\AI\Softwares`, and the LTX-2 model files live under `C:\AI\Softwares\models\`. You don't configure any of this by hand — `comfywrap doctor` checks it for you.

> comfywrap itself uses **no** torch/CUDA. The GPU stack (cu12x on the RTX 5090) lives entirely in ComfyUI's own venv (`C:\AI\Softwares\.venv`).

## 2. One-time setup

From the repo root `C:\Dev\MyRepos\ComfiUIWrapper`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install comfy-cli      # the engine (`comfy`)
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"    # comfywrap + test deps
```

After this the `comfywrap` and `comfy` commands are at `.venv\Scripts\comfywrap.exe` and `.venv\Scripts\comfy.exe`. Either activate the venv (`.\.venv\Scripts\Activate.ps1`) so `comfywrap` is on your PATH, or call the full path as shown below.

## 3. Step one — check the environment

```powershell
.\.venv\Scripts\comfywrap.exe doctor
```

Expect `READY` plus four green checks (comfy-cli, GPU, ComfyUI reachable, LTX-2 models present). Machine-readable form:

```powershell
.\.venv\Scripts\comfywrap.exe doctor --json
```

If a check fails, fix it before generating — see **Troubleshooting** below. The most common first-run issue is ComfyUI not running on `:8000` (exit/`comfyui` check fails) — start ComfyUI Desktop, or let comfywrap auto-launch it (it will, unless `attach_only` is set).

## 4. Step two — see what's available

```powershell
.\.venv\Scripts\comfywrap.exe capabilities
# text_to_video  ltx2-t2v  -> video/mp4
```

## 5. Step three — your first generation

```powershell
.\.venv\Scripts\comfywrap.exe generate "a serene koi pond at dawn, gentle ripples, cinematic soft morning light"
```

- The **final stdout line is the absolute path** to the produced `.mp4`.
- With only a prompt, every other knob keeps the workflow's defaults (720×1280, 192 frames, 24 fps, 20 steps, audio on) and the **seed is random** (and recorded). A first fresh render takes roughly **~100 seconds** on the RTX 5090; a repeat with the **same prompt + seed** returns in well under a second (the warm server serves it from cache).
- By default the file stays in ComfyUI's output dir: `C:\AI\Softwares\output\video\LTX-2_#####.mp4`, with a `<file>.mp4.json` provenance sidecar beside it. Pass `--output-dir <dir>` to also copy it somewhere of your choosing (collision-safe).

## 6. Step four — scripted use (`--json`)

For automation, add `--json` and read exactly one object from stdout:

```powershell
.\.venv\Scripts\comfywrap.exe generate "a red origami crane on a wooden table" --json --output-dir C:\tmp\out
```

```json
{ "capability": "text_to_video", "model": "ltx2-t2v",
  "artifacts": [ { "path": "C:\\tmp\\out\\LTX-2_00049_.mp4", "type": "video/mp4", "metadata": { } } ] }
```

A caller reads `artifacts[0].path` and branches on the **exit code** (0 = success; see the table below). On failure in `--json` mode you still get exactly one object: `{"error": {"code", "kind", "message", "hint", "details"}}`.

## 7. Tuning a generation

All optional; unset knobs keep the template defaults:

```powershell
.\.venv\Scripts\comfywrap.exe generate "a hummingbird over a flower" `
  --seed 42 --size 704x1280 --length 96 --fps 24 --steps 20 --negative "blurry, low quality"
```

- `--seed <int>` — set for reproducibility (otherwise random + recorded).
- `--size WxH` (or `--width`/`--height`) — dimensions are passed through as-is.
- `--length <frames>` or `--seconds <s>` (converted via `--fps`).
- `--fps <n>`, `--steps <n>`, `--negative "<text>"`.
- `--audio` / `--no-audio` — accepted and recorded, but **LTX-2 is audio-native**: the mp4 still carries audio (there is no clean off switch in this workflow).

See all flags with `.\.venv\Scripts\comfywrap.exe generate --help`.

## 8. Performance & keep-warm

ComfyUI loads tens of GB of LTX-2 weights. comfywrap **attaches** to a running ComfyUI (e.g. on `:8000`) and **leaves it warm**, so back-to-back generations pay the model load only once. Don't start a second ComfyUI on the same box — two copies of the weights will oversubscribe VRAM. If nothing is running and auto-launch is on, comfywrap starts one headless and keeps it warm.

## 9. Configuration (when defaults don't fit)

Precedence: **CLI flag > `CUW_*` env var > config file (`comfywrap.toml` or `config.toml` in the working dir) > builtin defaults**. The builtins target this workstation and are fully overridable. Common overrides:

```powershell
$env:CUW_PORT = "8188"            # ComfyUI on a different port
$env:CUW_ATTACH_ONLY = "true"     # never auto-launch; require a running server
$env:CUW_OUTPUT_DIR = "C:\tmp\out"
```

Other keys: `CUW_HOST`, `CUW_AUTO_LAUNCH`, `CUW_KEEP_WARM`, `CUW_PER_EVENT_TIMEOUT`, `CUW_COMFY_BIN`, `CUW_COMFYUI_OUTPUT_DIR`, `CUW_COMFYUI_MODELS_DIR`, `CUW_COMFYUI_PYTHON`, `CUW_COMFYUI_MAIN`. A config-file key is the same name without the `CUW_` prefix, lower-cased (e.g. `port = 8188`).

## 10. Troubleshooting (by exit code)

| Exit | What happened | Fix |
|------|---------------|-----|
| 2 | Bad arguments (e.g. malformed `--size`, empty prompt) | Correct the flag; `generate --help`. |
| 9 | ComfyUI not reachable | Start ComfyUI (or ComfyUI Desktop), or allow auto-launch; check `CUW_HOST`/`CUW_PORT`; run `comfywrap doctor`. |
| 5 | Out of VRAM during the run | Close other GPU apps; don't run two ComfyUI instances; try a smaller `--size`/`--length`. |
| 8 | Unknown model | `comfywrap capabilities`; use `ltx2-t2v`. |
| 10 | A node failed during the run | Check the stderr message; verify the LTX-2 models (`comfywrap doctor`). |
| 11 | Timed out waiting | The server went silent too long; raise `CUW_PER_EVENT_TIMEOUT`. |
| 6 | Gated/licensed model | Provide the model's access token to ComfyUI. |

Run with `-v` (`comfywrap -v generate …`) for a traceback on unexpected errors.

## 11. Running the tests (optional)

```powershell
.\.venv\Scripts\python.exe -m pytest          # GPU-free unit suite (mocks `comfy`)
$env:CUW_RUN_INTEGRATION = "1"; .\.venv\Scripts\python.exe -m pytest tests\test_integration.py   # real GPU
```

## 12. Pointers

- `README.md` — concise reference of the same material.
- `human-docs\skill-invocation.md` — the exact contract + exit codes for callers.
- `human-docs\validation.md` — measured results from the first runs.
- `human-docs\Implementation.md` — what the project is and how it was built.
