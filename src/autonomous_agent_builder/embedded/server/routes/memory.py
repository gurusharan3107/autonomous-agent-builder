"""Memory API routes for embedded server."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.session import get_db

router = APIRouter()


def parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from markdown content."""
    frontmatter = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            yaml_content = parts[1].strip()
            for line in yaml_content.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    # Handle lists in square brackets
                    if value.startswith("[") and value.endswith("]"):
                        # Remove brackets and split by comma
                        items = value[1:-1].split(",")
                        value = [v.strip() for v in items if v.strip()]
                    frontmatter[key] = value
    return frontmatter


@router.get("/memory/")
async def list_memories(req: Request, db: AsyncSession = Depends(get_db)):
    """List all memory entries from .memory folder."""
    project_root = Path(req.app.state.project_root)
    memory_dir = project_root / ".memory"
    
    if not memory_dir.exists():
        return []
    
    memories = []
    
    # Read decisions
    decisions_dir = memory_dir / "decisions"
    if decisions_dir.exists():
        for file in decisions_dir.glob("*.md"):
            content = file.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content)
            tags = frontmatter.get("tags", [])
            # Ensure tags is always a list
            if isinstance(tags, str):
                tags = []
            memories.append({
                "slug": file.stem,
                "title": frontmatter.get("title", file.stem.replace("-", " ").title()),
                "type": "decision",
                "path": str(file.relative_to(project_root)),
                "date": frontmatter.get("date", ""),
                "phase": frontmatter.get("phase", ""),
                "entity": frontmatter.get("entity", ""),
                "tags": tags,
                "status": frontmatter.get("status", ""),
            })
    
    # Read patterns
    patterns_dir = memory_dir / "patterns"
    if patterns_dir.exists():
        for file in patterns_dir.glob("*.md"):
            content = file.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content)
            tags = frontmatter.get("tags", [])
            # Ensure tags is always a list
            if isinstance(tags, str):
                tags = []
            memories.append({
                "slug": file.stem,
                "title": frontmatter.get("title", file.stem.replace("-", " ").title()),
                "type": "pattern",
                "path": str(file.relative_to(project_root)),
                "date": frontmatter.get("date", ""),
                "phase": frontmatter.get("phase", ""),
                "entity": frontmatter.get("entity", ""),
                "tags": tags,
                "status": frontmatter.get("status", ""),
            })
    
    # Read corrections
    corrections_dir = memory_dir / "corrections"
    if corrections_dir.exists():
        for file in corrections_dir.glob("*.md"):
            content = file.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content)
            tags = frontmatter.get("tags", [])
            # Ensure tags is always a list
            if isinstance(tags, str):
                tags = []
            memories.append({
                "slug": file.stem,
                "title": frontmatter.get("title", file.stem.replace("-", " ").title()),
                "type": "correction",
                "path": str(file.relative_to(project_root)),
                "date": frontmatter.get("date", ""),
                "phase": frontmatter.get("phase", ""),
                "entity": frontmatter.get("entity", ""),
                "tags": tags,
                "status": frontmatter.get("status", ""),
            })
    
    return memories


@router.get("/memory/{slug}")
async def get_memory(slug: str, req: Request, db: AsyncSession = Depends(get_db)):
    """Get a specific memory entry."""
    project_root = Path(req.app.state.project_root)
    memory_dir = project_root / ".memory"
    
    # Search in all subdirectories
    for subdir in ["decisions", "patterns", "corrections"]:
        file_path = memory_dir / subdir / f"{slug}.md"
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content)
            return {
                "slug": slug,
                "title": frontmatter.get("title", slug.replace("-", " ").title()),
                "content": content,
                "type": subdir.rstrip("s"),  # Remove trailing 's'
                "path": str(file_path.relative_to(project_root)),
                "date": frontmatter.get("date", ""),
                "phase": frontmatter.get("phase", ""),
                "entity": frontmatter.get("entity", ""),
                "tags": frontmatter.get("tags", []),
                "status": frontmatter.get("status", ""),
            }
    
    return {"slug": slug, "content": "", "type": "", "error": "Memory not found"}
