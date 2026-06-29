"""The comfy-cli driver: the single module that shells out to the ``comfy`` binary.

Everything comfy-cli / ComfyUI-version-specific lives here (spec section 5):
argv construction, server lifecycle (probe / attach / auto-launch / keep-warm),
running a workflow, parsing the NDJSON ``--json`` stream, resolving produced
``/view`` URLs to absolute local paths, and mapping failures onto the exit-code
taxonomy. comfy-cli is invoked as a subprocess and never imported.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

from . import errors
from .config import Config

# A runner executes an argv and returns (returncode, stdout, stderr). Tests inject a fake.
Runner = Callable[[list[str]], "tuple[int, str, str]"]
# An HTTP opener returns (status, body). Tests inject a fake.
Opener = Callable[..., "tuple[int, bytes]"]

_MIME_BY_EXT = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".gif": "image/gif",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
}


def mime_for(path: str) -> str:
    return _MIME_BY_EXT.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def _default_runner(argv: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(  # noqa: S603 - argv is fully constructed by us
        argv, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return proc.returncode, proc.stdout, proc.stderr


@dataclass
class Artifact:
    path: str
    type: str
    url: str | None = None
    node_id: str | None = None


@dataclass
class RunResult:
    artifacts: list[Artifact]
    prompt_id: str | None = None
    elapsed_seconds: float | None = None
    envelope: dict = field(default_factory=dict)
    events: list = field(default_factory=list)


def _parse_ndjson(text: str) -> list[dict]:
    events: list[dict] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def _find_envelope(events: list[dict]) -> dict | None:
    for event in reversed(events):
        if event.get("type") == "envelope":
            return event
    return None


class ComfyDriver:
    """Drives comfy-cli. Holds no global state; one instance per command invocation."""

    def __init__(self, config: Config, runner: Runner | None = None, opener: Opener | None = None):
        self.cfg = config
        self._runner = runner or _default_runner
        self._opener = opener or self._http_get
        self._launched_proc: subprocess.Popen | None = None

    # ---- binary resolution -------------------------------------------------
    def comfy_bin(self) -> str:
        if self.cfg.comfy_bin:
            return self.cfg.comfy_bin
        found = shutil.which("comfy")
        if found:
            return found
        # Fall back to a comfy alongside the running interpreter (same venv Scripts dir).
        exe = "comfy.exe" if os.name == "nt" else "comfy"
        candidate = os.path.join(os.path.dirname(sys.executable), exe)
        return candidate if os.path.exists(candidate) else "comfy"

    # ---- argv builders -----------------------------------------------------
    def run_argv(self, workflow_path: str) -> list[str]:
        return [
            self.comfy_bin(), "run",
            "--workflow", str(workflow_path),
            "--wait", "--json",
            "--host", self.cfg.host,
            "--port", str(self.cfg.port),
            "--timeout", str(self.cfg.per_event_timeout),
        ]

    def print_prompt_argv(self, workflow_path: str) -> list[str]:
        return [
            self.comfy_bin(), "run",
            "--workflow", str(workflow_path),
            "--print-prompt", "--json",
            "--host", self.cfg.host,
            "--port", str(self.cfg.port),
        ]

    def launch_argv(self) -> list[str]:
        argv = [
            self.cfg.comfyui_python, self.cfg.comfyui_main,
            "--listen", self.cfg.host,
            "--port", str(self.cfg.port),
            "--base-directory", self.cfg.comfyui_base_directory,
            "--user-directory", self.cfg.comfyui_user_dir,
            "--output-directory", self.cfg.comfyui_output_dir,
            "--input-directory", self.cfg.comfyui_input_dir,
        ]
        if self.cfg.extra_model_paths_config:
            argv += ["--extra-model-paths-config", self.cfg.extra_model_paths_config]
        argv += list(self.cfg.launch_extra_args)
        return argv

    # ---- server lifecycle --------------------------------------------------
    def _http_get(self, url: str, timeout: float = 3.0) -> tuple[int, bytes]:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - local http only
            return resp.status, resp.read()

    def probe(self) -> bool:
        url = f"http://{self.cfg.host}:{self.cfg.port}/system_stats"
        try:
            status, _ = self._opener(url, timeout=3.0)
        except Exception:
            return False
        return 200 <= status < 300

    def ensure_server(self) -> str:
        """Attach to a reachable server, or auto-launch one (keep-warm). Returns 'attached' or 'launched'."""
        if self.probe():
            return "attached"
        if self.cfg.attach_only or not self.cfg.auto_launch:
            raise errors.BackendUnavailableError(
                f"No ComfyUI reachable at {self.cfg.host}:{self.cfg.port} and auto-launch is disabled.",
                hint="Start ComfyUI, or enable auto-launch (auto_launch=true, attach_only=false).",
            )
        self._launch_background()
        if not self._wait_ready(self.cfg.ready_timeout):
            raise errors.BackendUnavailableError(
                f"Launched ComfyUI but it did not become ready within {self.cfg.ready_timeout}s.",
                hint="Check the ComfyUI logs, or raise ready_timeout in config.",
            )
        return "launched"

    def _launch_background(self) -> None:
        if not os.path.exists(self.cfg.comfyui_python):
            raise errors.BackendUnavailableError(
                f"ComfyUI Python interpreter not found: {self.cfg.comfyui_python}",
                hint="Set comfyui_python in config (CUW_COMFYUI_PYTHON).",
            )
        if not os.path.exists(self.cfg.comfyui_main):
            raise errors.BackendUnavailableError(
                f"ComfyUI entry point not found: {self.cfg.comfyui_main}",
                hint="Set comfyui_main in config (CUW_COMFYUI_MAIN).",
            )
        creationflags = 0
        if os.name == "nt":
            # New process group + detached so the server outlives this command (keep-warm).
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
        self._launched_proc = subprocess.Popen(  # noqa: S603
            self.launch_argv(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    def _wait_ready(self, timeout: int) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.probe():
                return True
            time.sleep(2.0)
        return False

    def stop(self) -> None:
        """Shut down only a server we launched, and only when keep-warm is off."""
        if self.cfg.keep_warm:
            return
        proc = self._launched_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    # ---- running -----------------------------------------------------------
    def run_workflow(self, workflow_path: str) -> RunResult:
        code, out, err = self._runner(self.run_argv(workflow_path))
        events = _parse_ndjson(out)
        envelope = _find_envelope(events)

        if envelope is None:
            tail = (err or out or "").strip()[-800:]
            low = tail.lower()
            if any(m in low for m in ("not running", "connection refused", "connection error", "refused")):
                raise errors.BackendUnavailableError(
                    "ComfyUI backend is unavailable.", details={"stderr": tail}
                )
            raise errors.InternalError(
                f"comfy run produced no result envelope (exit {code}).", details={"stderr": tail}
            )

        if not envelope.get("ok"):
            err_obj = envelope.get("error") or {}
            raise errors.from_comfy_error(
                err_obj.get("code"),
                err_obj.get("message", ""),
                err_obj.get("hint"),
                err_obj.get("details"),
            )

        data = envelope.get("data") or {}
        artifacts = self._extract_artifacts(data)
        if not artifacts:
            raise errors.WorkflowExecutionError(
                "Workflow completed but produced no output artifacts.",
                details={"prompt_id": data.get("prompt_id")},
            )
        return RunResult(
            artifacts=artifacts,
            prompt_id=data.get("prompt_id"),
            elapsed_seconds=data.get("elapsed_seconds"),
            envelope=envelope,
            events=events,
        )

    def capture_api_prompt(self, workflow_path: str) -> dict:
        """Run ``comfy run --print-prompt`` to get the converted API-format graph without executing."""
        code, out, err = self._runner(self.print_prompt_argv(workflow_path))
        events = _parse_ndjson(out)
        envelope = _find_envelope(events)
        if envelope is not None and not envelope.get("ok"):
            e = envelope.get("error") or {}
            raise errors.from_comfy_error(e.get("code"), e.get("message", ""), e.get("hint"), e.get("details"))
        for event in events:
            if event.get("type") == "prompt_preview":
                for key in ("prompt", "graph", "workflow"):
                    val = event.get(key)
                    if isinstance(val, dict) and val:
                        return val
                data = event.get("data")
                if isinstance(data, dict) and isinstance(data.get("prompt"), dict):
                    return data["prompt"]
        raise errors.InternalError(
            f"comfy run --print-prompt did not emit a prompt_preview (exit {code}).",
            details={"stderr": (err or "")[-500:]},
        )

    # ---- output resolution -------------------------------------------------
    def _extract_artifacts(self, data: dict) -> list[Artifact]:
        urls: list[str] = list(data.get("outputs") or [])
        by_node = data.get("outputs_by_node") or {}
        url_to_node: dict[str, str] = {}
        for node_id, node_urls in by_node.items():
            for u in node_urls or []:
                url_to_node.setdefault(u, node_id)

        artifacts: list[Artifact] = []
        seen: set[str] = set()
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            path = self._resolve_view_url(url)
            artifacts.append(
                Artifact(path=path, type=mime_for(path), url=url, node_id=url_to_node.get(url))
            )
        return artifacts

    def _resolve_view_url(self, url: str) -> str:
        """Resolve a ComfyUI /view?filename=..&subfolder=..&type=.. URL to an absolute local path."""
        query = parse_qs(urlparse(url).query)
        filename = (query.get("filename") or [""])[0]
        subfolder = (query.get("subfolder") or [""])[0]
        out_type = (query.get("type") or ["output"])[0]
        base = {
            "output": self.cfg.comfyui_output_dir,
            "temp": self.cfg.comfyui_temp_dir,
            "input": self.cfg.comfyui_input_dir,
        }.get(out_type, self.cfg.comfyui_output_dir)
        return os.path.normpath(os.path.join(base, subfolder, filename))
