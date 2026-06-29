"""Typed parameter surface for text_to_video (the shared video knobs).

Validation is permissive where it is safe (sizes rounded to a multiple of 32 for
LTX latent constraints; seconds converted to frames) and strict where a value
would be nonsensical (non-integer / negative). Unset params fall back to the
template's baked-in defaults.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ....core import errors


@dataclass
class T2VParams:
    prompt: str
    negative: str | None = None
    seed: int | None = None
    width: int | None = None
    height: int | None = None
    length: int | None = None
    fps: int | None = None
    steps: int | None = None
    audio: bool = True


def _require_non_negative_int(name: str, value) -> None:
    if value is None:
        return
    if not isinstance(value, int) or value < 0:
        raise errors.UsageError(f"--{name} must be a non-negative integer (got {value!r}).")


def build_params(args) -> T2VParams:
    """Validate and normalize an argparse namespace into T2VParams."""
    prompt = (getattr(args, "prompt", None) or "").strip()
    if not prompt:
        raise errors.UsageError("A non-empty prompt is required.", hint='Example: comfywrap generate "a cat" ...')

    width = getattr(args, "width", None)
    height = getattr(args, "height", None)
    size = getattr(args, "size", None)
    if size:
        normalized = size.lower().replace("\u00d7", "x")  # accept the unicode multiplication sign
        try:
            w_str, h_str = normalized.split("x")
            width = int(w_str)
            height = int(h_str)
        except ValueError:
            raise errors.UsageError(f"Invalid --size {size!r}. Use WxH, e.g. 720x1280.")
    if width is not None:
        width = int(width)
    if height is not None:
        height = int(height)

    fps = getattr(args, "fps", None)
    length = getattr(args, "length", None)
    seconds = getattr(args, "seconds", None)
    if length is None and seconds is not None:
        if seconds <= 0:
            raise errors.UsageError("--seconds must be positive.")
        length = max(1, int(round(seconds * (fps or 24))))

    seed = getattr(args, "seed", None)
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    steps = getattr(args, "steps", None)
    _require_non_negative_int("seed", seed)
    _require_non_negative_int("length", length)
    _require_non_negative_int("fps", fps)
    _require_non_negative_int("steps", steps)
    if width is not None:
        _require_non_negative_int("width", width)
    if height is not None:
        _require_non_negative_int("height", height)

    return T2VParams(
        prompt=prompt,
        negative=getattr(args, "negative", None),
        seed=seed,
        width=width,
        height=height,
        length=length,
        fps=fps,
        steps=steps,
        audio=bool(getattr(args, "audio", True)),
    )
