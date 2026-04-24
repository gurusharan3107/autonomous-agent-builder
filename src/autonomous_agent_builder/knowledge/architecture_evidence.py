"""Deterministic evidence graph and manifest support for System Architecture docs."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .proof_contract import (
    Citation,
    Claim,
    compute_dependency_hash,
    git_head,
    line_range_for_match,
    load_evidence_manifest,
    verify_evidence_manifest,
    write_evidence_manifest,
)

EXTRACTOR_VERSION = "system-architecture-mvp-v2"
SYSTEM_ARCHITECTURE_SLUG = "system-architecture"
SYSTEM_ARCHITECTURE_TITLE = "System Architecture"
MANIFEST_RELATIVE_PATH = ".evidence/system-architecture.json"
GRAPH_DB_RELATIVE_PATH = ".evidence/system-architecture.sqlite3"

_ROUTE_FILE_LABELS = {
    "dashboard_api.py": "dashboard read models",
    "dispatch.py": "task dispatch entrypoints",
    "features.py": "feature and task APIs",
    "gates.py": "gate and approval APIs",
    "knowledge.py": "knowledge retrieval APIs",
    "memory_api.py": "memory retrieval APIs",
    "onboarding.py": "onboarding control APIs",
    "projects.py": "project CRUD APIs",
}

@dataclass(frozen=True)
class GraphNode:
    key: str
    kind: str
    label: str
    citation: Citation
    metadata: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str
    metadata: dict[str, Any]


class ArchitectureEvidencePlanner:
    """Build the evidence graph, manifest, and markdown for the pilot doc."""

    def __init__(self, workspace_path: Path, collection_path: Path):
        self.workspace_path = workspace_path.resolve()
        self.collection_path = collection_path.resolve()
        self.evidence_root = self.collection_path / ".evidence"
        self.manifest_path = self.collection_path / MANIFEST_RELATIVE_PATH
        self.graph_db_path = self.collection_path / GRAPH_DB_RELATIVE_PATH
        self._node_index: dict[str, GraphNode] = {}

    def build(self) -> dict[str, Any]:
        self.evidence_root.mkdir(parents=True, exist_ok=True)

        nodes = self._collect_nodes()
        edges = self._collect_edges(nodes)
        claims = self._collect_claims(nodes)
        dependencies = self._dependencies_from_claims(claims)
        dependency_hash = compute_dependency_hash(self.workspace_path, dependencies)
        source_commit = git_head(self.workspace_path)

        self._write_graph(nodes, edges, dependencies)
        _manifest_rel_path, dependency_hash, _manifest = write_evidence_manifest(
            workspace_path=self.workspace_path,
            collection_path=self.collection_path,
            doc_slug=SYSTEM_ARCHITECTURE_SLUG,
            claims=claims,
            dependencies=dependencies,
            unresolved_claims=[],
            contradicted_claims=[],
            extractor_version=EXTRACTOR_VERSION,
            source_commit=source_commit,
            extra={
                "nodes": [
                    {
                        "key": node.key,
                        "kind": node.kind,
                        "label": node.label,
                        "citation": node.citation.to_dict(),
                        "metadata": node.metadata,
                    }
                    for node in nodes
                ],
                "edges": [
                    {
                        "source": edge.source,
                        "target": edge.target,
                        "kind": edge.kind,
                        "metadata": edge.metadata,
                    }
                    for edge in edges
                ],
            },
        )

        verification = verify_evidence_manifest(self.workspace_path, self.manifest_path)
        if not verification["valid"]:
            issue_text = "; ".join(verification["issues"][:5])
            raise RuntimeError(f"System architecture evidence verification failed: {issue_text}")

        markdown = self._render_markdown(claims)
        return {
            "title": SYSTEM_ARCHITECTURE_TITLE,
            "doc_type": "system-docs",
            "content": markdown,
            "tags": ["architecture", "design", "runtime", "system-docs", "seed"],
            "card_summary": (
                "Dashboard, CLI, runtimes, orchestration, and local knowledge fit together "
                "into one repo-owned system."
            ),
            "detail_summary": (
                "Gives users a product-level system view, adds a runtime diagram, and "
                "preserves an agent-oriented change map with file-and-line-backed proof."
            ),
            "verified": True,
            "authoritative": True,
            "evidence_manifest": MANIFEST_RELATIVE_PATH,
            "source_commit": source_commit,
            "extractor_version": EXTRACTOR_VERSION,
            "dependency_hash": dependency_hash,
            "preserve_content": True,
        }

    def _collect_nodes(self) -> list[GraphNode]:
        nodes = [
            self._node(
                "component:api-runtime",
                "component",
                "API runtime",
                "src/autonomous_agent_builder/api/app.py",
                r"def create_app",
                {"role": "FastAPI app assembly and route registration"},
            ),
            self._node(
                "component:embedded-server",
                "component",
                "Embedded server",
                "src/autonomous_agent_builder/embedded/server/app.py",
                r"def create_app",
                {"role": "Local dashboard-serving FastAPI app"},
            ),
            self._node(
                "component:dashboard-frontend",
                "component",
                "Dashboard frontend",
                "frontend/src/App.tsx",
                r"function App\(|<Routes>|const NAV_ITEMS",
                {"role": "React SPA entry and route tree"},
            ),
            self._node(
                "component:cli",
                "entrypoint",
                "Builder CLI",
                "src/autonomous_agent_builder/cli/main.py",
                r"app = typer\.Typer",
                {"role": "Operator CLI entry and subcommand registration"},
            ),
            self._node(
                "component:orchestrator",
                "boundary",
                "Deterministic orchestrator",
                "src/autonomous_agent_builder/orchestrator/orchestrator.py",
                r"class Orchestrator",
                {"role": "Task-status-driven SDLC phase routing"},
            ),
            self._node(
                "component:onboarding",
                "boundary",
                "Onboarding pipeline",
                "src/autonomous_agent_builder/onboarding.py",
                r"PHASES|def start_onboarding",
                {"role": "Repo bootstrap and KB extraction lifecycle"},
            ),
            self._node(
                "component:agents",
                "component",
                "Agent runtime",
                "src/autonomous_agent_builder/agents/definitions.py",
                r"model\s*=",
                {"role": "Agent definitions, prompts, and model selection"},
            ),
            self._node(
                "component:knowledge",
                "component",
                "Knowledge pipeline",
                "src/autonomous_agent_builder/knowledge/extractor.py",
                r"class KnowledgeExtractor",
                {"role": "Reverse-engineering extraction and normalization"},
            ),
            self._node(
                "component:publisher",
                "component",
                "Knowledge publisher",
                "src/autonomous_agent_builder/knowledge/publisher.py",
                r"def publish_document",
                {"role": "Single-writer local KB publication"},
            ),
            self._node(
                "component:persistence",
                "data_surface",
                "Persistence layer",
                "src/autonomous_agent_builder/db/session.py",
                r"Session|engine|get_session",
                {"role": "Database session and engine wiring"},
            ),
            self._node(
                "component:data-models",
                "data_surface",
                "Database models",
                "src/autonomous_agent_builder/db/models.py",
                r"class ",
                {"role": "Persisted entities and workflow state"},
            ),
            self._node(
                "component:config",
                "config_surface",
                "Settings contract",
                "src/autonomous_agent_builder/config.py",
                r"class AgentSettings",
                {"role": "Nested BaseSettings env-prefix contract"},
            ),
        ]

        nodes.extend(self._route_nodes())
        nodes.extend(self._config_prefix_nodes())
        return nodes

    def _route_nodes(self) -> list[GraphNode]:
        route_dir = self.workspace_path / "src" / "autonomous_agent_builder" / "api" / "routes"
        nodes: list[GraphNode] = []
        for route_file in sorted(route_dir.glob("*.py")):
            if route_file.name == "__init__.py":
                continue
            rel_path = _relative_path(self.workspace_path, route_file)
            label = _ROUTE_FILE_LABELS.get(route_file.name, route_file.stem.replace("_", " "))
            citation = _line_span(
                route_file,
                r"router\s*=\s*APIRouter|@router\.(get|post|put|delete)",
            )
            node = GraphNode(
                key=f"integration:{route_file.stem}",
                kind="integration",
                label=label,
                citation=citation._replace_path(rel_path),
                metadata={"path": rel_path},
            )
            self._node_index[node.key] = node
            nodes.append(node)
        return nodes

    def _config_prefix_nodes(self) -> list[GraphNode]:
        config_path = self.workspace_path / "src" / "autonomous_agent_builder" / "config.py"
        content = config_path.read_text(encoding="utf-8")
        nodes: list[GraphNode] = []
        for match in re.finditer(
            r"class\s+(\w+)\(BaseSettings\):[\s\S]*?model_config\s*=\s*\{\"env_prefix\":\s*\"([A-Z_]+)\"",
            content,
        ):
            class_name, prefix = match.group(1), match.group(2)
            line_start, line_end = line_range_for_match(content, match.start(), match.end())
            citation = Citation(
                path=_relative_path(self.workspace_path, config_path),
                line_start=line_start,
                line_end=line_end,
                kind="config_surface",
            )
            node = GraphNode(
                key=f"config:{prefix.rstrip('_').lower()}",
                kind="config_surface",
                label=f"{class_name} ({prefix})",
                citation=citation,
                metadata={"prefix": prefix, "class_name": class_name},
            )
            self._node_index[node.key] = node
            nodes.append(node)
        return nodes

    def _collect_edges(self, nodes: list[GraphNode]) -> list[GraphEdge]:
        edges = [
            GraphEdge(
                source="component:dashboard-frontend",
                target="component:api-runtime",
                kind="calls",
                metadata={"reason": "SPA and dashboard APIs share the main FastAPI runtime"},
            ),
            GraphEdge(
                source="component:cli",
                target="component:knowledge",
                kind="invokes",
                metadata={"reason": "builder knowledge extract and validate live under the root CLI"},
            ),
            GraphEdge(
                source="component:api-runtime",
                target="component:knowledge",
                kind="serves",
                metadata={"reason": "Knowledge and memory retrieval routes are mounted under /api"},
            ),
            GraphEdge(
                source="component:api-runtime",
                target="component:persistence",
                kind="persists_via",
                metadata={"reason": "API routes depend on DB sessions and persisted models"},
            ),
            GraphEdge(
                source="component:onboarding",
                target="component:knowledge",
                kind="extracts",
                metadata={"reason": "Onboarding blocks on KB extraction before ready state"},
            ),
            GraphEdge(
                source="component:orchestrator",
                target="component:agents",
                kind="dispatches_to",
                metadata={"reason": "Orchestrator selects agent definitions by task phase"},
            ),
            GraphEdge(
                source="component:knowledge",
                target="component:publisher",
                kind="writes_via",
                metadata={"reason": "Extraction normalizes docs before single-writer publish"},
            ),
        ]
        known_keys = {node.key for node in nodes}
        return [
            edge
            for edge in edges
            if edge.source in known_keys and edge.target in known_keys
        ]

    def _collect_claims(self, nodes: list[GraphNode]) -> list[Claim]:
        api_runtime = self._node_index["component:api-runtime"].citation
        embedded_server = self._node_index["component:embedded-server"].citation
        dashboard_frontend = self._node_index["component:dashboard-frontend"].citation
        builder_cli = self._node_index["component:cli"].citation
        orchestrator = self._node_index["component:orchestrator"].citation
        onboarding = self._node_index["component:onboarding"].citation
        agents = self._node_index["component:agents"].citation
        knowledge = self._node_index["component:knowledge"].citation
        publisher = self._node_index["component:publisher"].citation
        persistence = self._node_index["component:persistence"].citation
        data_models = self._node_index["component:data-models"].citation
        config = self._node_index["component:config"].citation

        route_nodes = [
            self._node_index[key]
            for key in sorted(self._node_index)
            if key.startswith("integration:")
        ]
        config_nodes = [
            self._node_index[key]
            for key in sorted(self._node_index)
            if key.startswith("config:")
        ]

        claims: list[Claim] = [
            Claim(
                section="Overview",
                text=(
                    "This repository is an autonomous SDLC control plane: it onboards a "
                    "repo, seeds work items, runs agent-backed delivery phases, and "
                    "exposes the resulting system state through a dashboard, CLI, and "
                    "local knowledge base."
                ),
                citations=(builder_cli, orchestrator, onboarding, knowledge),
            ),
            Claim(
                section="Overview",
                text=(
                    "The runtime is split into a main FastAPI app and a repo-local "
                    "embedded server. The main app serves the API and SPA, while the "
                    "embedded server serves the local dashboard against `.agent-builder` "
                    "state for day-to-day operation."
                ),
                citations=(api_runtime, embedded_server, dashboard_frontend),
            ),
            Claim(
                section="User mental model",
                text=(
                    "A user should think of the system in four layers: onboarding "
                    "prepares repo-local state, the board and agent pages expose current "
                    "work, approvals pause automation for human decisions, and "
                    "knowledge or memory explain what the system knows about the repo."
                ),
                citations=(dashboard_frontend, onboarding, orchestrator, knowledge),
            ),
            Claim(
                section="User mental model",
                text=(
                    "The dashboard is a control surface, not the execution engine. It "
                    "reads task, approval, onboarding, knowledge, and memory state that "
                    "is produced elsewhere in the system."
                ),
                citations=(dashboard_frontend, api_runtime, embedded_server, persistence, data_models),
            ),
            Claim(
                section="How work moves through the system",
                text=(
                    "Onboarding is the first gate. It prepares `.agent-builder` state, "
                    "seeds the initial project records, and generates the first local "
                    "knowledge set so the dashboard has something concrete to show."
                ),
                citations=(onboarding, persistence, knowledge),
            ),
            Claim(
                section="How work moves through the system",
                text=(
                    "After onboarding, the board reflects task state rather than "
                    "controlling it directly. The orchestrator reads task status, "
                    "dispatches the next phase, records results, and pauses when "
                    "approvals or failures require human intervention."
                ),
                citations=(orchestrator, data_models, dashboard_frontend),
            ),
            Claim(
                section="How work moves through the system",
                text=(
                    "Knowledge and memory are supporting surfaces. They help the user "
                    "understand the current system and help agents retrieve bounded "
                    "context before making changes."
                ),
                citations=(knowledge, builder_cli),
            ),
            Claim(
                section="Boundaries",
                text=(
                    "Presentation lives in the SPA plus the two serving runtimes. "
                    "Those surfaces own navigation and route contracts."
                ),
                citations=(api_runtime, embedded_server, dashboard_frontend),
            ),
            Claim(
                section="Boundaries",
                text=(
                    "Execution control stays outside the UI. Onboarding prepares the "
                    "repo, and the orchestrator plus agents execute the phases."
                ),
                citations=(orchestrator, onboarding, agents),
            ),
            Claim(
                section="Boundaries",
                text=(
                    "Knowledge is separate. Extraction generates docs, the publisher is "
                    "the single writer, and retrieval routes expose knowledge or memory."
                ),
                citations=(
                    knowledge,
                    publisher,
                    *tuple(
                        node.citation
                        for node in route_nodes
                        if node.key in {"integration:knowledge", "integration:memory_api"}
                    ),
                ),
            ),
            Claim(
                section="Boundaries",
                text=(
                    "Persistence and configuration stay separate through DB session or model code and nested settings classes."
                ),
                citations=(persistence, data_models, config, *tuple(node.citation for node in config_nodes)),
            ),
            Claim(
                section="Invariants",
                text=(
                    "Task status is the dispatch contract; phase changes belong in the orchestrator, not hidden in prompts."
                ),
                citations=(orchestrator,),
            ),
            Claim(
                section="Invariants",
                text=(
                    "Local KB bytes stay single-writer through extraction and the builder publisher."
                ),
                citations=(knowledge, publisher),
            ),
            Claim(
                section="Invariants",
                text=(
                    "Runtime settings stay centralized in prefixed BaseSettings classes before API, agent, or gate code consumes them."
                ),
                citations=(config, *tuple(node.citation for node in config_nodes)),
            ),
            Claim(
                section="Evidence",
                text=(
                    "The system separates presentation, execution, persistence, and "
                    "knowledge clearly enough that each user-facing surface maps to a "
                    "small number of internal owners instead of one giant runtime blob. "
                    "That separation is what makes the dashboard readable, the CLI "
                    "useful, and the architecture explainable."
                ),
                citations=(api_runtime, embedded_server, orchestrator, persistence, knowledge),
            ),
            Claim(
                section="Evidence",
                text=(
                    "The local knowledge base is part of the product, not an external "
                    "wiki. That is why the dashboard, CLI, generator, and publisher all "
                    "share the same repo-local collection."
                ),
                citations=(knowledge, publisher, builder_cli),
            ),
            Claim(
                section="Proof for agents",
                text=(
                    "The main API runtime mounts project, feature, gate, dispatch, "
                    "dashboard, onboarding, knowledge, and memory route families under "
                    "`/api`, while the embedded server exposes agent, dashboard, "
                    "feature, task, gate, stream, project, KB, and memory routers."
                ),
                citations=(api_runtime, embedded_server, *tuple(node.citation for node in route_nodes)),
            ),
            Claim(
                section="Proof for agents",
                text=(
                    "Persistence is split between database wiring and model "
                    "declarations. API and orchestration layers consume that state "
                    "through the session module and SQLAlchemy models rather than "
                    "embedding data contracts directly in route files."
                ),
                citations=(persistence, data_models, api_runtime, orchestrator),
            ),
            Claim(
                section="Proof for agents",
                text=(
                    "Configuration is repo-wide, not per-surface. `DB_`, `AGENT_`, "
                    "`GATE_`, and `HARNESS_` prefixes define the knobs that feed "
                    "database selection, model policy, retry timeouts, and "
                    "harnessability thresholds."
                ),
                citations=(config, *tuple(node.citation for node in config_nodes)),
            ),
            Claim(
                section="Agent change map",
                text=(
                    "UI or route-contract changes need the dashboard route tree, the "
                    "JSON and SSE APIs each page calls, and the task or approval "
                    "payloads those routes expose."
                ),
                citations=(
                    dashboard_frontend,
                    api_runtime,
                    embedded_server,
                    *tuple(node.citation for node in route_nodes),
                ),
            ),
            Claim(
                section="Agent change map",
                text=(
                    "Workflow-automation changes need the task status machine, "
                    "approval-gate transitions, gate feedback loop, and onboarding "
                    "phase records because those determine what the system can do "
                    "without a human."
                ),
                citations=(orchestrator, onboarding, data_models),
            ),
            Claim(
                section="Agent change map",
                text=(
                    "Knowledge changes need the seed system-doc generator, the "
                    "single-writer publisher, the document contract, and the retrieval "
                    "routes because the user-facing doc and agent-facing retrieval "
                    "slice are two shapes over the same local KB."
                ),
                citations=(
                    knowledge,
                    publisher,
                    self._citation_for_path(
                        "src/autonomous_agent_builder/knowledge/document_spec.py",
                        "DOC_TYPE_SECTION_GUIDANCE|User vs Agent Retrieval|Reverse-engineering",
                    ),
                    *tuple(
                        node.citation
                        for node in route_nodes
                        if node.key in {"integration:knowledge", "integration:memory_api"}
                    ),
                ),
            ),
            Claim(
                section="Change guidance",
                text=(
                    "For user-facing changes, pick the owning product surface first, "
                    "update that API or UI layer, then regenerate this architecture doc."
                ),
                citations=(api_runtime, dashboard_frontend, *tuple(node.citation for node in route_nodes)),
            ),
            Claim(
                section="Change guidance",
                text=(
                    "For agent or KB changes, inspect task states, approvals, route "
                    "payloads, and the KB contract first; then rerun `builder knowledge "
                    "extract --force --doc system-architecture --json` and `builder knowledge "
                    "validate --no-use-agent`."
                ),
                citations=(
                    orchestrator,
                    onboarding,
                    agents,
                    self._citation_for_path("src/autonomous_agent_builder/knowledge/architecture_evidence.py", "class ArchitectureEvidencePlanner"),
                    self._citation_for_path("src/autonomous_agent_builder/knowledge/quality_gate.py", "class KnowledgeQualityGate"),
                ),
            ),
        ]
        return claims

    def _render_markdown(self, claims: list[Claim]) -> str:
        lines = [f"# {SYSTEM_ARCHITECTURE_TITLE}", ""]
        for section in (
            "Overview",
            "User mental model",
            "How work moves through the system",
            "Runtime diagram",
            "Lifecycle diagram",
            "Boundaries",
            "Invariants",
            "Agent change map",
            "Evidence",
            "Proof for agents",
            "Change guidance",
        ):
            lines.append(f"## {section}")
            lines.append("")
            if section == "Runtime diagram":
                lines.extend(self._render_runtime_diagram())
                lines.append("")
                continue
            if section == "Lifecycle diagram":
                lines.extend(self._render_lifecycle_diagram())
                lines.append("")
                continue
            if section == "Agent change map":
                section_claims = [claim for claim in claims if claim.section == section]
                for claim in section_claims:
                    lines.append(f"- {claim.text}")
                lines.append("")
                lines.extend(self._render_agent_change_map())
                lines.append("")
                continue
            section_claims = [claim for claim in claims if claim.section == section]
            for claim in section_claims:
                if section == "Proof for agents":
                    refs = ", ".join(citation.inline_ref() for citation in claim.citations)
                    lines.append(f"- {claim.text} ({refs})")
                else:
                    lines.append(f"- {claim.text}")
            lines.append("")
        return "\n".join(lines).strip()

    def _render_runtime_diagram(self) -> list[str]:
        return [
            "```mermaid",
            "flowchart LR",
            '    User["Operator"] --> SPA["React dashboard"]',
            '    User --> CLI["builder CLI"]',
            '    SPA --> MainAPI["Main API runtime"]',
            '    SPA --> Embedded["Embedded server"]',
            '    CLI --> MainAPI',
            '    CLI --> KB["Knowledge pipeline"]',
            '    MainAPI --> DB["Project state and workflow records"]',
            '    Embedded --> DB',
            '    MainAPI --> Orch["Deterministic orchestrator"]',
            '    Orch --> Agents["Agent runner and definitions"]',
            '    Orch --> Gates["Quality gates and approvals"]',
            '    Onboarding["Onboarding pipeline"] --> DB',
            '    Onboarding --> KB',
            '    KB --> LocalDocs[".agent-builder knowledge"]',
            "```",
            "",
            "The diagram is intentionally product-oriented: it shows which surfaces a "
            "user touches, which runtimes serve them, and which internal subsystems "
            "actually move work or knowledge.",
        ]

    def _render_lifecycle_diagram(self) -> list[str]:
        return [
            "```mermaid",
            "flowchart LR",
            '    Repo["Repository"] --> Onboard["Onboarding"]',
            '    Onboard --> Seed["Project and task seed"]',
            '    Seed --> Board["Board and agent surfaces"]',
            '    Board --> Dispatch["Orchestrator dispatch"]',
            '    Dispatch --> Work["Agent phase execution"]',
            '    Work --> Gates["Quality gates"]',
            '    Gates --> Review["Approval or review"]',
            '    Review --> Done["Done or next phase"]',
            '    Onboard --> KB["Initial knowledge generation"]',
            '    Work --> KB',
            '    KB --> UserRead["User understanding"]',
            '    KB --> AgentRead["Agent retrieval"]',
            "```",
            "",
            "This flow is closer to the user journey: it shows how a repository "
            "becomes a managed system and where knowledge is generated or reused.",
        ]

    def _render_agent_change_map(self) -> list[str]:
        return [
            "| Change area | Owning surfaces | Data an agent should inspect first |",
            "| --- | --- | --- |",
            (
                "| Dashboard UX or page behavior | `frontend/src/App.tsx`, page "
                "components, `api/app.py`, embedded server routes | Current route "
                "tree, page fetches, SSE streams, task or approval payloads |"
            ),
            (
                "| Workflow phase behavior | `orchestrator/orchestrator.py`, "
                "`agents/definitions.py`, gate handlers, task models | Task status "
                "lifecycle, gate outcomes, approval transitions, runner inputs and "
                "outputs |"
            ),
            (
                "| Onboarding and repo bootstrap | `onboarding.py`, onboarding API "
                "routes, `.agent-builder` state | Phase records, seeded DB entities, "
                "KB extraction status, archive behavior |"
            ),
            (
                "| Knowledge generation and retrieval | `knowledge/extractor.py`, "
                "`knowledge/architecture_evidence.py`, `knowledge/publisher.py`, KB "
                "API routes | KB contract, local collection layout, retrieval "
                "summaries, validation and freshness signals |"
            ),
            (
                "| Persistence or config | `db/session.py`, `db/models.py`, "
                "`config.py` | Entity relationships, repo-local DB path or URL, "
                "env-prefix settings, runtime assumptions |"
            ),
        ]

    def _node(
        self,
        key: str,
        kind: str,
        label: str,
        relative_path: str,
        pattern: str,
        metadata: dict[str, Any],
    ) -> GraphNode:
        citation = self._citation_for_path(relative_path, pattern, kind=kind)
        node = GraphNode(
            key=key,
            kind=kind,
            label=label,
            citation=citation,
            metadata={"path": relative_path, **metadata},
        )
        self._node_index[key] = node
        return node

    def _citation_for_path(
        self,
        relative_path: str,
        pattern: str,
        *,
        kind: str = "component",
    ) -> Citation:
        abs_path = self.workspace_path / relative_path
        span = _line_span(abs_path, pattern)
        return Citation(
            path=relative_path,
            line_start=span.line_start,
            line_end=span.line_end,
            kind=kind,
        )

    def _dependencies_from_claims(self, claims: list[Claim]) -> list[str]:
        return sorted({citation.path for claim in claims for citation in claim.citations})

    def _write_graph(
        self,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
        dependencies: list[str],
    ) -> None:
        connection = sqlite3.connect(self.graph_db_path)
        try:
            cursor = connection.cursor()
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    key TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL,
                    path TEXT NOT NULL,
                    line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence_spans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS edges (
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS doc_dependencies (
                    doc_slug TEXT NOT NULL,
                    path TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                );
                DELETE FROM nodes;
                DELETE FROM evidence_spans;
                DELETE FROM edges;
                DELETE FROM doc_dependencies;
                """
            )
            cursor.executemany(
                """
                INSERT INTO nodes (key, kind, label, path, line_start, line_end, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        node.key,
                        node.kind,
                        node.label,
                        node.citation.path,
                        node.citation.line_start,
                        node.citation.line_end,
                        json.dumps(node.metadata, sort_keys=True),
                    )
                    for node in nodes
                ],
            )
            cursor.executemany(
                """
                INSERT INTO evidence_spans (owner_key, kind, path, line_start, line_end)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        node.key,
                        node.citation.kind,
                        node.citation.path,
                        node.citation.line_start,
                        node.citation.line_end,
                    )
                    for node in nodes
                ],
            )
            cursor.executemany(
                """
                INSERT INTO edges (source, target, kind, metadata_json)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (edge.source, edge.target, edge.kind, json.dumps(edge.metadata, sort_keys=True))
                    for edge in edges
                ],
            )
            cursor.executemany(
                """
                INSERT INTO doc_dependencies (doc_slug, path, content_hash)
                VALUES (?, ?, ?)
                """,
                [
                    (
                        SYSTEM_ARCHITECTURE_SLUG,
                        dependency,
                        _content_hash(self.workspace_path / dependency),
                    )
                    for dependency in dependencies
                ],
            )
            connection.commit()
        finally:
            connection.close()
def _content_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_path(workspace_path: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace_path).as_posix()
@dataclass(frozen=True)
class _Span:
    line_start: int
    line_end: int

    def _replace_path(self, path: str) -> Citation:
        return Citation(path=path, line_start=self.line_start, line_end=self.line_end, kind="integration")


def _line_span(path: Path, pattern: str) -> _Span:
    content = path.read_text(encoding="utf-8")
    match = re.search(pattern, content, flags=re.MULTILINE)
    if match:
        line_start, line_end = line_range_for_match(content, match.start(), match.end())
        return _Span(line_start=line_start, line_end=line_end)

    lines = content.splitlines()
    if not lines:
        return _Span(line_start=1, line_end=1)
    return _Span(line_start=1, line_end=min(len(lines), 25))
