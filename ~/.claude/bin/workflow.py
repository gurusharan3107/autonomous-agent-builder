#!/usr/bin/env python3
"""
Workflow CLI - Reference doc and memory management for agent workflows.

Usage:
    workflow summary <name>                    # Load from ~/.claude/docs/
    workflow --docs-dir <dir> summary <name>   # Load from custom dir
    workflow memory list [--phase <phase>] [--status <status>]
    workflow memory search [--entity <entity>] "<query>"
    workflow memory add --type <type> --phase <phase> --entity <entity> --tags "<tags>" "<title>"
"""

import argparse
import sys
from pathlib import Path


def load_summary(name: str, docs_dir: Path) -> str:
    """Load a reference document by name."""
    # Try with .md extension
    doc_path = docs_dir / f"{name}.md"
    if not doc_path.exists():
        # Try without extension
        doc_path = docs_dir / name
        if not doc_path.exists():
            return f"Error: Document '{name}' not found in {docs_dir}"
    
    try:
        content = doc_path.read_text(encoding='utf-8')
        return content
    except Exception as e:
        return f"Error reading {doc_path}: {e}"


def memory_list(phase: str = None, status: str = None) -> str:
    """List memories from .memory/ directory."""
    memory_dir = Path(".memory")
    if not memory_dir.exists():
        return "No .memory/ directory found in current project"
    
    results = []
    
    # Search in category subdirectories
    for category in ["decisions", "patterns", "corrections"]:
        cat_dir = memory_dir / category
        if not cat_dir.exists():
            continue
        
        for file in cat_dir.glob("*.md"):
            # Read frontmatter to check phase/status filters
            try:
                content = file.read_text(encoding='utf-8')
                
                # Simple filter check (could be enhanced with proper frontmatter parsing)
                if phase and f"phase: {phase}" not in content.lower():
                    continue
                if status and f"status: {status}" not in content.lower():
                    continue
                
                # Extract title from first heading
                title = file.stem.replace("-", " ").title()
                for line in content.split('\n'):
                    if line.startswith('# '):
                        title = line[2:].strip()
                        break
                
                results.append(f"- [{category}] {title} ({file.name})")
            except Exception as e:
                results.append(f"- [{category}] {file.name} (error reading: {e})")
    
    # Also search root .memory/ directory for files created by builder memory add
    for file in memory_dir.glob("*.md"):
        if file.name in ["INDEX.md", "README.md"]:
            continue
        
        try:
            content = file.read_text(encoding='utf-8')
            
            # Detect category from filename prefix
            category = "unknown"
            if file.name.startswith("pattern_"):
                category = "patterns"
            elif file.name.startswith("decision_"):
                category = "decisions"
            elif file.name.startswith("correction_"):
                category = "corrections"
            
            # Simple filter check
            if phase and f"phase: {phase}" not in content.lower():
                continue
            if status and f"status: {status}" not in content.lower():
                continue
            
            # Extract title from first heading or filename
            title = file.stem.replace("_", " ").replace("-", " ").title()
            for line in content.split('\n'):
                if line.startswith('# '):
                    title = line[2:].strip()
                    break
            
            results.append(f"- [{category}] {title} ({file.name})")
        except Exception as e:
            results.append(f"- [unknown] {file.name} (error reading: {e})")
    
    if not results:
        return "No memories found matching criteria"
    
    return "\n".join(results)


def memory_search(query: str, entity: str = None) -> str:
    """Search memories for a query string."""
    memory_dir = Path(".memory")
    if not memory_dir.exists():
        return "No .memory/ directory found in current project"
    
    results = []
    
    # Search in category subdirectories
    for category in ["decisions", "patterns", "corrections"]:
        cat_dir = memory_dir / category
        if not cat_dir.exists():
            continue
        
        for file in cat_dir.glob("*.md"):
            try:
                content = file.read_text(encoding='utf-8')
                
                # Check entity filter
                if entity and f"entity: {entity}" not in content.lower():
                    continue
                
                # Check query match
                if query.lower() in content.lower():
                    # Extract title
                    title = file.stem.replace("-", " ").title()
                    for line in content.split('\n'):
                        if line.startswith('# '):
                            title = line[2:].strip()
                            break
                    
                    results.append(f"\n## [{category}] {title}\nFile: {file.name}\n\n{content[:500]}...")
            except Exception as e:
                results.append(f"\n## [{category}] {file.name}\nError: {e}")
    
    # Also search root .memory/ directory
    for file in memory_dir.glob("*.md"):
        if file.name in ["INDEX.md", "README.md"]:
            continue
        
        try:
            content = file.read_text(encoding='utf-8')
            
            # Detect category from filename prefix
            category = "unknown"
            if file.name.startswith("pattern_"):
                category = "patterns"
            elif file.name.startswith("decision_"):
                category = "decisions"
            elif file.name.startswith("correction_"):
                category = "corrections"
            
            # Check entity filter
            if entity and f"entity: {entity}" not in content.lower():
                continue
            
            # Check query match
            if query.lower() in content.lower():
                # Extract title
                title = file.stem.replace("_", " ").replace("-", " ").title()
                for line in content.split('\n'):
                    if line.startswith('# '):
                        title = line[2:].strip()
                        break
                
                results.append(f"\n## [{category}] {title}\nFile: {file.name}\n\n{content[:500]}...")
        except Exception as e:
            results.append(f"\n## [{category}] {file.name}\nError: {e}")
    
    if not results:
        return f"No memories found matching '{query}'"
    
    return "\n".join(results)


def memory_add(type_: str, phase: str, entity: str, tags: str, title: str) -> str:
    """Add a new memory entry."""
    memory_dir = Path(".memory")
    category_dir = memory_dir / f"{type_}s"  # decisions, patterns, corrections
    
    if not category_dir.exists():
        category_dir.mkdir(parents=True, exist_ok=True)
    
    # Create filename from title
    filename = title.lower().replace(" ", "-").replace("/", "-")
    filename = "".join(c for c in filename if c.isalnum() or c == "-")
    filepath = category_dir / f"{filename}.md"
    
    # Create template based on type
    if type_ == "decision":
        template = f"""---
type: decision
phase: {phase}
entity: {entity}
tags: {tags}
status: active
---

# {title}

## Trace

**Inputs:**
- [Add context]

**Policy:**
- [Add policy/rule]

**Exception:**
- [Add exception granted]

**Approval:**
- [Add approval source]

## Outcome

[Add outcome]
"""
    elif type_ == "correction":
        template = f"""---
type: correction
phase: {phase}
entity: {entity}
tags: {tags}
status: active
---

# {title}

## Constraint

[Add constraint that was violated]

## What Went Wrong

[Add description of the mistake]

## What To Do Instead

[Add correct approach]
"""
    elif type_ == "pattern":
        template = f"""---
type: pattern
phase: {phase}
entity: {entity}
tags: {tags}
status: active
---

# {title}

## Context

[Add when this pattern applies]

## Approach

[Add the validated approach]

## Benefits

[Add why this works well]
"""
    else:
        return f"Error: Unknown memory type '{type_}'. Use: decision, correction, or pattern"
    
    filepath.write_text(template, encoding='utf-8')
    return f"Created memory: {filepath}"


def main():
    parser = argparse.ArgumentParser(description="Workflow CLI for reference docs and memory")
    parser.add_argument("--docs-dir", type=Path, help="Custom docs directory")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Summary command
    summary_parser = subparsers.add_parser("summary", help="Load reference document")
    summary_parser.add_argument("name", help="Document name")
    
    # Memory commands
    memory_parser = subparsers.add_parser("memory", help="Memory operations")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")
    
    # Memory list
    list_parser = memory_subparsers.add_parser("list", help="List memories")
    list_parser.add_argument("--phase", help="Filter by phase")
    list_parser.add_argument("--status", help="Filter by status")
    
    # Memory search
    search_parser = memory_subparsers.add_parser("search", help="Search memories")
    search_parser.add_argument("--entity", help="Filter by entity")
    search_parser.add_argument("query", help="Search query")
    
    # Memory add
    add_parser = memory_subparsers.add_parser("add", help="Add memory")
    add_parser.add_argument("--type", required=True, choices=["decision", "correction", "pattern"])
    add_parser.add_argument("--phase", required=True, help="SDLC phase")
    add_parser.add_argument("--entity", required=True, help="Entity name")
    add_parser.add_argument("--tags", required=True, help="Comma-separated tags")
    add_parser.add_argument("title", help="Memory title")
    
    args = parser.parse_args()
    
    if args.command == "summary":
        # Determine docs directory
        if args.docs_dir:
            docs_dir = args.docs_dir
        else:
            docs_dir = Path.home() / ".claude" / "docs"
        
        result = load_summary(args.name, docs_dir)
        print(result)
    
    elif args.command == "memory":
        if args.memory_command == "list":
            result = memory_list(args.phase, args.status)
            print(result)
        elif args.memory_command == "search":
            result = memory_search(args.query, args.entity)
            print(result)
        elif args.memory_command == "add":
            result = memory_add(args.type, args.phase, args.entity, args.tags, args.title)
            print(result)
        else:
            memory_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
