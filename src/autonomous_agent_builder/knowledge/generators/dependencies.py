"""Graph-backed dependencies generator."""

from __future__ import annotations

from autonomous_agent_builder.knowledge.evidence_graph import (
    build_shared_evidence_graph,
    render_blocking_doc,
)

from .base import BaseGenerator


class DependenciesGenerator(BaseGenerator):
    """Generate the blocking Dependencies document from the shared graph."""

    def generate(self, scope: str = "full") -> dict[str, object] | None:
        del scope
        if self.output_path is None:
            raise RuntimeError("DependenciesGenerator requires an output path for evidence artifacts.")
        graph = self.shared_graph or build_shared_evidence_graph(self.workspace_path, self.output_path)
        return render_blocking_doc(
            "dependencies",
            graph,
            workspace_path=self.workspace_path,
            collection_path=self.output_path,
        )
