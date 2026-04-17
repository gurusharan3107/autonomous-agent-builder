"""Knowledge Base API routes for embedded server."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.session import get_db

router = APIRouter()

KBScope = Literal["local", "global"]


def extract_wikilinks(content: str) -> list[str]:
    """Extract [[wikilink]] references from markdown content."""
    pattern = r'\[\[([^\]]+)\]\]'
    matches = re.findall(pattern, content)
    return [m.strip() for m in matches]


def extract_tags(content: str) -> list[str]:
    """Extract tags from YAML frontmatter."""
    tags = []
    lines = content.split("\n")
    
    if lines and lines[0].strip() == "---":
        in_frontmatter = True
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if line.startswith("tags:"):
                # Parse tags: [tag1, tag2] or tags: tag1, tag2
                tag_content = line.split("tags:", 1)[1].strip()
                if tag_content.startswith("[") and tag_content.endswith("]"):
                    tag_content = tag_content[1:-1]
                tags = [t.strip().strip('"\'') for t in tag_content.split(",")]
                break
    
    return tags


def extract_frontmatter_field(content: str, field: str) -> str | None:
    """Extract a specific field from YAML frontmatter."""
    lines = content.split("\n")
    
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if line.startswith(f"{field}:"):
                value = line.split(f"{field}:", 1)[1].strip().strip('"\'')
                return value
    
    return None


def get_body_content(content: str) -> str:
    """Extract body content after frontmatter, skipping headers."""
    lines = content.split("\n")
    body_start_idx = 0
    
    # Find where frontmatter ends
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                body_start_idx = i + 1
                break
    
    # Get body lines after frontmatter
    body_lines = lines[body_start_idx:]
    
    # Extract first meaningful paragraph (skip headers and empty lines)
    content_lines = []
    
    for line in body_lines:
        stripped = line.strip()
        
        # Skip empty lines and markdown headers
        if not stripped or stripped.startswith("#"):
            # If we already have content and hit a break, stop
            if content_lines and len("\n".join(content_lines)) > 100:
                break
            continue
        
        # This is actual content
        content_lines.append(line)
        
        # Stop if we have enough
        if len("\n".join(content_lines)) > 500:
            break
    
    return "\n".join(content_lines).strip()


def find_backlinks(doc_id: str, doc_title: str, kb_path: Path) -> list[dict]:
    """Find all docs that link to this doc via wikilinks."""
    backlinks = []
    
    for file_path in kb_path.rglob("*.md"):
        relative_path = file_path.relative_to(kb_path)
        relative_parts = relative_path.parts
        
        # Skip hidden files/dirs
        if any(part.startswith(".") for part in relative_parts):
            continue
        
        # Skip self
        if str(relative_path) == doc_id:
            continue
        
        try:
            content = file_path.read_text(encoding="utf-8")
            links = extract_wikilinks(content)
            
            # Check if any link matches this doc's id or title
            for link in links:
                if link in doc_id or doc_id in link or link.lower() in doc_title.lower():
                    # Extract title from this file
                    lines = content.split("\n")
                    title = file_path.stem
                    
                    if lines:
                        if lines[0].strip() == "---":
                            for i, line in enumerate(lines[1:], 1):
                                if line.strip() == "---":
                                    break
                                if line.startswith("title:"):
                                    title = line.split("title:", 1)[1].strip().strip('"\'')
                                    break
                        elif lines[0].startswith("#"):
                            title = lines[0].strip("# ").strip()
                    
                    backlinks.append({
                        "id": str(relative_path),
                        "title": title,
                        "content": content[:200]
                    })
                    break
        except Exception:
            continue
    
    return backlinks


def find_similar_docs(doc: dict, kb_path: Path, limit: int = 10) -> list[dict]:
    """Find similar documents by shared tags."""
    doc_tags = set(doc.get("tags", []))
    if not doc_tags:
        return []
    
    similar = []
    
    for file_path in kb_path.rglob("*.md"):
        relative_path = file_path.relative_to(kb_path)
        relative_parts = relative_path.parts
        
        # Skip hidden files/dirs
        if any(part.startswith(".") for part in relative_parts):
            continue
        
        # Skip self (normalize paths for cross-platform comparison)
        if str(relative_path).replace("\\", "/") == doc["id"].replace("\\", "/"):
            continue
        
        try:
            content = file_path.read_text(encoding="utf-8")
            tags = extract_tags(content)
            
            # Calculate similarity by shared tags
            shared_tags = doc_tags.intersection(set(tags))
            if shared_tags:
                # Extract title
                lines = content.split("\n")
                title = file_path.stem
                
                if lines:
                    if lines[0].strip() == "---":
                        for i, line in enumerate(lines[1:], 1):
                            if line.strip() == "---":
                                break
                            if line.startswith("title:"):
                                title = line.split("title:", 1)[1].strip().strip('"\'')
                                break
                    elif lines[0].startswith("#"):
                        title = lines[0].strip("# ").strip()
                
                similar.append({
                    "id": str(relative_path),
                    "title": title,
                    "content": content[:200],
                    "tags": tags,
                    "shared_tags": list(shared_tags),
                    "similarity_score": len(shared_tags) / len(doc_tags)
                })
        except Exception:
            continue
    
    # Sort by similarity score and return top N
    similar.sort(key=lambda x: x["similarity_score"], reverse=True)
    return similar[:limit]


def _get_kb_path(scope: KBScope) -> Path:
    """Get the knowledge base directory path based on scope."""
    if scope == "global":
        return Path.home() / ".claude" / "knowledge"
    return Path(".agent-builder") / "knowledge"


def _list_kb_files(kb_path: Path, doc_type: str | None = None) -> list[dict]:
    """List knowledge base files from a directory."""
    if not kb_path.exists():
        return []
    
    docs = []
    for file_path in kb_path.rglob("*.md"):
        # Skip hidden files/dirs within kb_path (but not kb_path itself like .claude)
        relative_parts = file_path.relative_to(kb_path).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        
        # Read file metadata
        try:
            content = file_path.read_text(encoding="utf-8")
            stat = file_path.stat()
            
            # Extract title from first line or YAML frontmatter
            lines = content.split("\n")
            title = file_path.stem  # Default to filename
            has_frontmatter = False
            frontmatter_end_idx = 0
            
            if lines:
                # Check for YAML frontmatter
                if lines[0].strip() == "---":
                    has_frontmatter = True
                    # Look for title in frontmatter and find end of frontmatter
                    for i, line in enumerate(lines[1:], 1):
                        if line.strip() == "---":
                            frontmatter_end_idx = i + 1
                            break
                        if line.startswith("title:"):
                            title = line.split("title:", 1)[1].strip().strip('"\'')
                # Check for markdown header if no frontmatter
                elif lines[0].startswith("#"):
                    title = lines[0].strip("# ").strip()
            
            # Determine doc type from directory structure or filename
            relative_path = file_path.relative_to(kb_path)
            inferred_type = relative_path.parts[0] if len(relative_path.parts) > 1 else "context"
            
            # Filter by doc_type if specified
            if doc_type and inferred_type != doc_type:
                continue
            
            # Extract wikilinks, tags, and metadata
            wikilinks = extract_wikilinks(content)
            tags = extract_tags(content)
            date_published = extract_frontmatter_field(content, "date_published")
            source_author = extract_frontmatter_field(content, "source_author")
            
            # Get clean body content
            preview = get_body_content(content)
            
            docs.append({
                "id": str(file_path.relative_to(kb_path)),
                "task_id": "",
                "doc_type": inferred_type,
                "title": title,
                "content": preview,
                "version": 1,
                "created_at": stat.st_ctime,
                "wikilinks": wikilinks,
                "tags": tags,
                "date_published": date_published,
                "source_author": source_author,
            })
        except Exception:
            continue
    
    return docs


@router.get("/kb/")
async def list_kb_docs(
    scope: KBScope = "local",
    task_id: str | None = None,
    doc_type: str | None = None,
    tags: str | None = None,  # Comma-separated tags
    limit: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List knowledge base documents from local or global scope."""
    kb_path = _get_kb_path(scope)
    docs = _list_kb_files(kb_path, doc_type)
    
    # Filter by tags if provided (intersection - documents must have ALL selected tags)
    if tags:
        selected_tags = set(t.strip() for t in tags.split(","))
        docs = [
            doc for doc in docs
            if selected_tags.issubset(set(doc.get("tags", [])))
        ]
    
    if limit:
        docs = docs[:limit]
    
    return docs


@router.get("/kb/tags")
async def get_all_tags(
    scope: KBScope = "local",
    tags: str | None = None,  # Comma-separated selected tags for contextual filtering
    db: AsyncSession = Depends(get_db)
):
    """Get all unique tags with document counts and co-occurrence data.
    
    If tags parameter is provided, returns only tags that appear in documents
    matching the selected tags (contextual filtering).
    """
    kb_path = _get_kb_path(scope)
    all_docs = _list_kb_files(kb_path)
    
    # Filter docs by selected tags if provided (using intersection logic)
    if tags:
        selected_tags = set(t.strip() for t in tags.split(","))
        docs = [
            doc for doc in all_docs
            if selected_tags.issubset(set(doc.get("tags", [])))
        ]
    else:
        docs = all_docs
    
    # Count tag occurrences in filtered docs
    tag_counts = {}
    tag_cooccurrence = {}  # Track which tags appear together
    
    for doc in docs:
        doc_tags = doc.get("tags", [])
        
        # Count individual tags
        for tag in doc_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        # Track co-occurrence (which tags appear together)
        for i, tag1 in enumerate(doc_tags):
            if tag1 not in tag_cooccurrence:
                tag_cooccurrence[tag1] = {}
            
            for tag2 in doc_tags[i+1:]:
                tag_cooccurrence[tag1][tag2] = tag_cooccurrence[tag1].get(tag2, 0) + 1
                
                # Symmetric relationship
                if tag2 not in tag_cooccurrence:
                    tag_cooccurrence[tag2] = {}
                tag_cooccurrence[tag2][tag1] = tag_cooccurrence[tag2].get(tag1, 0) + 1
    
    # If tags are selected, check which tags would result in documents
    # when added to the current selection (for disabling unavailable tags)
    if tags:
        selected_tags = set(t.strip() for t in tags.split(","))
        # A tag is available if there exists at least one document with all selected tags + this tag
        available_tags = set()
        for tag in tag_counts.keys():
            if tag in selected_tags:
                # Already selected tags are always available
                available_tags.add(tag)
            else:
                # Check if adding this tag would result in any documents
                test_tags = selected_tags | {tag}
                has_docs = any(
                    test_tags.issubset(set(doc.get("tags", [])))
                    for doc in all_docs
                )
                if has_docs:
                    available_tags.add(tag)
    else:
        # No tags selected, all tags are available
        available_tags = set(tag_counts.keys())
    
    # Format response
    tags_list = [
        {
            "name": tag,
            "count": count,
            "related": tag_cooccurrence.get(tag, {}),
            "available": tag in available_tags
        }
        for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    ]
    
    return tags_list


@router.get("/kb/search")
async def search_kb_docs(
    q: str,
    scope: KBScope = "local",
    db: AsyncSession = Depends(get_db)
):
    """Search knowledge base documents."""
    kb_path = _get_kb_path(scope)
    all_docs = _list_kb_files(kb_path)
    
    # Simple search in title and content
    query_lower = q.lower()
    results = []
    
    for doc in all_docs:
        if query_lower in doc["title"].lower() or query_lower in doc["content"].lower():
            results.append(doc)
    
    return results


@router.get("/kb/{doc_id:path}/related")
async def get_related_docs(
    doc_id: str,
    scope: KBScope = "local",
    db: AsyncSession = Depends(get_db)
):
    """Get related documents via wikilinks, backlinks, and similarity."""
    kb_path = _get_kb_path(scope)
    file_path = kb_path / doc_id
    
    if not file_path.exists():
        return {"wikilinks": [], "backlinks": [], "similar": []}
    
    try:
        content = file_path.read_text(encoding="utf-8")
        
        # Extract title
        lines = content.split("\n")
        title = file_path.stem
        if lines:
            if lines[0].strip() == "---":
                for i, line in enumerate(lines[1:], 1):
                    if line.strip() == "---":
                        break
                    if line.startswith("title:"):
                        title = line.split("title:", 1)[1].strip().strip('"\'')
                        break
            elif lines[0].startswith("#"):
                title = lines[0].strip("# ").strip()
        
        # Extract wikilinks from content
        wikilink_ids = extract_wikilinks(content)
        
        # Resolve wikilinks to actual documents
        wikilink_docs = []
        for link in wikilink_ids:
            # Try to find matching file
            for candidate in kb_path.rglob("*.md"):
                relative_path = candidate.relative_to(kb_path)
                if link.lower() in str(relative_path).lower() or link.lower() in candidate.stem.lower():
                    try:
                        link_content = candidate.read_text(encoding="utf-8")
                        link_lines = link_content.split("\n")
                        link_title = candidate.stem
                        
                        if link_lines:
                            if link_lines[0].strip() == "---":
                                for line in link_lines[1:]:
                                    if line.strip() == "---":
                                        break
                                    if line.startswith("title:"):
                                        link_title = line.split("title:", 1)[1].strip().strip('"\'')
                                        break
                            elif link_lines[0].startswith("#"):
                                link_title = link_lines[0].strip("# ").strip()
                        
                        wikilink_docs.append({
                            "id": str(relative_path),
                            "title": link_title,
                            "content": link_content[:200],
                            "doc_type": relative_path.parts[0] if len(relative_path.parts) > 1 else "context"
                        })
                        break
                    except Exception:
                        continue
        
        # Find backlinks
        backlinks = find_backlinks(doc_id, title, kb_path)
        
        # Find similar docs
        doc_data = {
            "id": doc_id,
            "tags": extract_tags(content)
        }
        similar = find_similar_docs(doc_data, kb_path, limit=5)
        
        return {
            "wikilinks": wikilink_docs,
            "backlinks": backlinks,
            "similar": similar
        }
    except Exception as e:
        return {"wikilinks": [], "backlinks": [], "similar": [], "error": str(e)}


@router.get("/kb/{doc_id:path}")
async def get_kb_doc(
    doc_id: str,
    scope: KBScope = "local",
    db: AsyncSession = Depends(get_db)
):
    """Get a specific knowledge base document."""
    kb_path = _get_kb_path(scope)
    file_path = kb_path / doc_id
    
    if not file_path.exists() or not file_path.is_file():
        return {"id": doc_id, "content": "", "doc_type": "", "error": "File not found"}
    
    try:
        content = file_path.read_text(encoding="utf-8")
        stat = file_path.stat()
        
        # Extract title from first line or YAML frontmatter
        lines = content.split("\n")
        title = file_path.stem  # Default to filename
        
        if lines:
            # Check for YAML frontmatter
            if lines[0].strip() == "---":
                # Look for title in frontmatter
                for i, line in enumerate(lines[1:], 1):
                    if line.strip() == "---":
                        break
                    if line.startswith("title:"):
                        title = line.split("title:", 1)[1].strip().strip('"\'')
                        break
            # Check for markdown header
            elif lines[0].startswith("#"):
                title = lines[0].strip("# ").strip()
        
        # Determine doc type from directory structure
        relative_path = file_path.relative_to(kb_path)
        inferred_type = relative_path.parts[0] if len(relative_path.parts) > 1 else "context"
        
        # Extract wikilinks and tags
        wikilinks = extract_wikilinks(content)
        tags = extract_tags(content)
        
        return {
            "id": doc_id,
            "task_id": "",
            "doc_type": inferred_type,
            "title": title,
            "content": content,
            "version": 1,
            "created_at": stat.st_ctime,
            "wikilinks": wikilinks,
            "tags": tags,
        }
    except Exception as e:
        return {"id": doc_id, "content": "", "doc_type": "", "error": str(e)}
