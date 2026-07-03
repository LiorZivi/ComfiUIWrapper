"""Stable role -> node bindings for the captured LTX-2 image-to-video API template.

Node ids come from the flattened API graph captured via ``comfy run --print-prompt``
from ``video_ltx2_i2v.json`` (subgraph prefix ``92:``; the top-level ``LoadImage``
is ``98``). The two ``CLIPTextEncode`` nodes share the title
'CLIP Text Encode (Prompt)', so positive/negative are bound by id+role. ``--seed``
drives both ``RandomNoise`` nodes so the video and audio streams stay consistent.
Output size derives from the seed image (Resize/GetImageSize nodes) and fps is baked
at 25 in the template, so neither is bound here.
"""

from __future__ import annotations

from ....core.injection import Binding

BINDINGS: list[Binding] = [
    Binding("image", ["98"], "image", cast="str"),
    Binding("prompt", ["92:3"], "text", cast="str"),
    Binding("negative", ["92:4"], "text", cast="str", optional=True),
    Binding("seed", ["92:67", "92:11"], "noise_seed", cast="int"),
    Binding("length", ["92:62"], "value", cast="int"),
    Binding("steps", ["92:9"], "steps", cast="int"),
]
