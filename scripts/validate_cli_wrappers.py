#!/usr/bin/env python3
"""
CLI Wrapper Validation - Ensures cross-platform wrappers exist and are correct.

Validates that Python CLI tools have proper wrappers for both Unix (bash) and Windows (batch).
"""

import sys
from pathlib import Path


def validate_wrappers():
    """Validate that CLI tools have proper platform wrappers."""
    print("=" * 60)
    print("CLI Wrapper Validation")
    print("=" * 60)
    
    claude_bin = Path.home() / ".claude" / "bin"
    local_bin = Path.home() / ".local" / "bin"
    
    if not claude_bin.exists():
        print(f"\n❌ Directory not found: {claude_bin}")
        return 1
    
    if not local_bin.exists():
        print(f"\n⚠️  Directory not found: {local_bin}")
        print("   Creating it...")
        local_bin.mkdir(parents=True, exist_ok=True)
    
    # Find all Python CLI tools
    python_scripts = list(claude_bin.glob("*.py"))
    
    if not python_scripts:
        print(f"\n⚠️  No Python scripts found in {claude_bin}")
        return 0
    
    print(f"\nFound {len(python_scripts)} Python CLI tool(s):\n")
    
    issues = []
    validated = []
    
    for script in python_scripts:
        tool_name = script.stem
        print(f"🔍 Validating: {tool_name}")
        
        # Check bash wrapper
        bash_wrapper = local_bin / tool_name
        if bash_wrapper.exists():
            content = bash_wrapper.read_text()
            if script.name in content or str(script) in content:
                print(f"  ✓ Bash wrapper exists and references script")
            else:
                print(f"  ✗ Bash wrapper exists but doesn't reference {script.name}")
                issues.append(f"{tool_name}: bash wrapper incorrect")
        else:
            print(f"  ⚠️  Bash wrapper missing: {bash_wrapper}")
            issues.append(f"{tool_name}: missing bash wrapper")
        
        # Check Windows batch wrapper
        bat_wrapper = local_bin / f"{tool_name}.bat"
        if bat_wrapper.exists():
            content = bat_wrapper.read_text()
            if script.name in content or "workflow.py" in content:
                print(f"  ✓ Batch wrapper exists and references script")
            else:
                print(f"  ✗ Batch wrapper exists but doesn't reference {script.name}")
                issues.append(f"{tool_name}: batch wrapper incorrect")
        else:
            print(f"  ⚠️  Batch wrapper missing: {bat_wrapper}")
            issues.append(f"{tool_name}: missing batch wrapper")
        
        # Check if Python script is executable
        if script.stat().st_mode & 0o111:
            print(f"  ✓ Python script is executable")
        else:
            print(f"  ⚠️  Python script not executable (may not matter on Windows)")
        
        if not any(f"{tool_name}:" in issue for issue in issues):
            validated.append(tool_name)
        
        print()
    
    # Summary
    print("=" * 60)
    print(f"Validated: {len(validated)}/{len(python_scripts)} tools")
    
    if issues:
        print(f"\n⚠️  Issues found ({len(issues)}):")
        for issue in issues:
            print(f"  - {issue}")
        print("\n💡 To fix:")
        print("   1. Create missing wrappers in ~/.local/bin/")
        print("   2. Ensure wrappers reference correct Python scripts")
        print("   3. Add ~/.local/bin to PATH if not already there")
        return 1
    else:
        print("\n✅ All CLI wrappers validated")
        return 0


def main():
    """Run wrapper validation."""
    return validate_wrappers()


if __name__ == "__main__":
    sys.exit(main())
