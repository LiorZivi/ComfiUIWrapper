"""Process-level contract tests for the CLI, with the ``comfy`` subprocess mocked."""

import json

from comfywrap.core import cli, driver

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


def _attach(monkeypatch, out, code=0):
    monkeypatch.setattr(driver, "_default_runner", lambda argv: (code, out, ""))
    monkeypatch.setattr(driver.ComfyDriver, "probe", lambda self: True)


def test_generate_json_emits_single_envelope(tmp_path, monkeypatch, capsys):
    (tmp_path / "video").mkdir()
    (tmp_path / "video" / "LTX-2_00047_.mp4").write_bytes(b"vid")
    monkeypatch.setenv("CUW_COMFYUI_OUTPUT_DIR", str(tmp_path))
    _attach(monkeypatch, SUCCESS)

    rc = cli.main(["generate", "a cat in space", "--json", "--seed", "42"])
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["capability"] == "text_to_video"
    assert obj["model"] == "ltx2-t2v"
    assert obj["artifacts"][0]["path"].endswith("LTX-2_00047_.mp4")
    assert obj["artifacts"][0]["type"] == "video/mp4"
    assert obj["artifacts"][0]["metadata"]["seed"] == 42


def test_generate_human_final_line_is_absolute_path(tmp_path, monkeypatch, capsys):
    (tmp_path / "video").mkdir()
    (tmp_path / "video" / "LTX-2_00047_.mp4").write_bytes(b"vid")
    monkeypatch.setenv("CUW_COMFYUI_OUTPUT_DIR", str(tmp_path))
    _attach(monkeypatch, SUCCESS)

    rc = cli.main(["generate", "a cat", "--seed", "7"])
    assert rc == 0
    last = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()][-1]
    assert last.endswith("LTX-2_00047_.mp4")


def test_generate_backend_failure_returns_exit_9(monkeypatch, capsys):
    _attach(monkeypatch, FAIL_BACKEND, code=1)
    rc = cli.main(["generate", "x", "--json", "--seed", "1"])
    assert rc == 9
    obj = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert obj["error"]["code"] == 9


def test_capabilities_json(capsys):
    rc = cli.main(["capabilities", "--json"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["capabilities"][0]["model"] == "ltx2-t2v"


def test_unknown_model_returns_exit_8(monkeypatch, capsys):
    monkeypatch.setattr(driver.ComfyDriver, "probe", lambda self: True)
    rc = cli.main(["generate", "x", "--model", "nope", "--json"])
    assert rc == 8
