"""Knowledge extraction routes for dashboard."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import structlog

log = structlog.get_logger()

router = APIRouter(tags=["knowledge-extraction"])


class ExtractionRequest(BaseModel):
    """Request to extract knowledge base."""

    method: str = "ast"  # "ast" or "agent"
    force: bool = False
    validate: bool = True
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


@router.get("/knowledge/status", response_model=KnowledgeBaseStatus)
async def get_kb_status() -> KnowledgeBaseStatus:
    """Get current knowledge base status."""
    kb_path = Path(".agent-builder/knowledge/reverse-engineering")

    if not kb_path.exists():
        return KnowledgeBaseStatus(
            exists=False,
            document_count=0,
            last_extracted=None,
            extraction_method=None,
            quality_score=None,
        )

    # Count documents
    doc_files = list(kb_path.glob("*.md"))
    doc_count = len([f for f in doc_files if f.stem != "extraction-metadata"])

    # Read metadata
    metadata_file = kb_path / "extraction-metadata.md"
    last_extracted = None
    extraction_method = None

    if metadata_file.exists():
        content = metadata_file.read_text(encoding="utf-8")
        
        # Extract timestamp
        import re
        match = re.search(r"\*\*Extracted At\*\*:\s*([^\n]+)", content)
        if match:
            last_extracted = match.group(1).strip()
        
        # Extract method
        if "agent-based" in content.lower():
            extraction_method = "agent"
        elif "ast" in content.lower() or "reverse-engineering" in content.lower():
            extraction_method = "ast"

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

    kb_path = Path(".agent-builder/knowledge/reverse-engineering")
    workspace_path = Path.cwd()

    try:
        if request.method == "agent":
            # Agent-based extraction
            from autonomous_agent_builder.knowledge.agent_extractor import AgentKnowledgeExtractor

            log.info("starting_agent_extraction", doc_types=request.doc_types)

            extractor = AgentKnowledgeExtractor(
                workspace_path=workspace_path,
                output_path=kb_path,
            )

            results = extractor.extract(
                doc_types=request.doc_types,
                model=request.model,
            )

        else:
            # AST-based extraction
            from autonomous_agent_builder.knowledge import KnowledgeExtractor

            log.info("starting_ast_extraction")

            extractor = KnowledgeExtractor(
                workspace_path=workspace_path,
                output_path=kb_path,
            )

            results = extractor.extract(scope="full")

        # Run quality gate if requested
        quality_gate_result = None
        if request.validate:
            from autonomous_agent_builder.knowledge.agent_quality_gate import (
                AgentKnowledgeQualityGate,
            )

            log.info("running_quality_gate")

            gate = AgentKnowledgeQualityGate(kb_path, workspace_path)
            gate_result = gate.validate(model=request.model)
            quality_gate_result = gate_result.to_dict()

        duration = time.time() - start_time

        return ExtractionResponse(
            status="completed",
            documents=results.get("documents", []),
            errors=results.get("errors", []),
            quality_gate=quality_gate_result,
            extraction_method=request.method,
            duration_seconds=duration,
        )

    except Exception as e:
        log.error("extraction_error", error=str(e))
        duration = time.time() - start_time

        return ExtractionResponse(
            status="failed",
            documents=[],
            errors=[{"error": str(e)}],
            quality_gate=None,
            extraction_method=request.method,
            duration_seconds=duration,
        )


@router.post("/knowledge/validate", response_model=ValidationResponse)
async def validate_knowledge() -> ValidationResponse:
    """Run quality gate validation on existing knowledge base."""
    kb_path = Path(".agent-builder/knowledge/reverse-engineering")
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
        result = gate.validate()

        return ValidationResponse(
            passed=result.passed,
            score=result.score,
            summary=result.summary,
            evaluation=result.evaluation,
            recommendations=result.recommendations,
            agent_reasoning=result.agent_reasoning,
        )

    except Exception as e:
        log.error("validation_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/documents")
async def list_documents() -> dict[str, Any]:
    """List all knowledge base documents."""
    kb_path = Path(".agent-builder/knowledge/reverse-engineering")

    if not kb_path.exists():
        return {"documents": [], "total": 0}

    documents = []
    for doc_file in sorted(kb_path.glob("*.md")):
        if doc_file.stem == "extraction-metadata":
            continue

        content = doc_file.read_text(encoding="utf-8")

        # Extract frontmatter
        title = doc_file.stem.replace("-", " ").title()
        tags = []
        doc_type = "reverse-engineering"

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                
                # Extract title
                import re
                title_match = re.search(r'title:\s*"([^"]+)"', frontmatter)
                if title_match:
                    title = title_match.group(1)
                
                # Extract tags
                tags_match = re.search(r'tags:\s*\[([^\]]+)\]', frontmatter)
                if tags_match:
                    tags = [t.strip(' "') for t in tags_match.group(1).split(",")]

        # Get content preview
        body = content.split("---", 2)[2] if content.startswith("---") else content
        preview = body[:200].strip() + "..." if len(body) > 200 else body.strip()

        documents.append({
            "filename": doc_file.name,
            "title": title,
            "tags": tags,
            "doc_type": doc_type,
            "size": len(content),
            "preview": preview,
        })

    return {"documents": documents, "total": len(documents)}


@router.get("/knowledge/documents/{filename}")
async def get_document(filename: str) -> dict[str, Any]:
    """Get a specific knowledge base document."""
    kb_path = Path(".agent-builder/knowledge/reverse-engineering")
    doc_file = kb_path / filename

    if not doc_file.exists():
        raise HTTPException(status_code=404, detail="Document not found")

    content = doc_file.read_text(encoding="utf-8")

    # Extract frontmatter
    frontmatter = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter_text = parts[1]
            body = parts[2]

            # Parse frontmatter
            import re
            for line in frontmatter_text.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip().strip('"')

                    if key == "tags" and "[" in value:
                        tags = value.strip("[]").split(",")
                        frontmatter[key] = [t.strip().strip('"') for t in tags]
                    else:
                        frontmatter[key] = value

    return {
        "filename": filename,
        "frontmatter": frontmatter,
        "content": body.strip(),
        "full_content": content,
    }


@router.delete("/knowledge")
async def delete_knowledge_base() -> dict[str, str]:
    """Delete the entire knowledge base."""
    kb_path = Path(".agent-builder/knowledge/reverse-engineering")

    if not kb_path.exists():
        return {"message": "Knowledge base does not exist"}

    try:
        import shutil
        shutil.rmtree(kb_path)
        log.info("knowledge_base_deleted", path=str(kb_path))
        return {"message": "Knowledge base deleted successfully"}

    except Exception as e:
        log.error("delete_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
