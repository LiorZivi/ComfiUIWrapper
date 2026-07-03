"""image_to_video adapter backed by the LTX-2 (``ltx2-i2v``) workflow.

Like text_to_video, this declares its model id, typed parameter surface, artifact
type, expected model files, and the role->node binding map, then self-registers.
The one wrinkle over text-to-video is a **seed image**: the adapter stages the
caller's ``--image`` into ComfyUI's input directory (resolved from config, so it
honors ``--config`` / ``CUW_*`` just like the driver) and binds its basename to the
workflow's ``LoadImage`` node. The core runtime stays modality-agnostic -- nothing
here is referenced by the driver, config, or CLI dispatch except through the
registry.
"""

from __future__ import annotations

import hashlib
import importlib.resources as resources
import json
import os
import shutil

from ....core.config import load_config
from ....core.injection import inject
from ....core.registry import REGISTRY, CapabilityEntry
from .binding import BINDINGS
from .schema import I2VParams, build_params

CAPABILITY_ID = "image_to_video"
MODEL_ID = "ltx2-i2v"
ARTIFACT_TYPE = "video/mp4"
TEMPLATE_NAME = "ltx2_i2v.api.json"

# Model files this workflow loads, relative to the ComfyUI models dir (same set as t2v).
EXPECTED_MODELS = [
    "checkpoints/ltx-2-19b-dev-fp8.safetensors",
    "text_encoders/gemma_3_12B_it_fp4_mixed.safetensors",
    "latent_upscale_models/ltx-2-spatial-upscaler-x2-1.0.safetensors",
    "loras/ltx-2-19b-distilled-lora-384.safetensors",
]


def load_template() -> dict:
    ref = resources.files("comfywrap").joinpath("data", "workflows", TEMPLATE_NAME)
    return json.loads(ref.read_text(encoding="utf-8"))


def _stage_image(src_path: str, input_dir: str) -> str:
    """Copy the seed image into ComfyUI's input dir under a content-addressed name; return the basename.

    ComfyUI's LoadImage resolves its ``image`` input relative to the input directory,
    so the file must live there before the workflow runs. A content hash keeps the
    staged name stable (idempotent re-runs) and collision-free across images.
    """
    os.makedirs(input_dir, exist_ok=True)
    with open(src_path, "rb") as fh:
        digest = hashlib.sha1(fh.read()).hexdigest()[:12]
    ext = os.path.splitext(src_path)[1].lower() or ".png"
    name = f"comfywrap_i2v_{digest}{ext}"
    dst = os.path.join(input_dir, name)
    if not os.path.exists(dst):
        shutil.copyfile(src_path, dst)
    return name


class ImageToVideoAdapter:
    capability_id = CAPABILITY_ID
    model_id = MODEL_ID
    artifact_type = ARTIFACT_TYPE

    def add_arguments(self, parser) -> None:
        """Declare the image-to-video surface.

        The current core dispatcher builds the ``generate`` surface from the default
        (text_to_video) adapter, so ``--image`` is exposed there as part of the shared
        surface. This method documents i2v's own surface and is used verbatim if a
        future dispatcher contributes args from the *selected* model.
        """
        parser.add_argument("prompt", help="Motion/scene prompt for the seed image.")
        parser.add_argument("--image", help="Path to the seed image (image-to-video).")
        parser.add_argument("--negative", help="Negative prompt.")
        parser.add_argument("--seed", type=int, help="Reproducibility seed (random if omitted).")
        parser.add_argument("--length", type=int, help="Length in frames.")
        parser.add_argument("--seconds", type=float, help="Length in seconds (converted to frames at 25 fps).")
        parser.add_argument("--steps", type=int, help="Sampler steps.")
        parser.add_argument("--audio", dest="audio", action="store_true", default=True,
                            help="Generate with audio (default).")
        parser.add_argument("--no-audio", dest="audio", action="store_false",
                            help="Request video without audio (recorded; ltx2-i2v is audio-native).")

    def build_params(self, args) -> I2VParams:
        params = build_params(args)
        cfg = load_config(getattr(args, "config", None))
        params.image_name = _stage_image(params.image, cfg.comfyui_input_dir)
        return params

    def prepare_prompt(self, params: I2VParams) -> dict:
        values = {
            "image": params.image_name,
            "prompt": params.prompt,
            "negative": params.negative,
            "seed": params.seed,
            "length": params.length,
            "steps": params.steps,
        }
        return inject(load_template(), values, BINDINGS)

    def resolved_params(self, params: I2VParams) -> dict:
        return dict(params.__dict__)


REGISTRY.register(
    CapabilityEntry(
        capability_id=CAPABILITY_ID,
        model_id=MODEL_ID,
        adapter=ImageToVideoAdapter(),
        artifact_type=ARTIFACT_TYPE,
        template_ref=TEMPLATE_NAME,
        expected_models=EXPECTED_MODELS,
    )
)
