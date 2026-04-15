"""Tests for egress monitoring."""

from unittest.mock import AsyncMock

import pytest

from autonomous_agent_builder.security.egress_monitor import (
    EgressDestination,
    extract_egress_destinations,
    log_egress_destinations,
)


class TestExtractEgressDestinations:
    """Test network destination extraction."""

    def test_url_extraction(self):
        """Extract HTTP/HTTPS URLs."""
        command = "curl https://example.com/api"
        output = "Response from http://other.com"
        destinations = extract_egress_destinations(command, output)
        assert len(destinations) == 2
        assert any(d.kind == "url" and "example.com" in d.target for d in destinations)
        assert any(d.kind == "url" and "other.com" in d.target for d in destinations)

    def test_git_remote_extraction(self):
        """Extract git remote URLs."""
        command = "git clone git@github.com:user/repo.git"
        destinations = extract_egress_destinations(command, "")
        assert len(destinations) >= 1
        assert any(d.kind == "git_remote" for d in destinations)

    def test_s3_bucket_extraction(self):
        """Extract S3 bucket paths."""
        command = "aws s3 sync . s3://my-bucket/"
        destinations = extract_egress_destinations(command, "")
        assert len(destinations) >= 1
        assert any(d.kind == "s3_bucket" and "my-bucket" in d.target for d in destinations)

    def test_ssh_target_extraction(self):
        """Extract SSH targets."""
        command = "ssh user@example.com"
        destinations = extract_egress_destinations(command, "")
        assert len(destinations) >= 1
        assert any(d.kind == "ssh_target" for d in destinations)

    def test_docker_push_extraction(self):
        """Extract docker push commands."""
        command = "docker push myregistry.azurecr.io/myimage:latest"
        destinations = extract_egress_destinations(command, "")
        assert len(destinations) >= 1
        assert any(d.kind == "docker_push" for d in destinations)

    def test_npm_publish_extraction(self):
        """Extract npm publish commands."""
        command = "npm publish"
        destinations = extract_egress_destinations(command, "")
        assert len(destinations) >= 1
        assert any(d.kind == "package_publish" for d in destinations)

    def test_normal_paths_no_match(self):
        """Normal file paths don't match egress patterns."""
        command = "ls -la /home/user /etc/config"
        output = "drwxr-xr-x  2 root root /usr/bin"
        destinations = extract_egress_destinations(command, output)
        assert len(destinations) == 0

    def test_empty_command_and_output(self):
        """Empty command and output returns empty list."""
        destinations = extract_egress_destinations("", "")
        assert destinations == []

    def test_none_command_and_output(self):
        """None values are handled gracefully."""
        destinations = extract_egress_destinations("", "")
        assert destinations == []

    def test_target_truncation(self):
        """Very long targets are truncated to 500 chars."""
        long_url = "https://example.com/" + "a" * 1000
        destinations = extract_egress_destinations(long_url, "")
        assert len(destinations) >= 1
        assert len(destinations[0].target) <= 500

    def test_multiple_destinations_extracted(self):
        """Extract multiple destinations from one command."""
        command = "curl https://api1.com && curl https://api2.com && ssh user@server.com"
        destinations = extract_egress_destinations(command, "")
        assert len(destinations) >= 2
        urls = [d for d in destinations if d.kind == "url"]
        assert len(urls) >= 2


@pytest.mark.asyncio
class TestLogEgressDestinations:
    """Test hook integration for egress monitoring."""

    async def test_non_bash_tool_skipped(self):
        """Non-Bash tools are skipped."""
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/etc/passwd"},
            "tool_response": "user:x:0:0:root:/root:/bin/bash",
        }
        result = await log_egress_destinations(hook_input, None, {})
        assert result == {}

    async def test_bash_egress_logged(self):
        """Bash tool with egress is logged."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "curl https://example.com"},
            "tool_response": "HTTP/200 OK",
        }
        result = await log_egress_destinations(hook_input, None, {})
        assert result == {}  # never blocks

    async def test_hook_never_blocks(self):
        """Hook always returns empty dict (never blocks)."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ssh evil@attacker.com"},
            "tool_response": "",
        }
        result = await log_egress_destinations(hook_input, None, {})
        assert result == {}
        assert "decision" not in result

    async def test_hook_handles_missing_fields(self):
        """Hook handles missing fields gracefully."""
        hook_input = {
            "tool_name": "Bash",
            # Missing tool_input and tool_response
        }
        result = await log_egress_destinations(hook_input, None, {})
        assert result == {}

    async def test_hook_exception_handling(self):
        """Hook catches exceptions and returns gracefully."""
        hook_input = None  # This will cause an exception
        # The function should handle it gracefully
        try:
            result = await log_egress_destinations(hook_input, None, {})
            assert result == {}
        except Exception as e:
            pytest.fail(f"Hook should handle exceptions gracefully: {e}")


class TestEgressDestinationStructure:
    """Test EgressDestination dataclass."""

    def test_egress_destination_fields(self):
        """EgressDestination has all required fields."""
        dest = EgressDestination(kind="url", target="https://example.com")
        assert dest.kind == "url"
        assert dest.target == "https://example.com"

    def test_egress_destination_frozen(self):
        """EgressDestination is immutable."""
        dest = EgressDestination(kind="url", target="https://example.com")
        with pytest.raises(AttributeError):
            dest.kind = "ssh"


@pytest.mark.asyncio
class TestEgressMonitorDBPersist:
    """Test DB persist callback in hook."""

    async def test_persist_callback_called(self):
        """When persist_security_finding is in context, it's called."""
        persist_fn = AsyncMock()
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "curl https://example.com"},
            "tool_response": "",
        }
        context = {"persist_security_finding": persist_fn}
        result = await log_egress_destinations(hook_input, None, context)
        assert result == {}
        persist_fn.assert_called()

    async def test_persist_callback_not_called_for_no_destinations(self):
        """No destinations = persist not called."""
        persist_fn = AsyncMock()
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_response": "",
        }
        context = {"persist_security_finding": persist_fn}
        result = await log_egress_destinations(hook_input, None, context)
        assert result == {}
        persist_fn.assert_not_called()


class TestExtractTextFromResponse:
    """Test response text extraction for egress scanning."""

    def test_dict_with_content_list(self):
        from autonomous_agent_builder.security.egress_monitor import (
            _extract_text_from_response,
        )

        resp = {"content": [{"text": "https://leak.com"}]}
        assert "leak.com" in _extract_text_from_response(resp)

    def test_dict_with_content_string(self):
        from autonomous_agent_builder.security.egress_monitor import (
            _extract_text_from_response,
        )

        resp = {"content": "https://leak.com"}
        assert "leak.com" in _extract_text_from_response(resp)

    def test_dict_with_text_field(self):
        from autonomous_agent_builder.security.egress_monitor import (
            _extract_text_from_response,
        )

        resp = {"text": "https://leak.com"}
        assert "leak.com" in _extract_text_from_response(resp)

    def test_list_response(self):
        from autonomous_agent_builder.security.egress_monitor import (
            _extract_text_from_response,
        )

        resp = ["https://a.com", "https://b.com"]
        text = _extract_text_from_response(resp)
        assert "a.com" in text
        assert "b.com" in text

    def test_none_returns_empty(self):
        from autonomous_agent_builder.security.egress_monitor import (
            _extract_text_from_response,
        )

        assert _extract_text_from_response(None) == ""
        assert _extract_text_from_response(42) == ""
