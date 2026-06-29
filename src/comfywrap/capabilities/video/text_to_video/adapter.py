"""text_to_video adapter backed by the LTX-2 (ltx2-t2v) workflow.

The adapter declares its model id, typed parameter surface, artifact type, expected
model files, and the role->node binding map, then self-registers. The core runtime
stays modality-agnostic: nothing here is referenced by the driver, config, or CLI
dispatch except through the registry, so a future video or non-video capability is
added as a sibling adapter + template + binding with no core changes.
"""

from __future__ import annotations

import importlib.resources as resources
import json

from ....core.injection import inject
from ....core.registry import REGISTRY, CapabilityEntry
from .binding import BINDINGS
from .schema import T2VParams, build_params

CAPABILITY_ID = "text_to_video"
MODEL_ID = "ltx2-t2v"
ARTIFACT_TYPE = "video/mp4"
TEMPLATE_NAME = "ltx2_t2v.api.json"

# Model files this workflow loads, relative to the ComfyUI models dir (spec Appendix A).
EXPECTED_MODELS = [
    "checkpoints/ltx-2-19b-dev-fp8.safetensors",
    "text_encoders/gemma_3_12B_it_fp4_mixed.safetensors",
    "latent_upscale_models/ltx-2-spatial-upscaler-x2-1.0.safetensors",
    "loras/ltx-2-19b-distilled-lora-384.safetensors",
]


def load_template() -> dict:
    ref = resources.files("comfywrap").joinpath("data", "workflows", TEMPLATE_NAME)
    return json.loads(ref.read_text(encoding="utf-8"))


class TextToVideoAdapter:
    capability_id = CAPABILITY_ID
    model_id = MODEL_ID
    artifact_type = ARTIFACT_TYPE

    def add_arguments(self, parser) -> None:
        """Contribute the shared video-generation surface to the ``generate`` subparser."""
        parser.add_argument("prompt", help="Text prompt for the video.")
        parser.add_argument("--negative", help="Negative prompt.")
        parser.add_argument("--seed", type=int, help="Reproducibility seed (random if omitted).")
        parser.add_argument("--size", help="Output size as WxH, e.g. 720x1280.")
        parser.add_argument("--width", type=int, help="Output width (overrides --size).")
        parser.add_argument("--height", type=int, help="Output height (overrides --size).")
        parser.add_argument("--length", type=int, help="Length in frames.")
        parser.add_argument("--seconds", type=float, help="Length in seconds (converted to frames via --fps).")
        parser.add_argument("--fps", type=int, help="Frames per second.")
        parser.add_argument("--steps", type=int, help="Sampler steps.")
        parser.add_argument("--audio", dest="audio", action="store_true", default=True,
                            help="Generate with audio (default).")
        parser.add_argument("--no-audio", dest="audio", action="store_false",
                            help="Request video without audio (recorded; ltx2-t2v is audio-native).")

    def build_params(self, args) -> T2VParams:
        return build_params(args)

    def prepare_prompt(self, params: T2VParams) -> dict:
        values = {
            "prompt": params.prompt,
            "negative": params.negative,
            "seed": params.seed,
            "width": params.width,
            "height": params.height,
            "length": params.length,
            "fps_int": params.fps,
            "fps_float": params.fps,
            "steps": params.steps,
        }
        return inject(load_template(), values, BINDINGS)

    def resolved_params(self, params: T2VParams) -> dict:
        return dict(params.__dict__)


REGISTRY.register(
    CapabilityEntry(
        capability_id=CAPABILITY_ID,
        model_id=MODEL_ID,
        adapter=TextToVideoAdapter(),
        artifact_type=ARTIFACT_TYPE,
        template_ref=TEMPLATE_NAME,
        expected_models=EXPECTED_MODELS,
    )
)
