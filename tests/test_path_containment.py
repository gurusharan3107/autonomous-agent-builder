from __future__ import annotations

import json
from pathlib import Path

from autonomous_agent_builder.services.path_containment import resolve_contained_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_resolve_contained_path_rejects_sibling_prefix_escape(tmp_path) -> None:
    root = tmp_path / "work"
    sibling = tmp_path / "work-secret"
    root.mkdir()
    sibling.mkdir()

    assert resolve_contained_path(root, "../work-secret/file.txt") is None


def test_resolve_contained_path_rejects_symlink_escape(tmp_path) -> None:
    root = tmp_path / "work"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    (root / "linked.txt").symlink_to(outside / "secret.txt")

    assert resolve_contained_path(root, "linked.txt") is None


def test_resolve_contained_path_allows_nested_child(tmp_path) -> None:
    root = tmp_path / "work"
    child = root / "nested" / "file.txt"
    child.parent.mkdir(parents=True)
    child.write_text("inside", encoding="utf-8")

    assert resolve_contained_path(root, "nested/file.txt") == child.resolve()


def test_global_kb_api_routing_rejects_article_file_escape(tmp_path, monkeypatch) -> None:
    from autonomous_agent_builder.api.routes import knowledge

    kb_root = tmp_path / "knowledge"
    raw_root = kb_root / "raw"
    raw_root.mkdir(parents=True)
    inside = raw_root / "inside.md"
    outside = kb_root / "outside.md"
    inside.write_text("# Inside\n", encoding="utf-8")
    outside.write_text("# Outside\n", encoding="utf-8")
    (kb_root / "routing.json").write_text(
        json.dumps(
            {
                "articles": [
                    {"file": "../outside.md", "title": "Escaped"},
                    {"file": "inside.md", "title": "Inside"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(knowledge, "global_kb_root", lambda: kb_root)

    assert knowledge._global_doc_paths() == [inside.resolve()]


def test_filesystem_boundary_modules_use_containment_helper() -> None:
    required_modules = [
        "src/autonomous_agent_builder/api/routes/knowledge.py",
        "src/autonomous_agent_builder/api/routes/memory_api.py",
        "src/autonomous_agent_builder/knowledge/publisher.py",
        "src/autonomous_agent_builder/agents/tools/workspace_tools.py",
        "src/autonomous_agent_builder/embedded/server/app.py",
    ]

    missing = [
        module
        for module in required_modules
        if "resolve_contained_path"
        not in (PROJECT_ROOT / module).read_text(encoding="utf-8")
    ]

    assert missing == []


def test_controlled_root_path_joins_stay_behind_containment_helper() -> None:
    forbidden_patterns = {
        "src/autonomous_agent_builder/api/routes/knowledge.py": ["raw_root / file_name"],
        "src/autonomous_agent_builder/api/routes/memory_api.py": [
            "memory_root / entry",
            "memory_root / file",
            'memory_root / entry.get("file"',
        ],
        "src/autonomous_agent_builder/knowledge/publisher.py": [
            "root / existing_doc_id",
            "root / file_name",
            "root / requested_path",
        ],
    }
    offenders = []
    for module, patterns in forbidden_patterns.items():
        text = (PROJECT_ROOT / module).read_text(encoding="utf-8")
        offenders.extend(f"{module}:{pattern}" for pattern in patterns if pattern in text)

    assert offenders == []
