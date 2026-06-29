"""Capture (or refresh) an API-format workflow template for comfywrap.

Drives ``comfy run --print-prompt`` (via comfywrap's driver) to convert a UI-format
ComfyUI workflow into the flat API graph that comfywrap injects into, **without
executing it**. Requires a reachable ComfyUI (used only for /object_info).

Usage:
    python scripts/capture_template.py <ui_workflow.json> <out_template.api.json> \
        [--host 127.0.0.1] [--port 8000]

Example (refresh the bundled LTX-2 template):
    python scripts/capture_template.py \
        "C:\\AI\\Softwares\\user\\default\\workflows\\video_ltx2_t2v.json" \
        "src\\comfywrap\\data\\workflows\\ltx2_t2v.api.json"
"""

from __future__ import annotations

import argparse
import json
import sys

from comfywrap.core.config import Config
from comfywrap.core.driver import ComfyDriver


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture an API-format workflow template.")
    parser.add_argument("source", help="Path to the UI-format workflow JSON.")
    parser.add_argument("output", help="Path to write the API-format template JSON.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    driver = ComfyDriver(Config(host=args.host, port=args.port))
    if not driver.probe():
        print(f"error: no ComfyUI reachable at {args.host}:{args.port} (needed for conversion).", file=sys.stderr)
        return 9

    graph = driver.capture_api_prompt(args.source)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=2)
    print(f"wrote {len(graph)} nodes -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
