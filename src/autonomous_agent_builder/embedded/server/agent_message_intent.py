"""Message-intent classifiers for embedded Agent chat turns."""

from __future__ import annotations

import re

from autonomous_agent_builder.services.voice_operator import _dashboard_route_for_target

FEATURE_SPEC_INTENT_PATTERNS = (
    "feature spec",
    "create feature",
    "add feature",
    "new feature",
    "backlog item",
    "add to backlog",
)
FEATURE_REQUEST_ACTION_PATTERNS = (
    "i want",
    "we want",
    "i need",
    "we need",
    "i would like",
    "can you add",
    "could you add",
    "please add",
    "can you build",
    "could you build",
    "can you make",
    "could you make",
    "can you implement",
    "could you implement",
    "please implement",
    "ship",
    "take this through",
    "next steps",
    "allow users to",
    "users should be able to",
    "users to be able to",
)
FEATURE_REQUEST_IMPERATIVE_PREFIXES = (
    "add ",
    "build ",
    "create ",
    "implement ",
    "make ",
)
FEATURE_REQUEST_IMPERATIVE_EXCLUSION_PREFIXES = (
    "make sure ",
)
FEATURE_REQUEST_SCOPE_TERMS = (
    "user",
    "users",
    "post",
    "posts",
    "profile",
    "feature",
    "features",
    "improvement",
    "improvements",
    "page",
    "screen",
    "view",
    "app",
    "todo",
    "todos",
    "filter",
    "filters",
    "active",
    "completed",
    "unfinished",
    "save",
    "bookmark",
    "bookmarks",
)
FEATURE_DELIVERY_CONTINUE_PATTERNS = (
    "take this through",
    "next steps",
    "go ahead and implement",
    "go ahead and build",
    "build it",
    "build this",
    "implement this",
    "ship it",
    "ship this",
    "ship next",
    "ship the next",
    "ship the next feature",
    "do it",
    "deliver this",
    "dispatch it",
    "start delivery",
    "create the delivery task",
)
NATURAL_DELIVERY_CONFIRMATION_PATTERNS = (
    "yes",
    "yes please",
    "please start",
    "start now",
    "start it now",
    "that sounds good",
    "that sounds right",
    "sounds good",
    "sounds right",
    "looks good",
    "let's do it",
    "lets do it",
)
AUTONOMOUS_CONTINUATION_PATTERNS = (
    "continue building",
    "keep building",
    "keep going",
    "continue",
    "proceed",
    "go ahead",
    "get started",
    "start now",
    "move forward",
    "start with the task",
    "start the task",
    "continue my app",
    "continue the app",
    "continue this app",
    "continue the build",
    "continue building my app",
    "build my app",
    "finish my app",
    "finish it",
    "finish this",
    "complete it",
    "complete this",
    "next useful improvement",
    "next improvement",
    "ship the next useful",
    "ship the next improvement",
    "build the next useful",
    "build the next improvement",
)
READ_ONLY_STATUS_INTENT_TOKENS = {
    "any",
    "anything",
    "status",
    "verify",
    "check",
    "confirm",
    "whether",
    "accurate",
    "prepared",
    "left",
    "remaining",
    "approval",
    "approvals",
    "approve",
}
READ_ONLY_STATUS_SCOPE_TOKENS = {
    "backlog",
    "backlogs",
    "blocked",
    "recovery",
    "recover",
    "approval",
    "approvals",
    "approve",
    "prepared",
    "status",
    "board",
    "sprint",
}
RECOVERY_ACTION_TOKENS = {
    "recover",
    "recovery",
    "retry",
    "resume",
    "rerun",
    "restart",
}
RECOVERY_SCOPE_TOKENS = {
    "agent",
    "board",
    "blocked",
    "failed",
    "failure",
    "run",
    "task",
    "work",
}
DASHBOARD_NAVIGATION_MARKERS = (
    "go to",
    "go back to",
    "take me to",
    "open",
    "show me",
    "show",
    "switch to",
    "navigate to",
)
DASHBOARD_NAVIGATION_QUESTION_PREFIXES = (
    "why ",
    "how ",
    "what ",
    "what's ",
    "whats ",
    "which ",
    "where ",
    "when ",
)
AGENT_EVIDENCE_REQUEST_PATTERNS = (
    "diagnose",
    "diagnosis",
    "investigate",
    "deterministic checks",
    "checks and build",
    "verifier evidence",
    "shippable",
    "failing command",
    "failing gate",
    "exact failing",
    "exact command",
    "command or gate",
    "likely owner",
    "owning surface",
    "root cause",
    "builder evidence beyond",
    "beyond the board",
    "next safe recovery",
    "bounded recovery",
    "recovery plan",
    "recovery step",
    "safe operator plan",
    "classify the issue",
    "proposed steps",
    "approval would be needed",
)
AMBIGUOUS_CONTINUATION_PATTERNS = (
    "continue",
    "proceed",
    "go ahead",
    "get started",
    "start with the task",
    "start the task",
)
DELIVERY_PROGRESS_ACTION_TOKENS = {
    "continue",
    "proceed",
    "start",
    "plan",
    "build",
    "ship",
    "deliver",
    "implement",
    "execute",
    "queue",
    "finish",
    "complete",
    "advance",
    "move",
    "resume",
    "work",
}
DELIVERY_PROGRESS_SCOPE_TOKENS = {
    "next",
    "sprint",
    "backlog",
    "feature",
    "improvement",
    "item",
    "task",
    "app",
    "product",
    "work",
}
SPRINT_PLANNING_INTENT_PATTERNS = (
    "sprint planning",
    "start next sprint",
    "start the next sprint",
    "start a new sprint",
    "start new sprint",
    "plan the sprint",
    "plan sprint",
    "plan next sprint",
    "plan the next sprint",
    "queue the sprint",
    "queue these backlog items",
    "queue all backlog items",
    "queue all current backlog items",
    "queue all current product backlog items",
    "queue all product backlog items",
    "queue current backlog",
    "queue current product backlog",
    "move to sprint backlog",
)
SPRINT_PLANNING_ALL_PATTERNS = (
    "all",
    "everything",
    "all current product backlog items",
    "all product backlog items",
    "entire product backlog",
    "current backlog",
)
SPRINT_PLANNING_SELECTION_PROMPT = (
    "Delivery is ready. Reply with `all` to ship every ready improvement, "
    "or reply with one or more improvement IDs/titles."
)


def normalize_planning_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def operator_visible_feature_scope_text(text: str) -> str:
    visible = text.strip()
    if visible.upper().startswith("AGREEMENT:"):
        visible = visible.split(":", 1)[1].strip()
    elif visible.upper() == "AGREEMENT":
        visible = ""
    return visible


def message_requests_feature_spec(user_message: str) -> bool:
    lower_message = user_message.lower()
    normalized_message = " ".join(lower_message.split())
    if "documentation" in lower_message or "feature doc" in lower_message:
        return False
    if any(pattern in lower_message for pattern in FEATURE_SPEC_INTENT_PATTERNS):
        return True
    imperative_feature_request = (
        any(
            normalized_message.startswith(pattern)
            for pattern in FEATURE_REQUEST_IMPERATIVE_PREFIXES
        )
        and not any(
            normalized_message.startswith(pattern)
            for pattern in FEATURE_REQUEST_IMPERATIVE_EXCLUSION_PREFIXES
        )
    )
    if not imperative_feature_request and not any(
        pattern in lower_message for pattern in FEATURE_REQUEST_ACTION_PATTERNS
    ):
        return False
    return any(term in lower_message for term in FEATURE_REQUEST_SCOPE_TERMS)


def message_requires_agent_evidence(user_message: str) -> bool:
    lower_message = " ".join(user_message.lower().split())
    return any(pattern in lower_message for pattern in AGENT_EVIDENCE_REQUEST_PATTERNS)


def message_requests_feature_delivery(user_message: str) -> bool:
    lower_message = user_message.lower()
    if message_requires_agent_evidence(user_message):
        return False
    if "documentation" in lower_message or "feature doc" in lower_message:
        return False
    if any(pattern in lower_message for pattern in FEATURE_DELIVERY_CONTINUE_PATTERNS):
        return True
    if message_requests_feature_spec(user_message):
        return False
    if any(pattern in lower_message for pattern in FEATURE_SPEC_INTENT_PATTERNS):
        return False
    if not any(pattern in lower_message for pattern in FEATURE_REQUEST_ACTION_PATTERNS):
        return False
    return any(term in lower_message for term in FEATURE_REQUEST_SCOPE_TERMS)


def message_confirms_feature_delivery(user_message: str) -> bool:
    normalized = normalize_planning_token(user_message)
    if not normalized:
        return False
    if normalized in NATURAL_DELIVERY_CONFIRMATION_PATTERNS:
        return True
    return bool(
        re.search(r"\b(yes|please|sure|ok|okay)\b", normalized)
        and re.search(r"\b(start|plan|build|ship|do|deliver|continue|proceed)\b", normalized)
    )


def message_requests_autonomous_continuation(user_message: str) -> bool:
    if message_requires_agent_evidence(user_message):
        return False
    lower_message = user_message.lower()
    if "documentation" in lower_message or "feature doc" in lower_message:
        return False
    if message_requests_read_only_status(user_message):
        return False
    if any(pattern in lower_message for pattern in AUTONOMOUS_CONTINUATION_PATTERNS):
        return True
    if message_requests_feature_spec(user_message):
        return False
    tokens = set(normalize_planning_token(user_message).split())
    if not tokens:
        return False
    return bool(
        tokens & DELIVERY_PROGRESS_ACTION_TOKENS and tokens & DELIVERY_PROGRESS_SCOPE_TOKENS
    )


def message_requests_read_only_status(user_message: str) -> bool:
    if message_requires_agent_evidence(user_message):
        return False
    tokens = set(normalize_planning_token(user_message).split())
    if not tokens:
        return False
    return bool(tokens & READ_ONLY_STATUS_INTENT_TOKENS) and bool(
        tokens & READ_ONLY_STATUS_SCOPE_TOKENS
    )


def message_requests_recovery_preflight(user_message: str) -> bool:
    if message_requires_agent_evidence(user_message):
        return False
    tokens = set(normalize_planning_token(user_message).split())
    if not tokens:
        return False
    return bool(tokens & RECOVERY_ACTION_TOKENS) and bool(tokens & RECOVERY_SCOPE_TOKENS)


def message_requests_recovery_continuation(user_message: str) -> bool:
    if not message_requests_autonomous_continuation(user_message):
        return False
    tokens = set(normalize_planning_token(user_message).split())
    return bool(tokens & RECOVERY_ACTION_TOKENS)


def dashboard_navigation_route_from_message(user_message: str) -> str:
    normalized = " ".join(user_message.lower().replace("?", " ").split())
    if not normalized:
        return ""
    if normalized.startswith(DASHBOARD_NAVIGATION_QUESTION_PREFIXES):
        return ""
    marker_matches = [
        re.search(rf"\b{re.escape(marker)}\b", normalized)
        for marker in DASHBOARD_NAVIGATION_MARKERS
    ]
    if not any(marker_matches):
        return ""
    if any(
        word in normalized for word in ("status", "state", "count", "counts", "left", "remaining")
    ):
        return ""
    return _dashboard_route_for_target(normalized)


def dashboard_navigation_label(route: str) -> str:
    path = route.split("?", 1)[0].strip("/") or "Agent"
    if path == "observability":
        return "Observability"
    return path.replace("-", " ").title()


def message_requests_ambiguous_continuation(user_message: str) -> bool:
    normalized = normalize_planning_token(user_message)
    if not normalized:
        return False
    if normalized in AMBIGUOUS_CONTINUATION_PATTERNS:
        return True
    filler_tokens = {
        "can",
        "could",
        "you",
        "please",
        "now",
        "the",
        "with",
        "task",
        "ahead",
        "go",
        "start",
        "get",
        "started",
        "proceed",
        "continue",
    }
    tokens = set(normalized.split())
    return bool(tokens) and tokens <= filler_tokens


def message_requests_sprint_planning(user_message: str) -> bool:
    lower_message = user_message.lower()
    if any(pattern in lower_message for pattern in SPRINT_PLANNING_INTENT_PATTERNS):
        return True
    return (
        re.search(r"\bsprint\s+\d+\s+planning\b", lower_message) is not None
        or re.search(r"\bplan\s+sprint\s+\d+\b", lower_message) is not None
    )


def message_requests_delivery_lifecycle(user_message: str) -> bool:
    return (
        message_requests_autonomous_continuation(user_message)
        or message_requests_sprint_planning(user_message)
        or message_requests_feature_delivery(user_message)
    )


def message_selects_all_sprint_items(user_message: str) -> bool:
    normalized = normalize_planning_token(user_message)
    if not normalized:
        return False
    if normalized in SPRINT_PLANNING_ALL_PATTERNS:
        return True
    return bool(re.search(r"\ball\b", normalized)) and "backlog" in normalized
