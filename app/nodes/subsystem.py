from __future__ import annotations

from typing import Any, Mapping

from app.nodes.base import BaseNode


class BaseSubsystemNode(BaseNode):
    """Base class for nodes that adapt a child runtime into a parent workflow."""

    subsystem_type = "subsystem"

    def map_inputs(
        self,
        parent_state: Mapping[str, Any],
        input_map: Mapping[str, str],
    ) -> dict[str, Any]:
        """Map parent workflow paths to the child runtime's named inputs."""

        return self._map_values(
            parent_state,
            input_map,
            mapping_kind="input",
            source_name="parent workflow",
        )

    def map_outputs(
        self,
        subsystem_state: Mapping[str, Any],
        output_map: Mapping[str, str],
        *,
        source_name: str = "subsystem final state",
    ) -> dict[str, Any]:
        """Map child runtime paths to the parent node's named outputs."""

        return self._map_values(
            subsystem_state,
            output_map,
            mapping_kind="output",
            source_name=source_name,
        )

    def _map_values(
        self,
        data: Mapping[str, Any],
        value_map: Mapping[str, str],
        *,
        mapping_kind: str,
        source_name: str,
    ) -> dict[str, Any]:
        return {
            mapped_key: self._resolve_mapped_path(
                data,
                path,
                mapping_kind=mapping_kind,
                mapped_key=mapped_key,
                source_name=source_name,
            )
            for mapped_key, path in value_map.items()
        }

    def _resolve_mapped_path(
        self,
        data: Mapping[str, Any],
        path: str,
        *,
        mapping_kind: str,
        mapped_key: str,
        source_name: str,
    ) -> Any:
        value: Any = data
        for part in path.split("."):
            if not isinstance(value, Mapping) or part not in value:
                raise RuntimeError(
                    f"{self.subsystem_type} node '{self.config.id}' could not map {mapping_kind} "
                    f"'{mapped_key}': {source_name} path '{path}' was not found."
                )
            value = value[part]
        return value
