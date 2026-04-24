#!/usr/bin/env python3
"""
Clean up database - remove demo/duplicate projects and keep only autonomous-agent-builder.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def cleanup_database():
    """Remove demo projects and keep only autonomous-agent-builder."""
    import os
    from autonomous_agent_builder.db.session import get_session_factory
    from autonomous_agent_builder.db.models import Project
    from sqlalchemy import select, delete
    
    # Set database path
    project_root = Path(__file__).parent.parent
    db_path = project_root / ".agent-builder" / "agent_builder.db"
    os.environ["DB_NAME"] = str(db_path.with_suffix(""))
    
    # Clear cached engine
    from autonomous_agent_builder.db import session as session_mod
    session_mod._engine = None
    session_mod._session_factory = None
    
    factory = get_session_factory()
    
    async with factory() as session:
        try:
            # Get all projects
            result = await session.execute(select(Project))
            projects = result.scalars().all()
            
            print(f"📋 Found {len(projects)} projects:")
            for p in projects:
                print(f"  - {p.name} (ID: {p.id})")
            
            # Keep only the latest autonomous-agent-builder project
            aab_projects = [p for p in projects if p.name == "autonomous-agent-builder"]
            demo_projects = [p for p in projects if p.name != "autonomous-agent-builder"]
            
            if len(aab_projects) > 1:
                # Keep the most recent one (last in list)
                to_delete = aab_projects[:-1]
                print(f"\n🗑️  Removing {len(to_delete)} duplicate autonomous-agent-builder projects")
                for p in to_delete:
                    await session.delete(p)
            
            if demo_projects:
                print(f"\n🗑️  Removing {len(demo_projects)} demo projects:")
                for p in demo_projects:
                    print(f"  - {p.name}")
                    await session.delete(p)
            
            await session.commit()
            
            # Verify
            result = await session.execute(select(Project))
            remaining = result.scalars().all()
            
            print(f"\n✅ Cleanup complete!")
            print(f"   Remaining projects: {len(remaining)}")
            for p in remaining:
                print(f"   - {p.name} (ID: {p.id})")
            
            return 0
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error cleaning up database: {e}")
            import traceback
            traceback.print_exc()
            return 1


def main():
    """Run the cleanup."""
    return asyncio.run(cleanup_database())


if __name__ == "__main__":
    sys.exit(main())
