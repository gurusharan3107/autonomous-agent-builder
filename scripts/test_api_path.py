from pathlib import Path

# Simulate the path calculation from .agent-builder/server/routes/dashboard.py
current_file = Path(".agent-builder/server/routes/dashboard.py").resolve()
print(f"Current file: {current_file}")

agent_builder_dir = current_file.parent.parent.parent
print(f"Agent builder dir: {agent_builder_dir}")

project_root = agent_builder_dir.parent
print(f"Project root: {project_root}")

feature_list_path = project_root / ".claude" / "progress" / "feature-list.json"
print(f"Feature list path: {feature_list_path}")
print(f"Exists: {feature_list_path.exists()}")

if feature_list_path.exists():
    import json
    with open(feature_list_path) as f:
        data = json.load(f)
    print(f"Features: {len(data.get('features', []))}")
    print(f"Project: {data.get('metadata', {}).get('project', 'unknown')}")
