"""Layered configuration: CLI overrides > CUW_* environment > config file > builtin defaults.

The builtin defaults are tuned for the target workstation (ComfyUI Desktop on
127.0.0.1:8000 with its data root at C:\\AI\\Softwares) and are fully overridable.
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]


_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


@dataclass
class Config:
    """Resolved runtime configuration."""

    # comfy-cli driver
    comfy_bin: str | None = None  # None -> resolve via PATH / venv at run time
    host: str = "127.0.0.1"
    port: int = 8000
    auto_launch: bool = True
    keep_warm: bool = True
    attach_only: bool = False
    per_event_timeout: int = 1200  # comfy run --timeout (per-event silence, survives long model loads)
    ready_timeout: int = 240  # seconds to wait for an auto-launched server to become ready

    # capability / output
    default_model: str = "ltx2-t2v"
    output_dir: str | None = None  # where comfywrap copies artifacts; None -> leave in ComfyUI output dir
    workflows_dir: str | None = None  # override bundled templates

    # ComfyUI install / data root (used to resolve output paths and to auto-launch)
    comfyui_base_directory: str = r"C:\AI\Softwares"
    comfyui_output_dir: str = r"C:\AI\Softwares\output"
    comfyui_temp_dir: str = r"C:\AI\Softwares\temp"
    comfyui_user_dir: str = r"C:\AI\Softwares\user"
    comfyui_input_dir: str = r"C:\AI\Softwares\input"
    comfyui_models_dir: str = r"C:\AI\Softwares\models"
    comfyui_python: str = r"C:\AI\Softwares\.venv\Scripts\python.exe"
    comfyui_main: str = r"C:\AI\ComfyUI\resources\ComfyUI\main.py"
    extra_model_paths_config: str | None = (
        r"C:\Users\USER\AppData\Roaming\Comfy Desktop\shared_model_paths.yaml"
    )
    launch_extra_args: list[str] = field(default_factory=list)


def _coerce(value, to_type):
    """Coerce a string (from env/toml) to the dataclass field type."""
    if to_type is bool or to_type == "bool":
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in _TRUE:
            return True
        if s in _FALSE:
            return False
        raise ValueError(f"expected a boolean, got {value!r}")
    if to_type is int or to_type == "int":
        return int(value)
    if to_type == "list":
        if isinstance(value, list):
            return [str(v) for v in value]
        # comma- or whitespace-separated string
        return [p for p in str(value).replace(",", " ").split() if p]
    return value if value is not None else None


def _field_kind(f: dataclasses.Field) -> str:
    ann = f.type
    text = ann if isinstance(ann, str) else getattr(ann, "__name__", str(ann))
    if "bool" in text:
        return "bool"
    if "int" in text:
        return "int"
    if "list" in text:
        return "list"
    return "str"


def _discover_config_file(explicit: str | None) -> str | None:
    if explicit:
        if not os.path.exists(explicit):
            from .errors import UsageError

            raise UsageError(f"Config file not found: {explicit}")
        return explicit
    for name in ("comfywrap.toml", "config.toml"):
        if os.path.exists(name):
            return name
    return None


def load_config(config_path: str | None = None, cli_overrides: dict | None = None) -> Config:
    """Resolve config with precedence: CLI overrides > CUW_* env > config file > builtin defaults."""
    fields = {f.name: f for f in dataclasses.fields(Config)}
    values: dict = {}

    # 1) config file (lowest after builtins)
    path = _discover_config_file(config_path)
    if path:
        if tomllib is None:  # pragma: no cover
            from .errors import UsageError

            raise UsageError("tomllib is unavailable; cannot read a config file on this Python.")
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        for key, val in data.items():
            if key in fields:
                values[key] = _coerce(val, _field_kind(fields[key]))

    # 2) environment (CUW_*)
    for name, f in fields.items():
        env_key = "CUW_" + name.upper()
        if env_key in os.environ:
            values[name] = _coerce(os.environ[env_key], _field_kind(f))

    # 3) CLI overrides (highest)
    for key, val in (cli_overrides or {}).items():
        if key in fields and val is not None:
            values[key] = _coerce(val, _field_kind(fields[key]))

    return Config(**values)
