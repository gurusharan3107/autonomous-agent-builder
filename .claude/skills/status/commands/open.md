# /status open

Open the operator-facing goal overview in a browser. WSL-aware (plain `xdg-open`
silently fails on WSL2 — must route through the Windows host).

```bash
f=docs/goal/goal-overview.html
if grep -qi microsoft /proc/version 2>/dev/null; then
  explorer.exe "$(wslpath -w "$f")" 2>/dev/null \
    || cmd.exe /c start "" "$(wslpath -w "$f")" 2>/dev/null \
    || powershell.exe -NoProfile -Command "Start-Process '$(wslpath -w "$f")'"
else
  xdg-open "$f" >/dev/null 2>&1 &
fi
```

Report the path. `explorer.exe` returns rc=1 even on success — don't treat that
as failure. If no opener works (truly headless), print the absolute path for the
operator. Does **not** refresh the page — run `/status update` first for current numbers.
