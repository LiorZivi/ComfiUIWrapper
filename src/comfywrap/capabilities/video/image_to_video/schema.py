"""Typed parameter surface for image_to_video (LTX-2 ``ltx2-i2v``).

Mirrors the text_to_video knobs minus size/fps (i2v derives output size from the
seed image and bakes fps at 25) plus a **required seed image** (``--image``).
Validation raises ``errors.UsageError`` (exit 2) for bad input. Unset params fall
back to the template's baked-in defaults. No file I/O happens here -- the adapter
stages the validated image into ComfyUI's input dir.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass

from ....core import errors

# The LTX-2 i2v template's baked frame rate; used only to convert --seconds -> frames.
_TEMPLATE_FPS = 25


@dataclass
class I2VParams:
    prompt: str
    image: str  # absolute path to the source seed image (validated to exist)
    negative: str | None = None
    seed: int | None = None
    length: int | None = None
    steps: int | None = None
    audio: bool = True
    image_name: str | None = None  # staged basename in ComfyUI's input dir (set by the adapter)


def _require_non_negative_int(name: str, value) -> None:
    if value is None:
        return
    if not isinstance(value, int) or value < 0:
        raise errors.UsageError(f"--{name} must be a non-negative integer (got {value!r}).")


def build_params(args) -> I2VParams:
    """Validate and normalize an argparse namespace into I2VParams (no file I/O)."""
    prompt = (getattr(args, "prompt", None) or "").strip()
    if not prompt:
        raise errors.UsageError(
            "A non-empty prompt is required (describe the motion for the seed image).",
            hint='Example: comfywrap generate "the camera slowly pushes in" --model ltx2-i2v --image in.png',
        )

    image = getattr(args, "image", None)
    if not image:
        raise errors.UsageError(
            "--image is required for image_to_video (ltx2-i2v).",
            hint="Pass a seed image you own or are licensed to use: --image C:\\path\\to\\image.png",
        )
    image = os.path.abspath(os.path.expanduser(str(image)))
    if not os.path.isfile(image):
        raise errors.UsageError(f"Seed image not found: {image}")

    length = getattr(args, "length", None)
    seconds = getattr(args, "seconds", None)
    if length is None and seconds is not None:
        if seconds <= 0:
            raise errors.UsageError("--seconds must be positive.")
        length = max(1, int(round(seconds * _TEMPLATE_FPS)))

    seed = getattr(args, "seed", None)
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    steps = getattr(args, "steps", None)
    _require_non_negative_int("seed", seed)
    _require_non_negative_int("length", length)
    _require_non_negative_int("steps", steps)

    return I2VParams(
        prompt=prompt,
        image=image,
        negative=getattr(args, "negative", None),
        seed=seed,
        length=length,
        steps=steps,
        audio=bool(getattr(args, "audio", True)),
    )
