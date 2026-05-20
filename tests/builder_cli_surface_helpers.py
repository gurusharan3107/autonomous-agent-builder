"""Shared fixtures for builder CLI surface contract tests."""

from __future__ import annotations

from pathlib import Path

from autonomous_agent_builder.cli.commands import kb as kb_module


def assert_agent_json_contract(payload: dict, *, ok: bool = True) -> None:
    assert payload["ok"] is ok
    assert isinstance(payload["status"], str)
    assert isinstance(payload["exit_code"], int)
    assert payload["schema_version"] == "1"
    assert isinstance(payload["token_estimate"], int)
    assert isinstance(payload["truncated"], bool)


def configure_local_kb(monkeypatch, tmp_path: Path) -> Path:
    project_root = tmp_path
    kb_root = project_root / ".agent-builder" / "knowledge"
    kb_root.mkdir(parents=True)
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(kb_root))
    return kb_root


def write_local_kb_doc(kb_root: Path, doc_id: str, content: str) -> Path:
    path = kb_root / doc_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class PathClient:
    def __init__(self, mapping: dict[str, object]):
        self.mapping = mapping

    def get(self, path: str, **params):
        key = path
        if params:
            if path == "/projects/":
                key = "/projects/"
            elif path == "/tasks":
                key = "/tasks"
            elif path == "/gates":
                key = "/gates"
            elif path == "/runs":
                key = "/runs"
            elif path == "/approval-gates":
                key = "/approval-gates"
        if key not in self.mapping:
            raise kb_module.AabApiError(404, {"detail": f"missing {key}"})
        value = self.mapping[key]
        if callable(value):
            return value(path, **params)
        return value

    def post(self, path: str, data=None):
        key = f"POST:{path}"
        if key not in self.mapping:
            raise kb_module.AabApiError(404, {"detail": f"missing {key}"})
        value = self.mapping[key]
        return value(path, data=data) if callable(value) else value

    def put(self, path: str, data=None):
        key = f"PUT:{path}"
        if key not in self.mapping:
            raise kb_module.AabApiError(404, {"detail": f"missing {key}"})
        value = self.mapping[key]
        return value(path, data=data) if callable(value) else value

    def close(self) -> None:
        return None
