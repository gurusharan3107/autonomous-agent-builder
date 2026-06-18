# /status open

Open the operator-facing goal overview in a browser. WSL-aware (plain `xdg-open`
silently fails on WSL2 — must route through the Windows host).

```bash
f=docs/goal/goal-overview.html
if grep -qi microsoft /proc/version 2>/dev/null; then
  win=$(wslpath -w "$f")
  # Pick exactly ONE opener by availability — never chain on exit code:
  # explorer.exe returns rc=1 even on success, so `||` would fire a 2nd opener.
  if command -v explorer.exe >/dev/null 2>&1; then
    explorer.exe "$win" 2>/dev/null || true
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$win" 2>/dev/null || true
  else
    powershell.exe -NoProfile -Command "Start-Process '$win'" 2>/dev/null || true
  fi
else
  xdg-open "$f" >/dev/null 2>&1 &
fi
```

Report the path. `explorer.exe` returns rc=1 even on success, so the opener is
chosen by `command -v` availability, not exit code — chaining with `||` would
open the page twice. If no opener works (truly headless), print the absolute path
for the operator. Does **not** refresh the page — run `/status update` first for current numbers.
