"""CLI dispatcher: the ``comfywrap`` grammar, stdout/stderr discipline, and exit-code boundary.

Commands: ``doctor``, ``capabilities``, ``generate``. Global flags: ``--json``,
``--config``, ``-v/--verbose``, ``--version``. In ``--json`` mode exactly one JSON
object is written to stdout (success or error); diagnostics go to stderr. In human
mode the final stdout line is the absolute artifact path.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

from .. import __version__
from . import doctor as doctor_mod
from . import errors
from .config import load_config
from .driver import ComfyDriver
from .injection import write_temp_prompt
from .output import collect_and_write
from .registry import REGISTRY

# Importing the capabilities package self-registers every adapter.
import comfywrap.capabilities  # noqa: E402,F401

_DEFAULT_MODEL = "ltx2-t2v"


def _emit_json(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")


def _selected_model(argv: list[str]) -> str:
    """Peek at ``--model`` before argparse runs so the *selected* model contributes the
    ``generate`` surface — each adapter then declares only the flags it actually needs."""
    for index, token in enumerate(argv):
        if token == "--model" and index + 1 < len(argv):
            return argv[index + 1]
        if token.startswith("--model="):
            return token.split("=", 1)[1]
    return _DEFAULT_MODEL


def build_parser(argv: list[str] | None = None) -> argparse.ArgumentParser:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Global flags live on a parent parser so they are accepted both before and
    # after the subcommand (spec section 4.1). SUPPRESS keeps unspecified copies
    # from overwriting a value provided in the other position.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="Emit exactly one JSON object on stdout.")
    common.add_argument("--config", default=argparse.SUPPRESS,
                        help="Path to a config file (else ./comfywrap.toml or ./config.toml).")
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS,
                        help="Extra diagnostics on stderr.")

    parser = argparse.ArgumentParser(
        prog="comfywrap", parents=[common],
        description="Run ComfyUI workflows headlessly via comfy-cli.",
    )
    parser.add_argument("--version", action="version", version=f"comfywrap {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", parents=[common],
                   help="Verify GPU, comfy-cli, ComfyUI reachability, and model files.")
    sub.add_parser("capabilities", parents=[common], help="List registered capabilities and models.")

    gen = sub.add_parser("generate", parents=[common], help="Generate an artifact from a prompt.")
    gen.add_argument("--model", help=f"Model id (default: {_DEFAULT_MODEL}).")
    gen.add_argument("--output-dir", dest="output_dir", help="Directory to place the produced artifact.")
    # The *selected* capability's adapter contributes its own generation surface, so a
    # capability with extra flags (e.g. image_to_video's --image) declares only what it
    # needs and text_to_video is never polluted with flags it would ignore.
    try:
        REGISTRY.resolve_model(_selected_model(argv)).adapter.add_arguments(gen)
    except errors.ComfywrapError:
        # Unknown --model: fall back to the default surface so argparse can still parse;
        # cmd_generate re-resolves the model and raises the proper error (exit 8).
        try:
            REGISTRY.resolve_model(_DEFAULT_MODEL).adapter.add_arguments(gen)
        except errors.ComfywrapError:  # pragma: no cover - registry always has the default
            pass
    return parser


def _provenance(entry, model, params_dict, run_result, cfg, source_path, started_at, ended_at) -> dict:
    return {
        "capability": entry.capability_id,
        "model": model,
        "prompt": params_dict.get("prompt"),
        "negative": params_dict.get("negative"),
        "seed": params_dict.get("seed"),
        "resolved_params": params_dict,
        "workflow_template": entry.template_ref,
        "model_files": list(entry.expected_models),
        "prompt_id": run_result.prompt_id,
        "elapsed_seconds": run_result.elapsed_seconds,
        "output_filename": os.path.basename(source_path),
        "host": cfg.host,
        "port": cfg.port,
        "comfywrap_version": __version__,
        "started_at": started_at,
        "ended_at": ended_at,
    }


def cmd_generate(args, cfg, json_mode: bool) -> int:
    model = args.model or cfg.default_model or _DEFAULT_MODEL
    entry = REGISTRY.resolve_model(model)
    adapter = entry.adapter

    params = adapter.build_params(args)
    graph = adapter.prepare_prompt(params)
    tmp_path = write_temp_prompt(graph)

    driver = ComfyDriver(cfg)
    started_at = datetime.datetime.now().astimezone().isoformat()
    try:
        driver.ensure_server()
        result = driver.run_workflow(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        driver.stop()
    ended_at = datetime.datetime.now().astimezone().isoformat()

    primary = result.artifacts[0]
    provenance = _provenance(
        entry, model, adapter.resolved_params(params), result, cfg, primary.path, started_at, ended_at
    )
    final_path, _sidecar = collect_and_write(primary.path, args.output_dir or cfg.output_dir, provenance)

    artifacts = []
    for index, art in enumerate(result.artifacts):
        path = final_path if index == 0 else art.path
        artifacts.append(
            {
                "path": os.path.abspath(path),
                "type": art.type,
                "metadata": provenance if index == 0 else {},
            }
        )

    if json_mode:
        _emit_json({"capability": entry.capability_id, "model": model, "artifacts": artifacts})
    else:
        for art in artifacts:
            print(art["path"])
    return errors.EXIT_SUCCESS


def cmd_doctor(args, cfg, json_mode: bool) -> int:
    report = doctor_mod.run_doctor(cfg)
    if json_mode:
        _emit_json(report)
    else:
        for check in report["checks"]:
            mark = "OK" if check["ok"] else "XX"
            sys.stderr.write(f"[{mark}] {check['check']}: {check['detail']}\n")
        print("READY" if report["ready"] else "NOT READY")
    return errors.EXIT_SUCCESS if report["ready"] else errors.EXIT_INTERNAL


def cmd_capabilities(args, cfg, json_mode: bool) -> int:
    items = [
        {
            "capability": e.capability_id,
            "model": e.model_id,
            "artifact_type": e.artifact_type,
            "template": e.template_ref,
            "expected_models": e.expected_models,
        }
        for e in REGISTRY.list()
    ]
    if json_mode:
        _emit_json({"capabilities": items})
    else:
        for it in items:
            print(f"{it['capability']}  {it['model']}  -> {it['artifact_type']}")
    return errors.EXIT_SUCCESS


def _handle_error(err: errors.ComfywrapError, json_mode: bool, verbose: bool, exc: BaseException | None = None) -> None:
    if json_mode:
        _emit_json(
            {
                "error": {
                    "code": err.exit_code,
                    "kind": type(err).__name__,
                    "message": err.message,
                    "hint": err.hint,
                    "details": err.details,
                }
            }
        )
    else:
        sys.stderr.write(f"error: {err.message}\n")
        if err.hint:
            sys.stderr.write(f"hint: {err.hint}\n")
    if verbose and exc is not None:
        import traceback

        traceback.print_exception(exc)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(argv)
    args = parser.parse_args(argv)
    json_mode = bool(getattr(args, "json", False))
    verbose = bool(getattr(args, "verbose", False))

    try:
        cfg = load_config(getattr(args, "config", None))
        if args.command == "generate":
            return cmd_generate(args, cfg, json_mode)
        if args.command == "doctor":
            return cmd_doctor(args, cfg, json_mode)
        if args.command == "capabilities":
            return cmd_capabilities(args, cfg, json_mode)
        raise errors.UsageError(f"Unknown command: {args.command}")
    except errors.ComfywrapError as err:
        _handle_error(err, json_mode, verbose, exc=err)
        return err.exit_code
    except KeyboardInterrupt:
        sys.stderr.write("interrupted\n")
        return errors.EXIT_INTERNAL
    except Exception as exc:  # noqa: BLE001 - top-level safety net -> exit 1
        wrapped = errors.InternalError(f"Unexpected error: {exc}")
        _handle_error(wrapped, json_mode, verbose, exc=exc)
        return errors.EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
