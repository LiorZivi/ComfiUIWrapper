---
applyTo: "src/comfywrap/capabilities/**"
---

# Capability adapters (src\comfywrap\capabilities\)

This tree holds pluggable capability adapters grouped by **modality**: `video\text_to_video\` (`ltx2-t2v`) and `video\image_to_video\` (`ltx2-i2v`) are the current ones (both LTX-2). Future capabilities are **sibling packages** under the right modality folder (a new modality gets its own folder + `__init__.py`), registered via the manifest chain (`src\comfywrap\capabilities\__init__.py` → modality `__init__.py` → adapter). Adding one is **additive — never edit `src\comfywrap\core\`** to add a capability. See `agent-memory\adding-a-capability.md` for the full recipe.

## The adapter shape (mirror text_to_video)

An adapter declares `capability_id`, `model_id`, `artifact_type`, and `EXPECTED_MODELS`, and exposes `add_arguments(parser)`, `build_params(args)`, `prepare_prompt(params)` (which calls `inject(load_template(), values, BINDINGS)`), and `resolved_params(params)`. It calls `REGISTRY.register(CapabilityEntry(...))` at import. Bindings live in `binding.py`; typed validation in `schema.py`; the template under `src\comfywrap\data\workflows\`.

## LTX-2 text-to-video facts (src\comfywrap\capabilities\video\text_to_video\)

- The template was captured from `C:\AI\Softwares\user\default\workflows\video_ltx2_t2v.json` via `comfy run --print-prompt` (subgraphs flattened; node ids are prefixed `92:`).
- Bindings (`binding.py`) — the two `CLIPTextEncode` nodes share the title 'CLIP Text Encode (Prompt)', so they are bound **by id+role**: positive=`92:3`, negative=`92:4`. `--seed` drives **both** `RandomNoise` nodes (`92:67`, `92:11`); `--fps` drives **both** the int (`92:103`) and float (`92:102`) frame-rate primitives; size=`EmptyImage 92:89`; length=`92:62`; steps=`92:9`.
- **Do not force size to a multiple of 32** — the template default 720×1280 is known-good; pass dimensions through and let ComfyUI validate.
- LTX-2 is **audio-native**: `--no-audio` is accepted and recorded in provenance but there is no clean node toggle, so the produced mp4 still carries audio. Document, don't fake it.
- **Talking characters / spoken dialogue (verified):** LTX-2 generates synchronized audio *including controllable speech with native lip-sync*. To make a character say specific words, put the line **directly in the prompt** — e.g. `...looking at the camera and clearly saying: "<your exact line>"`. LTX-2 renders the speech and the matching lip movement in one pass. (Confirmed empirically: prompting `saying: "I like Coca-Cola"` produced a clip whose audio Whisper transcribed as exactly `I like Coca-Cola`; a full article line round-tripped the same way.) **Do NOT overlay external TTS / mux a separate audio track** to make a character "talk" — that does not lip-sync (the lips were never driven by that audio). Keep spoken lines short (a sentence or two) for the cleanest result; the voice timbre is the model's choice and is not selectable. If a *specific* named voice is required, that is the one case needing a separate lip-sync model (Wav2Lip/LatentSync) on top — not installed by default.
- To **verify** generated speech without playback, transcribe the audio with faster-whisper (`ffmpeg -i <mp4> -ar 16000 -ac 1 a.wav` → `WhisperModel("small.en")`).
- Unset knobs are left at the template's baked-in defaults (injection skips `None`); `--seed` is randomized and recorded when omitted.
- Keep `capability_id = "text_to_video"` and `model_id = "ltx2-t2v"` **stable** — they are part of the scriptable contract.

## LTX-2 image-to-video facts (src\comfywrap\capabilities\video\image_to_video\)

- `model_id = "ltx2-i2v"`, artifact `video/mp4`; template captured from `C:\AI\Softwares\user\default\workflows\video_ltx2_i2v.json`.
- **Seed image:** the caller's `--image` is copied into ComfyUI's input dir (`cfg.comfyui_input_dir`, resolved via `load_config(args.config)`) under a content-addressed name, then bound to the `LoadImage` node (id `98`, input `image`). ComfyUI resolves `LoadImage.image` **relative to its input dir**, so the file must be staged there before the run — the adapter does this in `build_params`.
- Bindings (`binding.py`): positive=`92:3`, negative=`92:4` (shared title, so bound by id+role); `--seed`→both `RandomNoise` (`92:67`,`92:11`); length=`92:62` (PrimitiveInt "Length"); steps=`92:9`. **Output size derives from the seed image** (Resize/GetImageSize nodes) and **fps is baked at 25**, so the i2v surface omits `--size`/`--fps`.
- **Per-model CLI surface:** `core\cli.py` peeks at `--model` and builds the `generate` options from the **selected** capability's adapter, so `image_to_video` declares its own `--image` in `add_arguments` and `text_to_video` is not polluted with flags it would ignore. A new capability with extra flags just declares them in its own adapter.
- Audio is native (same as t2v): `--no-audio` is recorded in provenance but the mp4 still carries audio.

## Don't

- Don't put capability-specific logic in `src\comfywrap\core\` — it stays modality-agnostic (the driver resolves any artifact type by file extension).
- Don't `import comfy_cli` — all `comfy` interaction goes through `src\comfywrap\core\driver.py` as a subprocess.
- Don't add new capabilities/models without an explicit ask.
