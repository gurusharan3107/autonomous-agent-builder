"""Knowledge extraction routes for dashboard."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from autonomous_agent_builder.knowledge.publisher import (
    DEFAULT_LOCAL_KB_COLLECTION,
    parse_markdown_document,
)

log = structlog.get_logger()

router = APIRouter(tags=["knowledge-extraction"])


class ExtractionRequest(BaseModel):
    """Request to extract knowledge base."""

    model_config = ConfigDict(populate_by_name=True)

    # Deprecated; extraction always uses the canonical deterministic lane.
    method: str | None = None
    force: bool = False
    run_validation: bool = Field(default=True, alias="validate")
    model: str = "claude-sonnet-4-20250514"
    doc_types: list[str] | None = None


class ExtractionResponse(BaseModel):
    """Response from extraction."""

    status: str  # "running", "completed", "failed"
    documents: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    quality_gate: dict[str, Any] | None = None
    extraction_method: str
    duration_seconds: float | None = None


class ValidationResponse(BaseModel):
    """Response from quality gate validation."""

    passed: bool
    score: float
    summary: str
    evaluation: dict[str, Any]
    recommendations: list[str]
    agent_reasoning: str


class KnowledgeBaseStatus(BaseModel):
    """Current status of knowledge base."""

    exists: bool
    document_count: int
    last_extracted: str | None
    extraction_method: str | None
    quality_score: float | None


def _local_knowledge_root() -> Path:
    return Path(".agent-builder/knowledge")


def _iter_local_docs(kb_root: Path) -> list[Path]:
    docs: list[Path] = []
    for doc_file in sorted(kb_root.rglob("*.md")):
        relative_parts = doc_file.relative_to(kb_root).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        if doc_file.stem == "extraction-metadata":
            continue
        docs.append(doc_file)
    return docs


@router.get("/knowledge/status", response_model=KnowledgeBaseStatus)
async def get_kb_status() -> KnowledgeBaseStatus:
    """Get current knowledge base status."""
    kb_root = _local_knowledge_root()
    kb_path = kb_root / DEFAULT_LOCAL_KB_COLLECTION

    if not kb_root.exists():
        return KnowledgeBaseStatus(
            exists=False,
            document_count=0,
            last_extracted=None,
            extraction_method=None,
            quality_score=None,
        )

    # Count documents
    doc_count = len(_iter_local_docs(kb_root))

    # Read metadata
    metadata_file = kb_path / "extraction-metadata.md"
    last_extracted = None
    extraction_method = None

    if metadata_file.exists():
        content = metadata_file.read_text(encoding="utf-8")

        # Extract timestamp
        match = re.search(r"\*\*Extracted At\*\*:\s*([^\n]+)", content)
        if match:
            last_extracted = match.group(1).strip()

        extraction_method = "deterministic"

    return KnowledgeBaseStatus(
        exists=True,
        document_count=doc_count,
        last_extracted=last_extracted,
        extraction_method=extraction_method,
        quality_score=None,  # Would need to run validation to get this
    )


@router.post("/knowledge/extract", response_model=ExtractionResponse)
async def extract_knowledge(request: ExtractionRequest) -> ExtractionResponse:
    """Extract knowledge base (async operation).

    This endpoint triggers knowledge extraction and returns immediately.
    Use /knowledge/status to poll for completion.
    """
    import time
    start_time = time.time()

    kb_path = Path(".agent-builder/knowledge") / DEFAULT_LOCAL_KB_COLLECTION
    workspace_path = Path.cwd()

    try:
        from autonomous_agent_builder.knowledge import KnowledgeExtractor

        log.info("starting_deterministic_extraction", doc_types=request.doc_types)

        extractor = KnowledgeExtractor(
            workspace_path=workspace_path,
            output_path=kb_path,
            doc_slugs=request.doc_types,
        )

        results = extractor.extract(scope="full")

        # Run quality gate if requested
        quality_gate_result = None
        if request.run_validation:
            from autonomous_agent_builder.knowledge.agent_quality_gate import (
                AgentKnowledgeQualityGate,
            )

            log.info("running_quality_gate")

            gate = AgentKnowledgeQualityGate(kb_path, workspace_path)
            gate_result = await gate.validate_async(model=request.model)
            quality_gate_result = gate_result.to_dict()

        duration = time.time() - start_time

        return ExtractionResponse(
            status="completed",
            documents=results.get("documents", []),
            errors=results.get("errors", []),
            quality_gate=quality_gate_result,
            extraction_method="deterministic",
            duration_seconds=duration,
        )

    except Exception as exc:
        log.error("extraction_error", error=str(exc))
        duration = time.time() - start_time

        return ExtractionResponse(
            status="failed",
            documents=[],
            errors=[{"error": str(exc)}],
            quality_gate=None,
            extraction_method="deterministic",
            duration_seconds=duration,
        )


@router.post("/knowledge/validate", response_model=ValidationResponse)
async def validate_knowledge() -> ValidationResponse:
    """Run quality gate validation on existing knowledge base."""
    kb_path = Path(".agent-builder/knowledge") / DEFAULT_LOCAL_KB_COLLECTION
    workspace_path = Path.cwd()

    if not kb_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found. Run extraction first.",
        )

    try:
        from autonomous_agent_builder.knowledge.agent_quality_gate import (
            AgentKnowledgeQualityGate,
        )

        log.info("running_quality_gate_validation")

        gate = AgentKnowledgeQualityGate(kb_path, workspace_path)
        result = await gate.validate_async()

        return ValidationResponse(
            passed=result.passed,
            score=result.score,
            summary=result.summary,
            evaluation=result.evaluation,
            recommendations=result.recommendations,
            agent_reasoning=result.agent_reasoning,
        )

    except Exception as exc:
        log.error("validation_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/knowledge/documents")
async def list_documents() -> dict[str, Any]:
    """List all knowledge base documents."""
    kb_root = _local_knowledge_root()

    if not kb_root.exists():
        return {"documents": [], "total": 0}

    documents = []
    for doc_file in _iter_local_docs(kb_root):
        content = doc_file.read_text(encoding="utf-8")
        relative_path = doc_file.relative_to(kb_root)
        inferred_type = relative_path.parts[0] if len(relative_path.parts) > 1 else "context"
        parsed = parse_markdown_document(content, default_doc_type=inferred_type)

        # Get content preview
        body = parsed.body
        preview = body[:200].strip() + "..." if len(body) > 200 else body.strip()

        documents.append({
            "filename": str(relative_path),
            "title": parsed.title,
            "tags": parsed.tags,
            "doc_type": inferred_type,
            "size": len(content),
            "preview": preview,
        })

    return {"documents": documents, "total": len(documents)}


@router.get("/knowledge/documents/{filename:path}")
async def get_document(filename: str) -> dict[str, Any]:
    """Get a specific knowledge base document."""
    kb_root = _local_knowledge_root()
    doc_file = kb_root / filename

    if not doc_file.exists() or not doc_file.is_file():
        raise HTTPException(status_code=404, detail="Document not found")

    content = doc_file.read_text(encoding="utf-8")
    relative_path = doc_file.relative_to(kb_root)
    inferred_type = relative_path.parts[0] if len(relative_path.parts) > 1 else "context"
    parsed = parse_markdown_document(content, default_doc_type=inferred_type)

    return {
        "filename": str(relative_path),
        "frontmatter": {
            "title": parsed.title,
            "tags": parsed.tags,
            "doc_type": inferred_type,
            "created": parsed.created,
            "auto_generated": parsed.auto_generated,
            "version": parsed.version,
            "updated": parsed.updated,
            "wikilinks": parsed.wikilinks,
            **parsed.extra_fields,
        },
        "content": parsed.body.strip(),
        "full_content": content,
    }


@router.delete("/knowledge")
async def delete_knowledge_base() -> dict[str, str]:
    """Delete the entire knowledge base."""
    kb_path = Path(".agent-builder/knowledge") / DEFAULT_LOCAL_KB_COLLECTION

    if not kb_path.exists():
        return {"message": "Knowledge base does not exist"}

    try:
        import shutil
        shutil.rmtree(kb_path)
        log.info("knowledge_base_deleted", path=str(kb_path))
        return {"message": "Knowledge base deleted successfully"}

    except Exception as exc:
        log.error("delete_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
