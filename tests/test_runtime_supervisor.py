from __future__ import annotations

import os

import pytest

from autonomous_agent_builder.runtime import supervisor


def test_server_status_classifies_owned_live_process(monkeypatch, tmp_path) -> None:
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir()
    metadata = supervisor.write_server_metadata(agent_builder_dir, host="127.0.0.1", port=9876)

    monkeypatch.setattr(
        supervisor,
        "listening_processes",
        lambda port: [supervisor.PortProcess(pid=metadata["pid"], command="builder start")],
    )

    payload = supervisor.server_status(agent_builder_dir, 9876)

    assert payload["unknown_listener_count"] == 0
    assert payload["servers"][0]["classification"] == "owned_live"
    assert payload["servers"][0]["owned_live"] is True


def test_ensure_port_available_rejects_unknown_listener(monkeypatch, tmp_path) -> None:
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir()
    monkeypatch.setattr(
        supervisor,
        "listening_processes",
        lambda port: [supervisor.PortProcess(pid=999999, command="python other.py")],
    )

    with pytest.raises(supervisor.RuntimeSupervisorError) as exc_info:
        supervisor.ensure_port_available(agent_builder_dir, 9876)

    assert exc_info.value.code == "port_in_use_unknown_owner"


def test_stop_server_removes_stale_metadata_without_listener(monkeypatch, tmp_path) -> None:
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir()
    supervisor.write_server_metadata(agent_builder_dir, host="127.0.0.1", port=9876)
    monkeypatch.setattr(supervisor, "listening_processes", lambda port: [])

    payload = supervisor.stop_server(agent_builder_dir, port=9876)

    assert payload["metadata_removed"] is True
    assert supervisor.read_server_metadata(agent_builder_dir, 9876) is None


def test_terminate_pid_uses_process_group(monkeypatch) -> None:
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(supervisor.sys, "platform", "darwin")
    monkeypatch.setattr(supervisor, "process_exists", lambda pid: False)

    def fake_kill(target: int, sig: int) -> None:
        calls.append((target, sig))

    monkeypatch.setattr(os, "kill", fake_kill)

    supervisor.terminate_pid(123, process_group_id=456)

    assert calls == [(-456, supervisor.signal.SIGTERM)]
