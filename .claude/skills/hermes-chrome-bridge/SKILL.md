---
name: hermes-chrome-bridge
description: Install the Hermes Chrome Bridge — creates the plugin folder, wires native messaging, and creates the hermes-chrome operate skill. Run once per machine.
version: 0.3.0
author: Hermes Agent
license: MIT
platforms: [macos, wsl2]
metadata:
  hermes:
    tags: [browser, chrome, install, setup]
    category: setup
---

# Hermes Chrome Bridge — Install Skill

Installs the `hermes_chrome` plugin, wires native messaging for the current
platform (macOS or WSL2), and writes the `hermes-chrome` operate skill to
`~/.claude/skills/hermes-chrome/SKILL.md`.

---

## Step 0 — Check if already installed

```bash
python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('127.0.0.1', 9797)); print('INSTALLED'); s.close()
except: print('NOT_INSTALLED')
"
```

If `INSTALLED` → skip to Step 4 (verify), then exit.

---

## Step 1 — Locate plugin source and install destination

```bash
python3 - << 'EOF'
import subprocess, sys
from pathlib import Path

# Source: plugin files ship alongside this skill in the repo
# Walk up from this skill's known relative position to find the repo root
# then locate .claude/plugin/hermes_chrome/
skill_dir = Path(__file__).resolve().parent if '__file__' in dir() else Path.cwd()

# Try to find plugin source relative to CWD or common repo paths
candidates = [
    Path.cwd() / ".claude/plugin/hermes_chrome",
    Path.home() / "code" / ".claude/plugin/hermes_chrome",
]
src = next((c for c in candidates if c.exists()), None)
if src:
    print(f"PLUGIN_SRC={src}")
else:
    print("PLUGIN_SRC=NOT_FOUND")
EOF
```

If `PLUGIN_SRC=NOT_FOUND`, ask the user for the path to the `hermes_chrome` plugin source folder.

---

## Step 2 — Install plugin globally

Copy the plugin to `~/.claude/plugin/hermes_chrome/` so the
`hermes_chrome_browser` tool is available in every project and session:

```bash
PLUGIN_SRC="<path from Step 1>"
GLOBAL_PLUGIN="$HOME/.claude/plugin/hermes_chrome"

mkdir -p "$GLOBAL_PLUGIN"
rsync -a --exclude='*.Zone.Identifier' --exclude='scripts/' \
  "$PLUGIN_SRC/" "$GLOBAL_PLUGIN/"
echo "Plugin installed at $GLOBAL_PLUGIN"
```

---

## Step 3 — Wire native messaging (platform-specific)

### 3a. Install runtime

```bash
python3 .claude/plugin/hermes_chrome/scripts/install_hermes_chrome_bridge.py --install-runtime
```

Read the `next_step` field in the JSON output — it contains the exact path to load in Chrome.

### 3b. Load the extension in Chrome

Tell the user:

> Open **chrome://extensions**, enable **Developer mode**, click **Load unpacked**,
> and select the path shown in `next_step` above.
> Copy the **extension ID** (32-character string under the extension name).

Use `AskUserQuestion` to collect the extension ID.

### 3c. Install native manifest

```bash
python3 .claude/plugin/hermes_chrome/scripts/install_hermes_chrome_bridge.py --extension-id <id from user>
```

### 3d. Sync and reload

```bash
.claude/plugin/hermes_chrome/scripts/sync.sh
```

Confirm output ends with `Bridge ready`.

---

## Step 4 — Create the operate skill

Write the `hermes-chrome` operate skill to `~/.claude/skills/hermes-chrome/SKILL.md`
so it is globally available in all sessions:

```bash
mkdir -p ~/.claude/skills/hermes-chrome
```

Then write the following content to `~/.claude/skills/hermes-chrome/SKILL.md`:

```markdown
---
name: hermes-chrome
description: Operate Chrome through the Hermes bridge — navigate, click with visible cursor, screenshot, read page. Requires hermes-chrome-bridge installed.
version: 0.2.0
platforms: [macos, wsl2]
---

# Hermes Chrome — Operate Skill

Controls the user's Chrome profile via the Hermes bridge (TCP 127.0.0.1:9797).
Use for authenticated pages, real browser state, and visible cursor interaction.

## Before every session

TCP probe (~100ms):

\`\`\`python
import socket, json

def bridge(payload, timeout=20):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(("127.0.0.1", 9797))
    s.sendall(json.dumps(payload).encode())
    s.shutdown(socket.SHUT_WR)
    chunks = []
    while True:
        chunk = s.recv(65536)
        if not chunk: break
        chunks.append(chunk)
    s.close()
    return json.loads(b"".join(chunks))

r = bridge({"type": "status", "timeoutSeconds": 5})
# success:true → ready. ConnectionRefusedError → run hermes-chrome-bridge first.
\`\`\`

## Progressive disclosure — always start here

| Level | Action | Size | Use when |
|-------|--------|------|----------|
| 1 | `page_context` | ~1KB | First look — URL, nav, buttons, inputs |
| 2 | `text` | 2–4KB | Read content; includes URL + title |
| 3 | `snapshot` | 3–8KB | Find selectors; interactive elements only |
| 4 | `evaluate` | varies | Arbitrary JS — last resort |

**Start with `page_context`. Escalate only if needed.**

## Call shape

\`\`\`python
r = bridge({
    "type": "run",
    "sessionName": "task-name",
    "useSelectedTab": True,   # control current tab; omit for managed tab
    "actions": [ ... ]
})
\`\`\`

## Action reference

\`\`\`python
# Level 1 — compact overview
{"type": "page_context"}
# → {url, title, headings, nav:[{text,href}], buttons:[str], inputs:[{name,type,value}]}

# Level 2 — full text
{"type": "text"}
# → {url, title, text}

# Level 3 — interactive element list (no div/span duplication)
{"type": "snapshot"}
# → {url, title, element_count, snapshot:[{i,tag,role,text,href,value?,input_type?,name?}]}

# Navigate
{"type": "goto", "url": "https://example.com"}

# Click by visible text — animates cursor
{"type": "click_text", "text": "Submit"}

# Click by CSS selector — animates cursor
{"type": "click_selector", "selector": "#submit-btn"}

# Fill a field
{"type": "fill_selector", "selector": "#email", "value": "user@example.com"}

# Screenshot (JPEG, always under 1MB limit)
{"type": "screenshot"}
# → {format:"jpeg", screenshot_path:"/wsl-or-macos/path/to/file.jpeg"}

# Wait
{"type": "wait", "ms": 500}

# Evaluate JS
{"type": "evaluate", "expression": "document.title"}

# Close managed tab
{"type": "close_tab"}
\`\`\`

## Common patterns

\`\`\`python
# Page audit
actions=[{"type":"page_context"}, {"type":"screenshot"}]

# Navigate + confirm
actions=[
    {"type":"goto","url":"https://app.example.com"},
    {"type":"page_context"}
]

# Click + verify
actions=[
    {"type":"click_text","text":"Sign in"},
    {"type":"wait","ms":800},
    {"type":"page_context"}
]

# Fill form + submit
actions=[
    {"type":"fill_selector","selector":"#email","value":"user@example.com"},
    {"type":"fill_selector","selector":"#password","value":"secret"},
    {"type":"click_text","text":"Sign in"},
    {"type":"wait","ms":1000},
    {"type":"page_context"}
]
\`\`\`

## Efficiency rules

- One `run` call per task — batch all actions together.
- `page_context` first; escalate to `snapshot` only if you need selectors.
- One state check after click/fill is enough.
- `screenshot` only when visual layout matters.
- Do not retry a failed selector — get a fresh `snapshot` first.

## Ongoing changes

Edit in `.claude/plugin/hermes_chrome/`, then:
\`\`\`bash
.claude/plugin/hermes_chrome/scripts/sync.sh
\`\`\`

## Pitfalls

- Do not read cookies, passwords, or local storage.
- `file://` URLs need Chrome file-access enabled — serve via `http://` instead.
- `ContentScript did not respond` → auto-recovers on next call.
- `ConnectionRefusedError` → Chrome extension not loaded; run `hermes-chrome-bridge`.
```

---

## Step 5 — Verify end-to-end

```bash
python3 - << 'EOF'
import socket, json

def bridge(payload, timeout=10):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(("127.0.0.1", 9797))
    s.sendall(json.dumps(payload).encode())
    s.shutdown(socket.SHUT_WR)
    chunks = []
    while True:
        chunk = s.recv(65536)
        if not chunk: break
        chunks.append(chunk)
    s.close()
    return json.loads(b"".join(chunks))

r = bridge({"type": "status", "timeoutSeconds": 5})
if r.get("success"):
    tab = r.get("active_tab", {})
    print(f"OK  bridge=127.0.0.1:9797  tab={tab.get('url','unknown')}")
    print("hermes-chrome skill is ready to use.")
else:
    print(f"FAIL  {r.get('error')}")
EOF
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `PLUGIN_SRC=NOT_FOUND` | Ask user for repo path or clone it |
| `Bridge did not reconnect` | Reload extension manually in `chrome://extensions` |
| Wrong extension ID | Re-copy from `chrome://extensions` — the 32-char string under the name |
| macOS: `operation not permitted` | `chmod +x ~/.hermes/chrome-bridge/native/native_host.py` |
| WSL2: registry error | Run the install script from your normal user shell, not elevated |
