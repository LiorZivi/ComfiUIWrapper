"""Typed error taxonomy and the comfy-cli error/exit -> exit-code mapping (spec section 4.3 / 5).

Every failure class is a ``ComfywrapError`` subclass carrying a stable ``exit_code``
in the range 0-11. ``from_comfy_error`` translates a comfy-cli failure envelope
(``ok=false`` with ``error.code`` / ``error.message``) onto this taxonomy.
"""

from __future__ import annotations

# Exit codes (spec section 4.3).
EXIT_SUCCESS = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_GPU_STACK = 3
EXIT_NO_GPU = 4
EXIT_OOM = 5
EXIT_GATED_MODEL = 6
EXIT_NETWORK = 7
EXIT_UNKNOWN_CAPABILITY = 8
EXIT_BACKEND_UNAVAILABLE = 9
EXIT_WORKFLOW_EXECUTION = 10
EXIT_TIMEOUT = 11


class ComfywrapError(Exception):
    """Base class for every typed failure. Carries a stable exit code and an actionable message."""

    exit_code = EXIT_INTERNAL

    def __init__(self, message: str, hint: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = dict(details or {})


class InternalError(ComfywrapError):
    exit_code = EXIT_INTERNAL


class UsageError(ComfywrapError):
    exit_code = EXIT_USAGE


class GpuStackError(ComfywrapError):
    exit_code = EXIT_GPU_STACK


class NoGpuError(ComfywrapError):
    exit_code = EXIT_NO_GPU


class OutOfMemoryError(ComfywrapError):
    exit_code = EXIT_OOM


class GatedModelError(ComfywrapError):
    exit_code = EXIT_GATED_MODEL


class NetworkError(ComfywrapError):
    exit_code = EXIT_NETWORK


class UnknownCapabilityError(ComfywrapError):
    exit_code = EXIT_UNKNOWN_CAPABILITY


class BackendUnavailableError(ComfywrapError):
    exit_code = EXIT_BACKEND_UNAVAILABLE


class WorkflowExecutionError(ComfywrapError):
    exit_code = EXIT_WORKFLOW_EXECUTION


class WaitTimeoutError(ComfywrapError):
    exit_code = EXIT_TIMEOUT


# Substring markers used to refine a generic failure into a more specific class.
_OOM_MARKERS = (
    "out of memory",
    "cuda out of memory",
    "outofmemory",
    "cublas_status_alloc_failed",
    "not enough memory",
    "failed to allocate",
)
_GATED_MARKERS = (
    "gated",
    "unauthorized",
    "http 401",
    "http 403",
    " 401 ",
    " 403 ",
    "access token",
    "requires authentication",
    "must be authenticated",
)
_NETWORK_MARKERS = (
    "download",
    "failed to fetch",
    "name resolution",
    "temporary failure in name resolution",
    "max retries exceeded",
)
_UNKNOWN_NODE_MARKERS = ("not found", "unknown", "does not exist", "no such", "unrecognized")

# comfy-cli error.code -> our error class (spec section 5).
_CODE_MAP: dict[str, type[ComfywrapError]] = {
    "server_not_running": BackendUnavailableError,
    "connection_error": BackendUnavailableError,
    "connection_lost": BackendUnavailableError,
    "ws_disconnected": BackendUnavailableError,
    "object_info_unavailable": BackendUnavailableError,
    "ws_timeout": WaitTimeoutError,
    "timeout": WaitTimeoutError,
    "execution_error": WorkflowExecutionError,
    "prompt_rejected": UsageError,
    "validation_error": UsageError,
    "client_error": UsageError,
    "workflow_invalid_json": UsageError,
    "workflow_read_error": UsageError,
    "workflow_not_found": UnknownCapabilityError,
    "workflow_not_api_format": UnknownCapabilityError,
    "workflow_empty": UnknownCapabilityError,
    "conversion_error": UnknownCapabilityError,
    "conversion_crash": UnknownCapabilityError,
    "server_error": InternalError,
    "invalid_response": InternalError,
    "cancelled": InternalError,
}


def from_comfy_error(
    code: str | None,
    message: str = "",
    hint: str | None = None,
    details: dict | None = None,
) -> ComfywrapError:
    """Map a comfy-cli failure envelope onto the comfywrap exit-code taxonomy."""
    msg = message or code or "comfy-cli reported a failure"
    low = (message or "").lower()
    details = dict(details or {})
    details.setdefault("comfy_error_code", code)

    if any(m in low for m in _OOM_MARKERS):
        return OutOfMemoryError(msg, hint=hint, details=details)
    if any(m in low for m in _GATED_MARKERS):
        return GatedModelError(msg, hint=hint, details=details)

    cls = _CODE_MAP.get(code or "", InternalError)
    # A network failure dressed up as a generic execution/server error.
    if cls in (WorkflowExecutionError, InternalError) and any(m in low for m in _NETWORK_MARKERS):
        cls = NetworkError
    # A validation rejection that names an unknown node/model is really an unknown-id error.
    if cls is UsageError and any(m in low for m in _UNKNOWN_NODE_MARKERS):
        cls = UnknownCapabilityError

    return cls(msg, hint=hint, details=details)
