"""Opt-in real-GPU integration test.

Skipped by default so the suite stays GPU-free. Enable on a machine with a real,
reachable ComfyUI that has the LTX-2 models, e.g.:

    $env:CUW_RUN_INTEGRATION = "1"; python -m pytest tests/test_integration.py -q

It drives the real ``comfy`` against a real ComfyUI and asserts a playable .mp4.
"""

from __future__ import annotations

import json
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CUW_RUN_INTEGRATION") != "1",
    reason="set CUW_RUN_INTEGRATION=1 to run the real-GPU integration test",
)


def test_real_generate_produces_playable_mp4(tmp_path):
    from comfywrap.core import cli

    rc = cli.main(
        ["generate", "a red origami crane on a wooden table, soft light",
         "--json", "--output-dir", str(tmp_path)]
    )
    assert rc == 0
    # The single JSON object is on stdout; re-run capture not available here, so
    # assert via the produced file in the output dir.
    mp4s = list(tmp_path.glob("*.mp4"))
    assert mp4s, "no .mp4 produced"
    assert mp4s[0].stat().st_size > 100_000
    sidecar = mp4s[0].with_suffix(mp4s[0].suffix + ".json")
    assert sidecar.exists()
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta["capability"] == "text_to_video"
    assert meta["model"] == "ltx2-t2v"
