---
applyTo: "src/comfywrap/capabilities/**"
---

# Capability adapters (src\comfywrap\capabilities\)

This tree holds pluggable capability adapters grouped by **modality**:
`video\text_to_video\` (LTX-2) is the first. Future capabilities are **sibling
packages** under the right modality folder (a new modality gets its own folder +
`__init__.py`), registered via the manifest chain
(`src\comfywrap\capabilities\__init__.py` → modality `__init__.py` → adapter).
Adding one is **additive — never edit `src\comfywrap\core\`** to add a capability.
See `agent-memory\adding-a-capability.md` for the full recipe.

## The adapter shape (mirror text_to_video)

An adapter declares `capability_id`, `model_id`, `artifact_type`, and
`EXPECTED_MODELS`, and exposes `add_arguments(parser)`, `build_params(args)`,
`prepare_prompt(params)` (which calls `inject(load_template(), values,
BINDINGS)`), and `resolved_params(params)`. It calls
`REGISTRY.register(CapabilityEntry(...))` at import. Bindings live in
`binding.py`; typed validation in `schema.py`; the template under
`src\comfywrap\data\workflows\`.

## LTX-2 text-to-video facts (src\comfywrap\capabilities\video\text_to_video\)

- The template was captured from
  `C:\AI\Softwares\user\default\workflows\video_ltx2_t2v.json` via
  `comfy run --print-prompt` (subgraphs flattened; node ids are prefixed `92:`).
- Bindings (`binding.py`) — the two `CLIPTextEncode` nodes share the title
  'CLIP Text Encode (Prompt)', so they are bound **by id+role**: positive=`92:3`,
  negative=`92:4`. `--seed` drives **both** `RandomNoise` nodes (`92:67`,
  `92:11`); `--fps` drives **both** the int (`92:103`) and float (`92:102`)
  frame-rate primitives; size=`EmptyImage 92:89`; length=`92:62`; steps=`92:9`.
- **Do not force size to a multiple of 32** — the template default 720×1280 is
  known-good; pass dimensions through and let ComfyUI validate.
- LTX-2 is **audio-native**: `--no-audio` is accepted and recorded in provenance
  but there is no clean node toggle, so the produced mp4 still carries audio.
  Document, don't fake it.
- Unset knobs are left at the template's baked-in defaults (injection skips
  `None`); `--seed` is randomized and recorded when omitted.
- Keep `capability_id = "text_to_video"` and `model_id = "ltx2-t2v"` **stable** —
  they are part of the scriptable contract.

## Don't

- Don't put capability-specific logic in `src\comfywrap\core\` — it stays
  modality-agnostic (the driver resolves any artifact type by file extension).
- Don't `import comfy_cli` — all `comfy` interaction goes through
  `src\comfywrap\core\driver.py` as a subprocess.
- Don't add new capabilities/models without an explicit ask.
