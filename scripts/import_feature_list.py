#!/usr/bin/env python3
"""
Import feature-list.json into the agent builder database.

This script loads the autonomous-agent-builder's feature backlog from
.claude/progress/feature-list.json and imports it into the database
so the dashboard shows real data instead of mock data.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autonomous_agent_builder.db.models import Feature, FeatureStatus, Project
from autonomous_agent_builder.db.session import get_session_factory, init_db


async def import_feature_list():
    """Import features from feature-list.json into the database."""
    import os
    
    # Ensure we're in the project root
    project_root = Path(__file__).parent.parent
    
    # Read feature-list.json
    feature_list_path = project_root / ".claude/progress/feature-list.json"
    if not feature_list_path.exists():
        print(f"❌ Feature list not found: {feature_list_path}")
        return 1
    
    with open(feature_list_path) as f:
        data = json.load(f)
    
    features_data = data.get("features", [])
    metadata = data.get("metadata", {})
    
    print(f"📋 Found {len(features_data)} features in feature-list.json")
    print(f"   Project: {metadata.get('project', 'unknown')}")
    print(f"   Done: {metadata.get('done', 0)}, Pending: {metadata.get('pending', 0)}")
    
    # Set database path to .agent-builder/agent_builder.db
    db_path = project_root / ".agent-builder" / "agent_builder.db"
    
    # Set DB_NAME to the full path (without .db extension)
    # The config will add .db and construct: sqlite+aiosqlite:///./.agent-builder/agent_builder.db
    os.environ["DB_NAME"] = str(db_path.with_suffix(""))
    
    print(f"\n📂 Using database: {db_path}")
    
    # Clear any cached engine/session factory
    from autonomous_agent_builder.db import session as session_mod
    session_mod._engine = None
    session_mod._session_factory = None
    
    # Initialize database
    await init_db()
    
    # Get session factory
    factory = get_session_factory()
    
    async with factory() as session:
        try:
            # Check if project exists
            project_name = metadata.get("project", "autonomous-agent-builder")
            
            # Create or get project
            project = Project(
                name=project_name,
                description="Autonomous SDLC builder with Claude Agent SDK",
                repo_url="https://github.com/accenture/autonomous-agent-builder",
                language="python",
            )
            session.add(project)
            await session.flush()  # Get project ID
            
            print(f"\n✅ Created project: {project.name} (ID: {project.id})")
            
            # Import features
            imported = 0
            skipped = 0
            
            for feature_data in features_data:
                feature_id = feature_data.get("id", "")
                title = feature_data.get("title", "")
                description = feature_data.get("description", "")
                status_str = feature_data.get("status", "pending")
                priority = feature_data.get("priority", "P1")
                
                # Map status string to FeatureStatus enum
                status_map = {
                    "done": FeatureStatus.DONE,
                    "pending": FeatureStatus.BACKLOG,
                    "in_progress": FeatureStatus.IN_PROGRESS,
                    "review": FeatureStatus.REVIEW,
                    "blocked": FeatureStatus.BLOCKED,
                }
                status = status_map.get(status_str, FeatureStatus.BACKLOG)
                
                # Map priority to integer (P0=0, P1=1, P2=2)
                priority_map = {"P0": 0, "P1": 1, "P2": 2}
                priority_int = priority_map.get(priority, 1)
                
                # Create feature
                feature = Feature(
                    project_id=project.id,
                    title=f"{feature_id}: {title}",
                    description=description,
                    status=status,
                    priority=priority_int,
                )
                session.add(feature)
                imported += 1
                
                if imported <= 5:  # Show first 5
                    print(f"  ✓ {feature_id}: {title[:50]}... [{status_str}]")
            
            if imported > 5:
                print(f"  ... and {imported - 5} more features")
            
            await session.commit()
            
            print(f"\n✅ Successfully imported {imported} features")
            print(f"   Skipped: {skipped}")
            print(f"\n🎯 Dashboard should now show real data!")
            print(f"   Open: http://127.0.0.1:9876")
            
            return 0
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error importing features: {e}")
            import traceback
            traceback.print_exc()
            return 1


def main():
    """Run the import."""
    return asyncio.run(import_feature_list())


if __name__ == "__main__":
    sys.exit(main())
