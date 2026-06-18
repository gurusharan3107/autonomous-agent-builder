"""Product-UI design directive for UI-bearing code-gen runs (IMP-034a).

The builder's code-gen agent had no design guidance in its prompt, so generated
apps shipped generic AI-slop UIs (default blue/purple, missing interactive
states, ad-hoc spacing, flat typography). This module supplies a compact,
STACK-AGNOSTIC, principle-level directive distilled from the taste-skill project
plus Vercel Web Interface Guidelines, Refactoring UI (Wathan/Schoger), and NN/g
usability heuristics.

Design constraints that shaped this:
- Stack-agnostic / principle-level: generated apps may be vanilla HTML/CSS/JS or
  React, so no framework-, Tailwind-, or library-specific code (the taste-skill
  upstream is React/Next/Tailwind/Motion-bound and not directly reusable here).
- Product-UI scoped: dashboards, tables, CRUD tools, kanban, forms — NOT landing
  pages (upstream taste-skill explicitly excludes product UI).
- Compact + STATIC: ~520 tokens, identical text for every UI task, so it rides
  the cached system-prompt prefix the code-gen run already replays each turn
  (~0 marginal tokens/turn after the first; respects the IMP-028 context budget).
  Wholesale-pasting the ~35K-token upstream skill would fight that budget.

Gating is the caller's job: the orchestrator passes ``is_ui_task(...)`` so the
block is empty for CLI/library/non-UI code-gen and never bloats those prompts.
"""

from __future__ import annotations

# Imperative fragments only — no citations or rationale (those live in this
# docstring and the ROADMAP). Grouped highest-slop-signal first.
PRODUCT_UI_DESIGN_DIRECTIVE = (
    "UI DESIGN BAR (for user-facing screens — make it tasteful, not generic AI slop):\n"
    "- Color: ONE neutral base scale + ONE accent. Accent only for the primary action and "
    "the active/selected state; everything else neutral. NEVER default to a blue/purple "
    "button or a purple/AI gradient. Decide hierarchy in grayscale first, add color last.\n"
    "- Spacing: use one fixed scale (4/8px steps: 4, 8, 12, 16, 24, 32, 48) — no ad-hoc "
    "margins. Be generous with whitespace; cramped layouts read amateur. Constrain content "
    "width; no purposeless full-bleed hero in a product app.\n"
    "- Hierarchy: build it from size + weight + color together, never size alone. Keep to "
    "~2 sizes/weights per view. De-emphasize secondary text with a muted neutral or lighter "
    "weight, not gray-on-gray mush. Use tabular-nums for numeric columns.\n"
    "- Depth: shadows model one soft top light source, layered and subtle — no harsh black "
    "drop shadows. Do not reach for glassmorphism/blur or repeated identical card grids as a "
    "default.\n"
    "- States (most-skipped by AI): EVERY interactive element needs hover + active + "
    "focus-visible + disabled. Never remove the focus outline without a visible replacement. "
    "Buttons give a small tactile press feedback.\n"
    "- Empty / loading / error: implement all three explicitly — never ship only the happy "
    "path. Show async status (skeleton or spinner, aria-live for updates). Errors are inline, "
    "plain-language, say how to fix, and focus the first bad field.\n"
    "- Forms: every input has a real label and correct type + autocomplete; never block "
    "paste. Keep submit enabled until the request starts, then show progress. Confirm or offer "
    "undo for destructive actions.\n"
    "- Consistency + a11y: one button system, one input style, one radius scale, applied "
    "everywhere. Meet WCAG AA contrast (4.5:1 text, 3:1 large/UI). Semantic HTML before ARIA; "
    "icon-only controls need an aria-label.\n"
    "- Motion: animate only transform/opacity, short durations, honor prefers-reduced-motion; "
    "never `transition: all`.\n"
    "Apply with judgment to THIS app's purpose and any tone the operator specified. Do not add "
    "chrome the task does not need."
)


def design_directive_block(is_ui: bool) -> str:
    """Return the design directive as a prompt block, or empty for non-UI work.

    ``is_ui`` is the caller's gate decision (e.g. ``is_ui_task(task, feature)``).
    When true, returns the directive followed by a blank line so it sits cleanly
    inside the code-gen template; when false, returns ``""`` so CLI/library
    prompts carry no design noise.
    """
    if not is_ui:
        return ""
    return f"{PRODUCT_UI_DESIGN_DIRECTIVE}\n\n"
