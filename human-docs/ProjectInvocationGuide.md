# Project Invocation Guide — ComfiUIWrapper

ComfiUIWrapper is a headless, scriptable wrapper for running ComfyUI workflows on your local GPU (it drives [comfy-cli](https://github.com/Comfy-Org/comfy-cli) as a subprocess), driven entirely by the `comfywrap` command (installed at `.venv\Scripts\comfywrap.exe`; entry point `comfywrap.core.cli:main`).
One-shot commands print the saved absolute artifact path as their final stdout line; add the global `--json` flag to any command to get a single machine-readable JSON object instead (diagnostics → stderr).

## General functionality

| Function | How to invoke |
|----------|---------------|
| **Verify the environment** | `comfywrap doctor` → confirms comfy-cli, an NVIDIA GPU, ComfyUI reachable/auto-launchable at `127.0.0.1:8000`, and the LTX-2 model files (exit `0` when ready). |
| **List capabilities & models** | `comfywrap capabilities` → shows valid `--model` ids (`ltx2-t2v` default, `ltx2-i2v` for image-to-video). |

## Capabilities

| Capability | How to invoke (high level) |
|------------|----------------------------|
| **Generate a video from text** — Text-to-Video (LTX-2) | `comfywrap generate "<prompt>"` → saves an MP4 + `.json` sidecar. Tune with `--size`, `--seconds`/`--length`, `--seed`, `--steps`; audio with native lip-sync is on by default (put a character's line in the prompt, e.g. `...saying: "<line>"`).<br>Example: `comfywrap.exe generate "a news anchor looks at the camera and clearly says: 'Good evening, welcome back'" --seconds 5 --fps 24 --size 720x1280 --seed 42 --steps 30 --output-dir C:\Dev\out` |
| **Animate a seed image** — Image-to-Video (LTX-2) | `comfywrap generate "<motion prompt>" --model ltx2-i2v --image <path>` → animates a still you provide into an MP4 (output size derives from the image; fps baked at 25).<br>Example: `comfywrap.exe generate "the camera slowly pushes in" --model ltx2-i2v --image C:\Dev\in.png --seconds 5 --seed 42 --output-dir C:\Dev\out` |

> Add `--json` to any command for scripting. For all flags, the `--json` schema, and exit codes (`0`–`11`), see [README.md](../README.md) and [human-docs/skill-invocation.md](skill-invocation.md).
