"""Deterministic CI planning for canonical-branch documentation freshness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

ACTIONABLE_STATUSES = {"stale", "migration_needed"}


@dataclass(frozen=True)
class ActionableDoc:
    doc_id: str
    doc_type: str
    canonical_ref: str
    stale_reason: str
    owned_paths: tuple[str, ...]
    matched_changed_paths: tuple[str, ...]
    documented_against_commit: str
    current_main_commit: str


@dataclass(frozen=True)
class DocumentationFreshnessPlan:
    mode: str
    summary: str
    prompt: str
    actionable_docs: tuple[ActionableDoc, ...]
    manual_attention_reasons: tuple[str, ...]


def prepare_documentation_freshness_plan(
    validation_payload: dict[str, Any],
    *,
    workspace_path: str | Path = ".",
) -> DocumentationFreshnessPlan:
    checks = validation_payload.get("checks")
    failed_checks = (
        tuple(
            str(item.get("name", "")).strip()
            for item in checks
            if isinstance(item, dict) and not bool(item.get("passed", False))
        )
        if isinstance(checks, list)
        else tuple()
    )

    actionable_docs: list[ActionableDoc] = []
    blocked_reasons: list[str] = []
    freshness_report = validation_payload.get("freshness_report")
    if isinstance(freshness_report, list):
        for item in freshness_report:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "") or "").strip()
            blocking = bool(item.get("blocking", False))
            doc_id = str(item.get("doc_id", "") or "").strip()
            if not doc_id or not blocking:
                continue
            if status == "blocked":
                blocked_reason = str(item.get("stale_reason", "") or "").strip()
                blocked_reasons.append(f"{doc_id}: {blocked_reason}")
                continue
            if status not in ACTIONABLE_STATUSES:
                continue
            stale_reason = str(item.get("stale_reason", "") or "").strip()
            canonical_ref = str(item.get("canonical_ref", "") or "").strip() or "main"
            documented_against_commit = str(
                item.get("documented_against_commit", "") or ""
            ).strip()
            current_main_commit = str(item.get("current_main_commit", "") or "").strip()
            actionable_docs.append(
                ActionableDoc(
                    doc_id=doc_id,
                    doc_type=str(item.get("doc_type", "") or "").strip(),
                    canonical_ref=canonical_ref,
                    stale_reason=stale_reason,
                    owned_paths=tuple(_normalize_paths(item.get("owned_paths"))),
                    matched_changed_paths=tuple(
                        _normalize_paths(item.get("matched_changed_paths"))
                    ),
                    documented_against_commit=documented_against_commit,
                    current_main_commit=current_main_commit,
                )
            )

    if bool(validation_payload.get("passed", False)):
        return DocumentationFreshnessPlan(
            mode="no_op",
            summary=str(
                validation_payload.get("summary", "") or "Knowledge validation already passed."
            ),
            prompt="",
            actionable_docs=tuple(),
            manual_attention_reasons=tuple(),
        )

    manual_attention_reasons: list[str] = []
    if blocked_reasons:
        manual_attention_reasons.extend(blocked_reasons)

    non_freshness_failures = tuple(name for name in failed_checks if name and name != "freshness")
    if non_freshness_failures:
        manual_attention_reasons.append(
            "non-freshness validation failures require human review: "
            + ", ".join(sorted(set(non_freshness_failures)))
        )

    if manual_attention_reasons:
        return DocumentationFreshnessPlan(
            mode="manual_attention",
            summary=(
                "Deterministic validation found issues outside the bounded "
                "documentation-refresh lane."
            ),
            prompt="",
            actionable_docs=tuple(actionable_docs),
            manual_attention_reasons=tuple(manual_attention_reasons),
        )

    if not actionable_docs:
        return DocumentationFreshnessPlan(
            mode="manual_attention",
            summary=(
                "Deterministic validation failed, but no actionable maintained-doc "
                "freshness targets were found."
            ),
            prompt="",
            actionable_docs=tuple(),
            manual_attention_reasons=(
                "validation failed without actionable stale maintained docs",
            ),
        )

    prompt = _build_prompt(
        workspace_path=Path(workspace_path),
        validation_payload=validation_payload,
        actionable_docs=tuple(actionable_docs),
    )
    doc_ids = ", ".join(doc.doc_id for doc in actionable_docs)
    return DocumentationFreshnessPlan(
        mode="run_agent",
        summary=f"Refresh maintained docs via canonical builder surfaces: {doc_ids}",
        prompt=prompt,
        actionable_docs=tuple(actionable_docs),
        manual_attention_reasons=tuple(),
    )


def _build_prompt(
    *,
    workspace_path: Path,
    validation_payload: dict[str, Any],
    actionable_docs: tuple[ActionableDoc, ...],
) -> str:
    summary = str(validation_payload.get("summary", "") or "").strip()
    lines = [
        "You are the bounded documentation freshness automation for this repository.",
        "",
        "Trigger context:",
        "- This run started after a push to main.",
        f"- Repository path: {workspace_path.resolve()}",
        (
            "- Deterministic validation summary: "
            f"{summary or 'Knowledge validation failed on freshness.'}"
        ),
        "",
        "Non-negotiable rules:",
        "- Use `builder knowledge validate --json` as the authoritative freshness gate.",
        "- Refresh only the maintained docs listed below.",
        (
            "- Use canonical builder KB surfaces through Bash commands such as "
            "`builder knowledge show`, `builder knowledge update`, and "
            "`builder knowledge add`."
        ),
        "- Do not edit `.agent-builder/knowledge` files directly.",
        "- Do not modify repo docs under `docs/`, code, memory, or unrelated surfaces.",
        (
            "- For every maintained doc you refresh, stamp "
            "`documented_against_commit` with the current canonical commit, "
            "`documented_against_ref=<canonical_ref>`, and the listed `owned_paths`."
        ),
        "- Keep retrieval bounded to the listed docs and their owned paths.",
        (
            "- After updates, rerun `builder knowledge validate --json` and stop "
            "if freshness still fails."
        ),
        "",
        "Actionable maintained docs:",
    ]

    for doc in actionable_docs:
        lines.extend(
            [
                f"- doc_id: {doc.doc_id}",
                f"  doc_type: {doc.doc_type or 'unknown'}",
                f"  canonical_ref: {doc.canonical_ref}",
                f"  stale_reason: {doc.stale_reason or 'missing'}",
                (
                    "  documented_against_commit: "
                    f"{doc.documented_against_commit or 'missing'}"
                ),
                f"  current_main_commit: {doc.current_main_commit or 'unresolved'}",
                f"  owned_paths: {', '.join(doc.owned_paths) if doc.owned_paths else 'missing'}",
                (
                    "  matched_changed_paths: "
                    f"{_format_path_list(doc.matched_changed_paths, fallback='none')}"
                ),
            ]
        )

    lines.extend(
        [
            "",
            "Required execution loop:",
            "1. Inspect each targeted doc with `builder knowledge show <doc_id>`.",
            (
                "2. Refresh only the listed stale docs through canonical "
                "`builder knowledge` mutation commands."
            ),
            "3. Re-run `builder knowledge validate --json`.",
            "4. If validation passes, stop without touching unrelated docs.",
            (
                "5. If validation still fails for reasons outside these listed "
                "docs, stop and explain the exact remaining gap."
            ),
            "",
            "Return a short final summary suitable for a CI transcript.",
        ]
    )
    return "\n".join(lines).strip()


def _normalize_paths(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        items = []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip().replace("\\", "/").strip("/")
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _format_path_list(paths: tuple[str, ...], *, fallback: str) -> str:
    if not paths:
        return fallback
    return ", ".join(paths)
