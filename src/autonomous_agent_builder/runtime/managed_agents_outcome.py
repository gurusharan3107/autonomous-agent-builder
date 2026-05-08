"""Build `user.define_outcome` rubrics from builder feature data.

Phase D wiring: when the orchestrator's feature-verifier branch runs on
the claude_managed lane, it constructs an outcome from the Feature's
acceptance_criteria. This module owns the synthesis so the rubric format
stays consistent across roles and the orchestrator stays small.

Per MA outcomes docs: rubric criteria should be explicit and
independently gradeable. Vague criteria produce noisy iterate loops.
The synthesis below preserves the criterion text verbatim — it does NOT
try to rewrite for clarity. If the user's acceptance_criteria are
unclear, the grader will flag `failed` or `max_iterations_reached` and
the orchestrator surfaces that to the user; auto-cleanup would mask
the signal.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureOutcome:
    """A complete `user.define_outcome` payload synthesised for a feature."""

    description: str
    rubric: str
    max_iterations: int

    def as_event_payload(self) -> dict[str, object]:
        """Return the dict shape `client.beta.sessions.events.send` expects."""
        return {
            "type": "user.define_outcome",
            "description": self.description,
            "rubric": {"type": "text", "content": self.rubric},
            "max_iterations": self.max_iterations,
        }


def build_feature_outcome(
    *,
    feature_title: str,
    feature_description: str,
    acceptance_criteria: Sequence[str],
    max_iterations_cap: int = 5,
) -> FeatureOutcome:
    """Synthesise an outcome payload from builder Feature fields.

    Args:
        feature_title: Feature.title
        feature_description: Feature.description (free-text — what done means)
        acceptance_criteria: Feature.acceptance_criteria list (each entry
            becomes one rubric line)
        max_iterations_cap: orchestrator's gate.max_retries upper bound;
            actual iterations = `min(len(acceptance_criteria), cap)` so a
            feature with 2 criteria doesn't burn 5 grader passes.

    Behavior on missing inputs:
        - Empty acceptance_criteria: rubric body = "(none provided)" and
          max_iterations = 1. The grader will mark this `failed` quickly,
          which is the right signal — features without criteria can't be
          rubric-graded.

    The returned payload is suitable for `ManagedAgentsRuntime.run_outcome`.
    """
    description = (
        f"{feature_title}\n\n{feature_description.strip()}".strip()
        if feature_description
        else feature_title
    )

    cleaned_criteria = [c.strip() for c in acceptance_criteria if c and c.strip()]
    if cleaned_criteria:
        rubric_lines = [
            f"{i + 1}. {criterion}" for i, criterion in enumerate(cleaned_criteria)
        ]
        rubric_body = (
            "Each numbered criterion must be independently met for the "
            "outcome to be satisfied:\n\n" + "\n".join(rubric_lines)
        )
        max_iter = max(1, min(len(cleaned_criteria), max_iterations_cap))
    else:
        rubric_body = (
            "Acceptance criteria: (none provided). Mark the outcome as "
            "failed — features without explicit criteria cannot be "
            "rubric-graded; the orchestrator should surface this to the "
            "user before retrying."
        )
        max_iter = 1

    return FeatureOutcome(
        description=description,
        rubric=rubric_body,
        max_iterations=max_iter,
    )
