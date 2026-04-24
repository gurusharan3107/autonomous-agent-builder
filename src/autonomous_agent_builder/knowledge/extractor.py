"""Knowledge extractor for deterministic seed system-doc generation."""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import tomli
except ImportError:
    import tomllib as tomli  # Python 3.11+

from autonomous_agent_builder.config import get_settings

from .evidence_graph import (
    BLOCKING_DOCS as GRAPH_BLOCKING_DOCS,
    GRAPH_ARTIFACT_RELATIVE_PATH,
    build_shared_evidence_graph,
)
from .generators import (
    AgentSystemGenerator,
    APIEndpointsGenerator,
    ArchitectureGenerator,
    BusinessOverviewGenerator,
    CodeStructureGenerator,
    ConfigurationGenerator,
    DatabaseModelsGenerator,
    DependenciesGenerator,
    ProjectOverviewGenerator,
    TechnologyStackGenerator,
    WorkflowsGenerator,
)
from .publisher import PublishError, publish_document
from .proof_contract import (
    CORE_TARGET_DOCS,
    build_repo_index,
    repo_looks_like_builder_repo,
)

SYSTEM_DOC_SEED_TAGS: dict[str, list[str]] = {
    "project overview": ["overview", "project", "delivery-system", "system-docs", "seed"],
    "technology stack": ["technology", "stack", "runtime", "system-docs", "seed"],
    "dependencies": ["dependencies", "packages", "runtime", "system-docs", "seed"],
    "system architecture": ["architecture", "design", "runtime", "system-docs", "seed"],
    "code structure": ["code-structure", "organization", "ownership", "system-docs", "seed"],
    "database models": ["database", "models", "schema", "system-docs", "seed"],
    "api endpoints": ["api", "endpoints", "http", "system-docs", "seed"],
    "business overview": ["business", "domain", "workflow", "system-docs", "seed"],
    "workflows and orchestration": ["workflows", "orchestration", "phases", "system-docs", "seed"],
    "configuration": ["configuration", "settings", "environment", "system-docs", "seed"],
    "agent system": ["agents", "tools", "hooks", "system-docs", "seed"],
}

SYSTEM_DOC_SEED_RELATED_DOCS: dict[str, list[str]] = {
    "Project Overview": ["System Architecture", "Technology Stack", "Workflows and Orchestration"],
    "Technology Stack": ["Code Structure", "Configuration", "Dependencies"],
    "Dependencies": ["Technology Stack", "Configuration"],
    "System Architecture": ["Code Structure", "API Endpoints", "Agent System"],
    "Code Structure": ["System Architecture", "Agent System", "Configuration"],
    "Database Models": ["API Endpoints", "System Architecture"],
    "API Endpoints": ["System Architecture", "Configuration", "Database Models"],
    "Business Overview": ["Project Overview", "Workflows and Orchestration"],
    "Workflows and Orchestration": ["Agent System", "Project Overview", "System Architecture"],
    "Configuration": ["Technology Stack", "API Endpoints", "Agent System"],
    "Agent System": ["Workflows and Orchestration", "Configuration", "Code Structure"],
}

SYSTEM_DOC_SEED_PROFILES: dict[str, dict[str, str]] = {
    "project overview": {
        "card_focus": "Project purpose, operating model, and what this repository is built to deliver.",
        "detail_focus": "Use this document to orient around the product purpose, operator workflow, and repository shape that define the autonomous delivery system.",
        "overview_focus": "The repository centers on an autonomous delivery system that turns scoped work into orchestrated planning, implementation, review, and verification flows. It gives operators and agents one controlled path from request intake to code change, quality checks, and publishable project knowledge.",
        "evidence_focus": "Highlight the repo signals that prove the delivery model, ownership shape, and core execution path.",
        "boundary_focus": "Primary boundaries include the product surface, operator workflow, and repository ownership split across the core delivery modules.",
        "invariant_focus": "Keep the autonomous delivery framing, operator workflow, and ownership boundaries consistent when changing this surface.",
        "invariant_points": "Keep the product purpose aligned with the autonomous delivery workflow.|Preserve the repo surface split between runtime, dashboard, and knowledge support layers.",
    },
    "technology stack": {
        "card_focus": "Runtime technologies, primary frameworks, and persistence choices that define the stack.",
        "detail_focus": "Use this document to orient around the runtime stack, core frameworks, libraries, and storage choices that shape development and deployment.",
        "overview_focus": "The system is built on a Python backend, a React dashboard, and supporting persistence and tooling layers that shape how changes are developed and shipped. Together these runtime pieces define how the product serves APIs, stores state, renders operator controls, and supports local developer workflows.",
        "evidence_focus": "Call out concrete languages, frameworks, databases, and supporting libraries from the codebase.",
        "boundary_focus": "Primary boundaries include runtime languages, framework layers, and persistence choices that other surfaces depend on.",
        "invariant_focus": "Preserve the documented runtime stack and dependency intent unless the underlying implementation or deployment model changes.",
        "invariant_points": "Keep backend, frontend, and persistence technology choices consistent with the owning runtime surfaces.|Verify stack changes against dependency manifests and deployment assumptions.",
    },
    "dependencies": {
        "card_focus": "Critical package groups, tooling dependencies, and what they enable in the build.",
        "detail_focus": "Use this document to orient around the important runtime and development dependencies, grouped by what they enable for operators and contributors.",
        "overview_focus": "This surface explains which runtime and tooling dependencies the repository relies on and what capability each dependency group enables. Read it to see which packages power the backend, dashboard, quality gates, and local operator workflow before changing manifests or build assumptions.",
        "evidence_focus": "Reference package managers, dependency groups, and notable libraries discovered in manifests or lockfiles.",
        "boundary_focus": "Primary boundaries include runtime packages, development tooling, and dependency groups used by the build and dashboard.",
        "invariant_focus": "Keep dependency changes scoped, verified, and aligned with the owning manifests or lockfiles.",
        "invariant_points": "Change dependency intent only through the owning manifest or lockfile.|Validate dependency updates against the surfaces they enable before broadening the blast radius.",
    },
    "system architecture": {
        "card_focus": "System layers, service boundaries, and how the major runtime surfaces connect.",
        "detail_focus": "Use this document to orient around the architecture layers, runtime boundaries, and how backend, dashboard, storage, and orchestration surfaces interact.",
        "overview_focus": "The architecture separates backend APIs, dashboard reading surfaces, persistence, and orchestration responsibilities so each layer has a clear role. That split keeps routing, storage, UI behavior, and task execution understandable when features evolve or debugging crosses multiple modules.",
        "evidence_focus": "Surface the concrete modules, route groups, runtime layers, and integration boundaries visible in the repository.",
        "boundary_focus": "Primary boundaries include backend APIs, dashboard surfaces, persistence layers, and orchestration flow ownership.",
        "invariant_focus": "Preserve layer boundaries and integration contracts so architectural responsibilities do not drift between modules.",
        "invariant_points": "Keep layer ownership explicit so routing, persistence, and UI concerns do not collapse together.|Preserve integration contracts between backend, dashboard, and orchestration surfaces.",
    },
    "code structure": {
        "card_focus": "Top-level modules, ownership boundaries, and where core logic lives in the repo.",
        "detail_focus": "Use this document to orient around how source code is organized, which directories own each surface, and where operators should look for key behaviors.",
        "overview_focus": "The repository is organized so backend logic, dashboard code, and knowledge or memory support surfaces can be changed with a clear ownership model. The folder layout is meant to make runtime code, operator UI, and documentation-supporting systems inspectable without rediscovering boundaries on each task.",
        "evidence_focus": "Use directory names, module boundaries, and code ownership clues as the proof surface.",
        "boundary_focus": "Primary boundaries include top-level packages, dashboard code, backend code, and knowledge or memory support surfaces.",
        "invariant_focus": "Preserve ownership boundaries so code changes stay in the right module and retrieval surfaces remain predictable.",
        "invariant_points": "Keep edits inside the owning module instead of spreading one concern across multiple directories.|Preserve the current ownership split so retrieval and maintenance remain predictable.",
    },
    "database models": {
        "card_focus": "Persisted entities, schema relationships, and what state the runtime stores.",
        "detail_focus": "Use this document to orient around the main models, stored entities, and relationships that matter for tasks, approvals, runs, and memory.",
        "overview_focus": "This surface explains which entities the runtime persists and how those records support tasks, approvals, runs, and memory-related behavior. Use it to understand which database records back workflow state, operator visibility, and the historical artifacts that the builder keeps across executions.",
        "evidence_focus": "Reference concrete models, fields, and persistence flows found in schema or ORM code.",
        "boundary_focus": "Primary boundaries include persisted entities, relationship edges, and the runtime surfaces that read or mutate them.",
        "invariant_focus": "Preserve model relationships and field semantics that other runtime surfaces or migrations rely on.",
        "invariant_points": "Preserve entity relationships that downstream queries, workflows, or approvals depend on.|Change field meaning only with matching updates to callers, persistence, and migrations.",
    },
    "api endpoints": {
        "card_focus": "Route groups, operational actions, and the backend surfaces exposed over HTTP.",
        "detail_focus": "Use this document to orient around the API surface by route group, including the operator actions, dashboard reads, and workflow mutations each group exposes.",
        "overview_focus": "The API surface is grouped by route family so operator actions, dashboard reads, and workflow mutations remain understandable and controllable. Each route cluster maps to a product responsibility, which helps when tracing UI actions back to backend state changes or permissioned mutations.",
        "evidence_focus": "Use concrete paths, route families, and request or response behavior as the proof surface.",
        "boundary_focus": "Primary boundaries include route groups, mutation versus read surfaces, and the caller workflows that depend on them.",
        "invariant_focus": "Preserve route intent, payload shape, and read or write semantics unless the owning callers change too.",
        "invariant_points": "Keep route-family ownership clear between read surfaces and mutation surfaces.|Preserve request and response intent for callers unless the dependent workflows are updated too.",
    },
    "business overview": {
        "card_focus": "Product purpose, user workflow, and the delivery model reflected in the codebase.",
        "detail_focus": "Use this document to orient around the business goal, primary users, and delivery workflow the product and repository are designed to support.",
        "overview_focus": "The product surface is designed around a delivery workflow where operators coordinate autonomous implementation through visible control and review surfaces. Business intent in this repo is expressed through approvals, task progression, and evidence-backed readiness rather than through a generic CRUD application model.",
        "evidence_focus": "Tie the product story to concrete features, interfaces, and workflow surfaces present in the repo.",
        "boundary_focus": "Primary boundaries include user-facing flows, operator workflows, and repository surfaces that deliver the product promise.",
        "invariant_focus": "Preserve the product intent and user workflow assumptions encoded in the current features and orchestration.",
        "invariant_points": "Keep the operator workflow aligned with the product purpose the repository is trying to serve.|Preserve user-facing assumptions unless the corresponding flow and surfaces are intentionally redesigned.",
    },
    "workflows and orchestration": {
        "card_focus": "Execution phases, dispatch rules, and agent handoffs that move work through the pipeline.",
        "detail_focus": "Use this document to orient around execution phases, orchestrator routing, and the agent handoffs or retries that move work through the pipeline.",
        "overview_focus": "The orchestration layer moves work through fixed execution phases under orchestrator-owned routing, with explicit handoffs and controlled retry behavior. This document explains how planning, implementation, validation, and recovery connect so operators can reason about state transitions and failure handling.",
        "evidence_focus": "Reference phases, orchestration patterns, routing logic, and recovery behavior found in the codebase.",
        "boundary_focus": "Primary boundaries include execution phases, orchestrator routing decisions, and the handoff points between agent roles.",
        "invariant_focus": "Preserve phase ordering, orchestrator-owned routing, and retry or recovery behavior that downstream automation expects.",
        "invariant_points": "Keep execution phases ordered and explicit rather than letting work skip the orchestrator.|Preserve orchestrator-owned routing so agents do not self-route or blur role boundaries.",
    },
    "configuration": {
        "card_focus": "Environment settings, config files, and runtime switches that shape app behavior.",
        "detail_focus": "Use this document to orient around environment variables, config files, defaults, and runtime flags that shape app behavior.",
        "overview_focus": "Configuration determines how runtime behavior changes across environments, defaults, and feature toggles without requiring code changes for every operational shift. It is the main control surface for model choice, runtime endpoints, database access, and other environment-sensitive behavior.",
        "evidence_focus": "Reference actual config classes, files, and runtime toggles used by the repository.",
        "boundary_focus": "Primary boundaries include environment variables, config files, and runtime defaults consumed by backend and dashboard surfaces.",
        "invariant_focus": "Preserve the current config precedence and naming so runtime behavior remains predictable across environments.",
        "invariant_points": "Keep config precedence predictable between defaults, files, and environment overrides.|Preserve configuration naming and ownership so runtime behavior remains debuggable.",
    },
    "agent system": {
        "card_focus": "Agent roles, tool access, and how responsibilities split across the delivery system.",
        "detail_focus": "Use this document to orient around the agent model, role boundaries, and tool access patterns that coordinate planning, design, implementation, and review.",
        "overview_focus": "The agent system coordinates distinct roles with explicit responsibilities, tool access, and turn budgets so the delivery workflow stays safe and understandable. Its design keeps planning, implementation, review, and supporting automation separated enough that operators can inspect who owns each kind of action.",
        "evidence_focus": "Use concrete agent definitions, tools, turn limits, and orchestration hooks as the proof surface.",
        "boundary_focus": "Primary boundaries include agent roles, tool access, turn limits, and the orchestration hooks that coordinate them.",
        "invariant_focus": "Preserve role separation, tool permissions, and orchestrator control so agents do not drift into unsafe ownership.",
        "invariant_points": "Keep role separation explicit so planning, design, implementation, and review do not collapse into one undifferentiated agent.|Preserve tool permissions and orchestrator control when changing role behavior.",
    },
    "extraction metadata": {
        "card_focus": "Generated artifact inventory, extraction timing, and what changed in this run.",
        "detail_focus": "Use this document to orient around when extraction ran, what artifacts were generated, and how an operator should use or refresh the set.",
        "overview_focus": "This metadata record explains what the extraction run produced, when it ran, and how to interpret the current generated knowledge set. It is the audit surface for generated files, extraction health, and follow-up work when publication or validation does not complete cleanly.",
        "evidence_focus": "List generated documents, timestamps, and any extraction errors or follow-up actions.",
        "boundary_focus": "Primary boundaries include the extraction run, generated artifacts, and any errors surfaced during publication.",
        "invariant_focus": "Preserve the generated artifact inventory and extraction timestamps so operators can trust what changed in the run.",
        "invariant_points": "Keep the generated artifact inventory aligned with the actual extraction output.|Preserve timestamps and error reporting so operators can trust what changed in the run.",
    },
}


class KnowledgeExtractor:
    """Extract deterministic seed system docs for the local repository."""

    GENERATOR_SPECS = [
        ("project-overview", ProjectOverviewGenerator),
        ("technology-stack", TechnologyStackGenerator),
        ("dependencies", DependenciesGenerator),
        ("system-architecture", ArchitectureGenerator),
        ("code-structure", CodeStructureGenerator),
        ("database-models", DatabaseModelsGenerator),
        ("api-endpoints", APIEndpointsGenerator),
        ("business-overview", BusinessOverviewGenerator),
        ("workflows-and-orchestration", WorkflowsGenerator),
        ("configuration", ConfigurationGenerator),
        ("agent-system", AgentSystemGenerator),
    ]

    def __init__(
        self,
        workspace_path: Path,
        output_path: Path,
        *,
        doc_slugs: list[str] | None = None,
    ):
        """Initialize extractor.

        Args:
            workspace_path: Root directory of the project to analyze
            output_path: Directory to write extracted knowledge docs
        """
        self.workspace_path = workspace_path.resolve()
        self.output_path = output_path.resolve()
        self.output_collection = self._output_collection()
        self.doc_slugs = {slug.strip().lower() for slug in (doc_slugs or []) if slug.strip()}
        self._generator_slugs: dict[int, str] = {}
        self._builder_repo = repo_looks_like_builder_repo(self.workspace_path)
        self._shared_graph: dict[str, Any] | None = None

        # Initialize generators (order matters - overview first, details later)
        self.generators = []
        for slug, generator_cls in self.GENERATOR_SPECS:
            generator = generator_cls(workspace_path, output_path=self.output_path)
            self.generators.append(generator)
            self._generator_slugs[id(generator)] = slug

    def extract(self, scope: str = "full") -> dict[str, Any]:
        """Extract knowledge and write markdown files."""
        self.output_path.mkdir(parents=True, exist_ok=True)
        build_repo_index(self.workspace_path, self.output_path)
        self._shared_graph = None

        documents: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        expected_docs = self.expected_doc_slugs()

        unknown_docs = sorted(self.doc_slugs - expected_docs)
        if unknown_docs:
            raise ValueError(
                "Unsupported KB document slug(s): "
                + ", ".join(unknown_docs)
            )

        requested_docs = set(self.doc_slugs) if self.doc_slugs else expected_docs
        if requested_docs & set(GRAPH_BLOCKING_DOCS):
            self._shared_graph = build_shared_evidence_graph(self.workspace_path, self.output_path)
            for generator in self.generators:
                generator.shared_graph = self._shared_graph

        for generator in self.generators:
            generator_slug = self._generator_slugs.get(id(generator))
            if self.doc_slugs and generator_slug not in self.doc_slugs:
                continue
            try:
                doc = generator.generate(scope=scope)
                if not doc:
                    continue

                normalized = self._normalize_doc(doc)
                filename = self._get_filename(normalized["title"])
                try:
                    self._write_doc(filename, normalized)
                except PublishError as exc:
                    if " is unchanged." not in str(exc):
                        raise
                documents.append(
                    {
                        "type": normalized.get("doc_type", "unknown"),
                        "title": normalized["title"],
                        "filename": filename,
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive extraction lane
                errors.append(
                    {
                        "generator": generator.__class__.__name__,
                        "slug": generator_slug,
                        "error": str(exc),
                    }
                )

        generated_doc_slugs = sorted(
            {
                Path(str(document.get("filename", ""))).stem
                for document in documents
                if document.get("filename")
            }
        )
        existing_doc_slugs = sorted(
            path.stem
            for path in self.output_path.glob("*.md")
            if path.stem != "extraction-metadata"
        )
        expected_for_run = (
            sorted({*existing_doc_slugs, *generated_doc_slugs})
            if self.doc_slugs
            else generated_doc_slugs
        )
        if not expected_for_run:
            expected_for_run = sorted(expected_docs)
        configured_blocking_docs = get_settings().kb_blocking_docs
        blocking_for_run = [doc for doc in configured_blocking_docs if doc in expected_for_run]
        non_blocking_for_run = [
            doc
            for doc in CORE_TARGET_DOCS
            if doc not in blocking_for_run and doc in expected_for_run
        ]

        self._write_metadata(
            documents,
            errors,
            expected_documents=expected_for_run,
            blocking_documents=blocking_for_run,
            non_blocking_documents=non_blocking_for_run,
        )

        return {
            "documents": documents,
            "output_path": str(self.output_path),
            "errors": errors,
            "graph": self._shared_graph,
        }

    @classmethod
    def expected_doc_slugs(cls) -> set[str]:
        return {slug for slug, _generator_cls in cls.GENERATOR_SPECS}

    def _output_collection(self) -> str:
        """Return the collection path relative to .agent-builder/knowledge."""
        try:
            knowledge_root = self.output_path.parent.resolve()
            return str(self.output_path.relative_to(knowledge_root)).replace("\\", "/")
        except ValueError:
            return self.output_path.name

    def _get_filename(self, title: str) -> str:
        """Convert title to safe filename."""
        filename = title.lower().replace(" ", "-")
        filename = "".join(c for c in filename if c.isalnum() or c in "-_")
        return f"{filename}.md"

    def _normalize_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Normalize generator output into the canonical ingestion contract."""
        normalized = dict(doc)
        doc_type = str(normalized.get("doc_type", "system-docs")).strip().lower()
        if doc_type == "reverse-engineering":
            doc_type = "system-docs"
            normalized["doc_type"] = doc_type
        title = str(normalized["title"]).strip()
        content = str(normalized.get("content", "")).strip()
        preserve_content = bool(normalized.get("preserve_content"))

        if doc_type == "system-docs":
            if preserve_content:
                normalized["content"] = content
            else:
                normalized["content"] = self._normalize_reverse_engineering_content(title, content)
            normalized.setdefault("card_summary", self._build_card_summary(title, content))
            normalized.setdefault("detail_summary", self._build_detail_summary(title, content))
            normalized.setdefault("doc_family", "seed")
            normalized.setdefault("refresh_required", False)
            # Canonical seed system docs own their tags and related links.
            normalized["tags"] = self._reverse_engineering_tags(title)
            normalized["wikilinks"] = self._reverse_engineering_wikilinks(title)
        elif doc_type == "metadata":
            normalized["content"] = self._normalize_metadata_content(title, content)
            normalized["card_summary"] = "Generated artifact inventory, extraction timing, and what changed in this run."
            normalized["detail_summary"] = (
                "Summarizes when extraction ran, which seed system docs were published, and what an operator should rerun or inspect next."
            )

        return normalized

    def _sanitize_reverse_engineering_text(self, text: str) -> str:
        """Remove template boilerplate that the specificity gate rejects."""
        cleaned = text
        replacements = {
            "This document describes": "This surface explains",
            " (if applicable)": "",
            "(if applicable)": "",
            "if applicable": "",
            (
                "It frames the capability first so users and agents can decide where to "
                "read next before dropping into code-level proof."
            ): "",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)

        normalized_lines: list[str] = []
        for line in cleaned.splitlines():
            line = re.sub(r"\s+\(\)", "", line)
            line = re.sub(r"\s+([,.;:])", r"\1", line)
            line = re.sub(r" {2,}", " ", line).rstrip()
            normalized_lines.append(line)

        cleaned = "\n".join(normalized_lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _doc_profile(self, title: str) -> dict[str, str]:
        return SYSTEM_DOC_SEED_PROFILES.get(
            title.strip().lower(),
            {
                "card_focus": f"Repository-specific findings, structure, and operator-relevant details for {title.lower()}.",
                "detail_focus": f"Use this document to orient around what {title.lower()} covers in the repository and why an operator would read it.",
                "overview_focus": f"This document explains the core capability, surface behavior, and repository role of {title.lower()}.",
                "evidence_focus": "Use concrete code, config, or route evidence from the repository.",
                "boundary_focus": "Primary boundaries include the owning code paths, adjacent surfaces, and the main integration points this document covers.",
                "invariant_focus": "Preserve the documented ownership and contract boundaries unless the underlying implementation changes intentionally.",
                "invariant_points": "Keep ownership boundaries explicit when changing this surface.|Preserve dependent contracts unless the related callers and evidence change too.",
            },
        )

    def _strip_title_heading(self, title: str, content: str) -> str:
        """Remove an existing H1 matching the title if present."""
        body = content.strip()
        escaped = re.escape(title.strip())
        return re.sub(rf"^\s*#\s+{escaped}\s*\n+", "", body, count=1, flags=re.IGNORECASE)

    def _h2_sections(self, body: str) -> list[tuple[str, str]]:
        """Split a markdown body into top-level H2 sections."""
        pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(body))
        sections: list[tuple[str, str]] = []

        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            sections.append((match.group(1).strip(), body[start:end].strip()))

        return sections

    def _plain_text(self, text: str) -> str:
        """Collapse markdown into plainer text for short summaries."""
        cleaned = re.sub(r"```[\s\S]*?```", " ", text)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
        cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", cleaned)
        cleaned = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", cleaned)
        cleaned = re.sub(r"\[\[([^\]]+)\]\]", r"\1", cleaned)
        cleaned = re.sub(r"^#+\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _first_sentence(self, text: str, max_words: int = 20) -> str:
        """Extract a concise first sentence or phrase for a finding line."""
        plain = self._plain_text(text)
        if not plain:
            return ""
        sentence = re.split(r"(?<=[.!?])\s+", plain, maxsplit=1)[0].strip()
        words = sentence.split()
        if len(words) > max_words:
            sentence = " ".join(words[:max_words]).rstrip(",;:") + "..."
        return sentence

    def _word_count(self, text: str) -> int:
        """Count words in normalized plain text."""
        plain = self._plain_text(text)
        if not plain:
            return 0
        return len(plain.split())

    def _trim_words(self, text: str, max_words: int) -> str:
        """Trim text to a target word budget."""
        plain = self._plain_text(text)
        if not plain:
            return ""
        words = plain.split()
        if len(words) <= max_words:
            return plain
        return " ".join(words[:max_words]).rstrip(",;:") + "..."

    def _join_phrases(self, phrases: list[str]) -> str:
        cleaned = [phrase.strip().rstrip(".") for phrase in phrases if phrase.strip()]
        if not cleaned:
            return ""
        if len(cleaned) == 1:
            return cleaned[0]
        if len(cleaned) == 2:
            return f"{cleaned[0]} and {cleaned[1]}"
        return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"

    def _slug_from_title(self, title: str) -> str:
        return self._get_filename(title).removesuffix(".md")

    def _reverse_engineering_tags(self, title: str) -> list[str]:
        return SYSTEM_DOC_SEED_TAGS.get(
            title.strip().lower(),
            ["system-docs", "seed", "repository", "ownership", "operator"],
        )

    def _reverse_engineering_wikilinks(self, title: str) -> list[str]:
        return SYSTEM_DOC_SEED_RELATED_DOCS.get(title.strip(), [])

    def _related_documents_block(self, title: str) -> str:
        related_titles = self._reverse_engineering_wikilinks(title)
        if not related_titles:
            return ""
        lines = ["## Related documents", ""]
        for related in related_titles:
            lines.append(f"- [{related}]({self._slug_from_title(related)}.md)")
        return "\n".join(lines)

    def _top_headings_phrase(self, sections: list[tuple[str, str]]) -> str:
        headings = [heading for heading, _ in sections if heading.strip()][:3]
        return self._join_phrases([heading.lower() for heading in headings])

    def _build_card_summary(self, title: str, content: str) -> str:
        profile = self._doc_profile(title)
        return self._trim_words(profile["card_focus"], 18)

    def _build_detail_summary(self, title: str, content: str) -> str:
        body = self._strip_title_heading(title, content)
        sections = [
            (heading, section_body)
            for heading, section_body in self._h2_sections(body)
            if self._plain_text(section_body)
        ]
        profile = self._doc_profile(title)
        detail_parts = [profile["detail_focus"]]
        heading_phrase = self._top_headings_phrase(sections)
        if heading_phrase:
            detail_parts.append(f"Focus areas: {heading_phrase}.")
        return self._trim_words(" ".join(detail_parts), 58)

    def _build_boundaries(self, title: str, sections: list[tuple[str, str]]) -> str:
        profile = self._doc_profile(title)
        return self._trim_words(
            f"{profile['boundary_focus']} Use these boundaries to understand ownership and blast radius before editing adjacent surfaces.",
            48,
        )

    def _build_invariants(self, title: str, sections: list[tuple[str, str]]) -> list[str]:
        profile = self._doc_profile(title)
        invariants: list[str] = [
            f"- {item.strip()}"
            for item in str(profile.get("invariant_points", "")).split("|")
            if item.strip()
        ]
        invariants.append(f"- {profile['invariant_focus']}")
        deduped: list[str] = []
        seen: set[str] = set()
        for item in invariants:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped[:4]

    def _read_repo_text(self, relative_path: str) -> str:
        path = self.workspace_path / relative_path
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def _python_dependencies(self) -> list[str]:
        pyproject = self.workspace_path / "pyproject.toml"
        names: list[str] = []
        if pyproject.exists():
            try:
                data = tomli.loads(pyproject.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            deps = data.get("project", {}).get("dependencies", [])
            if isinstance(deps, list):
                for dep in deps:
                    if not isinstance(dep, str):
                        continue
                    name = re.split(r"[<>=!~\[]", dep, maxsplit=1)[0].strip()
                    if name:
                        names.append(name)
        if names:
            return names

        requirement_files = ("requirements.txt", "requirements-dev.txt", "requirements/base.txt")
        for relative_path in requirement_files:
            path = self.workspace_path / relative_path
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("-r"):
                    continue
                name = re.split(r"[<>=!~\[]", stripped, maxsplit=1)[0].strip()
                if name:
                    names.append(name)
        deduped: list[str] = []
        seen: set[str] = set()
        for name in names:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(name)
        return deduped

    def _frontend_dependencies(self) -> list[str]:
        package_json = self.workspace_path / "frontend" / "package.json"
        if not package_json.exists():
            return []
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            return []
        deps = data.get("dependencies", {})
        if not isinstance(deps, dict):
            return []
        return sorted(str(name) for name in deps.keys())

    def _package_dirs(self) -> list[str]:
        src_root = self.workspace_path / "src" / "autonomous_agent_builder"
        if src_root.exists():
            packages: list[str] = []
            for path in sorted(src_root.iterdir()):
                if not path.is_dir() or path.name.startswith("__"):
                    continue
                packages.append(path.name)
            return packages

        generic_src = self.workspace_path / "src"
        if generic_src.exists():
            generic_packages: list[str] = []
            for path in sorted(generic_src.iterdir()):
                if not path.is_dir() or path.name.startswith("."):
                    continue
                if path.name in {"tests", "test", "__pycache__"}:
                    continue
                generic_packages.append(path.name)
            if generic_packages:
                return generic_packages

        fallback_dirs: list[str] = []
        for path in sorted(self.workspace_path.iterdir()):
            if not path.is_dir() or path.name.startswith("."):
                continue
            if path.name in {"tests", "test", "docs", "examples", ".agent-builder"}:
                continue
            fallback_dirs.append(path.name)
        return fallback_dirs

    def _package_purpose(self, package_name: str) -> str:
        mapping = {
            "agents": "agent definitions, tool access, and execution hooks",
            "api": "FastAPI application wiring and JSON route surfaces",
            "cli": "builder command-line surfaces",
            "dashboard": "legacy server-rendered dashboard assets",
            "db": "database models and persistence session helpers",
            "embedded": "embedded dashboard and server assets",
            "harness": "repo harnessability scoring and routing signals",
            "integrations": "external integration surfaces",
            "knowledge": "local KB generation, retrieval, and publishing",
            "observability": "logging and observability helpers",
            "orchestrator": "deterministic task-phase routing",
            "quality_gates": "lint, test, and security gate execution",
            "security": "prompt safety, permissions, and egress controls",
            "services": "application service-layer helpers",
            "workspace": "workspace and git worktree handling",
        }
        return mapping.get(package_name, "repo-owned implementation surface")

    def _settings_snapshot(self) -> list[tuple[str, str, list[str]]]:
        snapshots: list[tuple[str, str, list[str]]] = []
        config_candidates: list[Path] = []
        preferred = self.workspace_path / "src" / "autonomous_agent_builder" / "config.py"
        if preferred.exists():
            config_candidates.append(preferred)
        for pattern in ("config.py", "settings.py", "**/config.py", "**/settings.py"):
            for path in sorted(self.workspace_path.glob(pattern)):
                try:
                    rel_parts = path.relative_to(self.workspace_path).parts
                except ValueError:
                    continue
                if len(rel_parts) > 4 or path in config_candidates:
                    continue
                config_candidates.append(path)

        for path in config_candidates[:6]:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                base_names = {self._ast_name(base) for base in node.bases}
                if not base_names.intersection({"BaseSettings", "Config", "Settings"}):
                    continue
                prefix = self._class_env_prefix(node) or "no explicit env prefix"
                fields = self._class_field_summaries(node)
                snapshots.append((node.name, prefix, fields))
        return snapshots

    def _ast_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""

    def _class_env_prefix(self, node: ast.ClassDef) -> str | None:
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "model_config":
                        try:
                            rendered = ast.unparse(item.value)
                        except Exception:
                            rendered = ""
                        match = re.search(r'env_prefix["\']?\s*[:=]\s*["\']([^"\']+)["\']', rendered)
                        if match:
                            return match.group(1)
            if isinstance(item, ast.ClassDef) and item.name == "Config":
                for inner in item.body:
                    if isinstance(inner, ast.Assign):
                        for target in inner.targets:
                            if isinstance(target, ast.Name) and target.id == "env_prefix":
                                if isinstance(inner.value, ast.Constant) and isinstance(inner.value.value, str):
                                    return inner.value.value
        return None

    def _class_field_summaries(self, node: ast.ClassDef) -> list[str]:
        fields: list[str] = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                name = item.target.id
                if name.startswith("_"):
                    continue
                rendered_default = ""
                if item.value is not None:
                    try:
                        rendered_default = ast.unparse(item.value)
                    except Exception:
                        rendered_default = "..."
                if rendered_default:
                    fields.append(f"{name}={rendered_default}")
                else:
                    fields.append(name)
            elif isinstance(item, ast.Assign):
                target_names = [target.id for target in item.targets if isinstance(target, ast.Name)]
                for name in target_names:
                    if name.startswith("_"):
                        continue
                    try:
                        rendered_default = ast.unparse(item.value)
                    except Exception:
                        rendered_default = "..."
                    fields.append(f"{name}={rendered_default}")
        return fields[:4]

    def _route_inventory(self) -> dict[str, list[str]]:
        routes_dir = self.workspace_path / "src" / "autonomous_agent_builder" / "api" / "routes"
        if not routes_dir.exists():
            return {}
        inventory: dict[str, list[str]] = {}
        route_pattern = re.compile(r'@router\.(get|post|put|delete|patch)\("([^"]*)"')
        prefix_pattern = re.compile(r'APIRouter\((?:[^)]*?)prefix="([^"]+)"')
        for path in sorted(routes_dir.glob("*.py")):
            text = self._read_repo_text(path.relative_to(self.workspace_path).as_posix())
            if not text:
                continue
            prefix_match = prefix_pattern.search(text)
            router_prefix = prefix_match.group(1) if prefix_match else ""
            group = path.stem.replace("_api", "").replace("_", "-")
            entries: list[str] = []
            for method, route_path in route_pattern.findall(text):
                full_path = f"/api{router_prefix}{route_path}"
                full_path = full_path.replace("//", "/")
                entries.append(f"{method.upper()} {full_path}")
            if entries:
                inventory[group] = entries
        return inventory

    def _agent_definition_rows(self) -> list[tuple[str, str, str, str]]:
        content = self._read_repo_text("src/autonomous_agent_builder/agents/definitions.py")
        if not content:
            return []
        rows: list[tuple[str, str, str, str]] = []
        pattern = re.compile(
            r'"([^"]+)":\s*AgentDefinition\((?P<body>.*?)\n\s*\)',
            re.DOTALL,
        )
        for match in pattern.finditer(content):
            name = match.group(1)
            body = match.group("body")
            description_match = re.search(r'description="([^"]+)"', body)
            model_match = re.search(r'model="([^"]+)"', body)
            turns_match = re.search(r"max_turns=(\d+)", body)
            rows.append(
                (
                    name,
                    description_match.group(1) if description_match else "phase-owned agent",
                    model_match.group(1) if model_match else "unknown",
                    turns_match.group(1) if turns_match else "?",
                )
            )
        return rows

    def _orchestrator_dispatch_summary(self) -> tuple[list[str], list[str]]:
        content = self._read_repo_text("src/autonomous_agent_builder/orchestrator/orchestrator.py")
        if not content:
            return ([], [])
        phase_matches = re.findall(r"TaskStatus\.([A-Z_]+):\s+\"(_phase_[^\"]+)\"", content)
        phases = [
            f"{status.lower()} -> {handler.removeprefix('_phase_').replace('_', '-')}"
            for status, handler in phase_matches
        ]
        blocked_match = re.search(r"BLOCKED_STATUSES\s*=\s*\{(.*?)\}", content, re.DOTALL)
        blocked: list[str] = []
        if blocked_match:
            blocked = [
                item.lower()
                for item in re.findall(r"TaskStatus\.([A-Z_]+)", blocked_match.group(1))
            ]
        return (phases, blocked)

    def _onboarding_phases(self) -> list[str]:
        content = self._read_repo_text("src/autonomous_agent_builder/onboarding.py")
        if not content:
            return []
        match = re.search(r"PHASES\s*=\s*\[(.*?)\]", content, re.DOTALL)
        if not match:
            return []
        return re.findall(r'"([^"]+)"', match.group(1))

    def _grounded_overview(self, title: str) -> str:
        normalized = title.strip().lower()
        if normalized == "project overview":
            return (
                "This repository is a dashboard-first autonomous delivery system built around a FastAPI backend, "
                "a React SPA operator surface, builder CLI commands, deterministic orchestration, and a local knowledge base. "
                "Its core job is to bring a repo under builder control, move work through agent-owned phases, and leave behind inspectable evidence."
            )
        if normalized == "system architecture":
            return (
                "The architecture combines a FastAPI application, database-backed task state, filesystem-backed knowledge and memory retrieval, "
                "and deterministic orchestration that dispatches agents by task phase. "
                "The app serves both JSON APIs and the React dashboard, so UI behavior and backend state transitions stay in one runtime."
            )
        if normalized == "technology stack":
            return (
                "The stack is primarily Python 3.11+ on the backend with FastAPI, SQLAlchemy, Pydantic Settings, Typer, and the Claude Agent SDK, "
                "paired with a React 19 and Vite frontend. "
                "Local development defaults to SQLite-backed state and a generated local knowledge base, while PostgreSQL remains available for production-style deployment."
            )
        if normalized == "code structure":
            return (
                "The codebase is organized around explicit ownership packages for API routes, agent runtime, orchestration, persistence, security, and knowledge generation. "
                "A first pass through the package map should tell an operator where to edit product behavior, infrastructure wiring, or documentation generation without diffusing responsibility."
            )
        if normalized == "api endpoints":
            return (
                "The API is grouped into task execution, dashboard read models, onboarding control, knowledge retrieval, memory retrieval, and project-management mutations. "
                "Those route families map closely to the product surfaces a new operator sees in the dashboard and builder CLI."
            )
        if normalized == "configuration":
            return (
                "Configuration is centered on nested Pydantic settings classes with distinct environment-variable prefixes for application, database, agent, gate, and harness concerns. "
                "That split makes it clear which knobs change runtime serving, model selection, storage, and quality-gate behavior."
            )
        if normalized == "agent system":
            return (
                "The agent system uses versioned agent definitions, a tool registry, and pre or post tool hooks to keep execution inspectable and bounded. "
                "The orchestrator chooses the phase agent; agents do not self-route or own the workflow lifecycle."
            )
        if normalized == "workflows and orchestration":
            return (
                "Workflow execution is deterministic: task status selects the phase handler, quality-gate outcomes decide whether work advances or loops, and review states block further automation until a human resolves them. "
                "Separate onboarding phases bootstrap the repo before the normal task pipeline begins."
            )
        return self._trim_words(self._doc_profile(title)["overview_focus"], 56)

    def _grounded_evidence_blocks(self, title: str) -> list[str]:
        normalized = title.strip().lower()
        if normalized == "project overview":
            packages = self._package_dirs()
            package_phrase = ", ".join(f"`{name}`" for name in packages[:8]) or "no package directories detected"
            return [
                "### Runtime entrypoints\n\n"
                "The repo starts from `src/autonomous_agent_builder/main.py`, which loads `.env` before launching the FastAPI app in `src/autonomous_agent_builder/api/app.py`. "
                "The CLI surface is registered through the `builder` script in `pyproject.toml` and routes into `src/autonomous_agent_builder/cli/main.py`.",
                "### Primary ownership surfaces\n\n"
                f"The main backend packages under `src/autonomous_agent_builder` are {package_phrase}. "
                "These surfaces roughly separate API wiring, agent execution, orchestration, persistence, quality gates, security, and knowledge generation.",
                "### Operator-facing flow\n\n"
                "A repo first moves through onboarding, which seeds builder-managed state and generates the seed system-doc KB. "
                "After that, the normal operator surface is the dashboard plus the task-phase orchestrator and associated agent runs.",
            ]
        if normalized == "system architecture":
            route_groups = self._route_inventory()
            route_phrase = ", ".join(f"`{name}`" for name in sorted(route_groups.keys())[:6])
            return [
                "### Application composition\n\n"
                "The FastAPI app registers project, feature, gate, dispatch, dashboard, onboarding, knowledge, and memory routers under `/api`, exposes `/health`, and serves either the React SPA build or the legacy dashboard routes depending on whether `frontend/dist` exists.",
                "### State and storage boundaries\n\n"
                "Runtime task state lives in the database layer, while local knowledge and memory retrieval are filesystem-backed. "
                "That means task progression and metrics come from DB models, but KB and memory search read the repo-local or global markdown stores.",
                "### Route-family architecture\n\n"
                f"The current API route groups are {route_phrase}. "
                "Onboarding and dashboard reads are separate from project-management mutations and separate again from KB or memory retrieval.",
            ]
        if normalized == "technology stack":
            python_deps = self._python_dependencies()
            frontend_deps = self._frontend_dependencies()
            backend_phrase = ", ".join(f"`{name}`" for name in python_deps[:8])
            frontend_phrase = ", ".join(f"`{name}`" for name in frontend_deps[:8])
            return [
                f"### Backend runtime\n\nThe Python dependency set is anchored by {backend_phrase}. These packages define the server, CLI, settings, async persistence, and agent-execution surfaces.",
                f"### Frontend runtime\n\nThe frontend package uses {frontend_phrase}. That combination indicates a React and Vite SPA with router-driven navigation, Tailwind-era styling helpers, and animation support.",
                "### Storage and execution defaults\n\n"
                "The default local database driver is SQLite through `sqlite+aiosqlite`, while PostgreSQL and `asyncpg` are available for production-style operation. "
                "The runtime also depends on the Claude Agent SDK and inherited auth tokens for Claude-backed execution and advisory checks.",
            ]
        if normalized == "code structure":
            packages = self._package_dirs()
            package_lines = "\n".join(
                f"- `{name}`: {self._package_purpose(name)}"
                for name in packages[:10]
            )
            if not package_lines:
                package_lines = "- No package-style directories detected; rely on key files and runtime entrypoints."
            return [
                f"### Package map\n\n{package_lines}",
                "### High-value files\n\n"
                "- `src/autonomous_agent_builder/api/app.py`: app assembly, router registration, SPA serving.\n"
                "- `src/autonomous_agent_builder/onboarding.py`: repo bootstrap pipeline and KB extraction integration.\n"
                "- `src/autonomous_agent_builder/orchestrator/orchestrator.py`: deterministic task-phase dispatch.\n"
                "- `src/autonomous_agent_builder/agents/definitions.py`: agent-as-artifact definitions.\n"
                "- `src/autonomous_agent_builder/config.py`: nested settings and env-prefix contract.",
            ]
        if normalized == "api endpoints":
            groups = self._route_inventory()
            blocks: list[str] = []
            label_map = {
                "dashboard": "Dashboard reads",
                "onboarding": "Onboarding control",
                "knowledge": "Knowledge retrieval",
                "memory-api": "Memory retrieval",
                "projects": "Project management",
                "features": "Feature and task management",
                "gates": "Gate and approval surfaces",
                "dispatch": "Task dispatch",
            }
            for key in ["dashboard", "onboarding", "knowledge", "memory-api", "projects", "features", "gates", "dispatch"]:
                entries = groups.get(key)
                if not entries:
                    continue
                label = label_map.get(key, key.replace("-", " ").title())
                bullets = "\n".join(f"- `{entry}`" for entry in entries[:6])
                blocks.append(f"### {label}\n\n{bullets}")
            return blocks
        if normalized == "configuration":
            snapshots = self._settings_snapshot()
            lines = []
            for class_name, prefix, fields in snapshots[:4]:
                field_phrase = ", ".join(fields[:4])
                lines.append(f"- `{class_name}` uses `{prefix}` and exposes {field_phrase}")
            return [
                "### Settings classes and prefixes\n\n" + "\n".join(lines),
                "### Critical runtime knobs\n\n"
                "- `AAB_PORT`, `AAB_HOST`, and `AAB_WORKSPACE_ROOT` control app serving and workspace placement.\n"
                "- `DB_DRIVER`, `DB_NAME`, and `AAB_DB_URL` decide whether local state uses SQLite or PostgreSQL.\n"
                "- `AGENT_IMPLEMENTATION_MODEL`, `AGENT_PERMISSION_MODE`, and `AGENT_AUTH_BACKEND` shape Claude-backed execution.\n"
                "- `GATE_*` and `HARNESS_*` tune retry, timeout, and harnessability thresholds.",
                "### Auth and process inheritance\n\n"
                "The server entrypoint loads `.env` before the app imports settings so Claude auth tokens can propagate into Claude CLI subprocesses during onboarding and advisory checks.",
            ]
        if normalized == "agent system":
            rows = self._agent_definition_rows()
            bullets = "\n".join(
                f"- `{name}`: {description} using `{model}` with max turns `{turns}`"
                for name, description, model, turns in rows[:6]
            )
            return [
                "### Versioned agent definitions\n\n" + bullets,
                "### Supporting execution surfaces\n\n"
                "- `agents/runner.py`: Claude SDK query loop and run result handling.\n"
                "- `agents/tool_registry.py`: tool discovery and prompt context.\n"
                "- `agents/hooks.py`: safety and audit hook wiring.\n"
                "- `agents/tools/`: builder-owned tool definitions.",
                "### Control model\n\n"
                "The orchestrator selects an agent definition by phase, injects tool context, and records execution lineage. "
                "Hooks then enforce workspace and argv constraints around the actual tool calls.",
            ]
        if normalized == "workflows and orchestration":
            phases, blocked = self._orchestrator_dispatch_summary()
            onboarding_phases = self._onboarding_phases()
            return [
                "### Task-status dispatch\n\n" + "\n".join(f"- `{entry}`" for entry in phases[:8]),
                "### Blocking and review states\n\n" + "\n".join(f"- `{state}` requires human resolution or stops automation" for state in blocked[:6]),
                "### Onboarding bootstrap\n\n" + "\n".join(f"- `{phase}`" for phase in onboarding_phases),
            ]
        return []

    def _grounded_touch_guidance(self, title: str) -> str:
        normalized = title.strip().lower()
        guidance_map = {
            "project overview": [
                "Change repo bootstrap or first-run operator flow in `src/autonomous_agent_builder/onboarding.py` and `src/autonomous_agent_builder/api/routes/onboarding.py`.",
                "Change top-level app serving or dashboard entry behavior in `src/autonomous_agent_builder/api/app.py` and `src/autonomous_agent_builder/main.py`.",
            ],
            "system architecture": [
                "Touch `src/autonomous_agent_builder/api/app.py` when route registration, SPA serving, or health wiring changes.",
                "Touch `src/autonomous_agent_builder/orchestrator/orchestrator.py` when phase ownership or system-level execution boundaries change.",
                "Touch `src/autonomous_agent_builder/api/routes/knowledge.py` or `src/autonomous_agent_builder/knowledge/publisher.py` when KB retrieval or publication behavior changes.",
            ],
            "technology stack": [
                "Touch `pyproject.toml` for backend runtime, CLI, persistence, and Claude SDK dependency changes.",
                "Touch `frontend/package.json` for React, Vite, styling, or dashboard dependency changes.",
                "Touch `src/autonomous_agent_builder/config.py` when a new dependency adds runtime configuration.",
            ],
            "code structure": [
                "Touch `src/autonomous_agent_builder/api/` for HTTP and dashboard-backed read models.",
                "Touch `src/autonomous_agent_builder/agents/` for agent prompts, tools, registry, or hook behavior.",
                "Touch `src/autonomous_agent_builder/orchestrator/` for phase routing, retry flow, or gate handoff logic.",
                "Touch `src/autonomous_agent_builder/knowledge/` for KB generation, retrieval, validation, or publishing.",
            ],
            "api endpoints": [
                "Touch `src/autonomous_agent_builder/api/routes/dashboard_api.py` for board, metrics, approval, and SSE read models.",
                "Touch `src/autonomous_agent_builder/api/routes/onboarding.py` plus `src/autonomous_agent_builder/onboarding.py` for first-run control flow.",
                "Touch `src/autonomous_agent_builder/api/routes/knowledge.py` and `src/autonomous_agent_builder/api/routes/memory_api.py` for retrieval surfaces.",
                "Touch `src/autonomous_agent_builder/api/routes/projects.py`, `features.py`, `gates.py`, and `dispatch.py` for mutation APIs.",
            ],
            "configuration": [
                "Touch `src/autonomous_agent_builder/config.py` to add or rename runtime settings.",
                "Touch `src/autonomous_agent_builder/main.py` when startup env loading or server launch semantics change.",
                "Touch deployment or local env files when only values change and the config contract stays stable.",
            ],
            "agent system": [
                "Touch `src/autonomous_agent_builder/agents/definitions.py` for role prompts, models, budgets, and tools.",
                "Touch `src/autonomous_agent_builder/agents/runner.py` for Claude execution behavior and result handling.",
                "Touch `src/autonomous_agent_builder/agents/hooks.py` or `agents/tool_registry.py` for safety and tool-registration changes.",
            ],
            "workflows and orchestration": [
                "Touch `src/autonomous_agent_builder/orchestrator/orchestrator.py` for task-status dispatch changes.",
                "Touch `src/autonomous_agent_builder/orchestrator/gate_feedback.py` and `quality_gates/` for failure handling and remediation loops.",
                "Touch `src/autonomous_agent_builder/onboarding.py` for the repo bootstrap pipeline rather than the normal task orchestrator.",
            ],
        }
        bullets = guidance_map.get(normalized)
        if not bullets:
            return ""
        return "## What to touch when\n\n" + "\n".join(f"- {item}" for item in bullets)

    def _compact_evidence_blocks(
        self,
        evidence_blocks: list[str],
        *,
        target_words: int = 320,
        max_block_words: int = 70,
    ) -> list[str]:
        if self._word_count("\n\n".join(evidence_blocks)) <= target_words:
            return evidence_blocks

        compacted: list[str] = []
        remaining = target_words
        for block in evidence_blocks:
            if remaining <= 0:
                break
            if "\n\n" not in block:
                trimmed = self._trim_words(block, min(max_block_words, remaining))
                if trimmed:
                    compacted.append(trimmed)
                    remaining -= self._word_count(trimmed)
                continue

            heading, body = block.split("\n\n", 1)
            trimmed_body = self._trim_words(body, min(max_block_words, remaining))
            if not trimmed_body:
                continue
            compacted.append(f"{heading}\n\n{trimmed_body}")
            remaining -= self._word_count(trimmed_body)

        return compacted or evidence_blocks[:3]

    def _normalize_reverse_engineering_content(self, title: str, content: str) -> str:
        """Rewrite seed system docs into the canonical explorer-friendly shape."""
        body = self._sanitize_reverse_engineering_text(self._strip_title_heading(title, content))
        sections = [
            (heading, section_body)
            for heading, section_body in self._h2_sections(body)
            if self._plain_text(section_body)
        ]

        overview = ""
        evidence_sections: list[tuple[str, str]] = []
        findings: list[str] = []

        for heading, section_body in sections:
            normalized_heading = heading.strip().lower()
            if normalized_heading == "overview" and not overview:
                overview = section_body
                continue

            evidence_sections.append((heading, section_body))
            sentence = self._first_sentence(section_body)
            if sentence:
                findings.append(f"- **{heading}**: {sentence}")
            else:
                findings.append(f"- **{heading}**")

        overview = self._trim_words(self._grounded_overview(title), 70)

        boundaries = self._build_boundaries(title, sections)
        invariants = self._build_invariants(title, sections)

        evidence_blocks = self._grounded_evidence_blocks(title)
        if not evidence_blocks:
            for heading, section_body in evidence_sections[:5]:
                cleaned = self._trim_words(section_body, 70)
                if not cleaned:
                    continue
                evidence_blocks.append(f"### {heading}\n\n{cleaned}")

        if not evidence_blocks and body.strip():
            evidence_blocks.append(self._trim_words(body, 90))

        if self._word_count("\n\n".join(evidence_blocks)) < 60:
            profile = self._doc_profile(title)
            evidence_blocks.append(
                "### Repository evidence\n\n"
                f"{profile['evidence_focus']} This summary is grounded in the checked-in source tree for {title.lower()}, including code structure, configuration, route-level behavior, and adjacent implementation detail visible in the repository at extraction time. Use these evidence blocks as the proof surface when validating what the dashboard should surface or when deciding which document to refresh after code changes."
            )
        evidence_blocks = self._compact_evidence_blocks(evidence_blocks)

        change_guidance = (
            f"Edit the owning surface only, verify the adjacent contracts that this document names, and refresh this record with "
            "`builder knowledge extract --force` after substantive code changes."
        )

        touch_guidance = self._grounded_touch_guidance(title)
        related_documents = self._related_documents_block(title)

        body_parts = [
            f"# {title}",
            "## Overview",
            overview,
            "## Boundaries",
            boundaries,
            "## Invariants",
            "\n".join(invariants),
            "## Evidence",
            "\n\n".join(evidence_blocks),
        ]
        if touch_guidance:
            body_parts.append(touch_guidance)
        body_parts.extend(
            [
                "## Change guidance",
                change_guidance,
            ]
        )
        if related_documents:
            body_parts.extend([related_documents])
        return "\n\n".join(body_parts).strip()

    def _normalize_metadata_content(self, title: str, content: str) -> str:
        """Ensure metadata docs still include the expected H1 heading."""
        body = self._strip_title_heading(title, content)
        return f"# {title}\n\n{body}".strip()

    def _write_doc(self, filename: str, doc: dict[str, Any]) -> None:
        """Write markdown file with frontmatter."""
        tags = doc.get("tags", ["system-docs", "seed", "auto-generated"])
        if not isinstance(tags, list):
            tags = [str(tags)]

        publish_document(
            title=doc["title"],
            body=doc["content"],
            doc_type=doc.get("doc_type", "system-docs"),
            tags=tags,
            wikilinks=doc.get("wikilinks"),
            scope="local",
            collection=self.output_collection,
            file_name=filename,
            extra_fields={
                key: doc[key]
                for key in (
                    "card_summary",
                    "detail_summary",
                    "verified",
                    "authoritative",
                    "evidence_manifest",
                    "source_commit",
                    "extractor_version",
                    "dependency_hash",
                    "graph_artifact",
                    "workspace_profile",
                    "render_status",
                )
                if key in doc
            },
        )

    def _write_metadata(
        self,
        documents: list[dict[str, Any]],
        errors: list[dict[str, Any]],
        *,
        expected_documents: list[str],
        blocking_documents: list[str],
        non_blocking_documents: list[str],
    ) -> None:
        """Write extraction metadata file."""
        metadata = {
            "extracted_at": datetime.now().isoformat(),
            "workspace_path": str(self.workspace_path),
            "document_count": len(documents),
            "documents": documents,
            "errors": errors,
            "expected_documents": expected_documents,
            "blocking_documents": blocking_documents,
            "non_blocking_documents": non_blocking_documents,
            "workspace_profile": self._shared_graph.get("workspace_profile") if self._shared_graph else None,
            "graph_artifact": GRAPH_ARTIFACT_RELATIVE_PATH if self._shared_graph else None,
            "graph_dependency_hash": self._shared_graph.get("dependency_hash") if self._shared_graph else None,
        }

        metadata_lines = [
            "# Extraction Metadata",
            "",
            "## Summary",
            f"**Extracted At**: {metadata['extracted_at']}  ",
            f"**Workspace**: `{metadata['workspace_path']}`  ",
            f"**Documents Generated**: {metadata['document_count']}  ",
            f"**Workspace Profile**: `{metadata['workspace_profile'] or 'unknown'}`",
            "",
            "## Generated artifacts",
        ]

        if documents:
            artifact_names = ", ".join(doc["filename"] for doc in documents[:6])
            metadata_lines.append(
                f"This extraction run published {len(documents)} seed system-doc artifacts. The generated set includes {artifact_names} and preserves the rest in the same local collection for dashboard retrieval."
            )
            metadata_lines.append("")
            for doc in documents:
                metadata_lines.append(f"- **{doc['type']}**: {doc['title']} (`{doc['filename']}`)")
        else:
            metadata_lines.append(
                "No documents were published during this extraction run because the generated output still violated the active ingestion contract."
            )

        if errors:
            metadata_lines.extend(["", "## Errors"])
            for error in errors:
                metadata_lines.append(f"- **{error['generator']}**: {error['error']}")

        metadata_lines.extend(
            [
                "",
                "## Usage",
                "These documents were automatically generated by analyzing the codebase.",
                "They provide a structured seed system-doc reference for the project.",
                "",
                f"Graph artifact: `{metadata['graph_artifact'] or 'not generated'}`",
                "Use `builder knowledge search` to search across all knowledge documents.",
                "Use `builder knowledge list --type system-docs` to list extracted seed docs.",
            ]
        )

        publish_document(
            title="Extraction Metadata",
            body="\n".join(metadata_lines),
            doc_type="metadata",
            tags=["metadata", "system-docs"],
            scope="local",
            collection=self.output_collection,
            file_name="extraction-metadata.md",
            extra_fields={
                "card_summary": "Generated artifact inventory, extraction timing, and what changed in this run.",
                "detail_summary": "Summarizes when extraction ran, which seed system-doc artifacts were published, and what an operator should rerun or inspect next.",
                "expected_documents": expected_documents,
                "blocking_documents": blocking_documents,
                "non_blocking_documents": non_blocking_documents,
                "workspace_profile": metadata["workspace_profile"],
                "graph_artifact": metadata["graph_artifact"],
                "graph_dependency_hash": metadata["graph_dependency_hash"],
            },
        )
