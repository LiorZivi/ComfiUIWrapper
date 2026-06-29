import os

import pytest

from comfywrap.core import errors
from comfywrap.core.config import Config
from comfywrap.core.driver import ComfyDriver

# Mirrors the real comfy-cli 1.11.1 success envelope (outputs are /view URLs).
SUCCESS = (
    '{"schema":"event/1","type":"queued","prompt_id":"p"}\n'
    '{"schema":"envelope/1","type":"envelope","ok":true,"command":"run","data":'
    '{"status":"completed","prompt_id":"p",'
    '"outputs":["http://127.0.0.1:8000/view?filename=LTX-2_00047_.mp4&subfolder=video&type=output"],'
    '"outputs_by_node":{"75":["http://127.0.0.1:8000/view?filename=LTX-2_00047_.mp4&subfolder=video&type=output"]},'
    '"elapsed_seconds":1.5},"error":null}'
)
FAIL_BACKEND = (
    '{"schema":"envelope/1","type":"envelope","ok":false,"command":"run","data":null,'
    '"error":{"code":"server_not_running","message":"ComfyUI not running"}}'
)
FAIL_OOM = (
    '{"schema":"envelope/1","type":"envelope","ok":false,"data":null,'
    '"error":{"code":"execution_error","message":"CUDA out of memory"}}'
)


def runner(out, code=0):
    return lambda argv: (code, out, "")


def test_run_success_resolves_local_path(tmp_path):
    cfg = Config(comfyui_output_dir=str(tmp_path))
    result = ComfyDriver(cfg, runner=runner(SUCCESS)).run_workflow("wf.json")
    assert result.artifacts[0].type == "video/mp4"
    assert result.artifacts[0].path == os.path.normpath(str(tmp_path / "video" / "LTX-2_00047_.mp4"))
    assert result.artifacts[0].node_id == "75"
    assert result.prompt_id == "p"
    assert result.elapsed_seconds == 1.5


def test_run_backend_failure_maps_to_exit_9():
    with pytest.raises(errors.BackendUnavailableError) as ei:
        ComfyDriver(Config(), runner=runner(FAIL_BACKEND, 1)).run_workflow("wf.json")
    assert ei.value.exit_code == 9


def test_run_oom_maps_to_exit_5():
    with pytest.raises(errors.OutOfMemoryError):
        ComfyDriver(Config(), runner=runner(FAIL_OOM, 1)).run_workflow("wf.json")


def test_run_no_envelope_is_internal_error():
    with pytest.raises(errors.ComfywrapError):
        ComfyDriver(Config(), runner=runner("garbage\n", 1)).run_workflow("wf.json")


def test_run_argv_shape():
    driver = ComfyDriver(Config(host="127.0.0.1", port=8000, per_event_timeout=900, comfy_bin="comfy"))
    argv = driver.run_argv("wf.json")
    assert argv[:4] == ["comfy", "run", "--workflow", "wf.json"]
    assert "--wait" in argv and "--json" in argv
    assert "8000" in argv and "900" in argv


def test_launch_argv_uses_base_directory():
    driver = ComfyDriver(Config(comfyui_python="py", comfyui_main="main.py",
                                comfyui_base_directory="BASE", extra_model_paths_config=None))
    argv = driver.launch_argv()
    assert argv[0] == "py" and argv[1] == "main.py"
    assert "--base-directory" in argv and "BASE" in argv


def _raise(*_a, **_k):
    raise OSError("refused")


def test_probe_true_and_false():
    assert ComfyDriver(Config(), opener=lambda url, timeout=3.0: (200, b"{}")).probe() is True
    assert ComfyDriver(Config(), opener=_raise).probe() is False
