#!/usr/bin/env python3
"""
CLI Tools Smoke Tests - Validates that CLI commands work correctly.

Tests workflow CLI and builder memory commands to catch integration issues early.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], expect_success: bool = True) -> tuple[bool, str]:
    """Run a command and check if it succeeded.
    
    Args:
        cmd: Command and arguments as list
        expect_success: Whether command should succeed (exit 0)
        
    Returns:
        Tuple of (passed, message)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        success = (result.returncode == 0) == expect_success
        
        if not success:
            msg = f"Command: {' '.join(cmd)}\n"
            msg += f"Expected {'success' if expect_success else 'failure'}, "
            msg += f"got exit code {result.returncode}\n"
            if result.stderr:
                msg += f"stderr: {result.stderr[:200]}\n"
            return False, msg
        
        return True, f"✓ {' '.join(cmd[:3])}"
        
    except subprocess.TimeoutExpired:
        return False, f"✗ Timeout: {' '.join(cmd)}"
    except FileNotFoundError:
        return False, f"✗ Command not found: {cmd[0]}"
    except Exception as e:
        return False, f"✗ Error running {' '.join(cmd)}: {e}"


def test_workflow_cli():
    """Test workflow CLI basic functionality."""
    print("\n🔍 Testing workflow CLI...")
    
    tests = [
        # Test Python script directly (always works)
        (["python", str(Path.home() / ".claude/bin/workflow.py"), "--help"], True),
        (["python", str(Path.home() / ".claude/bin/workflow.py"), "memory", "list"], True),
        
        # Test wrapper (platform-specific)
        (["workflow.bat", "memory", "list"], True) if sys.platform == "win32" else
        (["workflow", "memory", "list"], True),
    ]
    
    passed = 0
    failed = 0
    
    for cmd, expect_success in tests:
        success, msg = run_command(cmd, expect_success)
        if success:
            print(f"  {msg}")
            passed += 1
        else:
            print(f"  {msg}")
            failed += 1
    
    return passed, failed


def test_builder_memory():
    """Test builder memory commands."""
    print("\n🔍 Testing builder memory CLI...")
    
    tests = [
        # Basic commands that should work
        (["builder", "memory", "list"], True),
        (["builder", "memory", "search", "test"], True),
    ]
    
    passed = 0
    failed = 0
    
    for cmd, expect_success in tests:
        success, msg = run_command(cmd, expect_success)
        if success:
            print(f"  {msg}")
            passed += 1
        else:
            print(f"  {msg}")
            failed += 1
    
    return passed, failed


def test_builder_script():
    """Test builder script commands."""
    print("\n🔍 Testing builder script CLI...")
    
    # Only test if .agent-builder exists (project initialized)
    if not Path(".agent-builder").exists():
        print("  ⊘ Skipped (project not initialized)")
        return 0, 0
    
    tests = [
        (["builder", "script", "list"], True),
    ]
    
    passed = 0
    failed = 0
    
    for cmd, expect_success in tests:
        success, msg = run_command(cmd, expect_success)
        if success:
            print(f"  {msg}")
            passed += 1
        else:
            print(f"  {msg}")
            failed += 1
    
    return passed, failed


def main():
    """Run all CLI smoke tests."""
    print("=" * 60)
    print("CLI Tools Smoke Tests")
    print("=" * 60)
    
    total_passed = 0
    total_failed = 0
    
    # Run test suites
    passed, failed = test_workflow_cli()
    total_passed += passed
    total_failed += failed
    
    passed, failed = test_builder_memory()
    total_passed += passed
    total_failed += failed
    
    passed, failed = test_builder_script()
    total_passed += passed
    total_failed += failed
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {total_passed} passed, {total_failed} failed")
    print("=" * 60)
    
    if total_failed > 0:
        print("\n❌ Some CLI tests failed")
        return 1
    else:
        print("\n✅ All CLI tests passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
