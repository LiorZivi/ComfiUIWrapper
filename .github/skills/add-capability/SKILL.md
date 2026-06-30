---
name: add-capability
description: "Add a new ComfyUI workflow / model / capability to the comfywrap (ComfiUIWrapper) tool, following its core/adapter architecture. Use whenever the user wants to add, register, support, or wire up a new ComfyUI workflow as a typed comfywrap capability — another video model beside LTX-2, a new model variant, or a new modality (text-to-image, image-to-video, audio, upscaling, etc.). Triggers on 'add capability X', 'support workflow Y', 'wrap this ComfyUI workflow', 'add a new model to comfywrap', 'register a new workflow', 'add text-to-image to comfywrap', 'wire up a new modality'. Not for changing generation flags, fixing ComfyUI/GPU setup, or non-comfywrap repos."
---

# Add a Capability to comfywrap (ComfiUIWrapper)

comfywrap is a **reusable core** (`src\comfywrap\core`) that **drives comfy-cli as
a subprocess**, plus pluggable **capability adapters** grouped by **modality**
under `src\comfywrap\capabilities\<modality>\<capability>\` (e.g.
`video\text_to_video\`). Adding a capability is **additive**: capture a ComfyUI
workflow as an API template, map its node bindings, write a small adapter, and add
**one manifest import line** — with **no edits to the core**. This skill walks
that path so the result matches the conventions the LTX-2 `text_to_video`
capability already follows.

The single most reliable reference is the **live code**, not this document. Read
`src\comfywrap\capabilities\video\text_to_video\` (`adapter.py`, `schema.py`,
`binding.py`) when you write code, and **list `src\comfywrap\capabilities\`
yourself** to see the current modality groups. This skill is self-contained:
everything you need is here and in `references\templates.md`.

## Scope discipline (read before you build)

comfywrap ships **one capability today: `text_to_video` (LTX-2)**. Other
capabilities/modalities must **not** be built without an explicit ask.

- If the user named a specific ComfyUI workflow / model / modality, that is your
  green light — proceed.
- If the request is vague ("add more models"), **stop and ask**: which ComfyUI
  workflow (`.json` path), what `model_id` and `capability_id`, and what artifact
  type it emits (video/mp4, image/png, audio/wav, …).

## Step 0 — Read the ground truth

Read these so your changes match reality (the code is the source of truth):

- `agent-memory\adding-a-capability.md` — the canonical recipe (this skill expands it).
- `src\comfywrap\core\injection.py` — `Binding`, `inject`, `write_temp_prompt`.
- `src\comfywrap\core\registry.py` — `REGISTRY`, `CapabilityEntry`.
- `src\comfywrap\core\driver.py` — how the prompt is run and outputs resolved (you
  do **not** modify this; you rely on it).
- The whole `src\comfywrap\capabilities\video\text_to_video\` package — your template.
- `src\comfywrap\capabilities\__init__.py` and
  `src\comfywrap\capabilities\video\__init__.py` — the manifest chain you mirror.

Also classify the request:

| | **Case A — new model in an existing capability** | **Case B — new capability / modality** |
|---|---|---|
| Trigger | Same modality + the existing adapter's bindings fit the new workflow with a different template | A different modality, or a workflow whose params/output don't fit any existing adapter |
| Work | Add a template + a `CapabilityEntry` (and a small model branch if needed) | New package `src\comfywrap\capabilities\<modality>\<name>\` + one manifest line |
| Core edits | none | none |

## Step 1 — Capture the workflow as an API template (both cases)

ComfyUI's `/prompt` consumes the **API graph**, not the UI workflow. Convert it
**without executing** (needs a reachable ComfyUI for `/object_info`):

```powershell
python scripts\capture_template.py "<path-to-ui-workflow.json>" `
  "src\comfywrap\data\workflows\<your_template>.api.json"
```

Keep a reference copy under repo-root `workflows\`. Inspect the result: it's a
flat dict of `node_id -> {class_type, inputs, _meta:{title}}` (subgraphs are
flattened, ids may look like `92:3`).

## Step 2 — Map the node bindings

For each typed param your capability accepts, find the node id, its `_meta.title`,
and the input key to set. Prefer binding by stable **title/role**; fall back to
**node id** when titles collide (LTX-2's two `CLIPTextEncode` nodes share a title,
so positive=`92:3` / negative=`92:4` are bound by id+role). Note multi-node
params (LTX-2 binds `--seed` to two `RandomNoise` nodes and `--fps` to an int +
float primitive). Record these as a `list[Binding]` in `binding.py`.

> Tip: dump the template with a tiny script that prints, per node,
> `class_type`, `_meta.title`, and the scalar inputs — that's how the LTX-2
> bindings were discovered.

## Step 3 — Write the capability package

Create `src\comfywrap\capabilities\<modality>\<your_capability>\` with:

- `binding.py` — the `list[Binding]` from Step 2.
- `schema.py` — a typed params dataclass + `build_params(args)` that validates and
  normalizes; raise `errors.UsageError` (exit 2) for bad input. Leave unset params
  out so the template defaults apply.
- `adapter.py` — an adapter class with `add_arguments(parser)`,
  `build_params(args)`, `prepare_prompt(params)` (calls
  `inject(load_template(), values, BINDINGS)`), and `resolved_params(params)`.
  Declare `capability_id`, `model_id`, `artifact_type`, `EXPECTED_MODELS`, and
  call `REGISTRY.register(CapabilityEntry(...))` at module import.
- `__init__.py` for the package (and the modality folder if it's new).

Copy-shaped skeletons for all of these are in `references\templates.md`.

## Step 4 — Register it (the one line)

Importing the adapter self-registers it, so add an import to the manifest:

- **Existing modality:** add to
  `src\comfywrap\capabilities\<modality>\__init__.py`.
- **New modality:** create `src\comfywrap\capabilities\<modality>\__init__.py`
  importing your capability, then add one line to
  `src\comfywrap\capabilities\__init__.py`.

## Step 5 — Tests (must stay GPU-free)

Mirror `tests\`. The driver is exercised with a **mocked `comfy` subprocess**
(canned `--json` envelopes) — never a real GPU. Cover:

- **Injection against your real template:** assert each role sets the expected
  node input (guards against template re-capture drift) — see
  `tests\test_injection.py`.
- **Registry resolution:** `REGISTRY.resolve_model("<your_model>")` returns your
  entry; it shows under `comfywrap capabilities`.
- **Schema:** valid inputs normalize; bad inputs raise `UsageError`.

```powershell
.venv\Scripts\python.exe -m pytest tests\test_<your_capability>.py
.venv\Scripts\python.exe -m pytest
```

## Step 6 — Verify and finish

1. `comfywrap capabilities --json` — your capability + model(s) are listed.
2. `comfywrap generate --help` shows your surface; `.venv\Scripts\python.exe -m
   pytest` is green.
3. If a real ComfyUI + GPU is available and the user wants it, do **one** live
   `comfywrap generate "<prompt>" --model <your_model> --json` and confirm a
   playable artifact + the saved-path/`--json` contract. (Attach to the running
   ComfyUI; don't launch a second instance — VRAM.) Outputs land outside the repo
   (the ComfyUI output dir) and/or git-ignored `.scratch\`; **never commit**
   `.venv\`, `.scratch\`, generated media, or any token.
4. Tell the user exactly what changed (files added, the one import line), how to
   invoke the new model, and the test result.

## Rules of thumb (where adapters go wrong)

- **Never `import comfy_cli`** and never touch `src\comfywrap\core\` — all `comfy`
  interaction is the driver's subprocess job; the core stays modality-agnostic.
- The **artifact type** is declared by the adapter; the driver resolves any output
  by file extension, so a new image/audio type needs no core change.
- Keep the cross-capability surface stable: the `--json` envelope
  `{capability,model,artifacts:[{path,type,metadata}]}`, the "final stdout line is
  the saved path" rule, and exit codes **0–11** must not churn.
- Keep `capability_id` / `model_id` stable once shipped — a caller depends on them.
- If a ComfyUI param has no clean node toggle (LTX-2 audio on/off), accept the
  flag, record it in provenance, and document it as native — don't fake it.

## Exit codes (for error mapping and for telling the user what to expect)

`0` ok · `1` internal · `2` invalid args · `3` GPU stack unusable · `4` no GPU ·
`5` OOM · `6` gated model · `7` network · `8` unknown capability/model ·
`9` backend unavailable · `10` workflow execution error · `11` timeout.

## Pointers

- `references\templates.md` — copy-shaped skeletons (`binding.py`, `schema.py`,
  `adapter.py`, the manifest line, and a GPU-free test).
- `src\comfywrap\capabilities\video\text_to_video\` — the real, working reference.
- `scripts\capture_template.py` — the template-capture helper.
