"""Parameter injection: set typed values into an API-format prompt graph by stable role bindings.

A ``Binding`` maps a logical role (e.g. ``prompt``, ``seed``, ``width``) to one or
more node ids and an input key in the captured API template, so injection targets
node ``_meta.title``/role rather than relying on positional structure.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass

from . import errors


@dataclass(frozen=True)
class Binding:
    role: str
    node_ids: list[str]
    input_key: str
    cast: str = "raw"  # 'int' | 'float' | 'str' | 'raw'
    optional: bool = False


def _cast(value, kind: str):
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    if kind == "str":
        return str(value)
    return value


def inject(template: dict, values: dict, bindings: list[Binding]) -> dict:
    """Return a deep copy of ``template`` with bound ``values`` applied. Unbound values are ignored."""
    graph = copy.deepcopy(template)
    by_role = {b.role: b for b in bindings}
    for role, value in values.items():
        if value is None:
            continue
        binding = by_role.get(role)
        if binding is None:
            continue  # accepted-but-unbound (e.g. audio toggle for a template without one)
        for node_id in binding.node_ids:
            node = graph.get(node_id)
            if node is None:
                if binding.optional:
                    continue
                raise errors.InternalError(
                    f"Binding role '{role}' references missing node '{node_id}' in the template.",
                    hint="Re-capture the workflow template; node ids may have changed.",
                )
            node.setdefault("inputs", {})[binding.input_key] = _cast(value, binding.cast)
    return graph


def write_temp_prompt(graph: dict, directory: str | None = None) -> str:
    """Write the concrete prompt graph to a temp .json file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".api.json", prefix="comfywrap_", dir=directory)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(graph, fh)
    return path
