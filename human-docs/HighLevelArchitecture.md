# High-Level Architecture

> Human reference. For the agent's source of truth see `agent-memory\`.

`comfywrap` is a thin, typed CLI that **drives comfy-cli as a subprocess** to run
ComfyUI workflows headlessly. It is two layers: a reusable, modality-agnostic
**core** and pluggable **capability adapters**.

## The two layers

```
comfywrap generate "<prompt>" --json
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ core (src\comfywrap\core\)  — modality-agnostic                   │
│                                                                    │
│  cli.py        dispatch, global flags, the --json envelope,        │
│                error→exit-code boundary                            │
│  config.py     layered config (CLI > CUW_* env > file > builtin)   │
│  registry.py   (capability_id, model_id) → CapabilityEntry         │
│  injection.py  Binding + inject(template, values, bindings)        │
│  driver.py     THE comfy-cli isolation module (shells out to comfy)│
│  output.py     collision-safe placement + provenance sidecar       │
│  errors.py     typed errors → exit codes 0–11                      │
│  doctor.py     GPU / comfy-cli / ComfyUI / model-file checks       │
└──────────────────────────────────────────────────────────────────┘
        │ resolves model via registry, asks the adapter to prepare a prompt
        ▼
┌──────────────────────────────────────────────────────────────────┐
│ capabilities (src\comfywrap\capabilities\<modality>\<capability>\) │
│                                                                    │
│  video\text_to_video\                                              │
│    adapter.py   declares ids/artifact-type, prepares the prompt    │
│    schema.py    typed param surface + validation                   │
│    binding.py   role → node-id/input bindings for the template     │
│  data\workflows\ltx2_t2v.api.json   the captured API template      │
└──────────────────────────────────────────────────────────────────┘
        │ injected prompt written to a temp .api.json
        ▼
   comfy run --workflow <tmp> --wait --json --host .. --port ..   (subprocess)
        │
        ▼  ComfyUI (headless, 127.0.0.1:8000) renders the workflow
   /view?filename&subfolder&type URLs  →  driver resolves to absolute paths
```

## End-to-end flow of `generate`

1. **Dispatch** (`cli.py`): parse args, load layered config, resolve the model in
   the `REGISTRY` to its `CapabilityEntry` + adapter.
2. **Validate** (`schema.py`): `build_params(args)` normalizes the typed surface
   (size `WxH`, seconds→frames, random seed if omitted); bad input → exit 2.
3. **Inject** (`injection.py`): `prepare_prompt` deep-copies the captured API
   template and sets the bound node inputs by role (`binding.py`); the concrete
   prompt is written to a temp `.api.json`.
4. **Ensure server** (`driver.py`): probe `host:port`; **attach** if reachable,
   else auto-launch a headless ComfyUI and wait until ready (keep-warm).
5. **Run** (`driver.py`): `comfy run --wait --json` as a subprocess; parse the
   NDJSON stream + final `envelope/1`; on failure map `error.code`/exit to the
   0–11 taxonomy.
6. **Collect** (`driver.py` + `output.py`): resolve the produced
   `/view?…&type=output` URL to `<comfyui_output_dir>\<subfolder>\<filename>`;
   optionally copy into `--output-dir` with a collision-safe name; write the
   `<artifact>.json` provenance sidecar.
7. **Emit** (`cli.py`): one JSON object `{capability,model,artifacts:[{path,type,
   metadata}]}` (or the absolute path as the final stdout line in human mode).

## Why the driver is the only place that touches comfy-cli

`src\comfywrap\core\driver.py` is the single quarantine for every
comfy-cli/ComfyUI-version quirk: argv construction, server lifecycle, the NDJSON
envelope shape, the `/view`-URL→path resolution, and the error mapping. Because
comfy-cli is invoked **as a subprocess (never imported)**, a CUDA crash or hang
kills the child process — not the comfywrap process — and comfywrap stays
stdlib-only (the heavy torch/cu12x stack lives entirely in ComfyUI's venv).

## Extensibility

The `registry`/adapter seam is modality-agnostic: an adapter declares its own
`artifact_type` and param schema, and the driver resolves any output by file
extension. A future **video or non-video** capability is a new template + adapter
package + one manifest import line, with no core changes. See
`agent-memory\adding-a-capability.md`.
