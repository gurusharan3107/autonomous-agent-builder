// Shared HTTP client for the feedback CLIs that MUTATE the queue.
//
// Why HTTP and not direct file writes: the feedback server is the single
// authoritative writer of feedback-queue.json (it serializes every mutation
// through an in-process lock + atomic tmp+rename, and runs the durability
// reclaim sweep). CLIs that wrote the file directly could race the server and
// drop a write (e.g. clobber a reclaim). Routing mutations through the server's
// /api/agent/* endpoints removes that race.
//
// Read-only CLIs (next, details) stay file-based: they can't race, the file is
// written atomically, and keeping them file-based preserves offline inspection.

export function flagValue(args, name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
}

// Resolve the server base URL. Prefer --url, else --port (default 4177, the
// server's own default). --root is still accepted for backward-compatible
// invocation but is not used to reach the server.
export function serverBase(args) {
  const explicit = flagValue(args, "--url");
  if (explicit) return explicit.replace(/\/$/, "");
  const port = Number(flagValue(args, "--port") || process.env.AGENT_FEEDBACK_PORT || 4177);
  return `http://localhost:${port}`;
}

// Call a server JSON endpoint. Exits with a clear, distinct code on failure so
// an absent operator's automation surfaces the problem instead of silently
// continuing: 3 = server unreachable, 1 = HTTP error.
export async function apiJson(method, base, path, body) {
  let res;
  try {
    res = await fetch(`${base}${path}`, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined
    });
  } catch (err) {
    console.error(`feedback server not reachable at ${base} — is artifact-feedback-server.mjs running? (${err.code || err.message})`);
    process.exit(3);
  }
  const raw = await res.text();
  let data = {};
  try { data = raw ? JSON.parse(raw) : {}; } catch { data = { raw }; }
  if (!res.ok) {
    console.error(`feedback server ${method} ${path} → HTTP ${res.status}: ${raw}`);
    process.exit(1);
  }
  return data;
}
