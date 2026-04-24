"""Seed script — populate DB with a demo Python FastAPI project.

Creates a project, feature, and tasks to demonstrate the full SDLC pipeline.
Run: python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio

from autonomous_agent_builder.db.models import (
    Feature,
    FeatureStatus,
    Project,
    QualityGate,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.db.session import get_session_factory, init_db


async def seed() -> None:
    """Seed the database with demo data."""
    await init_db()
    factory = get_session_factory()

    async with factory() as db:
        # Create demo project
        project = Project(
            name="demo-fastapi-app",
            description="Demo FastAPI application for showcasing autonomous agent builder",
            repo_url="https://github.com/accenture/demo-fastapi-app",
            language="python",
        )
        db.add(project)
        await db.flush()

        # Create demo feature
        feature = Feature(
            project_id=project.id,
            title="Add health check endpoint",
            description=(
                "Add a /health endpoint that returns JSON with:\n"
                "- status: 'ok' or 'degraded'\n"
                "- version: from package metadata\n"
                "- db_connected: boolean (ping PostgreSQL)\n"
                "- uptime_seconds: time since server start\n\n"
                "Include tests for all response fields."
            ),
            status=FeatureStatus.BACKLOG,
            priority=1,
        )
        db.add(feature)
        await db.flush()

        # Create tasks for the feature
        tasks_data = [
            {
                "title": "Design health check response schema",
                "description": "Define the JSON response schema and error cases for /health endpoint",
                "complexity": 1,
            },
            {
                "title": "Implement /health endpoint",
                "description": "Create the endpoint handler with DB ping, version lookup, and uptime tracking",
                "complexity": 2,
            },
            {
                "title": "Add health check tests",
                "description": "Write pytest tests covering: healthy response, DB down case, response schema validation",
                "complexity": 2,
            },
        ]

        for td in tasks_data:
            task = Task(
                feature_id=feature.id,
                title=td["title"],
                description=td["description"],
                complexity=td["complexity"],
                status=TaskStatus.PENDING,
            )
            db.add(task)

        # Seed quality gate configurations
        gates_data = [
            {"name": "ruff", "gate_type": "code_quality", "tier": "pre_integration", "timeout_seconds": 30},
            {"name": "pytest", "gate_type": "testing", "tier": "pre_integration", "timeout_seconds": 120},
            {"name": "semgrep", "gate_type": "security", "tier": "post_integration", "timeout_seconds": 60},
            {"name": "trivy", "gate_type": "dependency", "tier": "post_integration", "timeout_seconds": 45},
        ]

        for gd in gates_data:
            gate = QualityGate(**gd)
            db.add(gate)

        await db.commit()

        print(f"Seeded project: {project.name} (id: {project.id})")
        print(f"Seeded feature: {feature.title} (id: {feature.id})")
        print(f"Seeded {len(tasks_data)} tasks")
        print(f"Seeded {len(gates_data)} quality gates")


if __name__ == "__main__":
    asyncio.run(seed())
