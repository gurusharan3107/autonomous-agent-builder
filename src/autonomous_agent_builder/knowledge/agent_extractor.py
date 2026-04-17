"""Agent-based knowledge extraction using Claude Agent SDK.

Alternative to AST-based extraction. Uses Claude to analyze codebase
and generate documentation with deeper understanding and context.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from claude_agent_sdk import query

log = structlog.get_logger()


class AgentKnowledgeExtractor:
    """Extract project knowledge using Claude Agent SDK.
    
    Advantages over AST-based extraction:
    - Deeper semantic understanding
    - Better context and explanations
    - Can infer intent and patterns
    - More natural language descriptions
    
    Disadvantages:
    - Slower (requires API calls)
    - Costs API usage
    - Requires internet connection
    - Less deterministic
    """

    EXTRACTION_PROMPT_TEMPLATE = """You are a technical documentation expert analyzing a codebase to generate comprehensive documentation.

## Your Task

Analyze the provided codebase and generate a **{doc_type}** document.

## Codebase Context

**Project Path**: {workspace_path}

**Key Files**:
{key_files}

**File Contents**:
{file_contents}

## Document Requirements

Generate a markdown document with:

1. **Frontmatter** (YAML):
```yaml
---
title: "{doc_title}"
tags: {tags}
doc_type: "reverse-engineering"
created: "{timestamp}"
auto_generated: true
version: 1
---
```

2. **Content Sections**:
{content_requirements}

## Guidelines

- Be specific and detailed (not generic)
- Include code examples where relevant
- Use proper markdown formatting
- Add diagrams (Mermaid) where helpful
- Focus on what's actually in the code
- Explain WHY, not just WHAT
- Make it useful for AI agents and developers

## Output Format

Return ONLY the complete markdown document (frontmatter + content).
Do not include explanations or meta-commentary.
"""

    DOCUMENT_SPECS = {
        "project-overview": {
            "title": "Project Overview",
            "tags": '["project", "overview", "metadata", "reverse-engineering"]',
            "requirements": """
- # Project Overview
- ## Description (what the project does)
- ## Key Features (main capabilities)
- ## Project Structure (high-level organization)
- ## Getting Started (how to run/use)
- ## Technology Summary (languages, frameworks)
""",
        },
        "technology-stack": {
            "title": "Technology Stack",
            "tags": '["technology", "stack", "frameworks", "tools", "reverse-engineering"]',
            "requirements": """
- # Technology Stack
- ## Languages (with versions)
- ## Frameworks (with versions)
- ## Databases (with types)
- ## Tools & Libraries (key dependencies)
- ## Development Tools (testing, linting, etc.)
""",
        },
        "system-architecture": {
            "title": "System Architecture",
            "tags": '["architecture", "design", "components", "reverse-engineering"]',
            "requirements": """
- # System Architecture
- ## Architecture Overview (high-level description)
- ## Component Diagram (Mermaid diagram)
- ## Key Components (with responsibilities)
- ## Data Flow (how data moves through system)
- ## Design Patterns (patterns used)
- ## Integration Points (external systems)
""",
        },
        "api-endpoints": {
            "title": "API Endpoints",
            "tags": '["api", "endpoints", "rest", "routes", "reverse-engineering"]',
            "requirements": """
- # API Endpoints
- ## Overview (API purpose and design)
- ## Base URL
- ## Endpoints by Category
  - For each endpoint:
    - Method and Path
    - Description
    - Parameters
    - Request/Response examples
    - Authentication requirements
""",
        },
        "workflows-and-orchestration": {
            "title": "Workflows and Orchestration",
            "tags": '["workflows", "orchestration", "phases", "reverse-engineering"]',
            "requirements": """
- # Workflows and Orchestration
- ## Overview (workflow system description)
- ## Workflow Diagram (Mermaid diagram)
- ## Execution Phases (with descriptions)
- ## Orchestration Patterns (how workflows are managed)
- ## Error Handling (retry logic, failures)
""",
        },
        "agent-system": {
            "title": "Agent System",
            "tags": '["agents", "tools", "hooks", "security", "reverse-engineering"]',
            "requirements": """
- # Agent System
- ## Overview (agent system description)
- ## Agent Definitions (with capabilities)
- ## Available Tools (categorized)
- ## Security Hooks (access control)
- ## Agent Execution Flow
""",
        },
    }

    def __init__(self, workspace_path: Path, output_path: Path):
        """Initialize agent-based extractor.
        
        Args:
            workspace_path: Root directory of the project to analyze
            output_path: Directory to write extracted knowledge docs
        """
        self.workspace_path = workspace_path.resolve()
        self.output_path = output_path.resolve()

    def extract(
        self,
        doc_types: list[str] | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_files_per_doc: int = 10,
    ) -> dict[str, Any]:
        """Extract knowledge using Claude Agent SDK.
        
        Args:
            doc_types: List of document types to generate (None = all)
            model: Claude model to use
            max_files_per_doc: Max files to include in context per document
        
        Returns:
            dict with 'documents' list and 'output_path' string
        """
        # Create output directory
        self.output_path.mkdir(parents=True, exist_ok=True)

        # Determine which documents to generate
        if doc_types is None:
            doc_types = list(self.DOCUMENT_SPECS.keys())

        documents = []
        errors = []

        log.info(
            "agent_extraction_start",
            workspace=str(self.workspace_path),
            doc_count=len(doc_types),
        )

        # Generate each document
        for doc_type in doc_types:
            try:
                log.info("generating_document", doc_type=doc_type)

                # Generate document using agent
                doc_content = self._generate_document(
                    doc_type=doc_type,
                    model=model,
                    max_files=max_files_per_doc,
                )

                if doc_content:
                    # Write to file
                    filename = f"{doc_type}.md"
                    file_path = self.output_path / filename
                    file_path.write_text(doc_content, encoding="utf-8")

                    documents.append({
                        "type": "reverse-engineering",
                        "title": self.DOCUMENT_SPECS[doc_type]["title"],
                        "filename": filename,
                    })

                    log.info("document_generated", doc_type=doc_type, filename=filename)
                else:
                    errors.append({
                        "doc_type": doc_type,
                        "error": "Agent returned empty content",
                    })

            except Exception as e:
                log.error("document_generation_error", doc_type=doc_type, error=str(e))
                errors.append({
                    "doc_type": doc_type,
                    "error": str(e),
                })

        # Write extraction metadata
        self._write_metadata(documents, errors)

        log.info(
            "agent_extraction_complete",
            documents=len(documents),
            errors=len(errors),
        )

        return {
            "documents": documents,
            "errors": errors,
            "output_path": str(self.output_path),
            "extracted_at": datetime.now().isoformat(),
            "extraction_method": "agent-based",
        }

    def _generate_document(
        self,
        doc_type: str,
        model: str,
        max_files: int,
    ) -> str | None:
        """Generate a single document using Claude agent.
        
        Args:
            doc_type: Type of document to generate
            model: Claude model to use
            max_files: Max files to include in context
        
        Returns:
            Markdown content or None if generation failed
        """
        if doc_type not in self.DOCUMENT_SPECS:
            log.warning("unknown_doc_type", doc_type=doc_type)
            return None

        spec = self.DOCUMENT_SPECS[doc_type]

        # Gather relevant files for this document type
        key_files = self._gather_relevant_files(doc_type, max_files)

        # Read file contents
        file_contents = self._read_files(key_files)

        # Build prompt
        prompt = self.EXTRACTION_PROMPT_TEMPLATE.format(
            doc_type=spec["title"],
            workspace_path=str(self.workspace_path),
            key_files="\n".join(f"- {f}" for f in key_files),
            file_contents=file_contents,
            doc_title=spec["title"],
            tags=spec["tags"],
            timestamp=datetime.now().isoformat(),
            content_requirements=spec["requirements"],
        )

        # Query Claude agent
        try:
            response = query(
                prompt=prompt,
                model=model,
                max_turns=10,
                tools=["Read", "Glob", "Grep"],  # Give agent file access
            )

            # Extract markdown from response
            content = self._extract_markdown(response)

            return content

        except Exception as e:
            log.error("agent_query_error", doc_type=doc_type, error=str(e))
            return None

    def _gather_relevant_files(self, doc_type: str, max_files: int) -> list[str]:
        """Gather relevant files for a document type.
        
        Args:
            doc_type: Type of document
            max_files: Maximum files to return
        
        Returns:
            List of file paths relative to workspace
        """
        # Define file patterns for each document type
        patterns = {
            "project-overview": ["README.md", "pyproject.toml", "package.json", "setup.py"],
            "technology-stack": ["pyproject.toml", "package.json", "requirements.txt", "Dockerfile"],
            "system-architecture": ["**/__init__.py", "**/main.py", "**/app.py", "**/server.py"],
            "api-endpoints": ["**/routes/*.py", "**/api/*.py", "**/endpoints/*.py"],
            "workflows-and-orchestration": ["**/orchestrator*.py", "**/workflow*.py", "**/definitions.py"],
            "agent-system": ["**/agents/*.py", "**/definitions.py", "**/tool*.py", "**/hooks.py"],
        }

        file_patterns = patterns.get(doc_type, ["**/*.py"])

        # Find files matching patterns
        files = []
        for pattern in file_patterns:
            for file_path in self.workspace_path.glob(pattern):
                if file_path.is_file() and len(files) < max_files:
                    rel_path = file_path.relative_to(self.workspace_path)
                    files.append(str(rel_path))

        return files[:max_files]

    def _read_files(self, file_paths: list[str]) -> str:
        """Read file contents for context.
        
        Args:
            file_paths: List of file paths relative to workspace
        
        Returns:
            Formatted string with file contents
        """
        contents = []

        for file_path in file_paths:
            full_path = self.workspace_path / file_path
            try:
                content = full_path.read_text(encoding="utf-8")
                # Truncate large files
                if len(content) > 5000:
                    content = content[:5000] + "\n... (truncated)"

                contents.append(f"### {file_path}\n\n```\n{content}\n```\n")
            except Exception as e:
                contents.append(f"### {file_path}\n\nError reading file: {e}\n")

        return "\n".join(contents)

    def _extract_markdown(self, response: str) -> str:
        """Extract markdown content from agent response.
        
        Args:
            response: Agent response text
        
        Returns:
            Extracted markdown content
        """
        # If response starts with frontmatter, return as-is
        if response.strip().startswith("---"):
            return response.strip()

        # Try to extract markdown code block
        if "```markdown" in response:
            start = response.find("```markdown") + 11
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()

        # Return entire response if no code block
        return response.strip()

    def _write_metadata(self, documents: list[dict], errors: list[dict]) -> None:
        """Write extraction metadata file.
        
        Args:
            documents: List of generated documents
            errors: List of errors encountered
        """
        metadata_content = f"""---
title: "Extraction Metadata (Agent-Based)"
tags: ["metadata", "reverse-engineering", "agent-based"]
doc_type: "metadata"
created: "{datetime.now().isoformat()}"
auto_generated: true
---

# Knowledge Extraction Metadata (Agent-Based)

**Extracted At**: {datetime.now().isoformat()}  
**Workspace**: `{self.workspace_path}`  
**Documents Generated**: {len(documents)}  
**Extraction Method**: Agent-based (Claude Agent SDK)

## Generated Documents

"""

        for doc in documents:
            metadata_content += f"- **{doc['type']}**: {doc['title']} (`{doc['filename']}`)\n"

        if errors:
            metadata_content += "\n## Errors\n\n"
            for error in errors:
                metadata_content += f"- **{error['doc_type']}**: {error['error']}\n"

        metadata_content += f"""

## Extraction Method

This knowledge base was generated using **agent-based extraction** with Claude Agent SDK.

**Advantages**:
- Deeper semantic understanding
- Better context and explanations
- Can infer intent and patterns
- More natural language descriptions

**Trade-offs**:
- Slower than AST-based extraction
- Requires API access and costs
- Less deterministic

## Usage

Use `builder kb search` to search across all knowledge documents.
Use `builder kb list --type reverse-engineering` to list all extracted docs.
"""

        (self.output_path / "extraction-metadata.md").write_text(
            metadata_content, encoding="utf-8"
        )
