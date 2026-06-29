"""Capability registry keyed by (capability_id, model_id).

This is the single, modality-agnostic seam for future capabilities: each adapter
declares its own artifact type and parameter schema and self-registers here, so a
new video *or* non-video capability slots in without touching the core runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import errors


@dataclass
class CapabilityEntry:
    capability_id: str
    model_id: str
    adapter: object
    artifact_type: str
    template_ref: str
    expected_models: list = field(default_factory=list)


class Registry:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], CapabilityEntry] = {}

    def register(self, entry: CapabilityEntry) -> None:
        self._entries[(entry.capability_id, entry.model_id)] = entry

    def get(self, capability_id: str, model_id: str) -> CapabilityEntry:
        try:
            return self._entries[(capability_id, model_id)]
        except KeyError:
            raise errors.UnknownCapabilityError(
                f"Unknown capability/model: {capability_id}/{model_id}",
                hint="Run 'comfywrap capabilities' to list available models.",
            )

    def resolve_model(self, model_id: str) -> CapabilityEntry:
        for entry in self._entries.values():
            if entry.model_id == model_id:
                return entry
        raise errors.UnknownCapabilityError(
            f"Unknown model: {model_id}",
            hint="Run 'comfywrap capabilities' to list available models.",
        )

    def list(self) -> list[CapabilityEntry]:
        return list(self._entries.values())


# Process-wide registry; adapters populate it on import.
REGISTRY = Registry()
