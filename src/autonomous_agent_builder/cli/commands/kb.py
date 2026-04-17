"""Knowledge base commands — add, list, show, search, update."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    get_client,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import render, table, truncate

app = typer.Typer(help="Knowledge base — agent-written docs (ADRs, contracts, runbooks).")


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


@app.command()
def add(
    task: str = typer.Option(..., "--task", help="Task ID this doc belongs to."),
    doc_type: str = typer.Option(
        ..., "--type", help="Doc type: adr, api_contract, schema, runbook, context."
    ),
    title: str = typer.Option(..., help="Document title."),
    content: str | None = typer.Option(None, help="Document content inline."),
    content_file: str | None = typer.Option(
        None, "--content-file", help="File to read content from (- for stdin)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Add a document to the knowledge base."""
    body = _read_content(content, content_file)
    payload = {
        "task_id": task,
        "doc_type": doc_type,
        "title": title,
        "content": body,
    }

    if dry_run:
        preview = {**payload, "content": truncate(body, 200)}
        render(
            {"dry_run": True, "would_create": preview},
            lambda d: f"Would create {doc_type} '{title}' for task {task}",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client()
    try:
        data = client.post("/kb/", payload)
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            return (
                f"created {d.get('doc_type', '')} document\n"
                f"id: {d.get('id', '')}\n"
                f"title: {d.get('title', '')}\n"
                f"version: {d.get('version', 1)}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command("list")
def list_docs(
    task: str | None = typer.Option(None, "--task", help="Filter by task ID."),
    doc_type: str | None = typer.Option(None, "--type", help="Filter by doc type."),
    limit: int = typer.Option(20, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List knowledge base documents."""
    client = get_client()
    params: dict = {}
    if task:
        params["task_id"] = task
    if doc_type:
        params["doc_type"] = doc_type
    params["limit"] = limit

    try:
        data = client.get("/kb/", **params)
    except AabApiError as e:
        handle_api_error(e)
    else:
        items = data if isinstance(data, list) else []

        def fmt(items: list) -> str:
            headers = ["ID", "TYPE", "TITLE", "VERSION", "CREATED"]
            rows = [
                [
                    str(d.get("id", ""))[:12],
                    d.get("doc_type", ""),
                    d.get("title", "")[:40],
                    f"v{d.get('version', 1)}",
                    str(d.get("created_at", ""))[:10],
                ]
                for d in items
            ]
            return table(headers, rows)

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def show(
    doc_id: str = typer.Argument(help="Document ID."),
    full: bool = typer.Option(False, "--full", help="Show full content."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a KB document. Default truncates content; use --full for complete."""
    client = get_client()
    try:
        data = client.get(f"/kb/{doc_id}")
    except AabApiError as e:
        handle_api_error(e)
    else:
        if not full and isinstance(data.get("content"), str):
            data["content"] = truncate(data["content"])

        def fmt(d: dict) -> str:
            lines = [
                f"id: {d.get('id', '')}",
                f"type: {d.get('doc_type', '')}",
                f"title: {d.get('title', '')}",
                f"version: v{d.get('version', 1)}",
                f"task_id: {d.get('task_id', '')}",
                f"created: {d.get('created_at', '')}",
                "",
                d.get("content", ""),
            ]
            return "\n".join(lines)

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def search(
    query: str = typer.Argument(help="Search query."),
    doc_type: str | None = typer.Option(None, "--type", help="Filter by doc type."),
    task: str | None = typer.Option(None, "--task", help="Filter by task ID."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search knowledge base documents by title and content."""
    client = get_client()
    params: dict = {"q": query, "limit": limit}
    if doc_type:
        params["doc_type"] = doc_type
    if task:
        params["task_id"] = task

    try:
        data = client.get("/kb/search", **params)
    except AabApiError as e:
        handle_api_error(e)
    else:
        items = data if isinstance(data, list) else []

        def fmt(items: list) -> str:
            headers = ["ID", "TYPE", "TITLE", "VERSION"]
            rows = [
                [
                    str(d.get("id", ""))[:12],
                    d.get("doc_type", ""),
                    d.get("title", "")[:45],
                    f"v{d.get('version', 1)}",
                ]
                for d in items
            ]
            return table(headers, rows)

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def update(
    doc_id: str = typer.Argument(help="Document ID to update."),
    title: str | None = typer.Option(None, help="New title."),
    content: str | None = typer.Option(None, help="New content inline."),
    content_file: str | None = typer.Option(
        None, "--content-file", help="File to read new content from (- for stdin)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Update a KB document. Bumps version on content change."""
    payload: dict = {}
    if title:
        payload["title"] = title
    if content or content_file:
        payload["content"] = _read_content(content, content_file)

    if not payload:
        from autonomous_agent_builder.cli.output import error
        error("Error: provide --title, --content, or --content-file")
        sys.exit(2)

    if dry_run:
        render(
            {"dry_run": True, "doc_id": doc_id, "would_update": payload},
            lambda d: f"Would update document {doc_id}",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client()
    try:
        data = client.put(f"/kb/{doc_id}", payload)
    except AabApiError as e:
        handle_api_error(e)
    else:
        def fmt(d: dict) -> str:
            return (
                f"updated document {doc_id}\n"
                f"title: {d.get('title', '')}\n"
                f"version: v{d.get('version', 1)}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def extract(
    scope: str = typer.Option("full", help="Scope: full | package:<name> | feature:<id>"),
    force: bool = typer.Option(False, "--force", help="Regenerate even if exists"),
    output_dir: str = typer.Option("reverse-engineering", help="Output subdirectory in knowledge/"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    validate: bool = typer.Option(True, help="Run quality gate after extraction"),
) -> None:
    """Extract project knowledge using reverse engineering (AI-DLC inspired).
    
    Generates comprehensive documentation by analyzing the codebase:
    - Project overview and description
    - Business context and domain entities
    - System architecture with diagrams
    - Code structure and organization
    - Technology stack and frameworks
    - Dependencies and packages
    
    Works offline (no server required). Writes directly to .agent-builder/knowledge/.
    
    Examples:
        builder kb extract
        builder kb extract --force
        builder kb extract --output-dir my-docs
        builder kb extract --no-validate  # Skip quality gate
    """
    from autonomous_agent_builder.knowledge import KnowledgeExtractor
    
    # Find .agent-builder directory
    agent_builder_dir = Path(".agent-builder")
    if not agent_builder_dir.exists():
        from autonomous_agent_builder.cli.output import error
        error("Error: .agent-builder/ not found. Run 'builder init' first.")
        sys.exit(4)
    
    kb_path = agent_builder_dir / "knowledge" / output_dir
    
    # Check if already exists
    if kb_path.exists() and not force:
        from autonomous_agent_builder.cli.output import error
        error(
            f"Knowledge already extracted at {kb_path}\n"
            "Use --force to regenerate"
        )
        sys.exit(1)
    
    # Extract knowledge
    if not json_output:
        typer.echo("🔍 Analyzing project structure...")
    
    try:
        extractor = KnowledgeExtractor(
            workspace_path=Path.cwd(),
            output_path=kb_path
        )
        results = extractor.extract(scope=scope)
        
        # Output results
        if json_output:
            import json as json_lib
            output_data = results
            
            # Run quality gate if requested
            if validate:
                from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate
                gate = KnowledgeQualityGate(kb_path, Path.cwd())
                gate_result = gate.validate()
                output_data["quality_gate"] = gate_result.to_dict()
            
            typer.echo(json_lib.dumps(output_data, indent=2))
        else:
            typer.echo(f"\n✓ Extracted {len(results['documents'])} documents to {kb_path}\n")
            for doc in results['documents']:
                typer.echo(f"  • {doc['type']}: {doc['title']}")
            
            if results.get('errors'):
                typer.echo(f"\n⚠ {len(results['errors'])} errors occurred:")
                for error_info in results['errors']:
                    typer.echo(f"  • {error_info['generator']}: {error_info['error']}")
            
            # Run quality gate
            if validate:
                typer.echo("\n🔍 Running agent-based quality gate...")
                from autonomous_agent_builder.knowledge.agent_quality_gate import AgentKnowledgeQualityGate
                gate = AgentKnowledgeQualityGate(kb_path, Path.cwd())
                gate_result = gate.validate()
                
                # Display results
                if gate_result.passed:
                    typer.echo(f"\n✅ {gate_result.summary}")
                else:
                    typer.echo(f"\n❌ {gate_result.summary}")
                
                # Show criteria scores
                if gate_result.evaluation.get("criteria_scores"):
                    typer.echo("\n📊 Criteria Scores:")
                    for criterion, score in gate_result.evaluation["criteria_scores"].items():
                        status = "✅" if score >= 75 else "⚠️" if score >= 60 else "❌"
                        typer.echo(f"  {status} {criterion.replace('_', ' ').title()}: {score}/100")
                
                # Show recommendations
                if gate_result.recommendations:
                    typer.echo("\n💡 Recommendations:")
                    for rec in gate_result.recommendations[:5]:
                        typer.echo(f"  • {rec}")
                
                # Exit with error if gate failed
                if not gate_result.passed:
                    typer.echo("\n⚠ Quality gate failed. Review issues above.")
                    sys.exit(1)
            
            typer.echo(f"\n📚 Use 'builder kb list --type reverse-engineering' to view extracted docs")
            typer.echo(f"🔎 Use 'builder kb search <query>' to search across all knowledge")
        
        sys.exit(EXIT_SUCCESS)
    
    except Exception as e:
        from autonomous_agent_builder.cli.output import error
        error(f"Error during extraction: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@app.command()
def validate(
    kb_dir: str = typer.Option(
        "reverse-engineering",
        help="Knowledge base directory to validate (relative to .agent-builder/knowledge/)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed check results"),
    use_agent: bool = typer.Option(True, help="Use Claude agent for dynamic evaluation"),
    model: str = typer.Option("claude-sonnet-4-20250514", help="Claude model for agent evaluation"),
) -> None:
    """Run quality gate on extracted knowledge base.
    
    Uses Claude Agent SDK for intelligent, dynamic evaluation of:
    - Completeness: All expected documents generated
    - Content Quality: Sufficient detail, no empty sections
    - Usefulness: Helpful for AI agents and developers
    - Structure & Clarity: Well-organized, clear writing
    - Accuracy: Correct information, no errors
    - Searchability: Proper tags and keywords
    
    The agent provides contextual feedback and actionable recommendations.
    
    Examples:
        builder kb validate
        builder kb validate --verbose
        builder kb validate --no-use-agent  # Use rule-based validation
        builder kb validate --model claude-opus-4-20250514
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
        error("Run 'builder kb extract' first.")
        sys.exit(1)
    
    # Run quality gate
    if not json_output:
        gate_type = "agent-based" if use_agent else "rule-based"
        typer.echo(f"🔍 Running {gate_type} quality gate on {kb_path}...\n")
    
    try:
        if use_agent:
            # Use agent-based quality gate
            from autonomous_agent_builder.knowledge.agent_quality_gate import AgentKnowledgeQualityGate
            
            gate = AgentKnowledgeQualityGate(kb_path, Path.cwd())
            result = gate.validate(model=model)
            
            if json_output:
                import json as json_lib
                typer.echo(json_lib.dumps(result.to_dict(), indent=2))
            else:
                # Display summary
                if result.passed:
                    typer.echo(f"✅ {result.summary}\n")
                else:
                    typer.echo(f"❌ {result.summary}\n")
                
                # Display criteria scores
                if result.evaluation.get("criteria_scores"):
                    typer.echo("📊 Criteria Scores:")
                    for criterion, score in result.evaluation["criteria_scores"].items():
                        status = "✅" if score >= 75 else "⚠️" if score >= 60 else "❌"
                        typer.echo(f"  {status} {criterion.replace('_', ' ').title()}: {score}/100")
                    typer.echo()
                
                # Display strengths
                if result.evaluation.get("strengths"):
                    typer.echo("💪 Strengths:")
                    for strength in result.evaluation["strengths"]:
                        typer.echo(f"  • {strength}")
                    typer.echo()
                
                # Display weaknesses
                if result.evaluation.get("weaknesses"):
                    typer.echo("⚠️  Weaknesses:")
                    for weakness in result.evaluation["weaknesses"]:
                        typer.echo(f"  • {weakness}")
                    typer.echo()
                
                # Display recommendations
                if result.recommendations:
                    typer.echo("💡 Recommendations:")
                    for rec in result.recommendations:
                        typer.echo(f"  • {rec}")
                    typer.echo()
                
                # Display reasoning in verbose mode
                if verbose and result.agent_reasoning:
                    typer.echo("🤔 Agent Reasoning:")
                    typer.echo(f"  {result.agent_reasoning}\n")
        else:
            # Use rule-based quality gate (original)
            from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate
            
            gate = KnowledgeQualityGate(kb_path, Path.cwd())
            result = gate.validate()
            
            if json_output:
                import json as json_lib
                typer.echo(json_lib.dumps(result.to_dict(), indent=2))
            else:
                # Display summary
                if result.passed:
                    typer.echo(f"✅ {result.summary}\n")
                else:
                    typer.echo(f"❌ {result.summary}\n")
                
                # Display checks
                typer.echo("Quality Checks:")
                for check in result.checks:
                    status = "✅" if check.passed else "❌"
                    typer.echo(f"  {status} {check.name}: {check.message} ({check.score:.0%})")
                    
                    # Show details in verbose mode
                    if verbose and check.details:
                        for key, value in check.details.items():
                            if isinstance(value, list) and value:
                                typer.echo(f"      {key}:")
                                for item in value[:5]:  # Show first 5
                                    typer.echo(f"        - {item}")
                                if len(value) > 5:
                                    typer.echo(f"        ... and {len(value) - 5} more")
                            elif not isinstance(value, list):
                                typer.echo(f"      {key}: {value}")
                
                # Recommendations
                if not result.passed:
                    typer.echo("\n💡 Recommendations:")
                    failed_checks = [c for c in result.checks if not c.passed]
                    
                    if any(c.name == "completeness" for c in failed_checks):
                        typer.echo("  • Run 'builder kb extract --force' to regenerate missing documents")
                    
                    if any(c.name == "content_quality" for c in failed_checks):
                        typer.echo("  • Review documents with insufficient content")
                        typer.echo("  • Ensure generators are extracting all relevant information")
                    
                    if any(c.name == "freshness" for c in failed_checks):
                        typer.echo("  • Run 'builder kb extract --force' to refresh stale documentation")
                    
                    if any(c.name in ["markdown_validity", "frontmatter"] for c in failed_checks):
                        typer.echo("  • Fix markdown syntax errors in generated documents")
                        typer.echo("  • Check generator templates for proper formatting")
        
        # Exit with appropriate code
        sys.exit(EXIT_SUCCESS if result.passed else 1)
    
    except Exception as e:
        from autonomous_agent_builder.cli.output import error
        error(f"Error during validation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@app.command()
def lint(
    kb_dir: str = typer.Option(
        "reverse-engineering",
        help="Knowledge base directory to lint (relative to .agent-builder/knowledge/)"
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
        builder kb lint
        builder kb lint --strict
        builder kb lint --verbose
        builder kb lint --kb-dir custom-docs
    """
    from autonomous_agent_builder.knowledge.document_spec import lint_directory
    
    # Find knowledge base directory
    kb_path = Path(".agent-builder") / "knowledge" / kb_dir
    
    if not kb_path.exists():
        from autonomous_agent_builder.cli.output import error
        error(f"Error: Knowledge base not found at {kb_path}")
        error("Run 'builder kb extract' first.")
        sys.exit(1)
    
    typer.echo(f"🔍 Linting documents in {kb_path}...")
    typer.echo()
    
    passed, failed, total = lint_directory(kb_path, strict=strict, verbose=verbose)
    
    typer.echo()
    typer.echo("=" * 60)
    typer.echo(f"📊 Results: {passed}/{total} passed, {failed}/{total} failed")
    
    if failed == 0:
        typer.echo("✅ All documents pass linting checks!")
        sys.exit(0)
    else:
        typer.echo(f"❌ {failed} document(s) failed linting")
        sys.exit(1)
