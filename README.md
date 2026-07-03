# comfywrap (ComfiUIWrapper)

A thin, typed, scriptable CLI that turns a prompt + parameters into a locally rendered video by **driving [comfy-cli](https://github.com/Comfy-Org/comfy-cli) as a subprocess**. v1 ships one capability — `text_to_video` via **LTX-2** (`ltx2-t2v`) — behind a stable command/JSON contract, with a provenance sidecar per artifact and a documented exit-code taxonomy.

comfy-cli already launches/attaches a headless ComfyUI, converts UI→API graphs, tracks progress, and collects outputs. comfywrap adds the typed capability surface, parameter injection into a curated workflow template, the stable contract, the exit-code mapping, provenance, and a `doctor` check. **comfy-cli is invoked as a subprocess and never imported** (crash isolation, dependency isolation, clean GPL boundary).

## Install

```powershell
# in a Python 3.12 venv that also has comfy-cli available on PATH
pip install comfy-cli          # the engine (provides the `comfy` binary)
pip install -e .               # comfywrap
```

`comfywrap doctor` verifies the rest (GPU, comfy-cli, ComfyUI reachability, LTX-2 model files).

## Quick start

```powershell
comfywrap doctor --json
comfywrap capabilities --json
comfywrap generate "a serene koi pond at dawn, cinematic soft light" --json
```

## The contract

```
comfywrap [--version] [--json] [--config PATH] [-v] <command> [options]
```

Commands:
- `doctor` — verify GPU/CUDA, comfy-cli, ComfyUI reachability/launchability, LTX-2 model files.
- `capabilities` — list registered capabilities and models.
- `generate "<prompt>" [options]` — produce an artifact.

`generate` options (the shared video surface): `--model <id>` · `--output-dir <dir>` · `--seed <int>` · `--negative "<text>"` · `--size WxH` (or `--width`/`--height`) · `--length <frames>` (or `--seconds`) · `--fps <n>` · `--steps <n>` · `--audio` / `--no-audio`. Unset knobs fall back to the workflow template's defaults; `--seed` is random if omitted.

### stdout / stderr discipline
- **Human mode:** each saved artifact's absolute path on its own line; the final stdout line is an absolute artifact path. Diagnostics go to stderr.
- **`--json` mode:** exactly one JSON object on stdout:

```json
{
  "capability": "text_to_video",
  "model": "ltx2-t2v",
  "artifacts": [{ "path": "C:\\...\\LTX-2_00048_.mp4", "type": "video/mp4", "metadata": { } }]
}
```

On failure in `--json` mode a single object `{"error": {"code", "kind", "message", "hint", "details"}}` is written to stdout; the process exit code is the authoritative signal.

### Exit codes

| Code | Meaning | Typical caller action |
|------|---------|-----------------------|
| 0 | Success | settle/complete |
| 1 | Internal error | dead-letter (investigate) |
| 2 | Invalid arguments / parameters | dead-letter (bad message) |
| 3 | GPU compute stack unusable | alert |
| 4 | No supported GPU | alert |
| 5 | Out of (V)RAM | retry |
| 6 | Gated / licensed model | dead-letter |
| 7 | Network / download failure | retry |
| 8 | Unknown capability / model / workflow | dead-letter |
| 9 | Backend unavailable (ComfyUI not running / unreachable) | retry |
| 10 | Workflow execution error (a node failed) | dead-letter / retry |
| 11 | Timeout waiting for completion | retry |

## Configuration

Layered precedence: **CLI > `CUW_*` env > config file (`./comfywrap.toml` or `./config.toml`) > builtin defaults**. Builtin defaults target the workstation in spec Appendix A (ComfyUI Desktop on `127.0.0.1:8000`, data root `C:\AI\Softwares`) and are fully overridable.

Common keys (env form in parentheses):
- `host` (`CUW_HOST`), `port` (`CUW_PORT`) — where ComfyUI runs.
- `auto_launch` (`CUW_AUTO_LAUNCH`), `keep_warm` (`CUW_KEEP_WARM`), `attach_only` (`CUW_ATTACH_ONLY`).
- `per_event_timeout` (`CUW_PER_EVENT_TIMEOUT`) — comfy-cli per-event silence timeout (survives long model loads).
- `comfy_bin` (`CUW_COMFY_BIN`) — path to the `comfy` binary (else resolved from PATH / the active venv).
- `comfyui_output_dir`, `comfyui_models_dir`, `comfyui_python`, `comfyui_main`, `extra_model_paths_config` — used to resolve output paths and to auto-launch a headless server.
- `output_dir` (`CUW_OUTPUT_DIR`) — where comfywrap copies artifacts (default: leave in ComfyUI's output dir).

### Server lifecycle (keep-warm)
`generate` probes `host:port`; if a ComfyUI is reachable it **attaches**, otherwise (when `auto_launch` is on) it launches a headless ComfyUI in the background and leaves it warm so subsequent calls skip the multi-tens-of-GB model load. Set `attach_only=true` to require an already-running server.

## Using it from a backend job (e.g. Azure Service Bus)

The queue consumer is out of scope; it just shells out to comfywrap and branches on the exit code:

```text
on message:
  comfywrap generate "<prompt>" --model ltx2-t2v \
    --seed <seed> --size <w>x<h> --length <frames> --fps <fps> [--no-audio] \
    --output-dir <staging> --json
  parse exactly one JSON object -> path = artifacts[0].path
  exit 0            -> upload(path); complete/settle
  exit 5,7,9,11     -> abandon -> retry (transient)
  exit 2,6,8        -> dead-letter (bad/unsatisfiable)
  exit 1,3,4,10     -> dead-letter + alert
```

The consumer never touches ComfyUI, the LTX-2 graph, node ids, or comfy-cli.

## Adding a capability (video or non-video)

The registry/adapter seam is modality-agnostic. To add a capability:
1. Capture an API-format template (see below) and drop it under `data/workflows/`.
2. Add an adapter package under `capabilities/<family>/<name>/` with a `binding.py` (role→node map), a `schema.py` (typed params), and an `adapter.py` that declares its `capability_id`, `model_id`, `artifact_type` (e.g. `image/png`, `audio/wav`), expected model files, and self-registers via `REGISTRY.register(...)`.
3. Import it from `capabilities/__init__.py`.

No `core/` changes are required — the driver resolves any artifact type by file extension and the contract is identical across capabilities.

## Capturing / refreshing a workflow template

```powershell
python scripts/capture_template.py `
  "C:\AI\Softwares\user\default\workflows\video_ltx2_t2v.json" `
  "src\comfywrap\data\workflows\ltx2_t2v.api.json"
```

This converts a UI workflow to the flat API graph via `comfy run --print-prompt` (no execution; needs a reachable ComfyUI for `/object_info`).

## Development

```powershell
pip install -e ".[dev]"
python -m pytest -q                 # GPU-free unit suite (mocks the comfy subprocess)
$env:CUW_RUN_INTEGRATION="1"; python -m pytest tests/test_integration.py -q   # real GPU
```

## License

MIT. (comfy-cli, invoked only as a subprocess, is GPL-3.0; arm's-length subprocess use does not impose its terms on this project.)
