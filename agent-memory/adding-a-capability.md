# Adding a New Capability

The platform is a reusable **core** (`src\comfywrap\core`) plus pluggable **capability adapters** (`src\comfywrap\capabilities\<modality>\<capability>\`). Adding a model or a whole new modality is a **new template + a new adapter package + one import line** — with **no edits to the core** and no changes to existing adapters. The `text_to_video` (LTX-2) capability already uses this seam; follow the same shape.

The most reliable reference is the **live code**: `src\comfywrap\capabilities\video\text_to_video\` (`adapter.py`, `schema.py`, `binding.py`) is a complete worked example. List `src\comfywrap\capabilities\` yourself to see the current modality groups (today `video\`) rather than trusting a hard-coded path here.

## Scope discipline (read before you build)

comfywrap ships **two** capabilities today: `text_to_video` (`ltx2-t2v`) and `image_to_video` (`ltx2-i2v`), both LTX-2. Do **not** add further capabilities/modalities (text_to_image, audio, …) without an explicit ask. If the request is vague ("add more models"), stop and ask **which** ComfyUI workflow (the `.json` path), what model id, and what artifact type.

## What you reuse from the core (do not reinvent)

- `src\comfywrap\core\driver.py` — the comfy-cli driver: server lifecycle (probe/attach/auto-launch keep-warm), `comfy run --json`, envelope parsing, `/view`-URL→absolute-path resolution, and the error→exit-code mapping.
- `src\comfywrap\core\injection.py` — `Binding` + `inject(template, values, bindings)` + `write_temp_prompt(...)`.
- `src\comfywrap\core\registry.py` — `REGISTRY` and `CapabilityEntry`.
- `src\comfywrap\core\output.py` — collision-safe placement + `<artifact>.json` provenance sidecar.
- `src\comfywrap\core\errors.py` — the typed errors / 0–11 exit codes.
- `src\comfywrap\core\cli.py` — the dispatcher; it calls your adapter's `add_arguments`, `build_params`, `prepare_prompt`, `resolved_params`.

## Steps

1. **Capture the workflow as an API-format template.** From a reachable ComfyUI, convert the UI workflow to the flat API graph (no execution):
   ```powershell
   python scripts\capture_template.py "<path-to-ui-workflow.json>" `
     "src\comfywrap\data\workflows\<your_template>.api.json"
   ```
   (This drives `comfy run --print-prompt`, which needs the server only for `/object_info`.) Keep a reference copy under repo-root `workflows\` too.

2. **Discover the node bindings.** Inspect the captured template and note, for each typed param, the node id, its `_meta.title`, and the input key to set (e.g. a `CLIPTextEncode`'s `text`, a `RandomNoise`'s `noise_seed`, an `EmptyImage`'s `width`/`height`). Prefer binding by stable title/role; fall back to node id when titles collide (LTX-2's two prompt nodes share a title, so positive=`92:3` / negative=`92:4` are bound by id+role).

3. **Create the capability package** at `src\comfywrap\capabilities\<modality>\<your_capability>\` with:
   - `binding.py` — a `list[Binding]` mapping each role → node id(s) + input key + cast.
   - `schema.py` — a typed params dataclass + a `build_params(args)` that validates and normalizes (raise `errors.UsageError` → exit 2 for bad input).
   - `adapter.py` — a small adapter class exposing `add_arguments(parser)`, `build_params(args)`, `prepare_prompt(params)` (calls `inject(load_template(), values, BINDINGS)`), and `resolved_params(params)`. Declare `capability_id`, `model_id`, `artifact_type` (e.g. `video/mp4`, `image/png`, `audio/wav`), `EXPECTED_MODELS`, and call `REGISTRY.register(CapabilityEntry(...))` at module import.
   - `__init__.py` files for the package (and the modality folder if new).

4. **Register it — the one line.** Importing the adapter self-registers it, so add an import to the manifest chain:
   - Existing modality: add to `src\comfywrap\capabilities\<modality>\__init__.py`.
   - New modality: create `src\comfywrap\capabilities\<modality>\__init__.py` importing your capability, then add one line to `src\comfywrap\capabilities\__init__.py`.

5. **Tests (GPU-free).** Mirror `tests\` — assert injection sets the right nodes against your real template, the registry resolves your model, and the schema validates. The driver is exercised with a **mocked `comfy` subprocess** (canned `--json` envelopes), never a real GPU.

That's it — the dispatcher auto-lists your capability under `comfywrap capabilities` and exposes `generate --model <your_model>`. **No core changes.**

## Rules of thumb

- The artifact type is declared by the adapter; the driver resolves any output by file extension, so a new image/audio type needs no core edit.
- Map failures to typed `core.errors` (the driver already maps comfy-cli `error.code` + OOM/gated/network message markers). Keep the cross-capability surface (`--json` envelope, exit codes, output paths) untouched.
- If a ComfyUI param has no clean node toggle (e.g. LTX-2 audio on/off), accept the flag, record it in provenance, and document it as accepted-but-native.
- Keep `capability_id` and `model_id` **stable** — they are part of the scriptable contract a caller depends on.
