"""Deterministic shared evidence graph for blocking seed system docs."""

from __future__ import annotations

import ast
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import tomli
except ImportError:
    import tomllib as tomli  # Python 3.11+

from autonomous_agent_builder.knowledge.proof_contract import (
    CLAIM_TYPE_DERIVED,
    CLAIM_TYPE_EXTRACTED,
    Citation,
    citation_for_file,
    citation_for_pattern,
    compute_dependency_hash,
    git_head,
    line_range_for_match,
)

GRAPH_ARTIFACT_RELATIVE_PATH = ".evidence/graph.json"
GRAPH_EXTRACTOR_VERSION = "shared-evidence-graph-v1"
BLOCKING_DOCS: tuple[str, ...] = (
    "system-architecture",
    "dependencies",
    "technology-stack",
)
SUPPORTED_WORKSPACE_PROFILES: tuple[str, ...] = (
    "python_fastapi_service",
    "python_cli_app",
    "polyglot_web_app",
    "generic_repo",
)
_MANIFEST_CANDIDATES: tuple[str, ...] = (
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
)
_PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "This document describes",
    "if applicable",
    "placeholder",
    "Add concrete evidence",
)
_DEPENDENCY_PURPOSES: dict[str, str] = {
    "fastapi": "HTTP API framework",
    "uvicorn": "ASGI server",
    "sqlalchemy": "ORM and SQL query layer",
    "asyncpg": "Async PostgreSQL driver",
    "pydantic": "Validation and settings",
    "pydantic-settings": "Settings management",
    "typer": "CLI framework",
    "react": "Client UI library",
    "vite": "Frontend build and dev server",
    "typescript": "Typed JavaScript toolchain",
    "pytest": "Python test runner",
}


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    label: str
    properties: dict[str, Any]
    evidence: tuple[Citation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "properties": _sort_dict(self.properties),
            "evidence": [citation.to_dict() for citation in self.evidence],
        }


@dataclass(frozen=True)
class GraphEdge:
    id: str
    kind: str
    source: str
    target: str
    properties: dict[str, Any]
    evidence: tuple[Citation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "source": self.source,
            "target": self.target,
            "properties": _sort_dict(self.properties),
            "evidence": [citation.to_dict() for citation in self.evidence],
        }


@dataclass(frozen=True)
class GraphAssertion:
    id: str
    doc_slug: str
    section: str
    claim_type: str
    text: str
    citations: tuple[Citation, ...]
    derived_from: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "doc_slug": self.doc_slug,
            "section": self.section,
            "claim_type": self.claim_type,
            "text": self.text,
            "citations": [citation.to_dict() for citation in self.citations],
            "derived_from": list(self.derived_from),
        }


@dataclass(frozen=True)
class GraphUnresolvedItem:
    id: str
    doc_slug: str
    section: str
    message: str
    citations: tuple[Citation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "doc_slug": self.doc_slug,
            "section": self.section,
            "message": self.message,
            "citations": [citation.to_dict() for citation in self.citations],
        }


@dataclass(frozen=True)
class EvidenceGraph:
    workspace_profile: str
    extractor_version: str
    source_commit: str | None
    dependency_hash: str
    dependency_inputs: tuple[str, ...]
    generated_at: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    assertions: tuple[GraphAssertion, ...]
    unresolved_items: tuple[GraphUnresolvedItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_profile": self.workspace_profile,
            "extractor_version": self.extractor_version,
            "source_commit": self.source_commit,
            "dependency_hash": self.dependency_hash,
            "dependency_inputs": list(self.dependency_inputs),
            "generated_at": self.generated_at,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "assertions": [assertion.to_dict() for assertion in self.assertions],
            "unresolved_items": [item.to_dict() for item in self.unresolved_items],
        }


def graph_artifact_path(collection_path: Path) -> Path:
    return collection_path / GRAPH_ARTIFACT_RELATIVE_PATH


def build_shared_evidence_graph(workspace_path: Path, collection_path: Path) -> dict[str, Any]:
    builder = _SharedEvidenceGraphBuilder(workspace_path.resolve(), collection_path.resolve())
    graph = builder.build()
    graph_path = graph_artifact_path(collection_path)
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(graph.to_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    _write_compatibility_sqlite(collection_path, graph)
    return graph.to_dict()


def load_shared_evidence_graph(collection_path: Path) -> dict[str, Any]:
    path = graph_artifact_path(collection_path)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_shared_evidence_graph(graph: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required_top_level = (
        "workspace_profile",
        "extractor_version",
        "source_commit",
        "dependency_hash",
        "dependency_inputs",
        "generated_at",
        "nodes",
        "edges",
        "assertions",
        "unresolved_items",
    )
    for field in required_top_level:
        if field not in graph:
            issues.append(f"graph missing `{field}`")
    if graph.get("workspace_profile") not in SUPPORTED_WORKSPACE_PROFILES:
        issues.append("graph workspace_profile is invalid")
    if not isinstance(graph.get("nodes"), list):
        issues.append("graph nodes must be a list")
    if not isinstance(graph.get("edges"), list):
        issues.append("graph edges must be a list")
    if not isinstance(graph.get("assertions"), list):
        issues.append("graph assertions must be a list")
    if not isinstance(graph.get("unresolved_items"), list):
        issues.append("graph unresolved_items must be a list")
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            issues.append("graph node must be an object")
            continue
        for field in ("id", "kind", "label", "properties", "evidence"):
            if field not in node:
                issues.append(f"graph node missing `{field}`")
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            issues.append("graph edge must be an object")
            continue
        for field in ("id", "kind", "source", "target", "properties", "evidence"):
            if field not in edge:
                issues.append(f"graph edge missing `{field}`")
    for assertion in graph.get("assertions") or []:
        if not isinstance(assertion, dict):
            issues.append("graph assertion must be an object")
            continue
        for field in ("id", "doc_slug", "section", "claim_type", "text", "citations", "derived_from"):
            if field not in assertion:
                issues.append(f"graph assertion missing `{field}`")
        if assertion.get("claim_type") not in {CLAIM_TYPE_EXTRACTED, CLAIM_TYPE_DERIVED}:
            issues.append(f"graph assertion `{assertion.get('id', '')}` has invalid claim_type")
    return issues


def render_blocking_doc(
    doc_slug: str,
    graph: dict[str, Any],
    *,
    workspace_path: Path,
    collection_path: Path,
) -> dict[str, Any]:
    slug = doc_slug.strip().lower()
    if slug not in BLOCKING_DOCS:
        raise ValueError(f"Unsupported blocking doc slug: {doc_slug}")
    if slug == "system-architecture":
        return _render_system_architecture(graph, workspace_path=workspace_path, collection_path=collection_path)
    if slug == "dependencies":
        return _render_dependencies(graph, workspace_path=workspace_path, collection_path=collection_path)
    return _render_technology_stack(graph, workspace_path=workspace_path, collection_path=collection_path)


class _SharedEvidenceGraphBuilder:
    def __init__(self, workspace_path: Path, collection_path: Path):
        self.workspace_path = workspace_path
        self.collection_path = collection_path
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}
        self.assertions: dict[str, GraphAssertion] = {}
        self.unresolved_items: dict[str, GraphUnresolvedItem] = {}
        self.dependencies: set[str] = set()
        self.python_dependencies: dict[str, str | None] = {}
        self.python_dev_dependencies: dict[str, str | None] = {}
        self.node_dependencies: dict[str, str | None] = {}
        self.node_dev_dependencies: dict[str, str | None] = {}
        self.route_records: list[dict[str, Any]] = []
        self.config_records: list[dict[str, Any]] = []
        self.cli_records: list[dict[str, Any]] = []
        self.entrypoint_records: list[dict[str, Any]] = []
        self.framework_names: set[str] = set()
        self.language_names: set[str] = set()
        self.manifest_paths: list[str] = []
        self.workspace_profile = "generic_repo"

    def build(self) -> EvidenceGraph:
        self._collect_manifests()
        self._collect_dependencies()
        self._collect_languages()
        self._collect_frameworks()
        self._collect_entrypoints()
        self._collect_fastapi_routes()
        self._collect_cli_commands()
        self._collect_config_prefixes()
        self._collect_db_surfaces()
        self.workspace_profile = self._detect_workspace_profile()
        self._add_profile_node()
        self._build_system_architecture_assertions()
        self._build_dependencies_assertions()
        self._build_technology_stack_assertions()

        dependency_list = sorted(self.dependencies)
        dependency_hash = compute_dependency_hash(self.workspace_path, dependency_list)
        return EvidenceGraph(
            workspace_profile=self.workspace_profile,
            extractor_version=GRAPH_EXTRACTOR_VERSION,
            source_commit=git_head(self.workspace_path),
            dependency_hash=dependency_hash,
            dependency_inputs=tuple(dependency_list),
            generated_at=_stable_generated_at(self.workspace_path, dependency_list),
            nodes=tuple(sorted(self.nodes.values(), key=lambda item: item.id)),
            edges=tuple(sorted(self.edges.values(), key=lambda item: item.id)),
            assertions=tuple(sorted(self.assertions.values(), key=lambda item: item.id)),
            unresolved_items=tuple(sorted(self.unresolved_items.values(), key=lambda item: item.id)),
        )

    def _collect_manifests(self) -> None:
        for relative_path in _MANIFEST_CANDIDATES:
            if not (self.workspace_path / relative_path).exists():
                continue
            citation = citation_for_file(self.workspace_path, relative_path, kind="manifest")
            self._add_node(
                GraphNode(
                    id=f"manifest:{relative_path}",
                    kind="manifest",
                    label=relative_path,
                    properties={"path": relative_path},
                    evidence=(citation,),
                )
            )
            self.manifest_paths.append(relative_path)
            self.dependencies.add(relative_path)

    def _collect_dependencies(self) -> None:
        pyproject = self.workspace_path / "pyproject.toml"
        if pyproject.exists():
            self.dependencies.add("pyproject.toml")
            try:
                data = tomli.loads(pyproject.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            for dep in data.get("project", {}).get("dependencies", []) or []:
                name, version = _parse_dep_string(str(dep))
                if name:
                    self.python_dependencies[name] = version
            for dep in data.get("project", {}).get("optional-dependencies", {}).get("dev", []) or []:
                name, version = _parse_dep_string(str(dep))
                if name:
                    self.python_dev_dependencies[name] = version

        for requirements_name, bucket in (
            ("requirements.txt", self.python_dependencies),
            ("requirements-dev.txt", self.python_dev_dependencies),
        ):
            requirements_path = self.workspace_path / requirements_name
            if not requirements_path.exists():
                continue
            self.dependencies.add(requirements_name)
            for line in requirements_path.read_text(encoding="utf-8").splitlines():
                name, version = _parse_dep_string(line)
                if name:
                    bucket[name] = version

        for package_json_name in ("package.json", "frontend/package.json"):
            package_json = self.workspace_path / package_json_name
            if not package_json.exists():
                continue
            self.dependencies.add(package_json_name)
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            for name, version in (data.get("dependencies") or {}).items():
                self.node_dependencies[str(name)] = str(version).lstrip("^~")
            for name, version in (data.get("devDependencies") or {}).items():
                self.node_dev_dependencies[str(name)] = str(version).lstrip("^~")

        all_packages = [
            ("python", False, self.python_dependencies, "pyproject.toml" if pyproject.exists() else "requirements.txt"),
            ("python", True, self.python_dev_dependencies, "pyproject.toml" if pyproject.exists() else "requirements-dev.txt"),
            ("node", False, self.node_dependencies, "frontend/package.json" if (self.workspace_path / "frontend/package.json").exists() else "package.json"),
            ("node", True, self.node_dev_dependencies, "frontend/package.json" if (self.workspace_path / "frontend/package.json").exists() else "package.json"),
        ]
        for ecosystem, is_dev, packages, source_path in all_packages:
            if not packages:
                continue
            if not (self.workspace_path / source_path).exists():
                continue
            for name, version in sorted(packages.items()):
                citation = citation_for_pattern(
                    self.workspace_path,
                    source_path,
                    pattern=rf'(?m)^\s*["\']?{re.escape(name)}["\']?\s*[:=]',
                    kind="dependency",
                )
                node_id = f"dependency:{ecosystem}:{name}"
                self._add_node(
                    GraphNode(
                        id=node_id,
                        kind="dependency",
                        label=name,
                        properties={
                            "ecosystem": ecosystem,
                            "version": version,
                            "bucket": "dev" if is_dev else "production",
                            "purpose": _DEPENDENCY_PURPOSES.get(name.lower()),
                        },
                        evidence=(citation,),
                    )
                )
                self._add_edge(
                    GraphEdge(
                        id=f"edge:manifest:{source_path}:{node_id}",
                        kind="declares",
                        source=f"manifest:{source_path}",
                        target=node_id,
                        properties={"bucket": "dev" if is_dev else "production"},
                        evidence=(citation,),
                    )
                )

    def _collect_languages(self) -> None:
        if self.python_dependencies or self.python_dev_dependencies or any(
            (self.workspace_path / path).exists() for path in ("pyproject.toml", "requirements.txt")
        ):
            self.language_names.add("Python")
            self._add_language_node("Python", "pyproject.toml" if (self.workspace_path / "pyproject.toml").exists() else "requirements.txt")
        if (self.workspace_path / "package.json").exists() or (self.workspace_path / "frontend/package.json").exists():
            self.language_names.add("Node.js")
            self._add_language_node("Node.js", "frontend/package.json" if (self.workspace_path / "frontend/package.json").exists() else "package.json")
        if (self.workspace_path / "tsconfig.json").exists() or (self.workspace_path / "frontend/tsconfig.json").exists():
            self.language_names.add("TypeScript")
            tsconfig_path = "frontend/tsconfig.json" if (self.workspace_path / "frontend/tsconfig.json").exists() else "tsconfig.json"
            self.dependencies.add(tsconfig_path)
            self._add_language_node("TypeScript", tsconfig_path)

    def _collect_frameworks(self) -> None:
        framework_sources = {
            "FastAPI": ("dependency:python:fastapi", "pyproject.toml"),
            "Typer": ("dependency:python:typer", "pyproject.toml"),
            "SQLAlchemy": ("dependency:python:sqlalchemy", "pyproject.toml"),
            "Pydantic": ("dependency:python:pydantic", "pyproject.toml"),
            "React": ("dependency:node:react", "package.json"),
            "Vite": ("dependency:node:vite", "package.json"),
        }
        for label, (dependency_node, source_path) in framework_sources.items():
            if dependency_node not in self.nodes:
                continue
            citation = self.nodes[dependency_node].evidence[0]
            framework_id = f"framework:{label.lower().replace('.', '').replace(' ', '-')}"
            self.framework_names.add(label)
            self._add_node(
                GraphNode(
                    id=framework_id,
                    kind="framework",
                    label=label,
                    properties={"source_manifest": source_path},
                    evidence=(citation,),
                )
            )
            self._add_edge(
                GraphEdge(
                    id=f"edge:{dependency_node}:{framework_id}",
                    kind="signals_framework",
                    source=dependency_node,
                    target=framework_id,
                    properties={},
                    evidence=(citation,),
                )
            )

    def _collect_entrypoints(self) -> None:
        candidate_patterns = (
            "main.py",
            "app.py",
            "server.py",
            "*.py",
            "src/**/main.py",
            "src/**/app.py",
            "src/**/server.py",
        )
        seen: set[str] = set()
        for pattern in candidate_patterns:
            for path in sorted(self.workspace_path.glob(pattern)):
                if not path.is_file():
                    continue
                relative = _relative_path(self.workspace_path, path)
                if relative in seen or _is_excluded(relative):
                    continue
                if not self._looks_like_entrypoint(path, relative):
                    continue
                seen.add(relative)
                citation = citation_for_file(self.workspace_path, relative, kind="entrypoint")
                self.entrypoint_records.append({"path": relative, "citation": citation})
                self.dependencies.add(relative)
                self._add_node(
                    GraphNode(
                        id=f"entrypoint:{relative}",
                        kind="entrypoint",
                        label=Path(relative).name,
                        properties={"path": relative},
                        evidence=(citation,),
                    )
                )

    def _looks_like_entrypoint(self, path: Path, relative: str) -> bool:
        if Path(relative).name in {"main.py", "app.py", "server.py", "manage.py", "run.py", "wsgi.py", "asgi.py"}:
            return True
        if len(Path(relative).parts) > 1:
            return True
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return False
        signals = (
            "__main__",
            "create_app(",
            "app.run(",
            "@app.cli.command",
            "Flask(",
            "uvicorn.run(",
            "typer.Typer(",
        )
        return any(signal in content for signal in signals)

    def _collect_fastapi_routes(self) -> None:
        route_files = sorted(self.workspace_path.glob("**/*.py"))
        decorator_pattern = re.compile(r"@router\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)[\"']")
        prefix_pattern = re.compile(r"APIRouter\([^)]*prefix\s*=\s*[\"']([^\"']+)[\"']")
        for path in route_files:
            relative = _relative_path(self.workspace_path, path)
            if _is_excluded(relative):
                continue
            content = path.read_text(encoding="utf-8")
            if "@router." not in content or "APIRouter" not in content:
                continue
            self.dependencies.add(relative)
            prefix_match = prefix_pattern.search(content)
            prefix = prefix_match.group(1) if prefix_match else ""
            for match in decorator_pattern.finditer(content):
                method = match.group(1).upper()
                route_path = _normalize_route_path(prefix, match.group(2))
                line_start, line_end = line_range_for_match(content, match.start(), match.end())
                citation = Citation(path=relative, line_start=line_start, line_end=line_end, kind="route")
                route_id = f"route:{method}:{route_path}"
                self.route_records.append(
                    {
                        "id": route_id,
                        "method": method,
                        "path": route_path,
                        "source": relative,
                        "citation": citation,
                    }
                )
                self._add_node(
                    GraphNode(
                        id=route_id,
                        kind="route",
                        label=f"{method} {route_path}",
                        properties={"method": method, "path": route_path, "source": relative},
                        evidence=(citation,),
                    )
                )

    def _collect_cli_commands(self) -> None:
        main_path = self.workspace_path / "src" / "autonomous_agent_builder" / "cli" / "main.py"
        if not main_path.exists():
            return
        relative = _relative_path(self.workspace_path, main_path)
        self.dependencies.add(relative)
        content = main_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return
        for node in tree.body:
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            if not isinstance(call.func, ast.Attribute):
                continue
            command_name = None
            kind = None
            if call.func.attr == "command":
                kind = "command"
                command_name = _keyword_str(call, "name")
            elif call.func.attr == "add_typer":
                kind = "group"
                command_name = _keyword_str(call, "name")
            if not command_name or not kind:
                continue
            segment = f"{kind}:{command_name}"
            match_pattern = rf'{call.func.attr}\([^)]*name\s*=\s*"{re.escape(command_name)}"'
            citation = citation_for_pattern(self.workspace_path, relative, pattern=match_pattern, kind="cli")
            node_id = f"cli:{command_name}"
            self.cli_records.append({"id": node_id, "name": command_name, "kind": kind, "citation": citation})
            self._add_node(
                GraphNode(
                    id=node_id,
                    kind="cli_command",
                    label=command_name,
                    properties={"kind": kind, "source": relative},
                    evidence=(citation,),
                )
            )

    def _collect_config_prefixes(self) -> None:
        config_path = self.workspace_path / "src" / "autonomous_agent_builder" / "config.py"
        if not config_path.exists():
            return
        relative = _relative_path(self.workspace_path, config_path)
        self.dependencies.add(relative)
        content = config_path.read_text(encoding="utf-8")
        pattern = re.compile(
            r"class\s+(\w+)\(BaseSettings\):[\s\S]*?model_config\s*=\s*\{\"env_prefix\":\s*\"([A-Z_]+)\"",
        )
        for match in pattern.finditer(content):
            class_name, prefix = match.group(1), match.group(2)
            line_start, line_end = line_range_for_match(content, match.start(), match.end())
            citation = Citation(path=relative, line_start=line_start, line_end=line_end, kind="config")
            node_id = f"config:{prefix.rstrip('_').lower()}"
            self.config_records.append(
                {"id": node_id, "class_name": class_name, "prefix": prefix, "citation": citation}
            )
            self._add_node(
                GraphNode(
                    id=node_id,
                    kind="config_surface",
                    label=f"{class_name} ({prefix})",
                    properties={"class_name": class_name, "prefix": prefix, "path": relative},
                    evidence=(citation,),
                )
            )

    def _collect_db_surfaces(self) -> None:
        for relative in ("src/autonomous_agent_builder/db/session.py", "src/autonomous_agent_builder/db/models.py"):
            if not (self.workspace_path / relative).exists():
                continue
            citation = citation_for_file(self.workspace_path, relative, kind="data_surface")
            self.dependencies.add(relative)
            kind = "data_surface" if relative.endswith("models.py") else "persistence"
            self._add_node(
                GraphNode(
                    id=f"surface:{relative}",
                    kind=kind,
                    label=Path(relative).name,
                    properties={"path": relative},
                    evidence=(citation,),
                )
            )

    def _detect_workspace_profile(self) -> str:
        python_present = "Python" in self.language_names
        node_present = "Node.js" in self.language_names
        fastapi_present = "FastAPI" in self.framework_names or bool(self.route_records)
        typer_present = "Typer" in self.framework_names or bool(self.cli_records)
        react_present = "React" in self.framework_names and "Vite" in self.framework_names
        if python_present and fastapi_present and node_present and react_present:
            return "polyglot_web_app"
        if python_present and fastapi_present:
            return "python_fastapi_service"
        if python_present and typer_present:
            return "python_cli_app"
        if node_present and python_present:
            return "polyglot_web_app"
        return "generic_repo"

    def _add_profile_node(self) -> None:
        citation = None
        if self.manifest_paths:
            citation = citation_for_file(self.workspace_path, self.manifest_paths[0], kind="profile")
        elif self.entrypoint_records:
            citation = self.entrypoint_records[0]["citation"]
        else:
            citation = Citation(path=".", line_start=1, line_end=1, kind="profile")
        self._add_node(
            GraphNode(
                id=f"profile:{self.workspace_profile}",
                kind="workspace_profile",
                label=self.workspace_profile,
                properties={"profile": self.workspace_profile},
                evidence=(citation,),
            )
        )

    def _build_system_architecture_assertions(self) -> None:
        overview_citations = tuple(
            citation
            for citation in (
                self._node_citation("profile:" + self.workspace_profile),
                self._framework_citation("FastAPI"),
                self._framework_citation("Typer"),
                self._framework_citation("React"),
            )
            if citation is not None
        )
        if overview_citations:
            summary = _profile_summary(self.workspace_profile, self.framework_names)
            self._add_assertion(
                GraphAssertion(
                    id="assertion:system-architecture:overview:runtime-shape",
                    doc_slug="system-architecture",
                    section="Overview",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text=summary,
                    citations=overview_citations,
                    derived_from=("profile:" + self.workspace_profile,),
                )
            )
        else:
            self._add_unresolved("system-architecture", "Overview", "No runtime profile evidence found.")

        boundary_items: list[str] = []
        boundary_citations: list[Citation] = []
        for record in self.entrypoint_records[:4]:
            boundary_items.append(f"`{record['path']}`")
            boundary_citations.append(record["citation"])
        if self.route_records:
            boundary_items.append("FastAPI route modules")
            boundary_citations.append(self.route_records[0]["citation"])
        if self.cli_records:
            boundary_items.append("Typer CLI command groups")
            boundary_citations.append(self.cli_records[0]["citation"])
        if boundary_items:
            self._add_assertion(
                GraphAssertion(
                    id="assertion:system-architecture:boundaries:owning-surfaces",
                    doc_slug="system-architecture",
                    section="Boundaries",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text="Primary runtime boundaries are " + ", ".join(boundary_items) + ".",
                    citations=tuple(boundary_citations),
                    derived_from=tuple(f"entrypoint:{item['path']}" for item in self.entrypoint_records[:4]),
                )
            )
        else:
            self._add_unresolved("system-architecture", "Boundaries", "No entrypoints were detected.")

        invariant_texts = [
            (
                "Route registration, CLI registration, and persisted state surfaces must stay aligned with the runtime entrypoints documented here.",
                tuple(c for c in (self._first_route_citation(), self._first_cli_citation(), self._models_citation()) if c),
            ),
            (
                "Blocking architecture docs must be regenerated when manifests, entrypoints, or route registration change.",
                tuple(c for c in (self._first_manifest_citation(), self._first_entrypoint_citation()) if c),
            ),
        ]
        for index, (text, citations) in enumerate(invariant_texts, start=1):
            if citations:
                self._add_assertion(
                    GraphAssertion(
                        id=f"assertion:system-architecture:invariants:{index}",
                        doc_slug="system-architecture",
                        section="Invariants",
                        claim_type=CLAIM_TYPE_DERIVED,
                        text=text,
                        citations=citations,
                    )
                )

        evidence_texts = [
            (
                "The runtime exposes route families rooted in "
                + ", ".join(sorted({record['path'] for record in self.route_records[:5]}))
                + ".",
                tuple(record["citation"] for record in self.route_records[:5]),
            )
            if self.route_records
            else None,
            (
                "Configuration is organized around env-prefixed settings surfaces "
                + ", ".join(f"`{record['prefix']}`" for record in self.config_records[:4])
                + ".",
                tuple(record["citation"] for record in self.config_records[:4]),
            )
            if self.config_records
            else None,
        ]
        for index, item in enumerate([value for value in evidence_texts if value], start=1):
            text, citations = item
            self._add_assertion(
                GraphAssertion(
                    id=f"assertion:system-architecture:evidence:{index}",
                    doc_slug="system-architecture",
                    section="Evidence",
                    claim_type=CLAIM_TYPE_EXTRACTED,
                    text=text,
                    citations=citations,
                )
            )

        guidance_citations = tuple(c for c in (self._first_manifest_citation(), self._first_route_citation()) if c)
        if guidance_citations:
            self._add_assertion(
                GraphAssertion(
                    id="assertion:system-architecture:change-guidance:refresh",
                    doc_slug="system-architecture",
                    section="Change guidance",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text="Refresh the blocking docs with `builder knowledge extract --force --doc system-architecture --json` after changing runtime wiring, manifests, or route registration.",
                    citations=guidance_citations,
                )
            )
        if self._first_manifest_citation():
            self._add_assertion(
                GraphAssertion(
                    id="assertion:system-architecture:invariants:manifest-linkage",
                    doc_slug="system-architecture",
                    section="Invariants",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text="Manifest-backed stack signals and entrypoint discovery must continue to describe the same runtime shape, or the blocking architecture view becomes stale.",
                    citations=tuple(c for c in (self._first_manifest_citation(), self._first_entrypoint_citation()) if c),
                )
            )
            self._add_assertion(
                GraphAssertion(
                    id="assertion:system-architecture:evidence:manifests-and-entrypoints",
                    doc_slug="system-architecture",
                    section="Evidence",
                    claim_type=CLAIM_TYPE_EXTRACTED,
                    text="The shared graph links checked-in manifests to the runtime entrypoints that define how the repository is started and validated.",
                    citations=tuple(c for c in (self._first_manifest_citation(), self._first_entrypoint_citation()) if c),
                )
            )

    def _build_dependencies_assertions(self) -> None:
        dependency_nodes = [node for node in self.nodes.values() if node.kind == "dependency"]
        manifest_citations = tuple(
            node.evidence[0]
            for node in self.nodes.values()
            if node.kind == "manifest" and node.properties.get("path") in self.manifest_paths
        )
        if manifest_citations:
            self._add_assertion(
                GraphAssertion(
                    id="assertion:dependencies:overview:manifests",
                    doc_slug="dependencies",
                    section="Overview",
                    claim_type=CLAIM_TYPE_EXTRACTED,
                    text="Declared dependencies are sourced from " + ", ".join(f"`{path}`" for path in self.manifest_paths) + ".",
                    citations=manifest_citations,
                )
            )
        else:
            self._add_unresolved("dependencies", "Overview", "No dependency manifests were detected.")

        if dependency_nodes:
            self._add_assertion(
                GraphAssertion(
                    id="assertion:dependencies:boundaries:manifests",
                    doc_slug="dependencies",
                    section="Boundaries",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text="Dependency intent is owned by the checked-in manifests and lock surfaces, not by generated KB prose.",
                    citations=manifest_citations or tuple(node.evidence[0] for node in dependency_nodes[:2]),
                )
            )
            self._add_assertion(
                GraphAssertion(
                    id="assertion:dependencies:invariants:manifest-scope",
                    doc_slug="dependencies",
                    section="Invariants",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text="Package changes must stay scoped to the owning manifest and preserve the runtime surfaces that consume them.",
                    citations=manifest_citations or tuple(node.evidence[0] for node in dependency_nodes[:2]),
                )
            )

            prod_count = sum(1 for node in dependency_nodes if node.properties.get("bucket") == "production")
            dev_count = sum(1 for node in dependency_nodes if node.properties.get("bucket") == "dev")
            self._add_assertion(
                GraphAssertion(
                    id="assertion:dependencies:evidence:inventory",
                    doc_slug="dependencies",
                    section="Evidence",
                    claim_type=CLAIM_TYPE_EXTRACTED,
                    text=f"The extracted manifests declare {prod_count} production dependencies and {dev_count} development dependencies across Python and Node ecosystems.",
                    citations=tuple(node.evidence[0] for node in dependency_nodes[:8]),
                )
            )
            self._add_assertion(
                GraphAssertion(
                    id="assertion:dependencies:change-guidance:refresh",
                    doc_slug="dependencies",
                    section="Change guidance",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text="Update the owning manifest first, then rerun `builder knowledge extract --force` so the dependency inventory and freshness hash stay aligned.",
                    citations=manifest_citations or tuple(node.evidence[0] for node in dependency_nodes[:2]),
                )
            )

    def _build_technology_stack_assertions(self) -> None:
        language_nodes = [node for node in self.nodes.values() if node.kind == "language"]
        framework_nodes = [node for node in self.nodes.values() if node.kind == "framework"]
        if language_nodes or framework_nodes:
            self._add_assertion(
                GraphAssertion(
                    id="assertion:technology-stack:overview:stack-shape",
                    doc_slug="technology-stack",
                    section="Overview",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text=_technology_summary(self.language_names, self.framework_names),
                    citations=tuple(node.evidence[0] for node in (language_nodes + framework_nodes)[:8]),
                )
            )
            self._add_assertion(
                GraphAssertion(
                    id="assertion:technology-stack:boundaries:layers",
                    doc_slug="technology-stack",
                    section="Boundaries",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text="The stack boundary is defined by checked-in runtime manifests, framework packages, and entrypoints that separate backend, CLI, and frontend concerns.",
                    citations=tuple(node.evidence[0] for node in (language_nodes + framework_nodes)[:8]),
                )
            )
            self._add_assertion(
                GraphAssertion(
                    id="assertion:technology-stack:invariants:consistency",
                    doc_slug="technology-stack",
                    section="Invariants",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text="Stack changes must stay consistent with the manifests, entrypoints, and persistence surfaces that currently define the runtime.",
                    citations=tuple(node.evidence[0] for node in (language_nodes + framework_nodes)[:8]),
                )
            )
            stack_evidence_citations = tuple(node.evidence[0] for node in (language_nodes + framework_nodes)[:8])
            self._add_assertion(
                GraphAssertion(
                    id="assertion:technology-stack:evidence:frameworks",
                    doc_slug="technology-stack",
                    section="Evidence",
                    claim_type=CLAIM_TYPE_EXTRACTED,
                    text="Detected stack signals include "
                    + ", ".join(
                        sorted(
                            list(self.language_names) + list(self.framework_names),
                            key=lambda item: item.lower(),
                        )
                    )
                    + ".",
                    citations=stack_evidence_citations,
                )
            )
            self._add_assertion(
                GraphAssertion(
                    id="assertion:technology-stack:change-guidance:refresh",
                    doc_slug="technology-stack",
                    section="Change guidance",
                    claim_type=CLAIM_TYPE_DERIVED,
                    text="After changing framework or runtime manifests, rerun `builder knowledge extract --force` to refresh the stack view and dependency hash.",
                    citations=stack_evidence_citations,
                )
            )
        else:
            self._add_unresolved("technology-stack", "Overview", "No stack signals were detected.")

    def _add_language_node(self, label: str, source_path: str) -> None:
        if not (self.workspace_path / source_path).exists():
            return
        citation = citation_for_file(self.workspace_path, source_path, kind="language")
        node_id = f"language:{label.lower().replace('.', '').replace(' ', '-')}"
        self._add_node(
            GraphNode(
                id=node_id,
                kind="language",
                label=label,
                properties={"source_manifest": source_path},
                evidence=(citation,),
            )
        )

    def _add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node

    def _add_edge(self, edge: GraphEdge) -> None:
        self.edges[edge.id] = edge

    def _add_assertion(self, assertion: GraphAssertion) -> None:
        self.assertions[assertion.id] = assertion

    def _add_unresolved(self, doc_slug: str, section: str, message: str) -> None:
        unresolved_id = f"unresolved:{doc_slug}:{section.lower().replace(' ', '-')}"
        self.unresolved_items[unresolved_id] = GraphUnresolvedItem(
            id=unresolved_id,
            doc_slug=doc_slug,
            section=section,
            message=message,
        )

    def _node_citation(self, node_id: str) -> Citation | None:
        node = self.nodes.get(node_id)
        return node.evidence[0] if node and node.evidence else None

    def _framework_citation(self, label: str) -> Citation | None:
        framework_id = f"framework:{label.lower().replace('.', '').replace(' ', '-')}"
        return self._node_citation(framework_id)

    def _first_manifest_citation(self) -> Citation | None:
        for path in self.manifest_paths:
            node = self.nodes.get(f"manifest:{path}")
            if node and node.evidence:
                return node.evidence[0]
        return None

    def _first_entrypoint_citation(self) -> Citation | None:
        return self.entrypoint_records[0]["citation"] if self.entrypoint_records else None

    def _first_route_citation(self) -> Citation | None:
        return self.route_records[0]["citation"] if self.route_records else None

    def _first_cli_citation(self) -> Citation | None:
        return self.cli_records[0]["citation"] if self.cli_records else None

    def _models_citation(self) -> Citation | None:
        node = self.nodes.get("surface:src/autonomous_agent_builder/db/models.py")
        return node.evidence[0] if node and node.evidence else None


def _render_system_architecture(
    graph: dict[str, Any],
    *,
    workspace_path: Path,
    collection_path: Path,
) -> dict[str, Any]:
    assertions = _doc_assertions(graph, "system-architecture")
    unresolved = _doc_unresolved(graph, "system-architecture")
    runtime_paths = _unique_property_values(graph, "route", "source")
    entrypoints = _entrypoint_paths(graph)
    profile = str(graph.get("workspace_profile", "generic_repo"))
    route_labels = [item["label"] for item in graph.get("nodes", []) if item.get("kind") == "route"][:8]
    config_prefixes = [
        node["properties"].get("prefix")
        for node in graph.get("nodes", [])
        if node.get("kind") == "config_surface"
    ][:4]

    body_parts = [
        "# System Architecture",
        "",
        "This blocking architecture view is rendered from the shared deterministic evidence graph for the repository.",
        "",
        "## Overview",
        "",
        _render_section_paragraphs(assertions, "Overview")
        + " It is intended to be the authoritative architecture read for both onboarding and bounded agent retrieval, so it avoids unstated assumptions and template filler.",
        "",
        "## User mental model",
        "",
        _profile_user_mental_model(profile)
        + " The graph-backed view keeps manifests, entrypoints, routes, commands, and config surfaces in one deterministic runtime map.",
        "",
        "## Boundaries",
        "",
        _render_section_paragraphs(assertions, "Boundaries")
        + " Read this section first when you need to decide which code surface owns a change and which adjacent runtime contracts are at risk.",
        "",
        "## Invariants",
        "",
        _render_section_bullets(assertions, "Invariants"),
        "",
        "## How work moves through the system",
        "",
        "The runtime shape is anchored by "
        + ", ".join(f"`{path}`" for path in entrypoints[:4])
        + (", plus registered API route modules." if runtime_paths else "."),
        "",
        "## Runtime diagram",
        "",
        "```mermaid",
        "graph LR",
        f'    Profile["{profile}"] --> Entrypoints["{_diagram_label(entrypoints[:4])}"]',
        '    Entrypoints --> Runtime["Runtime surfaces"]',
        '    Runtime --> Routes["API routes"]',
        '    Runtime --> CLI["CLI commands"]',
        '    Runtime --> Config["Config surfaces"]',
        '    Runtime --> Data["Persistence and models"]',
        "```",
        "",
        "## Lifecycle diagram",
        "",
        "```mermaid",
        "flowchart LR",
        '    Manifests["Checked-in manifests"] --> Graph["Shared evidence graph"]',
        '    Graph --> Docs["Blocking KB docs"]',
        '    Docs --> Validate["Deterministic validation"]',
        '    Validate --> Retrieve["builder knowledge summary/show"]',
        "```",
        "",
        "## Agent change map",
        "",
        "| Change area | Owning surfaces | Inspect first |",
        "| --- | --- | --- |",
        "| Runtime wiring | "
        + _table_paths(entrypoints[:3])
        + " | entrypoints, manifests, profile |",
        "| API behavior | "
        + _table_paths(runtime_paths[:3])
        + " | route registrations, response shapes |",
        "| Config and persistence | `config.py`, `db/session.py`, `db/models.py` | env prefixes, DB URLs, entity shape |",
        "",
        "## Evidence",
        "",
        _render_section_bullets(assertions, "Evidence"),
        "",
        "The evidence above is emitted from typed graph assertions rather than freeform prose, so each blocking statement stays tied to live files and line ranges. This makes freshness checks and citation validation operate on the same deterministic source of truth that produced the document.",
        "",
        "Manifest and entrypoint evidence stay in the same graph artifact, which lets the validator compare rendered markdown against the exact dependency set that produced it.",
        "",
        "## Proof for agents",
        "",
        "- Runtime entrypoints: " + ", ".join(f"`{path}`" for path in entrypoints[:4]),
        "- Route groups: " + (", ".join(f"`{label}`" for label in route_labels[:6]) if route_labels else "none detected"),
        "- Config prefixes: " + (", ".join(f"`{prefix}`" for prefix in config_prefixes if prefix) if config_prefixes else "none detected"),
        "",
        "## Change guidance",
        "",
        _render_section_paragraphs(assertions, "Change guidance"),
    ]
    content = "\n".join(body_parts).strip() + "\n"
    return _rendered_doc_payload(
        title="System Architecture",
        doc_slug="system-architecture",
        graph=graph,
        workspace_path=workspace_path,
        collection_path=collection_path,
        content=content,
        tags=["architecture", "design", "runtime", "system-docs", "seed"],
        wikilinks=["Code Structure", "API Endpoints", "Agent System"],
        card_summary="Graph-backed runtime boundaries, entrypoints, and change map for the blocking architecture view.",
        detail_summary="Renders the blocking architecture view from the shared evidence graph, with runtime boundaries, diagrams, and agent-oriented change guidance.",
        unresolved=unresolved,
        placeholder_scan=content,
    )


def _render_dependencies(
    graph: dict[str, Any],
    *,
    workspace_path: Path,
    collection_path: Path,
) -> dict[str, Any]:
    assertions = _doc_assertions(graph, "dependencies")
    unresolved = _doc_unresolved(graph, "dependencies")
    dependency_nodes = [node for node in graph.get("nodes", []) if node.get("kind") == "dependency"]
    python_prod = [node for node in dependency_nodes if node["properties"].get("ecosystem") == "python" and node["properties"].get("bucket") == "production"]
    python_dev = [node for node in dependency_nodes if node["properties"].get("ecosystem") == "python" and node["properties"].get("bucket") == "dev"]
    node_prod = [node for node in dependency_nodes if node["properties"].get("ecosystem") == "node" and node["properties"].get("bucket") == "production"]
    node_dev = [node for node in dependency_nodes if node["properties"].get("ecosystem") == "node" and node["properties"].get("bucket") == "dev"]

    content = "\n".join(
        [
            "# Dependencies",
            "",
            "This blocking dependency view is rendered from the shared deterministic evidence graph.",
            "",
            "## Overview",
            "",
            _render_section_paragraphs(assertions, "Overview")
            + " This keeps the blocking dependency view tied to the same manifests that the freshness gate hashes during validation, and it makes the inventory safe to compare across onboarding reruns.",
            "",
            "## Boundaries",
            "",
            _render_section_paragraphs(assertions, "Boundaries")
            + " Generated prose does not own package intent; the manifests and lock surfaces do.",
            "",
            "## Invariants",
            "",
            _render_section_bullets(assertions, "Invariants"),
            "- Runtime-facing dependency changes must remain visible in the evidence graph before the KB is considered fresh.",
            "",
            "## Evidence",
            "",
            "This evidence groups manifests and dependency buckets by ecosystem so operators can see which checked-in packages shape runtime behavior, test harnesses, and local build tooling before changing manifests.",
            "",
            "### Declared manifests",
            "",
            *[f"- `{path}`" for path in sorted(_manifest_paths(graph))],
            "",
            "### Python production dependencies",
            "",
            *_dependency_lines(python_prod),
            "",
            "### Python development dependencies",
            "",
            *_dependency_lines(python_dev),
            "",
            "### Node production dependencies",
            "",
            *_dependency_lines(node_prod),
            "",
            "### Node development dependencies",
            "",
            *_dependency_lines(node_dev),
            "",
            "## Change guidance",
            "",
            _render_section_paragraphs(assertions, "Change guidance"),
        ]
    ).strip() + "\n"
    return _rendered_doc_payload(
        title="Dependencies",
        doc_slug="dependencies",
        graph=graph,
        workspace_path=workspace_path,
        collection_path=collection_path,
        content=content,
        tags=["dependencies", "packages", "runtime", "system-docs", "seed"],
        wikilinks=["Technology Stack", "Configuration"],
        card_summary="Graph-backed dependency inventory grouped by manifest, ecosystem, and production-versus-dev scope.",
        detail_summary="Renders the authoritative dependency inventory from the shared evidence graph so manifest ownership and freshness checks stay deterministic.",
        unresolved=unresolved,
        placeholder_scan=content,
    )


def _render_technology_stack(
    graph: dict[str, Any],
    *,
    workspace_path: Path,
    collection_path: Path,
) -> dict[str, Any]:
    assertions = _doc_assertions(graph, "technology-stack")
    unresolved = _doc_unresolved(graph, "technology-stack")
    languages = sorted(node["label"] for node in graph.get("nodes", []) if node.get("kind") == "language")
    frameworks = sorted(node["label"] for node in graph.get("nodes", []) if node.get("kind") == "framework")
    production_deps = [
        node for node in graph.get("nodes", [])
        if node.get("kind") == "dependency" and node.get("properties", {}).get("bucket") == "production"
    ]
    framework_or_runtime_lines = (
        [f"- `{framework}`" for framework in frameworks]
        or _dependency_lines(production_deps[:6])
    )
    manifest_nodes = [
        node for node in graph.get("nodes", [])
        if node.get("kind") == "manifest" and node.get("properties", {}).get("path")
    ]
    manifest_lines = [
        f"- `{node['properties'].get('path')}`"
        for node in manifest_nodes[:10]
        if node.get("properties", {}).get("path")
    ] or ["- No manifests detected"]

    content = "\n".join(
        [
            "# Technology Stack",
            "",
            "This blocking stack view is rendered from the shared deterministic evidence graph.",
            "",
            "## Overview",
            "",
            _render_section_paragraphs(assertions, "Overview")
            + " It is rendered from manifests and deterministic runtime signals rather than broad narrative inference, so missing framework detection still falls back to the concrete runtime packages actually declared in the repo.",
            "",
            "## Boundaries",
            "",
            _render_section_paragraphs(assertions, "Boundaries"),
            "",
            "## Invariants",
            "",
            _render_section_bullets(assertions, "Invariants"),
            "- Stack changes must preserve explicit ownership between manifests, entrypoints, and persistence surfaces.",
            "",
            "## Evidence",
            "",
            "The evidence below groups language, framework, manifest, and representative package signals so the stack view stays useful even when framework detection is sparse and runtime packages carry most of the signal. Read these sections together before changing manifests, framework layers, or deployment assumptions.",
            "",
            "### Languages",
            "",
            *[f"- `{language}`" for language in languages],
            "",
            "### Frameworks and runtime packages",
            "",
            *framework_or_runtime_lines,
            "",
            "### Declared manifests",
            "",
            *manifest_lines,
            "",
            "### Representative production packages",
            "",
            *[
                f"- `{node['label']}`"
                + (f" (`{node['properties'].get('version')}`)" if node["properties"].get("version") else "")
                + (
                    f" - {node['properties'].get('purpose')}"
                    if node["properties"].get("purpose")
                    else ""
                )
                for node in production_deps[:12]
            ],
            "",
            "## Change guidance",
            "",
            _render_section_paragraphs(assertions, "Change guidance"),
        ]
    ).strip() + "\n"
    return _rendered_doc_payload(
        title="Technology Stack",
        doc_slug="technology-stack",
        graph=graph,
        workspace_path=workspace_path,
        collection_path=collection_path,
        content=content,
        tags=["technology", "stack", "runtime", "system-docs", "seed"],
        wikilinks=["Code Structure", "Configuration", "Dependencies"],
        card_summary="Graph-backed runtime stack view covering languages, frameworks, and representative production packages.",
        detail_summary="Renders the authoritative stack summary from the shared evidence graph so runtime technologies and framework signals stay deterministic.",
        unresolved=unresolved,
        placeholder_scan=content,
    )


def _rendered_doc_payload(
    *,
    title: str,
    doc_slug: str,
    graph: dict[str, Any],
    workspace_path: Path,
    collection_path: Path,
    content: str,
    tags: list[str],
    wikilinks: list[str],
    card_summary: str,
    detail_summary: str,
    unresolved: list[dict[str, Any]],
    placeholder_scan: str,
) -> dict[str, Any]:
    manifest_rel_path = f".evidence/{doc_slug}.json"
    dependency_hash = str(graph.get("dependency_hash", ""))
    dependency_inputs = list(graph.get("dependency_inputs") or _graph_dependencies(graph))
    source_commit = graph.get("source_commit")
    assertion_claims = []
    for assertion in _doc_assertions(graph, doc_slug):
        assertion_claims.append(
            {
                "section": assertion["section"],
                "text": assertion["text"],
                "claim_type": assertion["claim_type"],
                "citations": assertion["citations"],
            }
        )
    manifest = {
        "doc": doc_slug,
        "source_commit": source_commit,
        "extractor_version": GRAPH_EXTRACTOR_VERSION,
        "dependency_hash": dependency_hash,
        "dependencies": sorted(dependency_inputs),
        "claims": assertion_claims,
        "unresolved_claims": [
            {
                "doc": item["doc_slug"],
                "section": item["section"],
                "claim": item["message"],
                "reason": "unresolved_graph_item",
                "citations": item.get("citations", []),
            }
            for item in unresolved
        ],
        "contradicted_claims": [],
        "claim_types": sorted({assertion["claim_type"] for assertion in assertion_claims}),
        "graph_artifact": GRAPH_ARTIFACT_RELATIVE_PATH,
        "workspace_profile": graph.get("workspace_profile"),
        "placeholder_scan": [marker for marker in _PLACEHOLDER_MARKERS if marker.lower() in placeholder_scan.lower()],
        "render_status": {
            "doc_slug": doc_slug,
            "rendered_from_graph": True,
            "assertion_count": len(assertion_claims),
            "unresolved_count": len(unresolved),
        },
    }
    manifest_path = collection_path / manifest_rel_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "title": title,
        "content": content,
        "tags": tags,
        "doc_type": "system-docs",
        "card_summary": card_summary,
        "detail_summary": detail_summary,
        "verified": True,
        "authoritative": True,
        "evidence_manifest": manifest_rel_path,
        "graph_artifact": GRAPH_ARTIFACT_RELATIVE_PATH,
        "workspace_profile": graph.get("workspace_profile"),
        "source_commit": source_commit,
        "extractor_version": GRAPH_EXTRACTOR_VERSION,
        "dependency_hash": dependency_hash,
        "render_status": manifest["render_status"],
        "preserve_content": True,
        "wikilinks": wikilinks,
    }


def _doc_assertions(graph: dict[str, Any], doc_slug: str) -> list[dict[str, Any]]:
    return sorted(
        [item for item in graph.get("assertions", []) if item.get("doc_slug") == doc_slug],
        key=lambda item: item.get("id", ""),
    )


def _doc_unresolved(graph: dict[str, Any], doc_slug: str) -> list[dict[str, Any]]:
    return sorted(
        [item for item in graph.get("unresolved_items", []) if item.get("doc_slug") == doc_slug],
        key=lambda item: item.get("id", ""),
    )


def _entrypoint_paths(graph: dict[str, Any]) -> list[str]:
    return sorted(
        node.get("properties", {}).get("path")
        for node in graph.get("nodes", [])
        if node.get("kind") == "entrypoint" and node.get("properties", {}).get("path")
    )


def _manifest_paths(graph: dict[str, Any]) -> list[str]:
    return sorted(
        node.get("properties", {}).get("path")
        for node in graph.get("nodes", [])
        if node.get("kind") == "manifest" and node.get("properties", {}).get("path")
    )


def _graph_dependencies(graph: dict[str, Any]) -> list[str]:
    dependency_paths: set[str] = set()
    for node in graph.get("nodes", []):
        for citation in node.get("evidence", []):
            path = citation.get("path")
            if isinstance(path, str) and path and path != ".":
                dependency_paths.add(path)
    return sorted(dependency_paths)


def _render_section_paragraphs(assertions: list[dict[str, Any]], section: str) -> str:
    texts = [item["text"] for item in assertions if item.get("section") == section]
    return "\n\n".join(texts) if texts else "No deterministic evidence was available for this section."


def _render_section_bullets(assertions: list[dict[str, Any]], section: str) -> str:
    texts = [item["text"] for item in assertions if item.get("section") == section]
    return "\n".join(f"- {text}" for text in texts) if texts else "- No deterministic evidence was available."


def _dependency_lines(nodes: list[dict[str, Any]]) -> list[str]:
    if not nodes:
        return ["- None detected"]
    return [
        f"- `{node['label']}`"
        + (f" (`{node['properties'].get('version')}`)" if node["properties"].get("version") else "")
        + (f" - {node['properties'].get('purpose')}" if node["properties"].get("purpose") else "")
        for node in nodes
    ]


def _profile_summary(profile: str, frameworks: set[str]) -> str:
    if profile == "polyglot_web_app":
        return (
            "This repository is a polyglot web application with a Python runtime, API surfaces, and a separate frontend/tooling layer captured in the shared evidence graph."
        )
    if profile == "python_fastapi_service":
        return (
            "This repository is a Python FastAPI service whose API routes, manifests, and runtime entrypoints are captured in the shared evidence graph."
        )
    if profile == "python_cli_app":
        return (
            "This repository is a Python CLI-oriented application whose command groups, manifests, and runtime entrypoints are captured in the shared evidence graph."
        )
    framework_phrase = ", ".join(sorted(frameworks)) if frameworks else "checked-in manifests and entrypoints"
    return (
        f"This repository is reconstructed as a generic codebase whose runtime signals come from {framework_phrase} and the checked-in entrypoints."
    )


def _profile_user_mental_model(profile: str) -> str:
    if profile == "polyglot_web_app":
        return "Operators change manifests and backend wiring in one lane, while the frontend remains a separate but connected runtime surface."
    if profile == "python_fastapi_service":
        return "Operators should think of this repo as a service: manifests define the stack, entrypoints boot the runtime, and registered routes define the live API surface."
    if profile == "python_cli_app":
        return "Operators should think of this repo as a CLI-first runtime: manifests define the stack and command registration defines the user-facing behavior."
    return "Operators should start from checked-in manifests and entrypoints, then trace outward into routes, commands, and persistence surfaces."


def _technology_summary(languages: set[str], frameworks: set[str]) -> str:
    language_phrase = ", ".join(sorted(languages)) if languages else "no detected languages"
    framework_phrase = ", ".join(sorted(frameworks)) if frameworks else "no detected frameworks"
    return (
        f"The extracted stack signals show {language_phrase} with framework and runtime packages including {framework_phrase}."
    )


def _stable_generated_at(workspace_path: Path, dependencies: list[str]) -> str:
    mtimes: list[int] = []
    for dependency in dependencies:
        abs_path = workspace_path / dependency
        if abs_path.exists():
            mtimes.append(abs_path.stat().st_mtime_ns)
    if not mtimes:
        return "1970-01-01T00:00:00+00:00"
    latest = max(mtimes)
    return datetime.fromtimestamp(latest / 1_000_000_000, tz=UTC).isoformat()


def _write_compatibility_sqlite(collection_path: Path, graph: EvidenceGraph) -> None:
    sqlite_path = collection_path / ".evidence" / "system-architecture.sqlite3"
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(sqlite_path)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                label TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS graph_edges (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                target TEXT NOT NULL
            );
            DELETE FROM graph_nodes;
            DELETE FROM graph_edges;
            """
        )
        connection.executemany(
            "INSERT INTO graph_nodes (id, kind, label) VALUES (?, ?, ?)",
            [(node.id, node.kind, node.label) for node in graph.nodes],
        )
        connection.executemany(
            "INSERT INTO graph_edges (id, kind, source, target) VALUES (?, ?, ?, ?)",
            [(edge.id, edge.kind, edge.source, edge.target) for edge in graph.edges],
        )
        connection.commit()
    finally:
        connection.close()


def _relative_path(workspace_path: Path, path: Path) -> str:
    return str(path.relative_to(workspace_path)).replace("\\", "/")


def _is_excluded(relative_path: str) -> bool:
    return any(
        part in {".claude", ".agent-builder", ".git", ".venv", "node_modules", "dist", "build", "__pycache__"}
        or part.startswith(".agent-builder.archive-")
        for part in Path(relative_path).parts
    )


def _sort_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in sorted(value)}


def _parse_dep_string(dep: str) -> tuple[str | None, str | None]:
    candidate = dep.split(";", 1)[0].strip()
    if not candidate or candidate.startswith("#"):
        return None, None
    if "[" in candidate:
        candidate = candidate.split("[", 1)[0]
    for sep in ("==", ">=", "<=", "~=", ">", "<"):
        if sep in candidate:
            name, version = candidate.split(sep, 1)
            return name.strip(), version.strip()
    return candidate.strip(), None


def _normalize_route_path(prefix: str, path: str) -> str:
    joined = "/".join(
        part.strip("/")
        for part in (prefix, path)
        if part and part.strip("/")
    )
    return "/" + joined if joined else "/"


def _keyword_str(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


def _table_paths(paths: list[str]) -> str:
    return ", ".join(f"`{path}`" for path in paths) if paths else "No explicit owning surface detected"


def _diagram_label(paths: list[str]) -> str:
    return "\\n".join(paths) if paths else "No entrypoints detected"


def _unique_property_values(graph: dict[str, Any], kind: str, prop: str) -> list[str]:
    return sorted(
        {
            node.get("properties", {}).get(prop)
            for node in graph.get("nodes", [])
            if node.get("kind") == kind and node.get("properties", {}).get(prop)
        }
    )
