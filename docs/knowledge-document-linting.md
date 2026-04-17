# Knowledge Base Document Linting

## Overview

The knowledge base document linting system ensures all generated documents follow a standardized format for consistency, proper parsing, and dashboard compatibility.

## Components

### 1. Document Specification (`document_spec.py`)

Defines the required format for all knowledge base documents:

**Required Frontmatter Fields**:
- `title` (string): Document title
- `tags` (array): List of tags
- `doc_type` (string): Document type category
- `created` (string): ISO 8601 timestamp
- `auto_generated` (boolean): Whether auto-generated
- `version` (integer): Document version (≥1)

**Optional Fields**:
- `updated` (string): Last update timestamp
- `wikilinks` (array): Links to other documents

### 2. Document Linter (`DocumentLinter` class)

Validates documents against the specification:

**Validation Checks**:
- ✅ Valid YAML frontmatter syntax
- ✅ All required fields present
- ✅ Correct field types
- ✅ Valid ISO 8601 timestamps
- ✅ Non-empty strings
- ✅ Reasonable field lengths
- ✅ Non-empty body content
- ✅ Minimum content length (100 chars)
- ✅ At least one markdown heading
- ⚠️ Proper heading hierarchy

### 3. CLI Command (`builder kb lint`)

Command-line interface for linting documents:

```bash
# Lint all documents
builder kb lint

# Strict mode (warnings as errors)
builder kb lint --strict

# Verbose output (show all files)
builder kb lint --verbose

# Custom directory
builder kb lint --kb-dir custom-docs
```

## Usage

### Linting Documents

```bash
# Basic linting
$ builder kb lint
🔍 Linting documents in .agent-builder\knowledge\reverse-engineering...

============================================================
📊 Results: 12/12 passed, 0/12 failed
✅ All documents pass linting checks!
```

### Verbose Mode

```bash
$ builder kb lint --verbose
🔍 Linting documents in .agent-builder\knowledge\reverse-engineering...

✅ agent-system.md
✅ api-endpoints.md
✅ business-overview.md
✅ code-structure.md
✅ configuration.md
✅ database-models.md
✅ dependencies.md
✅ extraction-metadata.md
✅ project-overview.md
✅ system-architecture.md
✅ technology-stack.md
✅ workflows-and-orchestration.md

============================================================
📊 Results: 12/12 passed, 0/12 failed
✅ All documents pass linting checks!
```

### Strict Mode

Treats warnings as errors:

```bash
$ builder kb lint --strict
```

## Integration

### Generator Integration

All generators automatically produce compliant documents:

```python
# In extractor.py
def _write_doc(self, filename: str, doc: dict[str, Any]) -> None:
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
```

### Agent Extractor Integration

The agent-based extractor includes version in its prompt:

```python
EXTRACTION_PROMPT = """
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
"""
```

### Validation in Extraction

Linting can be integrated into the extraction process:

```python
from autonomous_agent_builder.knowledge.document_spec import DocumentLinter

linter = DocumentLinter()
if not linter.lint_content(content):
    print(linter.get_report())
    raise ValueError("Document failed validation")
```

## Error Messages

### Common Errors

**Missing Frontmatter**:
```
❌ document.md
ERRORS:
  ❌ document.md: Missing frontmatter (must start with '---')
```

**Invalid YAML**:
```
❌ document.md
ERRORS:
  ❌ document.md: Invalid YAML in frontmatter: ...
```

**Missing Required Field**:
```
❌ document.md
ERRORS:
  ❌ document.md: Missing required field 'version' in frontmatter
```

**Invalid Timestamp**:
```
❌ document.md
ERRORS:
  ❌ document.md: 'created' must be valid ISO 8601 timestamp, got: 2026-04-17
```

### Common Warnings

**Short Content**:
```
⚠️  document.md: Document body is very short (45 chars)
```

**No Headings**:
```
⚠️  document.md: No markdown headings found
```

**Heading Hierarchy**:
```
⚠️  document.md: Heading hierarchy skips levels (h1 -> h3)
```

## Benefits

### 1. Consistency

All documents follow the same format, making them:
- Easy to parse programmatically
- Consistent in the dashboard UI
- Predictable for AI agents

### 2. Quality Assurance

Catches common issues:
- Missing required fields
- Invalid data types
- Malformed YAML
- Empty or minimal content

### 3. Dashboard Compatibility

Ensures documents display correctly:
- Proper frontmatter parsing
- Correct type badges
- Valid tags and metadata
- Readable content

### 4. Maintainability

Makes it easy to:
- Validate bulk document changes
- Enforce standards across generators
- Catch regressions early
- Document format requirements

## Future Enhancements

Potential improvements:

1. **Auto-fix Mode**: Automatically fix common issues
2. **Custom Rules**: Allow project-specific validation rules
3. **CI Integration**: Run linting in CI/CD pipelines
4. **Format Conversion**: Convert between document formats
5. **Schema Validation**: JSON Schema for frontmatter
6. **Content Analysis**: Check for broken links, outdated info

## References

- [Document Format Specification](./knowledge-document-format.md)
- [Knowledge Extraction System](./knowledge-extraction-summary.md)
- [Quality Gate Documentation](./knowledge-quality-gate.md)
