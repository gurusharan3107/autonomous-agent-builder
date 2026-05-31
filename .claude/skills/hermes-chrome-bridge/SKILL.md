---
name: hermes-chrome-bridge
description: >
  Install the Hermes Chrome Bridge — deploys the hermes_chrome plugin
  (extension + native host) from the repo, wires native messaging for the
  current platform (macOS or WSL2), and installs the hermes-chrome operate
  skill globally. Run once per machine. Triggers: "install hermes chrome",
  "set up the chrome bridge", "set up hermes-chrome", "wire native messaging",
  "bootstrap the browser bridge".
version: 0.4.0
author: Hermes Agent
license: MIT
platforms: [macos, wsl2]
allowed-tools: Bash, Read, Write, Edit
metadata:
  hermes:
    tags: [browser, chrome, install, setup]
    category: setup
---

# Hermes Chrome Bridge — Install Skill

Bootstraps the three-part system from the repo as the single source of truth:

| Piece | Installed to | Role |
|---|---|---|
| `hermes_chrome` plugin | `~/.claude/plugin/hermes_chrome/` + platform extension/native paths | extension, native host, `hermes_chrome_browser` tool |
| `hermes-chrome` operate skill | `~/.claude/skills/hermes-chrome/` | daily Chrome operation |
| native messaging | platform manifest + (WSL2) registry | links Chrome ↔ native host |

Transport is a **Unix socket** at `~/.hermes/run/chrome-bridge.sock` (not TCP).
**Extension bridge only — no CDP.** `cdp_bridge.py` is banned by the operate
skill's hard rules; this installer never ships it and strips any stale copy.

All deployment goes through the repo's own scripts under
`.claude/plugin/hermes_chrome/scripts/` so this skill never reimplements (and
drifts from) the canonical install logic.

---

## Step 0 — Already installed?

Probe the Unix socket (~100 ms):

```bash
python3 - << 'EOF'
import socket, json, os
sock = os.path.expanduser("~/.hermes/run/chrome-bridge.sock")
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(2)
try:
    s.connect(sock)
    s.sendall(json.dumps({"type": "status", "timeoutSeconds": 3}).encode())
    s.shutdown(socket.SHUT_WR)
    data = b""
    while True:
        c = s.recv(65536)
        if not c: break
        data += c
    r = json.loads(data or b"{}")
    print("INSTALLED" if r.get("success") else "BRIDGE_DOWN")
except FileNotFoundError:
    print("NOT_INSTALLED")
except Exception:
    print("BRIDGE_DOWN")
finally:
    s.close()
EOF
```

- `INSTALLED` → skip to Step 6 (operate skill) then Step 7 (verify).
- `BRIDGE_DOWN` → files exist but Chrome/extension is idle; run `sync.sh` (Step 5) then verify.
- `NOT_INSTALLED` → full install from Step 1.

---

## Step 1 — Locate the repo plugin + skill source

```bash
python3 - << 'EOF'
from pathlib import Path
candidates = [
    Path.cwd(),
    Path.home() / "code" / "autonomous-agent-builder-codex-architecture-review"
        / "autonomous-agent-builder-codex-architecture-review",
]
for root in candidates:
    plug = root / ".claude/plugin/hermes_chrome"
    skill = root / ".claude/skills/hermes-chrome"
    if plug.exists() and skill.exists():
        print(f"REPO_ROOT={root}")
        print(f"PLUGIN_SRC={plug}")
        print(f"SKILL_SRC={skill}")
        break
else:
    print("REPO_ROOT=NOT_FOUND")
EOF
```

If `NOT_FOUND`, ask the user for the repo path (must contain both
`.claude/plugin/hermes_chrome/` and `.claude/skills/hermes-chrome/`).

---

## Step 2 — Install the native runtime (extension + native host)

Deploys the unpacked extension and native host to the platform install
location and prints the exact Chrome load path:

```bash
python3 "$PLUGIN_SRC/scripts/install_hermes_chrome_bridge.py" --install-runtime
```

Read the `next_step` field in the JSON output — it is the absolute path to load
in Chrome.

---

## Step 3 — Load the extension + capture its ID

Tell the user:

> Open **chrome://extensions**, enable **Developer mode**, click **Load unpacked**,
> and select the path shown in `next_step` above.
> Then copy the **extension ID** — the 32-character string under the extension name.

Use `AskUserQuestion` to collect the extension ID.

---

## Step 4 — Wire native messaging

Writes the native messaging manifest (and, on WSL2, the Windows registry key)
that authorizes that extension ID to reach the native host:

```bash
python3 "$PLUGIN_SRC/scripts/install_hermes_chrome_bridge.py" --extension-id <id from user>
```

---

## Step 5 — Deploy the global plugin + hot-reload

`sync.sh` is the canonical deployer: it installs the global plugin (making the
`hermes_chrome_browser` tool available in every session), re-syncs the extension
and native host, and hot-reloads Chrome over the Unix socket.

```bash
"$PLUGIN_SRC/scripts/sync.sh"
```

Wait for output ending in `Bridge ready — <url>`. If it reports
`Bridge did not reconnect`, reload the extension manually in
`chrome://extensions`, then re-run `sync.sh`.

Then strip any stale banned file from the global plugin (the operate skill
forbids `cdp_bridge.py`):

```bash
rm -f "$HOME/.claude/plugin/hermes_chrome/cdp_bridge.py" && echo "cleaned cdp_bridge.py"
```

---

## Step 6 — Install the operate skill (copy from repo, verbatim)

The operate skill is multi-file (`SKILL.md` + `references/` + `scripts/`). Copy
the repo tree as-is so the global copy stays a faithful mirror — do **not**
inline or hand-edit it here:

```bash
DST="$HOME/.claude/skills/hermes-chrome"
mkdir -p "$DST"
rsync -a --delete \
  --exclude='*.Zone.Identifier' --exclude='__pycache__/' --exclude='evals/' \
  "$SKILL_SRC/" "$DST/"
echo "operate skill installed at $DST"
ls "$DST" "$DST/references"
```

Expect `SKILL.md`, `references/{operate,optimize,best-practices,agent-handbook}.md`,
and `scripts/validate.sh`.

---

## Step 7 — Verify end-to-end

```bash
python3 - << 'EOF'
import socket, json, os
sock = os.path.expanduser("~/.hermes/run/chrome-bridge.sock")
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(10)
try:
    s.connect(sock)
    s.sendall(json.dumps({"type": "status", "timeoutSeconds": 5}).encode())
    s.shutdown(socket.SHUT_WR)
    data = b""
    while True:
        c = s.recv(65536)
        if not c: break
        data += c
    r = json.loads(data or b"{}")
    if r.get("success"):
        tab = r.get("active_tab", {})
        print(f"OK  socket={sock}  tab={tab.get('url','unknown')}")
        print("hermes-chrome skill is ready to use.")
    else:
        print(f"FAIL  {r.get('error')}")
finally:
    s.close()
EOF
```

Then run the operate skill's own preflight as the final gate:

```bash
bash "$HOME/.claude/plugin/hermes_chrome/scripts/preflight.sh"
```

Both green → installed. Hand control to the `hermes-chrome` operate skill.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `REPO_ROOT=NOT_FOUND` | Ask user for the repo path containing `.claude/plugin/hermes_chrome` + `.claude/skills/hermes-chrome` |
| `next_step` path missing | Re-run Step 2; ensure `--install-runtime` exited with `"success": true` |
| `Bridge did not reconnect` | Reload the extension in `chrome://extensions`, re-run `sync.sh` |
| Wrong extension ID | Re-copy the 32-char ID under the name in `chrome://extensions`, re-run Step 4 |
| macOS: `operation not permitted` | `chmod +x ~/.hermes/chrome-bridge/native/native_host.py` |
| WSL2: registry error | Run Step 4 from your normal user shell, not elevated |
| Socket probe `FileNotFoundError` | Extension not loaded or Chrome closed; complete Steps 3–5 |
