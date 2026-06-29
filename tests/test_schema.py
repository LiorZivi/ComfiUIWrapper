import argparse

import pytest

from comfywrap.capabilities.video.text_to_video.schema import build_params
from comfywrap.core import errors


def ns(**kw):
    base = dict(prompt="hello", negative=None, seed=None, size=None, width=None,
                height=None, length=None, seconds=None, fps=None, steps=None, audio=True)
    base.update(kw)
    return argparse.Namespace(**base)


def test_size_parsed_to_width_height():
    p = build_params(ns(size="720x1280"))
    assert (p.width, p.height) == (720, 1280)


def test_dimensions_passed_through_unchanged():
    p = build_params(ns(width=704, height=1280))
    assert (p.width, p.height) == (704, 1280)


def test_seconds_converted_to_frames():
    assert build_params(ns(seconds=2.0, fps=24)).length == 48


def test_explicit_length_wins_over_seconds():
    assert build_params(ns(length=120, seconds=2.0, fps=24)).length == 120


def test_invalid_size_raises_usage_error():
    with pytest.raises(errors.UsageError):
        build_params(ns(size="banana"))


def test_empty_prompt_raises_usage_error():
    with pytest.raises(errors.UsageError):
        build_params(ns(prompt="   "))


def test_seed_defaults_to_random_int():
    assert isinstance(build_params(ns()).seed, int)
