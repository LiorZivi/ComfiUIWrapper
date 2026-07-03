"""GPU-free tests for the image_to_video (``ltx2-i2v``) capability.

Injection is asserted against the real bundled template (guards against template
re-capture drift); schema validation and image staging use temp dirs. No GPU, no
real ComfyUI, no network.
"""

from __future__ import annotations

import types

import pytest

from comfywrap.capabilities.video.image_to_video.adapter import (
    ImageToVideoAdapter,
    load_template,
)
from comfywrap.capabilities.video.image_to_video.binding import BINDINGS
from comfywrap.capabilities.video.image_to_video.schema import build_params
from comfywrap.core import errors
from comfywrap.core.injection import inject
from comfywrap.core.registry import REGISTRY


def _args(**kw):
    base = dict(
        prompt=None, image=None, negative=None, seed=None,
        length=None, seconds=None, steps=None, audio=True, config=None,
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


def _png(tmp_path, name="seed.png", data=b"\x89PNG\r\n\x1a\nhello"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_registry_resolves_ltx2_i2v():
    entry = REGISTRY.resolve_model("ltx2-i2v")
    assert entry.capability_id == "image_to_video"
    assert entry.artifact_type == "video/mp4"
    assert entry.template_ref == "ltx2_i2v.api.json"


def test_capability_lists_both_models():
    models = {e.model_id for e in REGISTRY.list()}
    assert {"ltx2-t2v", "ltx2-i2v"} <= models


def test_injection_sets_bound_nodes():
    values = {
        "image": "seed.png",
        "prompt": "the camera slowly pushes in",
        "negative": "blurry, low quality",
        "seed": 4242,
        "length": 97,
        "steps": 12,
    }
    g = inject(load_template(), values, BINDINGS)
    assert g["98"]["inputs"]["image"] == "seed.png"
    assert g["92:3"]["inputs"]["text"] == "the camera slowly pushes in"
    assert g["92:4"]["inputs"]["text"] == "blurry, low quality"
    assert g["92:67"]["inputs"]["noise_seed"] == 4242
    assert g["92:11"]["inputs"]["noise_seed"] == 4242
    assert g["92:62"]["inputs"]["value"] == 97
    assert g["92:9"]["inputs"]["steps"] == 12


def test_schema_requires_prompt(tmp_path):
    with pytest.raises(errors.UsageError):
        build_params(_args(prompt="   ", image=str(_png(tmp_path))))


def test_schema_requires_image():
    with pytest.raises(errors.UsageError):
        build_params(_args(prompt="move", image=None))


def test_schema_rejects_missing_image_file(tmp_path):
    with pytest.raises(errors.UsageError):
        build_params(_args(prompt="move", image=str(tmp_path / "nope.png")))


def test_schema_seconds_to_frames(tmp_path):
    p = build_params(_args(prompt="move", image=str(_png(tmp_path)), seconds=2.0))
    assert p.length == 50  # 2.0s * 25fps


def test_seed_randomized_when_omitted(tmp_path):
    p = build_params(_args(prompt="move", image=str(_png(tmp_path))))
    assert isinstance(p.seed, int) and p.seed >= 0


def test_adapter_stages_image_and_binds_it(tmp_path, monkeypatch):
    img = _png(tmp_path, data=b"\x89PNG\r\n\x1aunique-bytes")
    input_dir = tmp_path / "comfy_input"
    monkeypatch.setenv("CUW_COMFYUI_INPUT_DIR", str(input_dir))

    adapter = ImageToVideoAdapter()
    params = adapter.build_params(_args(prompt="move", image=str(img)))

    assert params.image_name and params.image_name.startswith("comfywrap_i2v_")
    assert (input_dir / params.image_name).exists()
    g = adapter.prepare_prompt(params)
    assert g["98"]["inputs"]["image"] == params.image_name


def test_cli_builds_i2v_surface_with_image():
    from comfywrap.core import cli

    argv = ["generate", "--model", "ltx2-i2v", "--image", "seed.png", "a prompt"]
    args = cli.build_parser(argv).parse_args(argv)
    assert args.model == "ltx2-i2v"
    assert args.image == "seed.png"
    assert args.prompt == "a prompt"


def test_cli_t2v_surface_rejects_image():
    from comfywrap.core import cli

    # The default (text-to-video) surface no longer declares --image.
    argv = ["generate", "a prompt", "--image", "seed.png"]
    with pytest.raises(SystemExit):
        cli.build_parser(argv).parse_args(argv)
