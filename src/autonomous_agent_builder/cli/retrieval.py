"""Shared retrieval helpers for agent-friendly builder CLI surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
import re
from typing import Any, Callable


def join_query_parts(parts: list[str] | tuple[str, ...] | str) -> str:
    if isinstance(parts, str):
        return parts.strip()
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def query_terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9]{2,}", query.lower()) if term]


def compact_results_payload(
    query: str,
    items: list[dict[str, Any]],
    *,
    next_step: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "status": "ok",
        "exit_code": 0,
        "query": query,
        "count": len(items),
        "results": items,
        "schema_version": "1",
    }
    if next_step:
        payload["next"] = next_step
        payload["next_step"] = next_step
    return payload


@dataclass
class RetrievalResolution:
    item: dict[str, Any]
    matched_on: str
    suggestions: list[str]


def _coerce_text(value: Any) -> str:
    return str(value or "").strip()


def suggestion_label(item: dict[str, Any], *, id_key: str = "id", label_key: str = "title") -> str:
    item_id = _coerce_text(item.get(id_key))
    label = _coerce_text(item.get(label_key))
    if item_id and label and item_id != label:
        return f"{item_id} ({label})"
    return item_id or label


def resolve_collection_item(
    query: str,
    items: list[dict[str, Any]],
    *,
    id_keys: tuple[str, ...] = ("id",),
    text_keys: tuple[str, ...] = ("title", "name"),
    suggestion_id_key: str = "id",
    suggestion_label_key: str = "title",
) -> RetrievalResolution | None:
    lowered = query.lower().strip()
    if not lowered:
        return None
    terms = query_terms(lowered)
    ranked: list[tuple[float, str, dict[str, Any]]] = []
    suggestion_pool: list[str] = []

    for item in items:
        ids = [_coerce_text(item.get(key)) for key in id_keys]
        texts = [_coerce_text(item.get(key)) for key in text_keys]
        combined = " ".join(value.lower() for value in [*ids, *texts] if value).strip()
        if not combined:
            continue

        suggestion = suggestion_label(
            item,
            id_key=suggestion_id_key,
            label_key=suggestion_label_key,
        )
        if suggestion:
            suggestion_pool.append(suggestion)

        lowered_ids = [value.lower() for value in ids if value]
        lowered_texts = [value.lower() for value in texts if value]

        if lowered in lowered_ids:
            ranked.append((0.0, "id", item))
            continue
        if lowered in lowered_texts:
            ranked.append((0.1, "name", item))
            continue
        if any(value.startswith(lowered) for value in [*lowered_ids, *lowered_texts]):
            ranked.append((0.25, "prefix", item))
            continue
        if lowered in combined:
            ranked.append((0.5, "search", item))
            continue
        if terms and all(term in combined for term in terms):
            ranked.append((0.65, "search", item))
            continue

        best_ratio = max(
            [SequenceMatcher(a=lowered, b=value).ratio() for value in [*lowered_ids, *lowered_texts] if value],
            default=0.0,
        )
        if best_ratio >= 0.72:
            ranked.append((1.0 - best_ratio + 0.8, "fuzzy", item))

    ranked.sort(key=lambda row: row[0])
    if not ranked:
        suggestions = get_close_matches(lowered, suggestion_pool, n=3, cutoff=0.35)
        return RetrievalResolution(item={}, matched_on="", suggestions=suggestions)

    top_score, top_mode, top_item = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else None
    if top_mode in {"id", "name", "prefix"} or second_score is None or (second_score - top_score) >= 0.2:
        suggestions = [suggestion_label(item, id_key=suggestion_id_key, label_key=suggestion_label_key) for _, _, item in ranked[1:4]]
        return RetrievalResolution(item=top_item, matched_on=top_mode, suggestions=[s for s in suggestions if s])

    suggestions = [
        suggestion_label(item, id_key=suggestion_id_key, label_key=suggestion_label_key)
        for _, _, item in ranked[:3]
    ]
    return RetrievalResolution(item={}, matched_on="", suggestions=[s for s in suggestions if s])


def not_found_hint(
    query: str,
    *,
    search_command: str,
    suggestions: list[str],
) -> str:
    if suggestions:
        return f'Try {search_command}, or retry with one of: {", ".join(suggestions)}.'
    return f"Try {search_command}, then retry with the exact ID from the result."


def make_preview(
    item: dict[str, Any],
    *,
    preview_keys: tuple[str, ...] = ("summary", "description", "content"),
    max_chars: int = 160,
    transform: Callable[[str], str] | None = None,
) -> str:
    for key in preview_keys:
        value = _coerce_text(item.get(key))
        if not value:
            continue
        if transform:
            value = transform(value)
        compact = " ".join(value.split())
        return compact[:max_chars]
    return ""
