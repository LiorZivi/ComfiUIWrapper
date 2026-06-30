# Skill / automation invocation — the exact contract

> Human reference for anyone wiring `comfywrap` into a script, agent, CI job, or
> queue worker. This contract is **stable**; build against it.

## Grammar

```
comfywrap [--version] [--json] [--config PATH] [-v|--verbose] <command> [options]
```

Global flags work **before or after** the subcommand. Commands:

- `doctor` — verify GPU, comfy-cli, ComfyUI reachability/launchability, LTX-2 models.
- `capabilities` — list registered capabilities and models.
- `generate "<prompt>" [options]` — produce an artifact.

`generate` options (the shared video surface):
`--model <id>` (default `ltx2-t2v`) · `--output-dir <dir>` · `--seed <int>` ·
`--negative "<text>"` · `--size WxH` (or `--width`/`--height`) ·
`--length <frames>` (or `--seconds`) · `--fps <n>` · `--steps <n>` ·
`--audio` / `--no-audio`. Unset knobs use the template defaults; `--seed` is
random (and recorded) if omitted.

## stdout / stderr discipline

- **Human mode:** each saved artifact's absolute path on its own line; the
  **final stdout line is an absolute artifact path**. Diagnostics → stderr.
- **`--json` mode:** exactly **one** JSON object on stdout, nothing else.

Success envelope:

```json
{
  "capability": "text_to_video",
  "model": "ltx2-t2v",
  "artifacts": [
    { "path": "C:\\...\\LTX-2_00048_.mp4", "type": "video/mp4", "metadata": { } }
  ]
}
```

Failure envelope (still exactly one object; the exit code is authoritative):

```json
{ "error": { "code": 9, "kind": "BackendUnavailableError",
             "message": "…", "hint": "…", "details": { } } }
```

## Exit codes (0–11)

| Code | Meaning | Caller action |
|------|---------|---------------|
| 0 | Success | settle / complete |
| 1 | Internal error | dead-letter (investigate) |
| 2 | Invalid arguments / parameters | dead-letter (bad message) |
| 3 | GPU compute stack unusable | alert |
| 4 | No supported GPU | alert |
| 5 | Out of (V)RAM | retry |
| 6 | Gated / licensed model | dead-letter |
| 7 | Network / download failure | retry |
| 8 | Unknown capability / model / workflow | dead-letter |
| 9 | Backend unavailable (ComfyUI unreachable) | retry |
| 10 | Workflow execution error (a node failed) | dead-letter / retry |
| 11 | Timeout waiting for completion | retry |

argparse usage errors (unknown flag, missing prompt) also exit **2**.

## Provenance sidecar

Every artifact gets a `<artifact>.json` sidecar, identical to the embedded
`artifacts[0].metadata`: capability, model, prompt, negative, seed, resolved
params, workflow template, model file names, `prompt_id`, `elapsed_seconds`,
output filename, host/port, comfywrap version, and start/end timestamps.

## Example: an Azure Service Bus consumer (out of scope; this is the seam it calls)

```text
on message:
  comfywrap generate "<prompt>" --model ltx2-t2v \
    --seed <seed> --size <w>x<h> --length <frames> --fps <fps> [--no-audio] \
    --output-dir <staging> --json
  parse exactly one JSON object -> path = artifacts[0].path
  exit 0            -> upload(path); complete/settle
  exit 5,7,9,11     -> abandon -> retry (transient)
  exit 2,6,8        -> dead-letter (bad / unsatisfiable)
  exit 1,3,4,10     -> dead-letter + alert
```

The consumer never touches ComfyUI, the LTX-2 graph, node ids, or comfy-cli. To
keep latency low across many messages, leave a warm ComfyUI on `:8000` (or rely on
comfywrap's auto-launch + keep-warm) so model weights load once.

## Config knobs a caller may set (env form)

`CUW_HOST`, `CUW_PORT`, `CUW_AUTO_LAUNCH`, `CUW_KEEP_WARM`, `CUW_ATTACH_ONLY`,
`CUW_PER_EVENT_TIMEOUT`, `CUW_COMFY_BIN`, `CUW_OUTPUT_DIR`,
`CUW_COMFYUI_OUTPUT_DIR`, `CUW_COMFYUI_MODELS_DIR`, `CUW_COMFYUI_PYTHON`,
`CUW_COMFYUI_MAIN`. Precedence: CLI flag > `CUW_*` env > config file
(`comfywrap.toml` / `config.toml`) > builtin defaults.
