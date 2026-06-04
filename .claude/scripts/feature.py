#!/usr/bin/env python3
"""Feature list management — CRUD without reading the full JSON into context.

Usage:
    feature.py next                  # next pending (priority + deps)
    feature.py get FT-001            # get one feature
    feature.py done FT-001           # mark done, update counts
    feature.py add "title" "desc" P0 # add new feature
    feature.py list [pending|done]   # list features
    feature.py summary               # counts only
"""

import contextlib
import json
import sys
from pathlib import Path

FEATURE_FILE = Path(".claude/progress/feature-list.json")


def load():
    if not FEATURE_FILE.exists():
        print(f"Not found: {FEATURE_FILE}", file=sys.stderr)
        sys.exit(1)
    return json.loads(FEATURE_FILE.read_text(encoding="utf-8"))


def save(data):
    data["metadata"]["done"] = sum(
        1 for f in data["features"] if f["status"] == "done"
    )
    data["metadata"]["pending"] = sum(
        1 for f in data["features"] if f["status"] == "pending"
    )
    data["metadata"]["total_features"] = len(data["features"])
    FEATURE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def cmd_next(data):
    done_ids = {f["id"] for f in data["features"] if f["status"] == "done"}
    pending = [f for f in data["features"] if f["status"] == "pending"]
    ready = [
        f for f in pending
        if all(d in done_ids for d in f.get("dependencies", []))
    ]
    ready.sort(key=lambda f: f.get("priority", "P2"))
    if ready:
        print(json.dumps(ready[0], indent=2))
    else:
        print("No pending features with resolved dependencies.")
        sys.exit(1)


def cmd_get(data, feature_id):
    for f in data["features"]:
        if f["id"] == feature_id:
            print(json.dumps(f, indent=2))
            return
    print(f"Feature {feature_id} not found.", file=sys.stderr)
    sys.exit(1)


def cmd_done(data, feature_id):
    for f in data["features"]:
        if f["id"] == feature_id:
            if f["status"] == "done":
                print(f"{feature_id} is already done.")
                return
            f["status"] = "done"
            save(data)
            print(
                f"Marked {feature_id} as done. "
                f"({data['metadata']['done']} done, "
                f"{data['metadata']['pending']} pending)"
            )
            return
    print(f"Feature {feature_id} not found.", file=sys.stderr)
    sys.exit(1)


def cmd_add(data, title, description, priority="P1"):
    existing_ids = []
    for f in data["features"]:
        with contextlib.suppress(ValueError):
            existing_ids.append(int(f["id"].replace("FT-", "")))
    next_num = max(existing_ids) + 1 if existing_ids else 1
    feature = {
        "id": f"FT-{next_num:03d}",
        "title": title,
        "description": description,
        "priority": priority,
        "status": "pending",
        "acceptance_criteria": [],
        "dependencies": [],
    }
    data["features"].append(feature)
    save(data)
    print(f"Added {feature['id']}: {title} ({priority})")


def cmd_list(data, status=None):
    features = data["features"]
    if status:
        features = [f for f in features if f["status"] == status]
    for f in features:
        print(f"{f['id']}\t{f['priority']}\t{f['status']}\t{f['title']}")


def cmd_summary(data):
    done = sum(1 for f in data["features"] if f["status"] == "done")
    pending = sum(1 for f in data["features"] if f["status"] == "pending")
    total = len(data["features"])
    p0 = sum(
        1 for f in data["features"]
        if f["status"] == "pending" and f.get("priority") == "P0"
    )
    print(f"Total: {total}  Done: {done}  Pending: {pending}  P0 pending: {p0}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    data = load()

    if cmd == "next":
        cmd_next(data)
    elif cmd == "get" and len(sys.argv) >= 3:
        cmd_get(data, sys.argv[2])
    elif cmd == "done" and len(sys.argv) >= 3:
        cmd_done(data, sys.argv[2])
    elif cmd == "list":
        cmd_list(data, sys.argv[2] if len(sys.argv) >= 3 else None)
    elif cmd == "add" and len(sys.argv) >= 4:
        priority = sys.argv[4] if len(sys.argv) >= 5 else "P1"
        cmd_add(data, sys.argv[2], sys.argv[3], priority)
    elif cmd == "summary":
        cmd_summary(data)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
