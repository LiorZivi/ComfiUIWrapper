"""Stable role -> node bindings for the captured LTX-2 text-to-video API template.

Node ids come from the flattened API graph (subgraph prefix ``92:``) captured via
``comfy run --print-prompt`` from ``video_ltx2_t2v.json``. The two CLIPTextEncode
nodes share the title 'CLIP Text Encode (Prompt)', so positive/negative are bound
by id+role. ``--seed`` drives both RandomNoise nodes and ``--fps`` drives both the
int and float frame-rate primitives so the pipeline stays internally consistent.
"""

from __future__ import annotations

from ....core.injection import Binding

BINDINGS: list[Binding] = [
    Binding("prompt", ["92:3"], "text", cast="str"),
    Binding("negative", ["92:4"], "text", cast="str", optional=True),
    Binding("seed", ["92:67", "92:11"], "noise_seed", cast="int"),
    Binding("width", ["92:89"], "width", cast="int"),
    Binding("height", ["92:89"], "height", cast="int"),
    Binding("length", ["92:62"], "value", cast="int"),
    Binding("fps_int", ["92:103"], "value", cast="int"),
    Binding("fps_float", ["92:102"], "value", cast="float"),
    Binding("steps", ["92:9"], "steps", cast="int"),
]
