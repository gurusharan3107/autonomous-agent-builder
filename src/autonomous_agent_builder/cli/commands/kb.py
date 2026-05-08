"""Knowledge base commands — add, list, show, search, update."""

from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import emit_error, error, render, render_json, table, truncate
from autonomous_agent_builder.cli.retrieval import compact_results_payload, resolve_collection_item
from autonomous_agent_builder.knowledge.publisher import (
    DEFAULT_LOCAL_KB_COLLECTION,
    PublishError,
    publish_document,
    update_document,
)
from autonomous_agent_builder.knowledge.retrieval import (
    find_doc as find_local_doc,
    load_docs as load_local_docs,
    search_docs as search_local_docs,
)

app = typer.Typer(
    help="Project-local knowledge surfaces for agents and operators."
)
_WORKFLOW_GLOBAL_HINT = (
    "Global KB publication is owned by workflow CLI. "
    "Use `workflow knowledge ingest <file>` for ~/.codex/knowledge updates."
)
_KB_EXTRACT_PHASE = "kb_extract"
_KB_EXTRACT_ENGINE = "deterministic"
_SUPPORTED_DOC_TYPES = (
    "context",
    "adr",
    "api_contract",
    "schema",
    "runbook",
    "system-docs",
    "feature",
    "testing",
    "metadata",
    "raw",
)


def _render_publish_result(action: str, data: dict[str, Any], *, use_json: bool) -> None:
    def fmt(d: dict[str, Any]) -> str:
        return (
            f"{action} {d.get('doc_type', '')} document\n"
            f"id: {d.get('id', '')}\n"
            f"title: {d.get('title', '')}\n"
            f"scope: {d.get('scope', '')}\n"
            f"version: {d.get('version', 1)}"
        )

    render(data, fmt, use_json=use_json)


def _ensure_builder_write_scope(scope: str) -> None:
    if scope.strip().lower() == "global":
        error(f"Error: {_WORKFLOW_GLOBAL_HINT}")
        sys.exit(2)


def _read_content(content: str | None, content_file: str | None) -> str:
    """Resolve content from --content or --content-file (supports stdin via -)."""
    if content:
        return content
    if content_file:
        if content_file == "-":
            return sys.stdin.read()
        path = Path(content_file)
        if not path.exists():
            from autonomous_agent_builder.cli.output import error

            error(f"Error: file not found — {content_file}")
            sys.exit(2)
        return path.read_text(encoding="utf-8")
    from autonomous_agent_builder.cli.output import error

    error("Error: provide --content or --content-file")
    sys.exit(2)


def _normalize_tags(
    tags: str | None,
    *,
    doc_type: str,
    family: str | None = None,
    tag_values: list[str] | None = None,
    feature_tag: bool = False,
    testing_tag: bool = False,
) -> list[str]:
    items = [doc_type.strip()]
    if family:
        items.append(family.strip())
    if feature_tag:
        items.append("feature")
    if testing_tag:
        items.append("testing")
    if tags:
        items.extend(tag.strip() for tag in tags.split(","))
    if tag_values:
        items.extend(tag.strip() for tag in tag_values)

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        if item not in seen:
            seen.add(item)
            normalized.append(item)
    return normalized


def _system_doc_extra_fields(
    *,
    family: str | None,
    linked_feature: str | None,
    feature_id: str | None,
    refresh_required: bool | None,
    documented_against_commit: str | None,
    documented_against_ref: str | None,
    owned_paths: list[str] | None,
    verified_with: str | None,
    last_verified_at: str | None,
    lifecycle_status: str | None,
    superseded_by: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if family:
        payload["doc_family"] = family
    if linked_feature:
        payload["linked_feature"] = linked_feature
    if feature_id:
        payload["feature_id"] = feature_id
    if refresh_required is not None:
        payload["refresh_required"] = refresh_required
    if documented_against_commit:
        payload["documented_against_commit"] = documented_against_commit
    if documented_against_ref:
        payload["documented_against_ref"] = documented_against_ref
    if owned_paths:
        payload["owned_paths"] = owned_paths
    if verified_with:
        payload["verified_with"] = verified_with
    if last_verified_at:
        payload["last_verified_at"] = last_verified_at
    if lifecycle_status:
        payload["lifecycle_status"] = lifecycle_status
    if superseded_by:
        payload["superseded_by"] = superseded_by
    return payload


FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _strip_frontmatter(content: str) -> str:
    return FRONTMATTER_RE.sub("", content, count=1).strip()


def _extract_section(content: str, section: str) -> str | None:
    body = _strip_frontmatter(content)
    matches = list(SECTION_RE.finditer(body))
    wanted = section.strip().lower()

    for index, match in enumerate(matches):
        if match.group(1).strip().lower() != wanted:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        return body[start:end].strip()
    return None


def _first_content_block(content: str) -> str:
    body = _strip_frontmatter(content)
    for heading in ("Summary", "Overview", "Context", "Purpose", "Key Findings"):
        section_content = _extract_section(body, heading)
        if section_content:
            first = section_content.split("\n\n", 1)[0].strip()
            if first:
                return first

    cleaned_lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if stripped.startswith("#"):
            continue
        cleaned_lines.append(stripped)

    cleaned = "\n".join(cleaned_lines).strip()
    if not cleaned:
        return ""
    return cleaned.split("\n\n", 1)[0].strip()


def _summarize_document(doc: dict[str, Any]) -> str:
    detail_summary = str(doc.get("detail_summary", "") or "").strip()
    card_summary = str(doc.get("card_summary", "") or "").strip()
    boundaries = _extract_section(str(doc.get("content", "")), "Boundaries")
    invariants = _extract_section(str(doc.get("content", "")), "Invariants")
    change_guidance = _extract_section(str(doc.get("content", "")), "Change guidance")

    lines: list[str] = []
    if card_summary:
        lines.append(f"card: {card_summary}")
    if detail_summary:
        lines.append(f"detail: {detail_summary}")
    if boundaries:
        flattened_boundaries = boundaries.replace("\n", " ")
        lines.append(f"boundaries: {truncate(flattened_boundaries, 220)}")
    if invariants:
        invariant_lines = [
            line.strip()
            for line in invariants.splitlines()
            if line.strip().startswith("-")
        ][:3]
        if invariant_lines:
            lines.append("invariants:")
            lines.extend(f"  {line}" for line in invariant_lines)
    if change_guidance:
        flattened_guidance = change_guidance.replace("\n", " ")
        lines.append(f"change_guidance: {truncate(flattened_guidance, 180)}")

    if lines:
        return "\n".join(lines)

    summary = _first_content_block(str(doc.get("content", "")))
    return truncate(summary, 400) if summary else ""


def _resolve_local_document(query: str) -> tuple[dict[str, Any], str]:
    exact = find_local_doc(query, scope="local")
    if exact is not None:
        return exact, "id"
    searchable_items = []
    for item in load_local_docs("local"):
        searchable_items.append(
            {
                **item,
                "tags_text": " ".join(str(tag) for tag in item.get("tags", [])),
                "summary_text": " ".join(
                    part
                    for part in (
                        str(item.get("card_summary", "") or ""),
                        str(item.get("detail_summary", "") or ""),
                    )
                    if part
                ),
            }
        )
    resolution = resolve_collection_item(
        query,
        searchable_items,
        id_keys=("id",),
        text_keys=("title", "doc_type", "doc_family", "tags_text", "summary_text"),
        suggestion_id_key="id",
        suggestion_label_key="title",
    )
    if resolution and resolution.item:
        resolved = dict(resolution.item)
        resolved.pop("tags_text", None)
        resolved.pop("summary_text", None)
        return resolved, resolution.matched_on
    raise AabApiError(404, _kb_not_found_detail(query))


def _join_query_parts(parts: list[str] | str) -> str:
    if isinstance(parts, str):
        return parts.strip()
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def _kb_preview(doc: dict[str, Any], *, max_chars: int = 160) -> str:
    preview = (
        str(doc.get("card_summary", "")).strip()
        or str(doc.get("detail_summary", "")).strip()
        or _first_content_block(str(doc.get("content", "")))
    )
    return truncate(preview.replace("\n", " "), max_chars) if preview else ""


def _kb_hit(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc.get("id", "")),
        "title": str(doc.get("title", "")),
        "doc_type": str(doc.get("doc_type", "")),
        "preview": _kb_preview(doc, max_chars=110),
    }


def _kb_search_payload(query: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    next_step = (
        "builder knowledge show <doc-id> --section 'Change guidance' --json"
        if query == "list"
        else f"builder knowledge summary {json.dumps(query)} --json"
    )
    payload = compact_results_payload(query, [_kb_hit(item) for item in items], next_step=next_step)
    payload["truncated"] = False
    return payload


def _kb_full_payload(query: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "ok",
        "query": query,
        "count": len(items),
        "results": items,
        "next_step": "builder knowledge show <doc-id> --section 'Change guidance' --json",
        "schema_version": "1",
    }


def _kb_not_found_detail(query: str) -> dict[str, Any]:
    suggestions: list[str] = []
    try:
        items = load_local_docs("local")[:50]
        choices: list[str] = []
        for item in items:
            doc_id = str(item.get("id", "")).strip()
            title = str(item.get("title", "")).strip()
            if doc_id:
                choices.append(doc_id)
            if title:
                choices.append(title)
        seen: set[str] = set()
        for suggestion in difflib.get_close_matches(query, choices, n=3, cutoff=0.35):
            if suggestion not in seen:
                seen.add(suggestion)
                suggestions.append(suggestion)
    except Exception:
        suggestions = []
    return {"detail": f"Document '{query}' not found", "suggestions": suggestions}


def _handle_kb_lookup_error(query: str, err: AabApiError, *, use_json: bool) -> None:
    if err.status_code != 404:
        handle_api_error(err, use_json=use_json)
        return

    detail = err.detail if isinstance(err.detail, dict) else {"detail": str(err.detail)}
    message = detail.get("detail", f"Document '{query}' not found")
    suggestions = detail.get("suggestions", [])
    search_command = f'builder knowledge search "{query}" --json'
    if suggestions:
        hint = f"Try {search_command}, or retry with one of: {', '.join(suggestions)}."
    else:
        hint = f"Try {search_command}, then retry with the exact ID from the result."
    emit_error(
        message,
        code="not_found",
        hint=hint,
        detail={"query": query, "suggestions": suggestions},
        use_json=use_json,
    )
    sys.exit(1)


def _kb_extract_next_step(
    *,
    action: str,
    reason: str,
    target_phase: str = "",
    recommended_command: str = "",
) -> dict[str, str]:
    return {
        "action": action,
        "reason": reason,
        "target_phase": target_phase,
        "recommended_command": recommended_command,
    }


def _default_agent_advisory_payload() -> dict[str, Any]:
    return {
        "available": False,
        "passed": False,
        "score": 0.0,
        "summary": "",
        "recommendations": [],
    }


def _build_extract_contract(
    *,
    kb_path: Path,
    documents: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    graph: dict[str, Any] | None,
    lint: dict[str, Any] | None,
    deterministic_validation: dict[str, Any] | None,
    agent_advisory: dict[str, Any] | None,
    passed: bool,
    operator_message: str,
    next_step: dict[str, str],
) -> dict[str, Any]:
    return {
        "passed": passed,
        "phase": _KB_EXTRACT_PHASE,
        "engine": _KB_EXTRACT_ENGINE,
        "output_path": str(kb_path),
        "documents": documents,
        "errors": errors,
        "graph": {
            "artifact_path": str(kb_path / ".evidence" / "graph.json") if graph else "",
            "workspace_profile": graph.get("workspace_profile") if graph else "",
            "dependency_hash": graph.get("dependency_hash") if graph else "",
        },
        "lint": lint or {"passed": False, "counts": {"passed": 0, "failed": 0, "total": 0}},
        "validation": {
            "deterministic": deterministic_validation
            or {"passed": False, "score": 0.0, "summary": ""},
            "agent_advisory": agent_advisory or _default_agent_advisory_payload(),
        },
        "operator_message": operator_message,
        "next_step": next_step,
    }


def _run_extract_pipeline(
    *,
    workspace_path: Path,
    kb_path: Path,
    scope: str,
    run_validation: bool,
    doc_slug: str | None = None,
) -> dict[str, Any]:
    from autonomous_agent_builder.config import get_settings
    from autonomous_agent_builder.knowledge import KnowledgeExtractor
    from autonomous_agent_builder.knowledge.document_spec import lint_directory
    from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate

    extractor = KnowledgeExtractor(
        workspace_path=workspace_path,
        output_path=kb_path,
        doc_slugs=[doc_slug] if doc_slug else None,
    )
    results = extractor.extract(scope=scope)
    documents = results.get("documents", [])
    errors = results.get("errors", [])
    graph_payload = results.get("graph")

    lint_payload = {
        "passed": False,
        "counts": {"passed": 0, "failed": 0, "total": 0},
    }
    deterministic_payload = {
        "passed": False,
        "score": 0.0,
        "summary": "Deterministic KB validation did not run.",
        "blocking_docs": [],
        "non_blocking_docs": [],
        "claim_failures": [],
        "unresolved_claims": [],
        "contradicted_claims": [],
    }
    agent_payload = _default_agent_advisory_payload()

    required_error_slugs = {doc_slug} if doc_slug else set(get_settings().kb_blocking_docs)
    blocking_errors = [
        error_item for error_item in errors if str(error_item.get("slug", "")).strip() in required_error_slugs
    ]

    if blocking_errors:
        return _build_extract_contract(
            kb_path=kb_path,
            documents=documents,
            errors=errors,
            graph=graph_payload,
            lint=lint_payload,
            deterministic_validation=deterministic_payload,
            agent_advisory=agent_payload,
            passed=False,
            operator_message="KB extraction completed with blocking generator errors.",
            next_step=_kb_extract_next_step(
                action="stop",
                reason="blocking_doc_extraction_failed",
                recommended_command="builder knowledge extract --force --json",
            ),
        )

    if not documents:
        return _build_extract_contract(
            kb_path=kb_path,
            documents=documents,
            errors=errors,
            graph=graph_payload,
            lint=lint_payload,
            deterministic_validation=deterministic_payload,
            agent_advisory=agent_payload,
            passed=False,
            operator_message="KB extraction generated no documents.",
            next_step=_kb_extract_next_step(
                action="stop",
                reason="no_documents_generated",
                recommended_command="builder knowledge extract --force --json",
            ),
        )

    if not run_validation:
        return _build_extract_contract(
            kb_path=kb_path,
            documents=documents,
            errors=errors,
            graph=graph_payload,
            lint=lint_payload,
            deterministic_validation={
                "passed": True,
                "score": 1.0,
                "summary": "Validation skipped by request.",
                "blocking_docs": [],
                "non_blocking_docs": [],
                "claim_failures": [],
                "unresolved_claims": [],
                "contradicted_claims": [],
            },
            agent_advisory=agent_payload,
            passed=True,
            operator_message="Knowledge base generated; validation skipped by request.",
            next_step=_kb_extract_next_step(
                action="continue",
                reason="validation_skipped",
                target_phase="kb_ready",
            ),
        )

    lint_passed_count, lint_failed_count, lint_total_count = lint_directory(kb_path, strict=False)
    lint_payload = {
        "passed": lint_total_count > 0 and lint_failed_count == 0,
        "counts": {
            "passed": lint_passed_count,
            "failed": lint_failed_count,
            "total": lint_total_count,
        },
    }
    if not lint_payload["passed"]:
        return _build_extract_contract(
            kb_path=kb_path,
            documents=documents,
            errors=errors,
            graph=graph_payload,
            lint=lint_payload,
            deterministic_validation=deterministic_payload,
            agent_advisory=agent_payload,
            passed=False,
            operator_message="Knowledge base lint failed.",
            next_step=_kb_extract_next_step(
                action="stop",
                reason="lint_failed",
                recommended_command="builder knowledge lint --verbose",
            ),
        )

    deterministic_result = KnowledgeQualityGate(kb_path, workspace_path).validate()
    deterministic_payload = {
        "passed": deterministic_result.passed,
        "score": deterministic_result.score,
        "summary": deterministic_result.summary,
        "blocking_docs": list(getattr(deterministic_result, "blocking_docs", [])),
        "non_blocking_docs": list(getattr(deterministic_result, "non_blocking_docs", [])),
        "claim_failures": list(getattr(deterministic_result, "claim_failures", [])),
        "unresolved_claims": list(getattr(deterministic_result, "unresolved_claims", [])),
        "contradicted_claims": list(getattr(deterministic_result, "contradicted_claims", [])),
        "workspace_profile": getattr(deterministic_result, "workspace_profile", ""),
        "graph_artifact": getattr(deterministic_result, "graph_artifact", ""),
        "blocking_render_status": getattr(deterministic_result, "blocking_render_status", {}),
        "unresolved_item_counts": getattr(deterministic_result, "unresolved_item_counts", {}),
    }
    if not deterministic_result.passed:
        return _build_extract_contract(
            kb_path=kb_path,
            documents=documents,
            errors=errors,
            graph=graph_payload,
            lint=lint_payload,
            deterministic_validation=deterministic_payload,
            agent_advisory=agent_payload,
            passed=False,
            operator_message=deterministic_result.summary or "Deterministic KB validation failed.",
            next_step=_kb_extract_next_step(
                action="stop",
                reason="deterministic_validation_failed",
                recommended_command="builder knowledge validate --verbose",
            ),
        )

    operator_message = "Knowledge base generated; deterministic gate passed."
    next_step_reason = "deterministic_validation_passed"
    if errors:
        operator_message += " Non-blocking doc generation errors remain."
        next_step_reason = "deterministic_validation_passed_with_non_blocking_errors"

    return _build_extract_contract(
        kb_path=kb_path,
        documents=documents,
        errors=errors,
        graph=graph_payload,
        lint=lint_payload,
        deterministic_validation=deterministic_payload,
        agent_advisory=agent_payload,
        passed=True,
        operator_message=operator_message,
        next_step=_kb_extract_next_step(
            action="continue",
            reason=next_step_reason,
            target_phase="kb_ready",
        ),
    )


def _validate_output_payload(
    deterministic_result: Any,
    *,
    agent_advisory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    freshness_report = next(
        (
            list((check.details or {}).get("maintained_docs", []))
            for check in getattr(deterministic_result, "checks", [])
            if getattr(check, "name", "") == "freshness"
        ),
        [],
    )
    return {
        "passed": bool(deterministic_result.passed),
        "score": float(deterministic_result.score),
        "summary": str(deterministic_result.summary),
        "blocking_docs": list(getattr(deterministic_result, "blocking_docs", [])),
        "non_blocking_docs": list(getattr(deterministic_result, "non_blocking_docs", [])),
        "claim_failures": list(getattr(deterministic_result, "claim_failures", [])),
        "unresolved_claims": list(getattr(deterministic_result, "unresolved_claims", [])),
        "contradicted_claims": list(getattr(deterministic_result, "contradicted_claims", [])),
        "workspace_profile": str(getattr(deterministic_result, "workspace_profile", "")),
        "graph_artifact": str(getattr(deterministic_result, "graph_artifact", "")),
        "blocking_render_status": dict(getattr(deterministic_result, "blocking_render_status", {})),
        "unresolved_item_counts": dict(getattr(deterministic_result, "unresolved_item_counts", {})),
        "freshness_report": freshness_report,
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "score": check.score,
                "message": check.message,
                "details": check.details,
            }
            for check in getattr(deterministic_result, "checks", [])
        ],
        "agent_advisory": agent_advisory or _default_agent_advisory_payload(),
    }


@app.command()
def contract(
    doc_type: str = typer.Option(
        "system-docs",
        "--type",
        help=(
            "Document type to preview: context, adr, api_contract, schema, "
            "runbook, system-docs, feature, testing, metadata, raw. Defaults to the "
            "canonical local KB contract."
        ),
    ),
    title: str = typer.Option(
        "Document Title",
        "--title",
        help="Sample title to use in the generated markdown template.",
    ),
    json: bool = typer.Option(False, "--json", help="Output contract as JSON."),
) -> None:
    """Show the canonical KB markdown contract and a sample document template."""
    from autonomous_agent_builder.knowledge.document_spec import (
        DEFAULT_KB_CONTRACT_TYPE,
        contract_payload,
    )

    try:
        payload = contract_payload(doc_type=doc_type, sample_title=title)
    except ValueError as exc:
        from autonomous_agent_builder.cli.output import error

        error(f"Error: {exc}")
        sys.exit(2)

    def fmt(data: dict) -> str:
        rules = "\n".join(f"  • {rule}" for rule in data["rules"])
        sections = "\n".join(f"  • {section}" for section in data["required_sections"])
        budgets = "\n".join(
            "  • "
            f"{item['heading']}: {item['min_words']}-{item['max_words']} words"
            f" — {item['purpose']}"
            for item in data.get("section_budgets", [])
        )
        presentation = "\n".join(
            f"  • {item['field']}: <= {item['max_words']} words — {item['purpose']}"
            for item in data.get("presentation_fields", [])
        )
        expectations = "\n".join(
            f"  • {item['heading']}: {item['expectation']}"
            for item in data.get("section_expectations", [])
        )
        required = "\n".join(
            f"  • {field}: {field_type}"
            for field, field_type in data["required_frontmatter"].items()
        )
        optional = "\n".join(
            f"  • {field}: {field_type}"
            for field, field_type in data["optional_frontmatter"].items()
        )
        return (
            f"KB document contract ({data['doc_type']})\n\n"
            f"Owner surface: document_spec.py (default={DEFAULT_KB_CONTRACT_TYPE})\n\n"
            f"Required frontmatter:\n{required}\n\n"
            f"Optional frontmatter:\n{optional}\n\n"
            f"Rules:\n{rules}\n\n"
            f"Required section pattern:\n{sections}\n\n"
            f"Section budgets:\n{budgets}\n\n"
            f"Presentation fields:\n{presentation or '  • none'}\n\n"
            f"Section expectations:\n{expectations or '  • none'}\n\n"
            f"Sample markdown:\n{data['sample_markdown']}"
        )

    render(payload, fmt, use_json=json)


@app.command()
def add(
    task: str | None = typer.Option(
        None,
        "--task",
        help="Optional task ID this doc belongs to.",
    ),
    doc_type: str = typer.Option(
        ...,
        "--type",
        help=f"Doc type: {', '.join(_SUPPORTED_DOC_TYPES)}.",
    ),
    title: str = typer.Option(..., help="Document title."),
    family: str | None = typer.Option(None, "--family", help="Optional system-doc family."),
    linked_feature: str | None = typer.Option(
        None,
        "--linked-feature",
        help="Feature name or slug this system doc tracks. Maintained feature/testing docs require task or feature linkage.",
    ),
    feature_id: str | None = typer.Option(
        None,
        "--feature-id",
        help="Optional feature ID. Maintained feature/testing docs require task or feature linkage.",
    ),
    refresh_required: bool | None = typer.Option(
        None,
        "--refresh-required/--no-refresh-required",
        help="Whether this system doc must be refreshed before task completion.",
    ),
    documented_against_commit: str | None = typer.Option(
        None,
        "--documented-against-commit",
        help="Main-branch commit this maintained doc was refreshed against. Required for maintained feature/testing docs.",
    ),
    documented_against_ref: str | None = typer.Option(
        None,
        "--documented-against-ref",
        help="Canonical ref for maintained-doc freshness baselines. Use `main` for canonical updates. Required for maintained feature/testing docs.",
    ),
    owned_paths: str | None = typer.Option(
        None,
        "--owned-paths",
        help="Comma-separated repo-relative paths this maintained doc owns for diff-based freshness checks. Required for maintained feature/testing docs.",
    ),
    verified_with: str | None = typer.Option(
        None,
        "--verified-with",
        help="Verification surface used most recently, for example api, browser, or pytest.",
    ),
    last_verified_at: str | None = typer.Option(
        None,
        "--last-verified-at",
        help="ISO timestamp for the last successful verification using this doc. Required for testing docs.",
    ),
    lifecycle_status: str | None = typer.Option(
        None,
        "--lifecycle-status",
        help="Optional lifecycle status for maintained docs: active, superseded, or quarantined.",
    ),
    superseded_by: str | None = typer.Option(
        None,
        "--superseded-by",
        help="Replacement doc ID when lifecycle status is superseded.",
    ),
    tags: str | None = typer.Option(
        None,
        "--tags",
        help="Optional comma-separated tags. The doc type is always included.",
    ),
    tag: list[str] = typer.Option(None, "--tag", help="Optional tag. Repeat for multiple tags."),
    feature_tag: bool = typer.Option(
        False,
        "--feature",
        help="Append the `feature` tag for easy knowledge filtering.",
    ),
    testing_tag: bool = typer.Option(
        False,
        "--testing",
        help="Append the `testing` tag for easy knowledge filtering.",
    ),
    content: str | None = typer.Option(None, help="Document content inline."),
    content_file: str | None = typer.Option(
        None, "--content-file", help="File to read content from (- for stdin)."
    ),
    scope: str = typer.Option(
        "local",
        "--scope",
        help="Publish scope. Only local is supported; use workflow CLI for global KB.",
    ),
    source_url: str | None = typer.Option(
        None,
        "--source-url",
        help="Canonical source URL for raw articles.",
    ),
    source_title: str | None = typer.Option(
        None,
        "--source-title",
        help="Source article title for raw articles.",
    ),
    source_author: str | None = typer.Option(
        None,
        "--source-author",
        help="Source author for raw articles.",
    ),
    date_published: str | None = typer.Option(
        None,
        "--date-published",
        help="Source publication date for raw articles.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Add a document to the knowledge base."""
    _ensure_builder_write_scope(scope)
    body = _read_content(content, content_file)
    payload = {
        "task_id": task,
        "doc_type": doc_type,
        "tags": _normalize_tags(
            tags,
            doc_type=doc_type,
            family=family,
            tag_values=tag,
            feature_tag=feature_tag,
            testing_tag=testing_tag,
        ),
        "title": title,
        "content": body,
        "scope": scope,
        "source_url": source_url,
        "source_title": source_title,
        "source_author": source_author,
        "date_published": date_published,
        "extra_fields": _system_doc_extra_fields(
            family=family,
            linked_feature=linked_feature,
            feature_id=feature_id,
            refresh_required=refresh_required,
            documented_against_commit=documented_against_commit,
            documented_against_ref=documented_against_ref,
            owned_paths=[part.strip() for part in (owned_paths or "").split(",") if part.strip()] or None,
            verified_with=verified_with,
            last_verified_at=last_verified_at,
            lifecycle_status=lifecycle_status,
            superseded_by=superseded_by,
        ),
    }

    if dry_run:
        preview = {**payload, "content": truncate(body, 200)}
        render(
            {"dry_run": True, "would_create": preview},
            lambda d: f"Would create {doc_type} '{title}'",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    try:
        data = publish_document(
            title=title,
            body=body,
            doc_type=doc_type,
            tags=payload["tags"],
            scope=scope,
            task_id=task or "",
            source_url=source_url,
            source_title=source_title,
            source_author=source_author,
            date_published=date_published,
            extra_fields=payload["extra_fields"],
        )
    except PublishError as exc:
        error(f"Error: {exc}")
        sys.exit(1)
    else:
        _render_publish_result("created", data, use_json=json)
        sys.exit(EXIT_SUCCESS)


@app.command("list")
def list_docs(
    task: str | None = typer.Option(None, "--task", help="Filter by task ID."),
    doc_type: str | None = typer.Option(None, "--type", help="Filter by doc type."),
    limit: int = typer.Option(6, help="Max results."),
    full: bool = typer.Option(False, "--full", help="Include complete document payloads in JSON output."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List knowledge base documents."""
    items = load_local_docs("local")
    if task:
        items = [item for item in items if str(item.get("task_id", "")) == task]
    if doc_type:
        items = [item for item in items if str(item.get("doc_type", "")) == doc_type]
    items = items[:limit]
    payload = _kb_full_payload("list", items) if json and full else _kb_search_payload("list", items)

    def fmt(list_items: list) -> str:
        headers = ["ID", "TYPE", "TITLE", "VERSION", "PREVIEW"]
        rows = [
            [
                str(d.get("id", "")),
                d.get("doc_type", ""),
                d.get("title", ""),
                f"v{d.get('version', 1)}",
                _kb_preview(d, max_chars=60),
            ]
            for d in list_items
        ]
        return table(headers, rows)

    render(payload if json else items, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def show(
    doc_id_parts: list[str] = typer.Argument(help="Document ID or search query."),
    section: str | None = typer.Option(
        None, "--section", help="Render only one markdown section by heading."
    ),
    full: bool = typer.Option(False, "--full", help="Show full content."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a KB document. Default truncates content; use --full for complete."""
    query = _join_query_parts(doc_id_parts)
    try:
        data, matched_on = _resolve_local_document(query)
    except AabApiError as e:
        _handle_kb_lookup_error(query, e, use_json=json)
    else:
        payload = dict(data)
        payload["matched_on"] = matched_on
        if section:
            extracted = _extract_section(str(payload.get("content", "")), section)
            if extracted is None:
                from autonomous_agent_builder.cli.output import error

                error(
                    f"Error: section '{section}' not found in {payload.get('id', query)}\n"
                    "Hint: run 'builder knowledge show <doc> --full' to inspect headings"
                )
                sys.exit(2)
            payload["content"] = extracted
            payload["section"] = section
        elif not full and isinstance(payload.get("content"), str):
            payload["content"] = truncate(payload["content"])

        def fmt(d: dict) -> str:
            lines = [
                f"id: {d.get('id', '')}",
                f"type: {d.get('doc_type', '')}",
                f"title: {d.get('title', '')}",
                f"version: v{d.get('version', 1)}",
                f"matched_on: {d.get('matched_on', 'id')}",
                f"task_id: {d.get('task_id', '')}",
                f"created: {d.get('created_at', '')}",
            ]
            if d.get("section"):
                lines.append(f"section: {d['section']}")
            if d.get("tags"):
                lines.append("tags: " + ", ".join(d["tags"]))
            lines.extend(["", d.get("content", "")])
            return "\n".join(lines)

        render(payload, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)


@app.command()
def search(
    query_parts: list[str] = typer.Argument(help="Search query."),
    doc_type: str | None = typer.Option(None, "--type", help="Filter by doc type."),
    task: str | None = typer.Option(None, "--task", help="Filter by task ID."),
    tags: str | None = typer.Option(None, "--tags", help="Filter by comma-separated tags."),
    tag: list[str] = typer.Option(None, "--tag", help="Filter by tag. Repeat for multiple tags."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search knowledge base documents by title and content."""
    query = _join_query_parts(query_parts)
    selected_tags: list[str] | None = None
    if tags or tag:
        selected_tags = _normalize_tags(
            tags,
            doc_type=doc_type or "knowledge",
            tag_values=tag,
        )
        if not doc_type and selected_tags and selected_tags[0] == "knowledge":
            selected_tags = selected_tags[1:]
    items = search_local_docs(
        query,
        scope="local",
        doc_type=doc_type,
        task_id=task,
        tags=selected_tags,
        limit=limit,
    )
    payload = _kb_search_payload(query, items)

    def fmt(search_items: list) -> str:
        headers = ["ID", "TYPE", "TITLE", "PREVIEW"]
        rows = [
            [
                str(d.get("id", "")),
                d.get("doc_type", ""),
                d.get("title", ""),
                _kb_preview(d, max_chars=70),
            ]
            for d in search_items
        ]
        return table(headers, rows)

    render(payload if json else items, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def summary(
    query_parts: list[str] = typer.Argument(help="Document ID or search query."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a bounded summary for a local KB document."""
    query = _join_query_parts(query_parts)
    try:
        data, matched_on = _resolve_local_document(query)
    except AabApiError as e:
        _handle_kb_lookup_error(query, e, use_json=json)
    else:
        preview = _kb_preview(data, max_chars=220)
        detail_summary = str(data.get("detail_summary", "") or "").strip()
        if " ".join(detail_summary.split()) == " ".join(preview.split()):
            detail_summary = ""
        change_guidance = _extract_section(str(data.get("content", "")), "Change guidance") or ""
        payload = {
            "id": data.get("id", ""),
            "title": data.get("title", ""),
            "doc_type": data.get("doc_type", ""),
            "version": data.get("version", 1),
            "matched_on": matched_on,
            "tags": (data.get("tags", []) or [])[:4] if isinstance(data.get("tags"), list) else [],
            "preview": preview,
            "summary": preview,
            "detail": truncate(detail_summary.replace("\n", " "), 220) if detail_summary else "",
            "change_guidance": truncate(change_guidance.replace("\n", " "), 160) if change_guidance else "",
            "next_step": f"builder knowledge show {data.get('id', '')} --section 'Change guidance' --json",
        }

        def fmt(d: dict) -> str:
            lines = [
                d.get("title", ""),
                f"id: {d.get('id', '')}",
                f"type: {d.get('doc_type', '')}",
                f"version: v{d.get('version', 1)}",
                f"matched_on: {d.get('matched_on', '')}",
            ]
            if d.get("tags"):
                lines.append("tags: " + ", ".join(d["tags"]))
            lines.extend(["", d.get("preview", "")])
            if d.get("detail"):
                lines.extend(["", f"detail: {d.get('detail', '')}"])
            if d.get("change_guidance"):
                lines.extend(["", f"change_guidance: {d.get('change_guidance', '')}"])
            lines.extend(["", f"Next: {d.get('next_step', '')}"])
            return "\n".join(lines)

        render(payload, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)


@app.command()
def update(
    doc_id: str = typer.Argument(help="Document ID to update."),
    title: str | None = typer.Option(None, help="New title."),
    family: str | None = typer.Option(None, "--family", help="Updated system-doc family."),
    linked_feature: str | None = typer.Option(
        None,
        "--linked-feature",
        help="Updated linked feature name or slug. Maintained feature/testing docs require task or feature linkage.",
    ),
    feature_id: str | None = typer.Option(
        None,
        "--feature-id",
        help="Updated feature ID. Maintained feature/testing docs require task or feature linkage.",
    ),
    refresh_required: bool | None = typer.Option(
        None,
        "--refresh-required/--no-refresh-required",
        help="Updated refresh requirement for this system doc.",
    ),
    documented_against_commit: str | None = typer.Option(
        None,
        "--documented-against-commit",
        help="Updated main-branch commit this maintained doc now reflects. Required for maintained feature/testing docs.",
    ),
    documented_against_ref: str | None = typer.Option(
        None,
        "--documented-against-ref",
        help="Updated canonical ref for this maintained doc. Use `main` for canonical freshness. Required for maintained feature/testing docs.",
    ),
    owned_paths: str | None = typer.Option(
        None,
        "--owned-paths",
        help="Updated comma-separated repo-relative paths this maintained doc owns. Required for maintained feature/testing docs.",
    ),
    verified_with: str | None = typer.Option(
        None,
        "--verified-with",
        help="Updated verification surface used by this doc.",
    ),
    last_verified_at: str | None = typer.Option(
        None,
        "--last-verified-at",
        help="Updated ISO timestamp for the last successful verification. Required for testing docs.",
    ),
    lifecycle_status: str | None = typer.Option(
        None,
        "--lifecycle-status",
        help="Updated lifecycle status for maintained docs: active, superseded, or quarantined.",
    ),
    superseded_by: str | None = typer.Option(
        None,
        "--superseded-by",
        help="Replacement doc ID when lifecycle status is superseded.",
    ),
    tags: str | None = typer.Option(
        None,
        "--tags",
        help="Updated comma-separated tags. The existing doc type is preserved automatically.",
    ),
    tag: list[str] = typer.Option(None, "--tag", help="Updated tag. Repeat for multiple tags."),
    feature_tag: bool = typer.Option(
        False,
        "--feature",
        help="Append the `feature` tag for easy knowledge filtering.",
    ),
    testing_tag: bool = typer.Option(
        False,
        "--testing",
        help="Append the `testing` tag for easy knowledge filtering.",
    ),
    content: str | None = typer.Option(None, help="New content inline."),
    content_file: str | None = typer.Option(
        None, "--content-file", help="File to read new content from (- for stdin)."
    ),
    scope: str = typer.Option(
        "local",
        "--scope",
        help="Document scope. Only local is supported; use workflow CLI for global KB.",
    ),
    source_url: str | None = typer.Option(
        None,
        "--source-url",
        help="Canonical source URL for raw articles.",
    ),
    source_title: str | None = typer.Option(
        None,
        "--source-title",
        help="Source article title for raw articles.",
    ),
    source_author: str | None = typer.Option(
        None,
        "--source-author",
        help="Source author for raw articles.",
    ),
    date_published: str | None = typer.Option(
        None,
        "--date-published",
        help="Source publication date for raw articles.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Update a KB document. Bumps version on content change."""
    _ensure_builder_write_scope(scope)
    payload: dict[str, Any] = {}
    if title:
        payload["title"] = title
    if content or content_file:
        payload["content"] = _read_content(content, content_file)
    if tags or tag or feature_tag or testing_tag:
        payload["tag_update"] = {
            "tags": tags,
            "tag_values": tag,
            "feature_tag": feature_tag,
            "testing_tag": testing_tag,
        }
    extra_fields = _system_doc_extra_fields(
        family=family,
        linked_feature=linked_feature,
        feature_id=feature_id,
        refresh_required=refresh_required,
        documented_against_commit=documented_against_commit,
        documented_against_ref=documented_against_ref,
        owned_paths=[part.strip() for part in (owned_paths or "").split(",") if part.strip()] or None,
        verified_with=verified_with,
        last_verified_at=last_verified_at,
        lifecycle_status=lifecycle_status,
        superseded_by=superseded_by,
    )
    if extra_fields:
        payload["extra_fields"] = extra_fields
    for key, value in (
        ("source_url", source_url),
        ("source_title", source_title),
        ("source_author", source_author),
        ("date_published", date_published),
    ):
        if value:
            payload[key] = value

    if not payload:
        error("Error: provide --title, --content, --content-file, tags, or provenance fields")
        sys.exit(2)

    if dry_run:
        render(
            {"dry_run": True, "doc_id": doc_id, "would_update": payload},
            lambda d: f"Would update document {doc_id}",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    try:
        normalized_tags: list[str] | None = None
        if payload.get("tag_update"):
            existing = find_local_doc(doc_id, scope="local")
            if existing is None:
                error(f"Error: document '{doc_id}' not found")
                sys.exit(1)
            tag_update = payload["tag_update"]
            normalized_tags = _normalize_tags(
                tag_update.get("tags"),
                doc_type=str(existing.get("doc_type", "")),
                family=family or str(existing.get("doc_family", "") or "") or None,
                tag_values=tag_update.get("tag_values"),
                feature_tag=bool(tag_update.get("feature_tag")),
                testing_tag=bool(tag_update.get("testing_tag")),
            )
        data = update_document(
            doc_id=doc_id,
            scope=scope,
            title=title,
            body=payload.get("content"),
            source_url=source_url,
            source_title=source_title,
            source_author=source_author,
            date_published=date_published,
            extra_fields=payload.get("extra_fields"),
            tags=normalized_tags,
        )
    except PublishError as exc:
        error(f"Error: {exc}")
        sys.exit(1)
    else:
        _render_publish_result("updated", data, use_json=json)
        sys.exit(EXIT_SUCCESS)


@app.command()
def extract(
    scope: str = typer.Option("full", help="Scope: full | package:<name> | feature:<id>"),
    doc: str | None = typer.Option(
        None,
        "--doc",
        help="Extract only one seed system-doc slug (for example system-architecture).",
    ),
    force: bool = typer.Option(False, "--force", help="Regenerate even if exists"),
    output_dir: str = typer.Option(
        DEFAULT_LOCAL_KB_COLLECTION,
        help=(
            "Output subdirectory in knowledge/. "
            "Only the canonical local KB collection is supported."
        ),
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    validate: bool = typer.Option(True, help="Run quality gate after extraction"),
) -> None:
    """Extract project knowledge through the canonical KB CLI orchestration surface.

    Generates comprehensive documentation by analyzing the codebase:
    - Project overview and description
    - Business context and domain entities
    - System architecture with diagrams
    - Code structure and organization
    - Technology stack and frameworks
    - Dependencies and packages

    Works offline (no server required). Generated docs are published through the
    single CLI writer into .agent-builder/knowledge/. This command is the
    canonical owner for extraction, deterministic validation, and next-step
    guidance consumed by onboarding and agents.

    Examples:
        builder knowledge extract
        builder knowledge extract --force
        builder knowledge extract --no-validate  # Skip quality gate
    """
    if output_dir != DEFAULT_LOCAL_KB_COLLECTION:
        message = (
            "Only the canonical local KB collection is supported. "
            f"Use --output-dir {DEFAULT_LOCAL_KB_COLLECTION}."
        )
        if json_output:
            payload = _build_extract_contract(
                kb_path=Path(".agent-builder") / "knowledge" / output_dir,
                documents=[],
                errors=[{"stage": "preflight", "error": "noncanonical_output_dir"}],
                graph=None,
                lint=None,
                deterministic_validation=None,
                agent_advisory=None,
                passed=False,
                operator_message=message,
                next_step=_kb_extract_next_step(
                    action="stop",
                    reason="noncanonical_output_dir",
                    recommended_command=(
                        "builder knowledge extract "
                        f"--output-dir {DEFAULT_LOCAL_KB_COLLECTION} --json"
                    ),
                ),
            )
            render_json(payload)
            sys.exit(EXIT_SUCCESS)
        error(f"Error: {message}")
        sys.exit(2)

    # Find .agent-builder directory
    agent_builder_dir = Path(".agent-builder")
    if not agent_builder_dir.exists():
        if json_output:
            payload = _build_extract_contract(
                kb_path=agent_builder_dir / "knowledge" / output_dir,
                documents=[],
                errors=[{"stage": "preflight", "error": ".agent-builder/ not found"}],
                graph=None,
                lint=None,
                deterministic_validation=None,
                agent_advisory=None,
                passed=False,
                operator_message=".agent-builder/ not found. Run 'builder init' first.",
                next_step=_kb_extract_next_step(
                    action="stop",
                    reason="builder_dir_missing",
                    recommended_command="builder init",
                ),
            )
            render_json(payload)
            sys.exit(EXIT_SUCCESS)
        error("Error: .agent-builder/ not found. Run 'builder init' first.")
        sys.exit(4)

    kb_path = agent_builder_dir / "knowledge" / output_dir

    # Check if already exists
    if kb_path.exists() and not force:
        target_file = kb_path / f"{doc}.md" if doc else None
        if doc and (not target_file or not target_file.exists()):
            target_file = None
        if doc and target_file is None:
            pass
        else:
            if json_output:
                payload = _build_extract_contract(
                    kb_path=kb_path,
                    documents=[],
                    errors=[{"stage": "preflight", "error": "knowledge_already_exists"}],
                    graph=None,
                    lint=None,
                    deterministic_validation=None,
                    agent_advisory=None,
                    passed=False,
                    operator_message=(
                        f"Knowledge already extracted at {kb_path}. "
                        "Use --force to regenerate."
                    ),
                    next_step=_kb_extract_next_step(
                        action="stop",
                        reason="knowledge_already_exists",
                        recommended_command=(
                            "builder knowledge extract --force "
                            f"--doc {doc} --output-dir {output_dir} --json"
                            if doc
                            else (
                                "builder knowledge extract --force "
                                f"--output-dir {output_dir} --json"
                            )
                        ),
                    ),
                )
                render_json(payload)
                sys.exit(EXIT_SUCCESS)
            error(f"Knowledge already extracted at {kb_path}\nUse --force to regenerate")
            sys.exit(1)

    # Extract knowledge
    if not json_output:
        typer.echo("🔍 Analyzing project structure...")

    try:
        output_data = _run_extract_pipeline(
            workspace_path=Path.cwd(),
            kb_path=kb_path,
            scope=scope,
            run_validation=validate,
            doc_slug=doc,
        )

        if json_output:
            render_json(output_data)
            sys.exit(EXIT_SUCCESS)

        typer.echo(f"\n[OK] Extracted {len(output_data['documents'])} documents to {kb_path}\n")
        for doc in output_data["documents"]:
            typer.echo(f"  - {doc['type']}: {doc['title']}")

        if output_data.get("errors"):
            typer.echo(f"\n[WARN] {len(output_data['errors'])} errors occurred:")
            for error_info in output_data["errors"]:
                stage = error_info.get("generator", error_info.get("stage", "unknown"))
                typer.echo(f"  - {stage}: {error_info['error']}")

        lint_payload = output_data["lint"]
        if validate:
            typer.echo(
                "\nDeterministic KB gate: "
                f"{'passed' if output_data['validation']['deterministic']['passed'] else 'failed'}"
            )
            typer.echo(
                "  • Lint: "
                f"{'passed' if lint_payload['passed'] else 'failed'} "
                f"({lint_payload['counts']['passed']}/{lint_payload['counts']['total']} clean)"
            )
            typer.echo(
                "  • Validation: "
                f"{output_data['validation']['deterministic']['summary']}"
            )

            advisory = output_data["validation"]["agent_advisory"]
            if advisory["available"]:
                typer.echo(
                    "\n🤔 Agent advisory: "
                    f"{'passed' if advisory['passed'] else 'follow-up suggested'}"
                )
                typer.echo(f"  • {advisory['summary']}")
                if advisory["recommendations"]:
                    typer.echo("  • Recommendations:")
                    for rec in advisory["recommendations"][:5]:
                        typer.echo(f"    - {rec}")
            elif advisory["summary"]:
                typer.echo(f"\n🤔 Agent advisory unavailable: {advisory['summary']}")

        typer.echo(f"\n{output_data['operator_message']}")
        if output_data["next_step"]["recommended_command"]:
            typer.echo(f"Next: {output_data['next_step']['recommended_command']}")

        typer.echo("\n📚 Use 'builder knowledge list --type system-docs' to view extracted seed docs")
        typer.echo("🔎 Use 'builder knowledge search <query>' to search across all knowledge")

        if not output_data["passed"]:
            sys.exit(1)

        sys.exit(EXIT_SUCCESS)

    except Exception as e:
        if json_output:
            payload = _build_extract_contract(
                kb_path=kb_path,
                documents=[],
                errors=[{"stage": "exception", "error": str(e)}],
                graph=None,
                lint=None,
                deterministic_validation=None,
                agent_advisory=None,
                passed=False,
                operator_message=f"Error during extraction: {e}",
                next_step=_kb_extract_next_step(
                    action="stop",
                    reason="exception",
                    recommended_command="builder knowledge extract --force --json",
                ),
            )
            render_json(payload)
            sys.exit(EXIT_SUCCESS)
        error(f"Error during extraction: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@app.command()
def validate(
    kb_dir: str = typer.Option(
        "system-docs",
        help="Knowledge base directory to validate (relative to .agent-builder/knowledge/)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed check results"),
    use_agent: bool = typer.Option(
        False,
        "--use-agent/--no-use-agent",
        help="Run Claude agent as advisory after deterministic validation.",
    ),
    model: str | None = typer.Option(
        None,
        help="Claude model for advisory evaluation (defaults to the KB validation model in settings).",
    ),
) -> None:
    """Run deterministic KB validation.

    The default path validates only blocking docs using manifest-backed claims,
    citations, and freshness checks. `--use-agent` adds a non-blocking advisory
    Claude review after deterministic validation completes.

    Examples:
        builder knowledge validate
        builder knowledge validate --verbose
        builder knowledge validate --use-agent
        builder knowledge validate --use-agent --model claude-opus-4-7
    """
    # Find knowledge base directory
    agent_builder_dir = Path(".agent-builder")
    if not agent_builder_dir.exists():
        from autonomous_agent_builder.cli.output import error

        error("Error: .agent-builder/ not found. Run 'builder init' first.")
        sys.exit(4)

    kb_path = agent_builder_dir / "knowledge" / kb_dir

    if not kb_path.exists():
        from autonomous_agent_builder.cli.output import error

        error(f"Error: Knowledge base not found at {kb_path}")
        error("Run 'builder knowledge extract' first.")
        sys.exit(1)

    # Run quality gate
    if not json_output:
        typer.echo(f"🔍 Running deterministic KB validation on {kb_path}...\n")

    try:
        from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate

        deterministic_result = KnowledgeQualityGate(kb_path, Path.cwd()).validate()
        advisory_payload = _default_agent_advisory_payload()

        if use_agent:
            from autonomous_agent_builder.config import get_settings
            from autonomous_agent_builder.knowledge.agent_quality_gate import (
                AgentKnowledgeQualityGate,
            )

            advisory_result = AgentKnowledgeQualityGate(kb_path, Path.cwd()).validate(
                model=model or get_settings().agent.kb_validation_model
            )
            advisory_payload = {
                "available": advisory_result.evaluation.get("fallback") != "rule-based",
                "passed": advisory_result.passed,
                "score": advisory_result.score,
                "summary": advisory_result.summary,
                "recommendations": advisory_result.recommendations,
            }

        if json_output:
            import json as json_lib

            typer.echo(
                json_lib.dumps(
                    _validate_output_payload(
                        deterministic_result,
                        agent_advisory=advisory_payload,
                    ),
                    indent=2,
                )
            )
        else:
            if deterministic_result.passed:
                typer.echo(f"[OK] {deterministic_result.summary}\n")
            else:
                typer.echo(f"[FAIL] {deterministic_result.summary}\n")

            typer.echo("Quality Checks:")
            for check in deterministic_result.checks:
                status = "[OK]  " if check.passed else "[FAIL]"
                typer.echo(f"  {status} {check.name}: {check.message} ({check.score:.0%})")
                if verbose and check.details:
                    for key, value in check.details.items():
                        if isinstance(value, list) and value:
                            typer.echo(f"      {key}:")
                            for item in value[:5]:
                                if key == "maintained_docs" and isinstance(item, dict):
                                    typer.echo(
                                        "        - "
                                        f"{item.get('doc_id', '')}: {item.get('status', '')}"
                                        f" (baseline={item.get('documented_against_commit', '') or 'missing'}, "
                                        f"main={item.get('current_main_commit', '') or 'unresolved'})"
                                    )
                                    matched = item.get("matched_changed_paths") or []
                                    if matched:
                                        typer.echo(f"          matched_changed_paths: {', '.join(str(path) for path in matched[:4])}")
                                else:
                                    typer.echo(f"        - {item}")
                            if len(value) > 5:
                                typer.echo(f"        ... and {len(value) - 5} more")
                        elif not isinstance(value, list):
                            typer.echo(f"      {key}: {value}")

            if use_agent:
                typer.echo()
                label = "available" if advisory_payload["available"] else "unavailable"
                typer.echo(f"Agent advisory ({label}):")
                typer.echo(f"  {advisory_payload['summary'] or 'No advisory summary returned.'}")
                if advisory_payload.get("recommendations"):
                    typer.echo("  Recommendations:")
                    for rec in advisory_payload["recommendations"]:
                        typer.echo(f"    - {rec}")

            if not deterministic_result.passed:
                typer.echo("\nNext step:")
                typer.echo("  • Run `builder knowledge extract --force --json` after repairing the cited blocking docs.")

        sys.exit(EXIT_SUCCESS if deterministic_result.passed else 1)

    except Exception as e:
        from autonomous_agent_builder.cli.output import error

        error(f"Error during validation: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@app.command()
def lint(
    kb_dir: str = typer.Option(
        "system-docs",
        help="Knowledge base directory to lint (relative to .agent-builder/knowledge/)",
    ),
    content: str | None = typer.Option(
        None,
        "--content",
        help="Lint a single markdown document passed inline instead of a directory.",
    ),
    content_file: str | None = typer.Option(
        None,
        "--content-file",
        help="Lint a single markdown document from a file (- for stdin).",
    ),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as errors"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show details for all files"),
) -> None:
    """Lint knowledge base documents for format compliance.

    Validates:
    - Frontmatter format (YAML)
    - Required fields (title, tags, doc_type, created, auto_generated)
    - Field types and values
    - Markdown structure
    - Content quality

    Examples:
        builder knowledge lint
        builder knowledge lint --strict
        builder knowledge lint --verbose
        builder knowledge lint --kb-dir custom-docs
    """
    from autonomous_agent_builder.knowledge.document_spec import DocumentLinter, lint_directory

    if content and content_file:
        from autonomous_agent_builder.cli.output import error

        error("Error: choose either --content or --content-file, not both")
        sys.exit(2)

    if content or content_file:
        source = "<inline>"
        if content_file == "-":
            source = "<stdin>"
        elif content_file:
            source = content_file

        markdown = _read_content(content, content_file)
        linter = DocumentLinter(strict=strict)
        passed = linter.lint_content(markdown, source)

        typer.echo(f"Linting document {source}...")
        typer.echo()
        typer.echo(linter.get_report())
        typer.echo()

        if passed:
            typer.echo("[OK] Document passes KB contract checks")
            sys.exit(0)

        typer.echo("[FAIL] Document failed KB contract checks")
        sys.exit(1)

    # Find knowledge base directory
    kb_path = Path(".agent-builder") / "knowledge" / kb_dir

    if not kb_path.exists():
        from autonomous_agent_builder.cli.output import error

        error(f"Error: Knowledge base not found at {kb_path}")
        error("Run 'builder knowledge extract' first.")
        sys.exit(1)

    typer.echo(f"Linting documents in {kb_path}...")
    typer.echo()

    passed, failed, total = lint_directory(kb_path, strict=strict, verbose=verbose)

    typer.echo()
    typer.echo("=" * 60)
    typer.echo(f"Results: {passed}/{total} passed, {failed}/{total} failed")

    if failed == 0:
        typer.echo("[OK] All documents pass linting checks!")
        sys.exit(0)
    else:
        typer.echo(f"[FAIL] {failed} document(s) failed linting")
        sys.exit(1)
