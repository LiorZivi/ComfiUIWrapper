"""Injection is validated against the REAL bundled LTX-2 template, so the node-id
bindings stay correct (a guard against template re-capture drift)."""

from comfywrap.capabilities.video.text_to_video.adapter import load_template
from comfywrap.capabilities.video.text_to_video.binding import BINDINGS
from comfywrap.core.injection import inject


def _values():
    return {
        "prompt": "POSITIVE",
        "negative": "NEGATIVE",
        "seed": 123,
        "width": 512,
        "height": 768,
        "length": 96,
        "fps_int": 30,
        "fps_float": 30,
        "steps": 15,
    }


def test_inject_sets_all_bound_nodes():
    graph = inject(load_template(), _values(), BINDINGS)
    assert graph["92:3"]["inputs"]["text"] == "POSITIVE"
    assert graph["92:4"]["inputs"]["text"] == "NEGATIVE"
    assert graph["92:67"]["inputs"]["noise_seed"] == 123
    assert graph["92:11"]["inputs"]["noise_seed"] == 123
    assert graph["92:89"]["inputs"]["width"] == 512
    assert graph["92:89"]["inputs"]["height"] == 768
    assert graph["92:62"]["inputs"]["value"] == 96
    assert graph["92:103"]["inputs"]["value"] == 30
    assert graph["92:102"]["inputs"]["value"] == 30.0
    assert graph["92:9"]["inputs"]["steps"] == 15


def test_inject_is_non_destructive():
    template = load_template()
    original = template["92:3"]["inputs"]["text"]
    inject(template, {"prompt": "CHANGED"}, BINDINGS)
    assert template["92:3"]["inputs"]["text"] == original


def test_inject_ignores_unbound_value():
    # 'audio' has no binding; injection must silently ignore it.
    graph = inject(load_template(), {"audio": False}, BINDINGS)
    assert isinstance(graph, dict)
