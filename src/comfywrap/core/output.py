"""Artifact collection and provenance sidecar writing (spec section 4.4)."""

from __future__ import annotations

import json
import os
import shutil


def unique_path(directory: str, filename: str) -> str:
    """Return a collision-safe path inside ``directory`` for ``filename``."""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base}_{counter}{ext}")
        counter += 1
    return candidate


def collect_and_write(source_path: str, output_dir: str | None, provenance: dict) -> tuple[str, str]:
    """Place the produced artifact and write its ``<artifact>.json`` provenance sidecar.

    If ``output_dir`` is given, the artifact is copied there with a collision-safe
    name; otherwise it is left where ComfyUI wrote it. The sidecar is always written
    next to the final artifact. Returns (artifact_path, sidecar_path).
    """
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        final_path = unique_path(output_dir, os.path.basename(source_path))
        shutil.copy2(source_path, final_path)
    else:
        final_path = source_path

    sidecar_path = final_path + ".json"
    with open(sidecar_path, "w", encoding="utf-8") as fh:
        json.dump(provenance, fh, indent=2)
    return final_path, sidecar_path
