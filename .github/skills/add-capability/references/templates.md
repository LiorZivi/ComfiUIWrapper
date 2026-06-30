# Templates — copy-shaped skeletons for a new comfywrap capability

These mirror the real `src\comfywrap\capabilities\video\text_to_video\` package.
Adapt names, the modality folder, the node bindings, and the param surface.
**Read the live code too** — it is the source of truth.

Throughout, `<modality>` is e.g. `video` / `image` / `audio`, `<capability>` is
e.g. `text_to_video`, and the dotted import depth for the core from a capability
module is **four dots** (`....core`) because the package is
`comfywrap.capabilities.<modality>.<capability>`.

---

## `binding.py` — role → node bindings

```python
"""Stable role -> node bindings for the captured <capability> API template."""

from __future__ import annotations

from ....core.injection import Binding

BINDINGS: list[Binding] = [
    Binding("prompt", ["<positive_node_id>"], "text", cast="str"),
    Binding("negative", ["<negative_node_id>"], "text", cast="str", optional=True),
    Binding("seed", ["<seed_node_id>"], "noise_seed", cast="int"),
    # multi-node example: Binding("seed", ["92:67", "92:11"], "noise_seed", cast="int"),
    Binding("width", ["<size_node_id>"], "width", cast="int"),
    Binding("height", ["<size_node_id>"], "height", cast="int"),
    Binding("steps", ["<steps_node_id>"], "steps", cast="int"),
    # add the params your workflow exposes; bind by id+role when titles collide
]
```

---

## `schema.py` — typed params + validation

```python
"""Typed parameter surface for <capability>."""

from __future__ import annotations

import random
from dataclasses import dataclass

from ....core import errors


@dataclass
class Params:
    prompt: str
    negative: str | None = None
    seed: int | None = None
    width: int | None = None
    height: int | None = None
    steps: int | None = None


def build_params(args) -> Params:
    prompt = (getattr(args, "prompt", None) or "").strip()
    if not prompt:
        raise errors.UsageError("A non-empty prompt is required.")

    width = getattr(args, "width", None)
    height = getattr(args, "height", None)
    if getattr(args, "size", None):
        try:
            w, h = args.size.lower().replace("\u00d7", "x").split("x")
            width, height = int(w), int(h)
        except ValueError:
            raise errors.UsageError(f"Invalid --size {args.size!r}. Use WxH.")

    seed = getattr(args, "seed", None)
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    for name in ("seed", "width", "height", "steps"):
        v = locals().get(name) if name in ("width", "height") else getattr(args, name, None) if name != "seed" else seed
        if v is not None and (not isinstance(v, int) or v < 0):
            raise errors.UsageError(f"--{name} must be a non-negative integer.")

    return Params(prompt=prompt, negative=getattr(args, "negative", None),
                  seed=seed, width=width, height=height, steps=getattr(args, "steps", None))
```

---

## `adapter.py` — declare, prepare, self-register

```python
"""<capability> adapter backed by the <model> workflow."""

from __future__ import annotations

import importlib.resources as resources
import json

from ....core.injection import inject
from ....core.registry import REGISTRY, CapabilityEntry
from .binding import BINDINGS
from .schema import Params, build_params

CAPABILITY_ID = "<capability>"          # e.g. "text_to_video"
MODEL_ID = "<model-id>"                  # e.g. "ltx2-t2v"
ARTIFACT_TYPE = "<mime>"                 # e.g. "video/mp4", "image/png", "audio/wav"
TEMPLATE_NAME = "<your_template>.api.json"
EXPECTED_MODELS = [
    # "checkpoints/<file>.safetensors", ... (relative to the ComfyUI models dir)
]


def load_template() -> dict:
    ref = resources.files("comfywrap").joinpath("data", "workflows", TEMPLATE_NAME)
    return json.loads(ref.read_text(encoding="utf-8"))


class Adapter:
    capability_id = CAPABILITY_ID
    model_id = MODEL_ID
    artifact_type = ARTIFACT_TYPE

    def add_arguments(self, parser) -> None:
        parser.add_argument("prompt")
        parser.add_argument("--negative")
        parser.add_argument("--seed", type=int)
        parser.add_argument("--size")
        parser.add_argument("--width", type=int)
        parser.add_argument("--height", type=int)
        parser.add_argument("--steps", type=int)
        # add only the flags your modality needs

    def build_params(self, args) -> Params:
        return build_params(args)

    def prepare_prompt(self, params: Params) -> dict:
        values = {
            "prompt": params.prompt,
            "negative": params.negative,
            "seed": params.seed,
            "width": params.width,
            "height": params.height,
            "steps": params.steps,
        }
        return inject(load_template(), values, BINDINGS)

    def resolved_params(self, params: Params) -> dict:
        return dict(params.__dict__)


REGISTRY.register(CapabilityEntry(
    capability_id=CAPABILITY_ID, model_id=MODEL_ID, adapter=Adapter(),
    artifact_type=ARTIFACT_TYPE, template_ref=TEMPLATE_NAME, expected_models=EXPECTED_MODELS,
))
```

---

## The manifest lines (the "one line")

`src\comfywrap\capabilities\<modality>\__init__.py`:

```python
from .<capability> import adapter  # noqa: F401  (registers <capability>)
```

If the modality is new, also `src\comfywrap\capabilities\__init__.py`:

```python
from . import <modality>  # noqa: F401  (registers <modality> capabilities)
```

Each `<capability>\__init__.py` can be a one-line docstring; the adapter import in
the modality manifest is what triggers registration.

---

## `tests\test_<capability>.py` — GPU-free

```python
from comfywrap.capabilities.<modality>.<capability>.adapter import load_template
from comfywrap.capabilities.<modality>.<capability>.binding import BINDINGS
from comfywrap.core.injection import inject
from comfywrap.core.registry import REGISTRY


def test_injection_sets_bound_nodes():
    g = inject(load_template(), {"prompt": "P", "seed": 123}, BINDINGS)
    assert g["<positive_node_id>"]["inputs"]["text"] == "P"
    assert g["<seed_node_id>"]["inputs"]["noise_seed"] == 123


def test_registry_resolves_model():
    entry = REGISTRY.resolve_model("<model-id>")
    assert entry.capability_id == "<capability>"
    assert entry.artifact_type == "<mime>"
```

For a process-level contract test (mock the `comfy` subprocess), copy the pattern
in `tests\test_cli.py` / `tests\test_driver.py`: patch
`comfywrap.core.driver._default_runner` to return a canned `--json` envelope and
`comfywrap.core.driver.ComfyDriver.probe` to `True`, set `CUW_COMFYUI_OUTPUT_DIR`
to a temp dir holding a dummy artifact, then call `comfywrap.core.cli.main([...])`.
