"""Script execution framework for discovering, loading, and running scripts."""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from .base import Script, ScriptResult


class ScriptExecutor:
    """Framework for discovering, loading, and executing scripts."""

    def __init__(self, scripts_dir: Path):
        """Initialize the script executor.
        
        Args:
            scripts_dir: Directory containing script files
        """
        self.scripts_dir = scripts_dir

    def discover_scripts(self) -> list[str]:
        """Discover all available scripts in the scripts directory.
        
        Returns:
            List of script names (without .py extension)
        """
        if not self.scripts_dir.exists():
            return []

        scripts = []
        for file_path in self.scripts_dir.glob("*.py"):
            # Skip __init__.py, base.py, and executor.py
            if file_path.stem in ("__init__", "base", "executor"):
                continue
            scripts.append(file_path.stem)

        return sorted(scripts)

    def load_script(self, script_name: str) -> Script | None:
        """Load a script by name.
        
        Args:
            script_name: Name of the script (without .py extension)
            
        Returns:
            Script instance if found and valid, None otherwise
        """
        script_path = self.scripts_dir / f"{script_name}.py"
        if not script_path.exists():
            return None

        try:
            # Import the script as a module from the embedded.scripts package
            # This allows the scripts to use relative imports
            module_name = f"autonomous_agent_builder.embedded.scripts.{script_name}"
            
            # Check if already imported
            if module_name in sys.modules:
                module = sys.modules[module_name]
            else:
                # Load the module dynamically
                spec = importlib.util.spec_from_file_location(module_name, script_path)
                if spec is None or spec.loader is None:
                    return None

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

            # Find the Script subclass in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Script)
                    and attr is not Script
                ):
                    return attr()

            return None

        except Exception as e:
            # Log the error for debugging
            import traceback
            traceback.print_exc()
            return None

    def execute_script(
        self, script_name: str, args: dict[str, Any] | None = None
    ) -> ScriptResult:
        """Execute a script with the provided arguments.
        
        Args:
            script_name: Name of the script to execute
            args: Dictionary of arguments to pass to the script
            
        Returns:
            ScriptResult with execution outcome
        """
        args = args or {}

        # Load the script
        script = self.load_script(script_name)
        if script is None:
            return {
                "success": False,
                "data": None,
                "error": f"Script '{script_name}' not found or invalid",
            }

        # Validate arguments
        is_valid, error_message = script.validate_args(**args)
        if not is_valid:
            return {
                "success": False,
                "data": None,
                "error": f"Invalid arguments: {error_message}",
            }

        # Execute the script
        try:
            result = script.run(**args)
            return result
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": f"Script execution failed: {str(e)}",
            }

    def format_output(self, result: ScriptResult, json_output: bool = False) -> str:
        """Format script result for output.
        
        Args:
            result: Script execution result
            json_output: If True, format as JSON; otherwise as human-readable text
            
        Returns:
            Formatted output string
        """
        if json_output:
            return json.dumps(result, indent=2)

        if result["success"]:
            output = "Success"
            if result["data"] is not None:
                output += f"\n{result['data']}"
            return output
        else:
            output = "Error"
            if result["error"]:
                output += f": {result['error']}"
            return output
