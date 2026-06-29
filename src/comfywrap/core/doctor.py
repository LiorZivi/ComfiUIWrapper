"""The ``doctor`` environment check: GPU, comfy-cli, ComfyUI reachability, model files."""

from __future__ import annotations

import os
import shutil
import subprocess

from .config import Config
from .driver import ComfyDriver


def _gpu_name() -> str:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return ""
    try:
        out = subprocess.run(  # noqa: S603
            [smi, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return ""
    lines = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
    return lines[0] if lines else ""


def _comfy_version(driver: ComfyDriver) -> str:
    try:
        code, out, _ = driver._runner([driver.comfy_bin(), "--version"])  # noqa: SLF001
    except Exception:
        return ""
    import json

    for line in (out or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return line  # plain "x.y.z"
        if isinstance(obj, dict):
            return obj.get("version") or (obj.get("data") or {}).get("version") or ""
    return ""


def run_doctor(cfg: Config, driver: ComfyDriver | None = None) -> dict:
    driver = driver or ComfyDriver(cfg)
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    comfy_bin = driver.comfy_bin()
    comfy_ok = bool(shutil.which(comfy_bin) or os.path.exists(comfy_bin))
    version = _comfy_version(driver) if comfy_ok else ""
    add("comfy_cli", comfy_ok, f"{comfy_bin} (version {version or 'unknown'})")

    gpu = _gpu_name()
    add("gpu", bool(gpu), gpu or "no NVIDIA GPU detected")

    reachable = driver.probe()
    launchable = os.path.exists(cfg.comfyui_python) and os.path.exists(cfg.comfyui_main)
    add(
        "comfyui",
        reachable or (cfg.auto_launch and launchable),
        f"reachable at {cfg.host}:{cfg.port}" if reachable
        else (f"not running; auto-launchable={launchable}"),
    )

    from ..capabilities.video.text_to_video.adapter import EXPECTED_MODELS

    missing = [
        m for m in EXPECTED_MODELS
        if not os.path.exists(os.path.join(cfg.comfyui_models_dir, *m.split("/")))
    ]
    add("ltx2_models", not missing, "all present" if not missing else "missing: " + ", ".join(missing))

    ready = all(c["ok"] for c in checks)
    return {
        "ready": ready,
        "host": cfg.host,
        "port": cfg.port,
        "comfy_version": version,
        "gpu": gpu,
        "checks": checks,
    }
