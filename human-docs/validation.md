# Validation — measured end-to-end results

> Human reference. Numbers measured on the target workstation (RTX 5090, ComfyUI
> Desktop on `127.0.0.1:8000`, comfy-cli 1.11.1) during the v1 build.

## Environment readiness (`comfywrap doctor --json`)

```json
{"ready": true, "host": "127.0.0.1", "port": 8000, "comfy_version": "1.11.1",
 "gpu": "NVIDIA GeForce RTX 5090",
 "checks": [
   {"check": "comfy_cli", "ok": true, "detail": ".venv\\Scripts\\comfy.exe (version 1.11.1)"},
   {"check": "gpu", "ok": true, "detail": "NVIDIA GeForce RTX 5090"},
   {"check": "comfyui", "ok": true, "detail": "reachable at 127.0.0.1:8000"},
   {"check": "ltx2_models", "ok": true, "detail": "all present"}
 ]}
```

## Real generation (the definition of done)

`comfywrap generate "a serene koi pond at dawn …" --json --output-dir .scratch\out`

- **Exit 0.** A genuine fresh render (random seed `3142219665` → cache miss):
  **`elapsed_seconds ≈ 103.9`**, producing `LTX-2_00048_.mp4` (~2.5 MB), copied to
  the `--output-dir` with a `<artifact>.json` provenance sidecar.
- The single stdout JSON object (abridged):

```json
{
  "capability": "text_to_video",
  "model": "ltx2-t2v",
  "artifacts": [{
    "path": "C:\\Dev\\MyRepos\\ComfiUIWrapper\\.scratch\\out\\LTX-2_00048_.mp4",
    "type": "video/mp4",
    "metadata": {
      "capability": "text_to_video", "model": "ltx2-t2v",
      "seed": 3142219665, "workflow_template": "ltx2_t2v.api.json",
      "model_files": ["checkpoints/ltx-2-19b-dev-fp8.safetensors", "…"],
      "prompt_id": "d19632cd-…", "elapsed_seconds": 103.95,
      "host": "127.0.0.1", "port": 8000, "comfywrap_version": "0.1.0",
      "started_at": "2026-06-30T02:23:29+03:00", "ended_at": "2026-06-30T02:25:15+03:00"
    }
  }]
}
```

## Keep-warm reuse

A second `generate` (fixed `--seed 3142219665`, same prompt) **attached** to the
already-warm server and returned in **~0.37 s** (ComfyUI served the cached
result; no multi-tens-of-GB model reload) — vs ~104 s cold. This is the throughput
property the Service Bus scenario needs.

## Failure mapping (sampled live)

Running against a port with no server returned the real comfy-cli failure
envelope `{"ok": false, "error": {"code": "server_not_running", …}}` with process
exit 1, which `comfywrap` maps to **exit 9** (backend unavailable). The full
mapping is in `src\comfywrap\core\errors.py` and `human-docs\skill-invocation.md`.

## Unit suite (GPU-free)

`.venv\Scripts\python.exe -m pytest` → **34 passed, 1 skipped** (the skipped one
is the opt-in real-GPU integration test, enabled with `CUW_RUN_INTEGRATION=1`).
The suite mocks the `comfy` subprocess (canned `--json` envelopes) and validates
injection against the real bundled template, the error→exit-code mapping, the
`--json` envelope shape, config layering, schema validation, and output/provenance
— no GPU, no real ComfyUI, no network.
