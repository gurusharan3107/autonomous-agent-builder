"""Graph-backed System Architecture generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autonomous_agent_builder.knowledge.evidence_graph import (
    build_shared_evidence_graph,
    render_blocking_doc,
)

from .base import BaseGenerator


class ArchitectureGenerator(BaseGenerator):
    """Generate the blocking System Architecture document from the shared graph."""

    def __init__(self, workspace_path: Path, output_path: Path | None = None):
        super().__init__(workspace_path, output_path=output_path)

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        del scope
        if self.output_path is None:
            raise RuntimeError("ArchitectureGenerator requires an output path for evidence artifacts.")
        graph = self.shared_graph or build_shared_evidence_graph(self.workspace_path, self.output_path)
        return render_blocking_doc(
            "system-architecture",
            graph,
            workspace_path=self.workspace_path,
            collection_path=self.output_path,
        )
