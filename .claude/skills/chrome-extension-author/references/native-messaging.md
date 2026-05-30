# Native messaging — Unix-socket bridge pattern

Chrome's `chrome.runtime.connectNative` lets the extension talk to a local OS-side process. Use it when the extension needs file system access, shell execution, IPC with another local service, or to be driven by an external agent.

The pattern below is the one proven by hermes-chrome — survives service-worker idle restarts, tab navigations, and extension reloads.

## Architecture

```
External agent / CLI ──unix socket──► native_host.py ──stdio──► chrome.runtime.connectNative
                                                                  │
                                                          ┌───────┴───────┐
                                                          ▼               ▼
                                                  service_worker.js ──► content scripts
```

The native host is the long-lived process. The agent (or CLI) speaks to a Unix socket the host owns; the host relays to Chrome over stdio (per Chrome's native messaging contract); the service worker dispatches to content scripts as needed.

## The native host process

- **Long-lived Python (or Node) process.** Stays up across SW idles.
- **Binds a Unix socket** at a stable path (e.g., `~/.<extension>/run/bridge.sock`).
- **Speaks stdio JSON to Chrome** per [Chrome native messaging protocol](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging) — 4-byte little-endian length prefix + JSON body.
- **Speaks line-delimited JSON over the Unix socket** to the agent — one JSON per line, `\n`-terminated.
- **Logs to stderr only** — stdout is the Chrome message channel.

## Service worker side

- **`chrome.runtime.connectNative(hostName)` on demand.** Don't connect at install — connect when the first message needs to flow. The connection auto-tears when SW idles; reconnect on next need.
- **Handle `port.onDisconnect`** — log the reason (it's in `chrome.runtime.lastError`), reset the port reference. The next operation will reconnect.
- **Idempotent message handlers.** Same message id may arrive twice if SW restarted mid-flight.

## Host manifest (`native/host.json`)

Chrome looks up the host manifest in a specific directory per OS:

- macOS: `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/<host>.json`
- Linux (incl. WSL2): `~/.config/google-chrome/NativeMessagingHosts/<host>.json`
- Windows: registry entry

The scaffolded `native/install.sh` copies the manifest to the correct OS location.

Manifest shape:

```json
{
  "name": "com.example.<extension>",
  "description": "Native messaging host for <extension>",
  "path": "<absolute path to host.py>",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://<extension-id>/"]
}
```

The `<extension-id>` is only known after first install in Chrome. Two paths:
1. Operator installs the extension, copies the ID from `chrome://extensions/`, runs `install.sh` with the ID.
2. Use the version-specific extension key in `manifest.json` to fix the extension ID at known value (more setup, less friction later).

## WSL2 networking gotcha

If the host runs in WSL2 and the agent is on Windows (or vice versa):

- **Bind the Unix socket to `~/.<ext>/run/bridge.sock` inside WSL.** Windows-side agents can reach it via the WSL filesystem (`\\wsl$\<distro>\home\<user>\.<ext>\run\bridge.sock`).
- **If TCP instead of Unix socket:** bind to `::` (IPv6 wildcard) or `0.0.0.0`. Chrome on Windows reaches Node-bound localhost via `localhost`, NOT `127.0.0.1`. Document this gotcha in the generated extension's `agent-handbook.md`.
- **TCP Nagle**: tiny SSE writes coalesce into 4-9s delivery latency. Call `socket.setNoDelay(true)` on every connected socket.

## Lifecycle

1. **Install:** operator runs `native/install.sh` after loading the extension and finding the ID.
2. **Boot:** the native host is spawned by Chrome when the SW calls `connectNative`. It binds its Unix socket and waits.
3. **Idle:** SW idles → `port.onDisconnect` fires in the SW → native host's stdio closes → host may exit OR stay alive serving other agents. Hermes-chrome's host stays alive; some hosts exit.
4. **Reconnect:** next SW message → `connectNative` again → host spawns OR new connection accepted. Idempotent.

## Testing

After install, verify the chain end-to-end:

1. Open `chrome://extensions/` Errors page — zero errors.
2. From the SW console (chrome://extensions → "service worker" link), call `chrome.runtime.connectNative("com.example.<ext>")` and `port.postMessage({hello: "world"})`. The host should log to stderr that it received a message.
3. From the agent side, `nc -U ~/.<ext>/run/bridge.sock` and send a JSON line. The host should relay it to the SW; SW echoes back.

If step 2 fails: manifest path wrong, or `allowed_origins` doesn't match the extension ID.
If step 3 fails: socket path wrong, or host not running (manifest never invoked).
