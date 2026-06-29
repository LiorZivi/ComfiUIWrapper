from comfywrap.core import errors


def test_server_not_running_maps_to_backend_unavailable():
    e = errors.from_comfy_error("server_not_running", "ComfyUI not running")
    assert isinstance(e, errors.BackendUnavailableError)
    assert e.exit_code == 9


def test_ws_timeout_maps_to_timeout():
    assert errors.from_comfy_error("ws_timeout", "server silent").exit_code == 11


def test_execution_error_maps_to_workflow_execution():
    assert errors.from_comfy_error("execution_error", "a node failed").exit_code == 10


def test_oom_message_overrides_to_oom():
    e = errors.from_comfy_error("execution_error", "CUDA out of memory. Tried to allocate 2GB")
    assert isinstance(e, errors.OutOfMemoryError)
    assert e.exit_code == 5


def test_prompt_rejected_maps_to_usage():
    assert errors.from_comfy_error("prompt_rejected", "value 5 is invalid").exit_code == 2


def test_unknown_node_in_validation_maps_to_unknown_capability():
    assert errors.from_comfy_error("prompt_rejected", "node type Foo not found").exit_code == 8


def test_workflow_not_found_maps_to_unknown_capability():
    assert errors.from_comfy_error("workflow_not_found", "missing").exit_code == 8


def test_gated_model_message_maps_to_gated():
    e = errors.from_comfy_error("execution_error", "HTTP 401 unauthorized: model is gated")
    assert e.exit_code == 6


def test_comfy_error_code_recorded_in_details():
    e = errors.from_comfy_error("ws_timeout", "x")
    assert e.details.get("comfy_error_code") == "ws_timeout"
