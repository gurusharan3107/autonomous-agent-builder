"""Knowledge extractor - AI-DLC reverse engineering inspired."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

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


class KnowledgeExtractor:
    """Extract project knowledge using reverse engineering patterns.
    
    Inspired by AI-DLC reverse engineering methodology, adapted for
    filesystem-based knowledge base storage.
    """

    def __init__(self, workspace_path: Path, output_path: Path):
        """Initialize extractor.
        
        Args:
            workspace_path: Root directory of the project to analyze
            output_path: Directory to write extracted knowledge docs
        """
        self.workspace_path = workspace_path.resolve()
        self.output_path = output_path.resolve()
        
        # Initialize generators (order matters - overview first, details later)
        self.generators = [
            ProjectOverviewGenerator(workspace_path),
            TechnologyStackGenerator(workspace_path),
            DependenciesGenerator(workspace_path),
            ArchitectureGenerator(workspace_path),
            CodeStructureGenerator(workspace_path),
            DatabaseModelsGenerator(workspace_path),
            APIEndpointsGenerator(workspace_path),
            BusinessOverviewGenerator(workspace_path),
            WorkflowsGenerator(workspace_path),
            ConfigurationGenerator(workspace_path),
            AgentSystemGenerator(workspace_path),
        ]

    def extract(self, scope: str = "full") -> dict[str, Any]:
        """Extract knowledge and write markdown files.
        
        Args:
            scope: Extraction scope - "full" | "package:<name>" | "feature:<id>"
        
        Returns:
            dict with 'documents' list and 'output_path' string
        """
        # Create output directory
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        documents = []
        errors = []
        
        # Run each generator
        for generator in self.generators:
            try:
                doc = generator.generate(scope=scope)
                if doc:
                    filename = self._get_filename(doc["title"])
                    self._write_doc(filename, doc)
                    documents.append({
                        "type": doc.get("doc_type", "unknown"),
                        "title": doc["title"],
                        "filename": filename,
                    })
            except Exception as e:
                errors.append({
                    "generator": generator.__class__.__name__,
                    "error": str(e),
                })
        
        # Write extraction metadata
        self._write_metadata(documents, errors)
        
        return {
            "documents": documents,
            "errors": errors,
            "output_path": str(self.output_path),
            "extracted_at": datetime.now().isoformat(),
        }

    def _get_filename(self, title: str) -> str:
        """Convert title to filename."""
        # Convert to lowercase, replace spaces with hyphens
        filename = title.lower()
        filename = filename.replace(" ", "-")
        # Remove special characters
        filename = "".join(c for c in filename if c.isalnum() or c in "-_")
        return f"{filename}.md"

    def _write_doc(self, filename: str, doc: dict[str, Any]) -> None:
        """Write markdown file with frontmatter.
        
        Args:
            filename: Output filename
            doc: Document dict with title, tags, content
        """
        tags = doc.get("tags", ["reverse-engineering", "auto-generated"])
        
        # Format tags for YAML
        if isinstance(tags, list):
            tags_str = "[" + ", ".join(f'"{tag}"' for tag in tags) + "]"
        else:
            tags_str = f'["{tags}"]'
        
        content = f"""---
title: "{doc['title']}"
tags: {tags_str}
doc_type: "{doc.get('doc_type', 'reverse-engineering')}"
created: "{datetime.now().isoformat()}"
auto_generated: true
version: {doc.get('version', 1)}
---

{doc['content']}
"""
        
        file_path = self.output_path / filename
        file_path.write_text(content, encoding="utf-8")

    def _write_metadata(self, documents: list[dict], errors: list[dict]) -> None:
        """Write extraction metadata file."""
        metadata = {
            "extracted_at": datetime.now().isoformat(),
            "workspace_path": str(self.workspace_path),
            "document_count": len(documents),
            "documents": documents,
            "errors": errors,
        }
        
        metadata_content = f"""---
title: "Extraction Metadata"
tags: ["metadata", "reverse-engineering"]
doc_type: "metadata"
created: "{datetime.now().isoformat()}"
auto_generated: true
---

# Knowledge Extraction Metadata

**Extracted At**: {metadata['extracted_at']}  
**Workspace**: `{metadata['workspace_path']}`  
**Documents Generated**: {metadata['document_count']}

## Generated Documents

"""
        
        for doc in documents:
            metadata_content += f"- **{doc['type']}**: {doc['title']} (`{doc['filename']}`)\n"
        
        if errors:
            metadata_content += "\n## Errors\n\n"
            for error in errors:
                metadata_content += f"- **{error['generator']}**: {error['error']}\n"
        
        metadata_content += f"""

## Usage

These documents were automatically generated by analyzing the codebase.
They provide a comprehensive overview of the project structure, architecture,
and technology stack.

Use `builder kb search` to search across all knowledge documents.
Use `builder kb list --type reverse-engineering` to list all extracted docs.
"""
        
        (self.output_path / "extraction-metadata.md").write_text(
            metadata_content, encoding="utf-8"
        )
