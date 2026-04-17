"""Workflows and orchestration generator."""

from __future__ import annotations

import ast
from typing import Any

from .base import BaseGenerator


class WorkflowsGenerator(BaseGenerator):
    """Generate workflows and orchestration documentation."""

    def generate(self, scope: str = "full") -> dict[str, Any] | None:
        """Generate workflows documentation."""
        
        if not self._is_python_project():
            return None
        
        # Find orchestrator and definitions files
        orchestrator_files = self._find_files("**/orchestrator*.py", max_depth=4)
        definitions_files = self._find_files("**/definitions.py", max_depth=4)
        
        if not orchestrator_files and not definitions_files:
            return None
        
        phases = []
        workflows = []
        
        # Extract phases from definitions.py (AGENT_DEFINITIONS)
        for def_file in definitions_files:
            content = self._read_file_safe(def_file)
            if content and "AGENT_DEFINITIONS" in content:
                phase_info = self._extract_phases_from_definitions(content)
                phases.extend(phase_info)
        
        # Extract workflow logic from orchestrator
        for orch_file in orchestrator_files:
            content = self._read_file_safe(orch_file)
            if content:
                workflow_info = self._extract_workflow_info(content)
                if workflow_info:
                    workflows.extend(workflow_info)
        
        if not phases and not workflows:
            return None
        
        content = """# Workflows and Orchestration

## Overview

This document describes the system's workflows, orchestration patterns,
and execution phases.

"""
        
        # Add workflow diagram
        if phases:
            content += self._generate_workflow_diagram(phases)
        
        # Add phases
        if phases:
            content += "\n## Execution Phases\n\n"
            for phase in phases:
                content += f"### {phase['name']}\n\n"
                if phase.get('description'):
                    content += f"{phase['description']}\n\n"
                if phase.get('model'):
                    content += f"**Model**: {phase['model']}\n\n"
                if phase.get('max_turns'):
                    content += f"**Max Turns**: {phase['max_turns']}\n\n"
                if phase.get('tools'):
                    content += f"**Tools**: {', '.join(phase['tools'][:8])}"
                    if len(phase['tools']) > 8:
                        content += f" (and {len(phase['tools']) - 8} more)"
                    content += "\n\n"
        
        # Add workflows
        if workflows:
            content += "\n## Workflows\n\n"
            for workflow in workflows:
                content += f"### {workflow['name']}\n\n"
                if workflow.get('description'):
                    content += f"{workflow['description']}\n\n"
                if workflow.get('steps'):
                    content += "**Steps**:\n\n"
                    for i, step in enumerate(workflow['steps'], 1):
                        content += f"{i}. {step}\n"
                    content += "\n"
        
        content += """## Orchestration Patterns

### Deterministic Dispatch

The orchestrator uses deterministic dispatch based on task status:
- Task status determines which phase handler to invoke
- No agent self-routing - orchestrator owns all routing decisions
- Predictable execution flow

### Phase Chaining

Phases can chain together:
- Output of one phase becomes input to next
- Session context passed between phases
- Enables complex multi-step workflows

### Error Handling

Workflow error handling:
- Gate failures trigger autofix attempts
- Retry logic with configurable limits
- CAPABILITY_LIMIT for unrecoverable errors
- Dead-letter queue for failed tasks

### Concurrent Execution

Quality gates run concurrently:
- asyncio.gather for parallel execution
- Per-gate timeouts
- AND aggregation (all must pass)
"""
        
        return {
            "title": "Workflows and Orchestration",
            "content": content,
            "tags": ["workflows", "orchestration", "phases", "reverse-engineering"],
            "doc_type": "reverse-engineering",
        }

    def _extract_phases_from_definitions(self, content: str) -> list[dict]:
        """Extract phase information from AGENT_DEFINITIONS."""
        phases = []
        
        try:
            tree = ast.parse(content)
            
            # Look for AGENT_DEFINITIONS dict in module body
            for node in tree.body:
                # Handle both regular assignment and annotated assignment
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    # Get target name
                    target_name = None
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                target_name = target.id
                    elif isinstance(node, ast.AnnAssign):
                        if isinstance(node.target, ast.Name):
                            target_name = node.target.id
                    
                    if target_name == "AGENT_DEFINITIONS":
                        # Found the dict, extract agents
                        if isinstance(node.value, ast.Dict):
                            for key, value in zip(node.value.keys, node.value.values):
                                if isinstance(key, ast.Constant) and isinstance(value, ast.Call):
                                    phase_info = self._extract_phase_from_call(key.value, value)
                                    if phase_info:
                                        phases.append(phase_info)
        except Exception:
            pass
        
        return phases

    def _extract_phase_from_call(self, name: str, call: ast.Call) -> dict | None:
        """Extract phase info from AgentDefinition() call."""
        phase = {"name": name.replace("-", " ").title()}
        
        # Extract keyword arguments
        for keyword in call.keywords:
            if keyword.arg == "description" and isinstance(keyword.value, ast.Constant):
                phase["description"] = keyword.value.value
            elif keyword.arg == "model" and isinstance(keyword.value, ast.Constant):
                phase["model"] = keyword.value.value
            elif keyword.arg == "max_turns" and isinstance(keyword.value, ast.Constant):
                phase["max_turns"] = keyword.value.value
            elif keyword.arg == "tools" and isinstance(keyword.value, ast.Tuple):
                tools = []
                for elt in keyword.value.elts:
                    if isinstance(elt, ast.Constant):
                        tools.append(elt.value)
                phase["tools"] = tools
        
        return phase if len(phase) > 1 else None

    def _extract_workflow_info(self, content: str) -> list[dict]:
        """Extract workflow information."""
        workflows = []
        
        try:
            tree = ast.parse(content)
            
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if "dispatch" in node.name.lower() or "execute" in node.name.lower():
                        docstring = ast.get_docstring(node)
                        
                        workflows.append({
                            "name": node.name.replace("_", " ").title(),
                            "description": docstring,
                        })
        except Exception:
            pass
        
        return workflows

    def _generate_workflow_diagram(self, phases: list[dict]) -> str:
        """Generate Mermaid workflow diagram."""
        diagram = """## Workflow Diagram

```mermaid
graph LR
    Start([Start]) --> Phase1
"""
        
        for i, phase in enumerate(phases[:8], 1):  # Limit to 8 phases
            phase_id = f"Phase{i}"
            phase_name = phase['name']
            
            if i < len(phases):
                next_phase_id = f"Phase{i+1}"
                diagram += f"    {phase_id}[{phase_name}] --> {next_phase_id}\n"
            else:
                diagram += f"    {phase_id}[{phase_name}] --> End([End])\n"
        
        diagram += "```\n"
        
        return diagram
