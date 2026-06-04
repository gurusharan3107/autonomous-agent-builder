"""Tests for the Product-UI design directive (IMP-034a).

Covers the directive content guarantees, the UI gate, KeyError-safe template
formatting, and the compactness ceiling that keeps it cache-friendly.
"""

from __future__ import annotations

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.agents.design_directive import (
    PRODUCT_UI_DESIGN_DIRECTIVE,
    design_directive_block,
)
from autonomous_agent_builder.services.codex_optimization import estimate_tokens


def _format_code_gen(design_directive: str) -> str:
    """Format the code-gen template with all required vars + the given directive."""
    cg = get_agent_definition("code-gen")
    base = dict(
        language="node",
        scope_reminder="",
        workspace_map="",
        tool_context="",
        task_description="task",
        design_context="",
        gate_feedback="",
        recovery_context="",
        workspace_path="/w",
        knowledge_requirements="",
    )
    return cg.prompt_template.format(design_directive=design_directive, **base)


class TestDirectiveContent:
    def test_covers_highest_slop_signal_rules(self):
        text = PRODUCT_UI_DESIGN_DIRECTIVE.lower()
        # The rules most violated by AI-generated product UIs must all be present.
        assert "purple" in text  # the #1 AI tell (default blue/purple)
        assert "focus-visible" in text  # interactive states
        assert "empty" in text and "loading" in text and "error" in text
        assert "wcag" in text  # a11y contrast floor
        assert "prefers-reduced-motion" in text  # motion restraint
        assert "scale" in text  # spacing scale

    def test_is_stack_agnostic(self):
        # Must not leak framework/library-specific guidance — generated apps may
        # be vanilla HTML/CSS/JS, not React/Tailwind/Next.
        text = PRODUCT_UI_DESIGN_DIRECTIVE.lower()
        for banned in ("tailwind", "react", "next.js", "motion/react", "gsap", "shadcn"):
            assert banned not in text, f"directive leaked stack-specific term: {banned}"


class TestDirectiveGate:
    def test_ui_task_gets_directive_with_trailing_blank_line(self):
        block = design_directive_block(True)
        assert block.startswith("UI DESIGN BAR")
        assert block.endswith("\n\n")

    def test_non_ui_task_gets_empty_block(self):
        assert design_directive_block(False) == ""


class TestTemplateWiring:
    def test_ui_prompt_contains_directive(self):
        prompt = _format_code_gen(design_directive_block(True))
        assert "UI DESIGN BAR" in prompt

    def test_non_ui_prompt_omits_directive(self):
        prompt = _format_code_gen(design_directive_block(False))
        assert "UI DESIGN BAR" not in prompt

    def test_code_gen_template_declares_placeholder(self):
        cg = get_agent_definition("code-gen")
        assert "{design_directive}" in cg.prompt_template


class TestCompactness:
    def test_directive_stays_under_cache_friendly_ceiling(self):
        # Static + cached, but still bounded so the first-turn cost and any future
        # edits stay disciplined. Ceiling well above current ~520 tok, well below
        # the ~35K-token upstream taste-skill we deliberately did NOT inline.
        assert estimate_tokens(PRODUCT_UI_DESIGN_DIRECTIVE) < 900
