"""Compatibility wrappers around the owning builder tool service layer."""

from __future__ import annotations

from autonomous_agent_builder.services import builder_tool_service


async def builder_board(project_root: str | None = None) -> dict:
    """Get the current task pipeline board status."""
    return await builder_tool_service.builder_board(project_root=project_root)


async def builder_task_list(
    feature_id: str,
    status: str = "",
    limit: int = 50,
    *,
    project_root: str | None = None,
) -> dict:
    """List tasks for a feature."""
    return await builder_tool_service.builder_task_list(
        feature_id,
        status,
        limit,
        project_root=project_root,
    )


async def builder_task_show(task_id: str, *, project_root: str | None = None) -> dict:
    """Show task details including status, retry count, and blocked reason."""
    return await builder_tool_service.builder_task_show(task_id, project_root=project_root)


async def builder_task_status(task_id: str, *, project_root: str | None = None) -> dict:
    """Quick status check for a task."""
    return await builder_tool_service.builder_task_status(task_id, project_root=project_root)


async def builder_task_dispatch(task_id: str, *, project_root: str | None = None) -> dict:
    """Dispatch a task through the builder-owned task surface."""
    return await builder_tool_service.builder_task_dispatch(task_id, project_root=project_root)


async def builder_metrics(project_root: str | None = None) -> dict:
    """Get aggregate metrics about builder runs."""
    return await builder_tool_service.builder_metrics(project_root=project_root)


async def builder_kb_search(
    query: str,
    doc_type: str = "",
    tags: list[str] | None = None,
    *,
    project_root: str | None = None,
) -> dict:
    """Search the project knowledge base."""
    return await builder_tool_service.builder_kb_search(
        query,
        doc_type,
        tags,
        project_root=project_root,
    )


async def builder_kb_show(doc_id: str, *, project_root: str | None = None) -> dict:
    """Show a repo-local knowledge base document."""
    return await builder_tool_service.builder_kb_show(doc_id, project_root=project_root)


async def builder_kb_extract(
    kb_dir: str = "system-docs",
    scope: str = "full",
    doc_slug: str = "",
    force: bool = False,
    run_validation: bool = True,
    *,
    project_root: str | None = None,
) -> dict:
    """Run the canonical builder knowledge extraction flow."""
    return await builder_tool_service.builder_kb_extract(
        kb_dir,
        scope,
        doc_slug,
        force,
        run_validation,
        project_root=project_root,
    )


async def builder_kb_add(
    doc_type: str,
    title: str,
    content: str,
    task_id: str = "",
    tags: list[str] | None = None,
    family: str = "",
    linked_feature: str = "",
    feature_id: str = "",
    refresh_required: bool | None = None,
    documented_against_commit: str = "",
    documented_against_ref: str = "",
    owned_paths: list[str] | None = None,
    verified_with: str = "",
    last_verified_at: str = "",
    lifecycle_status: str = "",
    superseded_by: str = "",
    source_url: str = "",
    source_title: str = "",
    source_author: str = "",
    date_published: str = "",
    *,
    project_root: str | None = None,
) -> dict:
    """Publish a repo-local knowledge base document through the shared service."""
    return await builder_tool_service.builder_kb_add(
        doc_type,
        title,
        content,
        task_id,
        tags,
        family,
        linked_feature,
        feature_id,
        refresh_required,
        documented_against_commit,
        documented_against_ref,
        owned_paths,
        verified_with,
        last_verified_at,
        lifecycle_status,
        superseded_by,
        source_url,
        source_title,
        source_author,
        date_published,
        project_root=project_root,
    )


async def builder_kb_update(
    doc_id: str,
    title: str = "",
    content: str = "",
    tags: list[str] | None = None,
    family: str = "",
    linked_feature: str = "",
    feature_id: str = "",
    refresh_required: bool | None = None,
    documented_against_commit: str = "",
    documented_against_ref: str = "",
    owned_paths: list[str] | None = None,
    verified_with: str = "",
    last_verified_at: str = "",
    lifecycle_status: str = "",
    superseded_by: str = "",
    source_url: str = "",
    source_title: str = "",
    source_author: str = "",
    date_published: str = "",
    *,
    project_root: str | None = None,
) -> dict:
    """Update a repo-local knowledge base document through the shared service."""
    return await builder_tool_service.builder_kb_update(
        doc_id,
        title,
        content,
        tags,
        family,
        linked_feature,
        feature_id,
        refresh_required,
        documented_against_commit,
        documented_against_ref,
        owned_paths,
        verified_with,
        last_verified_at,
        lifecycle_status,
        superseded_by,
        source_url,
        source_title,
        source_author,
        date_published,
        project_root=project_root,
    )


async def builder_memory_search(
    query: str,
    entity: str = "",
    *,
    project_root: str | None = None,
) -> dict:
    """Search project memory for decisions, patterns, and corrections."""
    return await builder_tool_service.builder_memory_search(
        query,
        entity,
        project_root=project_root,
    )


async def builder_memory_show(slug: str, *, project_root: str | None = None) -> dict:
    """Get a memory entry by slug."""
    return await builder_tool_service.builder_memory_show(slug, project_root=project_root)


async def builder_memory_add(
    mem_type: str,
    phase: str,
    entity: str,
    tags: str,
    title: str,
    content: str,
    *,
    project_root: str | None = None,
) -> dict:
    """Record a repo-local decision, pattern, or correction through the shared service."""
    return await builder_tool_service.builder_memory_add(
        mem_type,
        phase,
        entity,
        tags,
        title,
        content,
        project_root=project_root,
    )


CLI_TOOLS = {
    "builder_board": builder_board,
    "builder_task_list": builder_task_list,
    "builder_task_show": builder_task_show,
    "builder_task_status": builder_task_status,
    "builder_task_dispatch": builder_task_dispatch,
    "builder_metrics": builder_metrics,
    "builder_kb_search": builder_kb_search,
    "builder_kb_show": builder_kb_show,
    "builder_kb_extract": builder_kb_extract,
    "builder_kb_add": builder_kb_add,
    "builder_kb_update": builder_kb_update,
    "builder_memory_search": builder_memory_search,
    "builder_memory_show": builder_memory_show,
    "builder_memory_add": builder_memory_add,
}
