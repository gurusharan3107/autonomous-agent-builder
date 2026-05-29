"""
Chrome DevTools Protocol bridge for hermes-chrome.

Architecture: tools.py → asyncio.run(execute(args)) → cdp_bridge.py → WebSocket → Chrome (WSL2)

Replaces the native-messaging extension path entirely:
  - No extension, no service_worker.js, no cursor-agent.js
  - No native_host.py, no native manifest, no Windows batch launcher
  - No MV3 service-worker idle kill (Chrome process stays alive)
  - Logged-in WSL2 Chrome profile used directly

Chrome must be started with --remote-debugging-port=9222.
Run: bash ~/.claude/plugin/hermes_chrome/scripts/start_chrome_cdp.sh
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from pathlib import Path
from typing import Any

import requests

try:
    import websockets
    import websockets.exceptions
    _HAS_WEBSOCKETS = True
except ImportError:
    _HAS_WEBSOCKETS = False

CDP_PORT = int(os.environ.get("HERMES_CDP_PORT", "9222"))
CDP_HOST = os.environ.get("HERMES_CDP_HOST", "localhost")
SCREENSHOT_DIR = Path.home() / ".hermes" / "cache" / "hermes-chrome"


# ── Structured errors ─────────────────────────────────────────────────────────

class CDPError(Exception):
    """Structured error. error_code routes recovery without string parsing."""
    def __init__(self, error_code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.error_code = error_code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"success": False, "error_code": self.error_code, "error": str(self)}
        if self.detail:
            d["detail"] = self.detail
        return d


# ── Cursor overlay JS ─────────────────────────────────────────────────────────

def _cursor_move_js(x: float, y: float) -> str:
    return (
        "(()=>{"
        "let c=document.getElementById('__hermes_cur');"
        "if(!c){"
        "c=document.createElement('div');c.id='__hermes_cur';"
        "Object.assign(c.style,{"
        "position:'fixed',width:'20px',height:'20px',"
        "background:'radial-gradient(circle,rgba(255,100,0,0.95) 0%,rgba(255,60,0,0.5) 55%,transparent 100%)',"
        "borderRadius:'50%',zIndex:'2147483647',pointerEvents:'none',"
        "transform:'translate(-50%,-50%)',"
        "boxShadow:'0 0 8px rgba(255,80,0,0.5)',"
        "transition:'left 0.04s,top 0.04s',left:'-50px',top:'-50px'"
        "});"
        "document.documentElement.appendChild(c);}"
        f"c.style.left='{x}px';c.style.top='{y}px';"
        "})()"
    )


# ── CDP session ───────────────────────────────────────────────────────────────

class CDPSession:
    def __init__(self, ws: Any, tab_id: str, tab_url: str):
        self._ws = ws
        self.tab_id = tab_id
        self.tab_url = tab_url
        self._mid = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._event_waiters: dict[str, list[asyncio.Future[Any]]] = {}
        self._recv_task: asyncio.Task[None] | None = None
        self._cur_x = 0.0
        self._cur_y = 0.0

    async def _recv_loop(self) -> None:
        try:
            async for raw in self._ws:
                data = json.loads(raw)
                msg_id = data.get("id")
                if msg_id is not None:
                    fut = self._pending.pop(msg_id, None)
                    if fut and not fut.done():
                        fut.set_result(data)
                elif "method" in data:
                    for fut in list(self._event_waiters.get(data["method"], [])):
                        if not fut.done():
                            fut.set_result(data.get("params", {}))
                            break
        except Exception:
            pass

    async def _init(self) -> None:
        self._recv_task = asyncio.create_task(self._recv_loop())
        await self.cmd("Runtime.enable")
        await self.cmd("Page.enable")

    async def cmd(self, method: str, params: dict[str, Any] | None = None,
                  timeout: float = 30.0) -> dict[str, Any]:
        self._mid += 1
        mid = self._mid
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[mid] = fut
        await self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(mid, None)
            raise CDPError("TIMEOUT", f"{method} timed out after {timeout}s")
        if "error" in result:
            raise CDPError("CDP_ERROR", result["error"]["message"], result["error"])
        return result.get("result") or {}

    async def wait_event(self, method: str, timeout: float = 8.0) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._event_waiters.setdefault(method, []).append(fut)
        try:
            return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
        except asyncio.TimeoutError:
            return {}
        finally:
            try:
                self._event_waiters.get(method, []).remove(fut)
            except ValueError:
                pass

    async def eval(self, expr: str, timeout: float = 10.0) -> Any:
        r = await self.cmd("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": False,
        }, timeout=timeout)
        if r.get("exceptionDetails"):
            msg = r["exceptionDetails"].get("text") or r["exceptionDetails"].get("exception", {}).get("description", "JS error")
            raise CDPError("JS_ERROR", msg, r["exceptionDetails"])
        rv = r.get("result", {})
        t = rv.get("type")
        if t in ("string", "number", "boolean"):
            return rv.get("value")
        if t in ("undefined",) or rv.get("subtype") == "null":
            return None
        v = rv.get("value")
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v

    # ── Cursor ────────────────────────────────────────────────────────────────

    async def _move_cursor(self, x: float, y: float, steps: int = 10) -> None:
        sx, sy = self._cur_x, self._cur_y
        for i in range(1, steps + 1):
            t = 1 - (1 - i / steps) ** 2           # ease-out
            ix, iy = sx + (x - sx) * t, sy + (y - sy) * t
            await self.cmd("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": ix, "y": iy, "button": "none",
            })
            await self.eval(_cursor_move_js(ix, iy))
            await asyncio.sleep(0.018)
        self._cur_x, self._cur_y = x, y

    async def _click(self, x: float, y: float, click_count: int = 1) -> None:
        await self._move_cursor(x, y)
        await asyncio.sleep(0.06)
        for evt in ("mousePressed", "mouseReleased"):
            await self.cmd("Input.dispatchMouseEvent", {
                "type": evt, "x": x, "y": y,
                "button": "left", "clickCount": click_count,
            })
        await asyncio.sleep(0.08)

    # ── Find element ──────────────────────────────────────────────────────────

    async def _find_by_text(self, text: str) -> dict[str, Any]:
        coords = await self.eval(
            f"(()=>{{"
            f"const t={json.dumps(text)};"
            f"const els=Array.from(document.querySelectorAll("
            f"'a,button,[role=button],[role=link],[role=menuitem],[role=tab],"
            f"input[type=submit],input[type=button],label,span,div,p,td,li'));"
            f"const el=els.find(e=>{{"
            f"const tx=(e.textContent||e.value||'').trim();"
            f"return tx===t||tx.includes(t);"
            f"}});"
            f"if(!el)return null;"
            f"const r=el.getBoundingClientRect();"
            f"if(r.width===0||r.height===0)return null;"
            f"return{{x:r.left+r.width/2,y:r.top+r.height/2,"
            f"tag:el.tagName.toLowerCase(),text:el.textContent.trim().slice(0,60)}};"
            f"}})()"
        )
        if coords is None:
            raise CDPError(
                "SELECTOR_NOT_FOUND",
                f"No visible element with text {text!r}. Use action_snapshot to see available elements.",
            )
        return coords

    async def _find_by_selector(self, selector: str) -> dict[str, Any]:
        coords = await self.eval(
            f"(()=>{{"
            f"const el=document.querySelector({json.dumps(selector)});"
            f"if(!el)return null;"
            f"const r=el.getBoundingClientRect();"
            f"if(r.width===0||r.height===0)return null;"
            f"return{{x:r.left+r.width/2,y:r.top+r.height/2,tag:el.tagName.toLowerCase()}};"
            f"}})()"
        )
        if coords is None:
            raise CDPError(
                "SELECTOR_NOT_FOUND",
                f"Selector {selector!r} not found or not visible. Use action_snapshot to refresh.",
            )
        return coords

    # ── Actions ───────────────────────────────────────────────────────────────

    async def do_page_context(self) -> dict[str, Any]:
        raw = await self.eval(
            "JSON.stringify({"
            "url:window.location.href,"
            "title:document.title,"
            "headings:Array.from(document.querySelectorAll('h1,h2,h3')).slice(0,10)"
            ".map(h=>({tag:h.tagName,text:h.textContent.trim().slice(0,80)})),"
            "nav:Array.from(document.querySelectorAll('nav a,[role=navigation] a')).slice(0,20)"
            ".map(a=>({text:a.textContent.trim().slice(0,50),href:a.href})),"
            "buttons:Array.from(document.querySelectorAll("
            "'button,[role=button],input[type=submit],input[type=button]')).slice(0,20)"
            ".map(b=>(b.textContent||b.value||'').trim().slice(0,50)).filter(Boolean),"
            "inputs:Array.from(document.querySelectorAll('input,textarea,select')).slice(0,20)"
            ".map(i=>({name:i.name||i.id||i.placeholder||'',type:i.type||'text',value:i.value||''}))"
            "})"
        )
        return raw if isinstance(raw, dict) else json.loads(raw)

    async def do_snapshot(self) -> dict[str, Any]:
        raw = await self.eval(
            "JSON.stringify({"
            "url:window.location.href,"
            "title:document.title,"
            "snapshot:Array.from(document.querySelectorAll("
            "'a,button,[role=button],[role=link],[role=menuitem],[role=tab],"
            "input,select,textarea,[role=checkbox],[role=radio],[role=combobox],"
            "h1,h2,h3,label')).filter(el=>{"
            "const r=el.getBoundingClientRect();"
            "return r.width>0&&r.height>0&&r.top<window.innerHeight&&r.top>-100;"
            "}).slice(0,80).map((el,i)=>{"
            "const r=el.getBoundingClientRect();"
            "return{i,tag:el.tagName.toLowerCase(),"
            "role:el.getAttribute('role')||'',"
            "text:(el.textContent||el.value||el.placeholder||'').trim().slice(0,80),"
            "href:el.href||'',value:el.value||'',name:el.name||el.id||'',"
            "x:Math.round(r.x),y:Math.round(r.y),"
            "w:Math.round(r.width),h:Math.round(r.height)};"
            "})})"
        )
        result = raw if isinstance(raw, dict) else json.loads(raw)
        result["element_count"] = len(result.get("snapshot", []))
        return result

    async def do_text(self, max_chars: int = 20000) -> dict[str, Any]:
        url   = await self.eval("window.location.href")
        title = await self.eval("document.title")
        text  = await self.eval("document.body ? document.body.innerText : ''")
        if isinstance(text, str) and len(text) > max_chars:
            text = text[:max_chars] + "…"
        return {"url": url, "title": title, "text": text}

    async def do_goto(self, url: str, wait_ms: int = 0) -> dict[str, Any]:
        nav = await self.cmd("Page.navigate", {"url": url}, timeout=30)
        await self.wait_event("Page.loadEventFired", timeout=10)
        if wait_ms:
            await asyncio.sleep(wait_ms / 1000)
        return {"url": url, "frame_id": nav.get("frameId")}

    async def do_screenshot(self, fmt: str = "jpeg") -> dict[str, Any]:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        params: dict[str, Any] = {"format": fmt, "captureBeyondViewport": False}
        if fmt == "jpeg":
            params["quality"] = 80
        r = await self.cmd("Page.captureScreenshot", params, timeout=20)
        data = r.get("data", "")
        path = SCREENSHOT_DIR / f"hermes-{uuid.uuid4().hex[:8]}.{fmt}"
        path.write_bytes(base64.b64decode(data))
        return {"format": fmt, "screenshot_path": str(path)}

    async def do_click_text(self, text: str) -> dict[str, Any]:
        coords = await self._find_by_text(text)
        await self._click(coords["x"], coords["y"])
        return {"type": "click_text", "text": text, "point": coords}

    async def do_click_selector(self, selector: str) -> dict[str, Any]:
        coords = await self._find_by_selector(selector)
        await self._click(coords["x"], coords["y"])
        return {"type": "click_selector", "selector": selector, "point": coords}

    async def do_fill_selector(self, selector: str, value: str, append: bool = False) -> dict[str, Any]:
        coords = await self._find_by_selector(selector)
        await self._click(coords["x"], coords["y"])
        await asyncio.sleep(0.05)
        if not append:
            await self.cmd("Input.dispatchKeyEvent", {
                "type": "keyDown", "modifiers": 2, "key": "a", "code": "KeyA",
            })
            await self.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a"})
            await asyncio.sleep(0.02)
        await self.cmd("Input.insertText", {"text": value})
        await self.eval(
            f"(()=>{{"
            f"const el=document.querySelector({json.dumps(selector)});"
            f"if(el){{"
            f"el.dispatchEvent(new Event('input',{{bubbles:true}}));"
            f"el.dispatchEvent(new Event('change',{{bubbles:true}}));"
            f"}}}})();"
        )
        return {"type": "fill_selector", "selector": selector, "value": value, "append": append}

    async def do_wait(self, ms: int) -> dict[str, Any]:
        await asyncio.sleep(ms / 1000)
        return {"type": "wait", "ms": ms}

    async def do_wait_for_url_change(self, from_url: str | None = None,
                                     timeout: float = 10.0) -> dict[str, Any]:
        start = from_url or await self.eval("window.location.href")
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            cur = await self.eval("window.location.href")
            if cur != start:
                return {"type": "wait_for_url_change", "from": start, "to": cur}
            await asyncio.sleep(0.2)
        return {"type": "wait_for_url_change", "timed_out": True, "url": start}

    async def do_wait_for_selector(self, selector: str, timeout: float = 10.0) -> dict[str, Any]:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            visible = await self.eval(
                f"(()=>{{"
                f"const el=document.querySelector({json.dumps(selector)});"
                f"if(!el)return false;"
                f"const r=el.getBoundingClientRect();"
                f"return r.width>0&&r.height>0;"
                f"}})()"
            )
            if visible:
                return {"type": "wait_for_selector", "selector": selector, "found": True}
            await asyncio.sleep(0.2)
        raise CDPError("TIMEOUT", f"Selector {selector!r} not visible within {timeout}s.")

    async def do_evaluate(self, expression: str) -> dict[str, Any]:
        value = await self.eval(expression)
        return {"type": "evaluate", "result": value}

    async def do_close_tab(self) -> dict[str, Any]:
        await self.cmd("Page.close")
        return {"type": "close_tab"}

    async def do_cursor_move(self, x: float, y: float) -> dict[str, Any]:
        await self._move_cursor(x, y)
        return {"type": "cursor_move", "x": x, "y": y}

    async def do_cursor_type(self, text: str) -> dict[str, Any]:
        await self.cmd("Input.insertText", {"text": text})
        return {"type": "cursor_type", "text": text}

    async def do_cursor_key(self, key: str, modifiers: list[str] | None = None) -> dict[str, Any]:
        mod = 0
        for m in (modifiers or []):
            mod |= {"ctrl": 2, "shift": 8, "alt": 1, "cmd": 4, "meta": 4}.get(m.lower(), 0)
        for evt in ("keyDown", "keyUp"):
            await self.cmd("Input.dispatchKeyEvent", {"type": evt, "key": key, "modifiers": mod})
        return {"type": "cursor_key", "key": key}

    async def do_cursor_scroll(self, delta_x: float = 0, delta_y: float = 300) -> dict[str, Any]:
        await self.cmd("Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "x": self._cur_x or 640, "y": self._cur_y or 400,
            "deltaX": delta_x, "deltaY": delta_y,
        })
        return {"type": "cursor_scroll", "deltaX": delta_x, "deltaY": delta_y}

    async def do_cursor_drag(self, x: float, y: float, duration: int = 300) -> dict[str, Any]:
        steps = max(5, duration // 30)
        await self.cmd("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": self._cur_x, "y": self._cur_y, "button": "left",
        })
        await self._move_cursor(x, y, steps=steps)
        await self.cmd("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y, "button": "left",
        })
        return {"type": "cursor_drag", "x": x, "y": y}

    async def dispatch(self, action: dict[str, Any]) -> dict[str, Any]:
        t = action.get("type", "")
        try:
            if t == "page_context":        return await self.do_page_context()
            if t == "snapshot":            return await self.do_snapshot()
            if t == "text":                return await self.do_text(action.get("max_chars", 20000))
            if t == "screenshot":          return await self.do_screenshot(action.get("format", "jpeg"))
            if t == "goto":                return await self.do_goto(action["url"], action.get("waitMs", 0))
            if t == "reload":              return await self.do_goto(await self.eval("window.location.href"))
            if t == "wait":                return await self.do_wait(action.get("ms", 500))
            if t == "wait_for_url_change": return await self.do_wait_for_url_change(action.get("from_url"), action.get("timeout", 10))
            if t == "wait_for_selector":   return await self.do_wait_for_selector(action["selector"], action.get("timeout", 10))
            if t == "click_text":          return await self.do_click_text(action["text"])
            if t == "click_selector":      return await self.do_click_selector(action["selector"])
            if t == "fill_selector":       return await self.do_fill_selector(action["selector"], action["value"], action.get("append", False))
            if t == "evaluate":            return await self.do_evaluate(action["expression"])
            if t == "close_tab":           return await self.do_close_tab()
            if t == "cursor_move":         return await self.do_cursor_move(action["x"], action["y"])
            if t == "cursor_type":         return await self.do_cursor_type(action["text"])
            if t == "cursor_key":          return await self.do_cursor_key(action["key"], action.get("modifiers"))
            if t == "cursor_click":
                await self._click(self._cur_x, self._cur_y)
                return {"type": "cursor_click"}
            if t == "cursor_double_click":
                await self._click(self._cur_x, self._cur_y, click_count=2)
                return {"type": "cursor_double_click"}
            if t == "cursor_triple_click":
                await self._click(self._cur_x, self._cur_y, click_count=3)
                return {"type": "cursor_triple_click"}
            if t == "cursor_right_click":
                await self.cmd("Input.dispatchMouseEvent", {
                    "type": "mousePressed", "x": self._cur_x, "y": self._cur_y,
                    "button": "right", "clickCount": 1,
                })
                return {"type": "cursor_right_click"}
            if t == "cursor_scroll":       return await self.do_cursor_scroll(action.get("deltaX", 0), action.get("deltaY", 300))
            if t == "cursor_drag":         return await self.do_cursor_drag(action["x"], action["y"], action.get("duration", 300))
            if t == "cursor_status":       return {"type": "cursor_status", "visible": True, "x": self._cur_x, "y": self._cur_y, "url": await self.eval("window.location.href"), "title": await self.eval("document.title")}
            if t == "cursor_hide":
                await self.eval("(()=>{const c=document.getElementById('__hermes_cur');if(c)c.style.left='-100px';})()")
                return {"type": "cursor_hide"}
            raise CDPError("UNKNOWN_ACTION", f"Unknown action type: {t!r}")
        except CDPError:
            raise
        except Exception as e:
            raise CDPError("ACTION_FAILED", f"Action {t!r} failed: {e}", str(e))


# ── Connection factory ────────────────────────────────────────────────────────

async def _get_targets(port: int) -> list[dict[str, Any]]:
    try:
        r = requests.get(f"http://{CDP_HOST}:{port}/json/list", timeout=3)
        return r.json()
    except requests.exceptions.ConnectionError:
        raise CDPError(
            "SOCKET_DOWN",
            f"Chrome CDP not reachable on port {port}. "
            "Run: bash ~/.claude/plugin/hermes_chrome/scripts/start_chrome_cdp.sh",
        )
    except Exception as e:
        raise CDPError("SOCKET_DOWN", f"CDP list failed: {e}")


async def open_session(port: int = CDP_PORT, tab_id: str | None = None) -> CDPSession:
    if not _HAS_WEBSOCKETS:
        raise CDPError("MISSING_DEP", "websockets not installed. Run: pip install websockets")

    targets = await _get_targets(port)
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        raise CDPError("NO_PAGE", "No Chrome page tabs open. Navigate Chrome to an HTTPS URL first.")

    tab = next((t for t in pages if t.get("id") == tab_id), pages[0]) if tab_id else pages[0]
    ws_url = tab.get("webSocketDebuggerUrl", "")
    if not ws_url:
        raise CDPError(
            "TAB_BLOCKED",
            f"Tab {tab.get('url')!r} has no debugger URL (chrome:// or devtools page). "
            "Navigate Chrome to an HTTPS page.",
        )

    try:
        ws = await websockets.connect(ws_url, max_size=64 * 1024 * 1024, open_timeout=10)
    except Exception as e:
        raise CDPError("SOCKET_DOWN", f"CDP WebSocket failed: {e}")

    session = CDPSession(ws, tab["id"], tab.get("url", ""))
    await session._init()
    return session


# ── Health check ──────────────────────────────────────────────────────────────

async def health(port: int = CDP_PORT) -> dict[str, Any]:
    try:
        ver = requests.get(f"http://{CDP_HOST}:{port}/json/version", timeout=3).json()
        targets = await _get_targets(port)
        pages = [t for t in targets if t.get("type") == "page"]
        active = pages[0] if pages else {}
        return {
            "success": True,
            "ready": True,
            "chrome": ver.get("Browser", "?"),
            "protocol": ver.get("Protocol-Version", "?"),
            "active_tab": {"url": active.get("url", ""), "title": active.get("title", "")},
            "page_count": len(pages),
        }
    except CDPError as e:
        return e.to_dict()
    except Exception as e:
        return {"success": False, "ready": False, "error_code": "SOCKET_DOWN", "error": str(e)}


# ── Main entry point ──────────────────────────────────────────────────────────

async def execute(args: dict[str, Any]) -> dict[str, Any]:
    """Entry point from tools.py. Called via asyncio.run(execute(args))."""
    port = int(args.get("cdp_port") or CDP_PORT)
    tab_id: str | None = args.get("tab_id") or None
    action = str(args.get("action") or "run").lower()

    if action in ("status", "health", "preflight", "diagnose"):
        return await health(port)

    if action != "run":
        return {"success": False, "error_code": "BAD_ACTION", "error": f"Unknown action: {action!r}"}

    actions = list(args.get("actions") or [{"type": "page_context"}])

    # Optional URL prepend
    url = str(args.get("url") or "").strip()
    if url:
        actions.insert(0, {"type": "goto", "url": url})

    try:
        session = await open_session(port, tab_id)
    except CDPError as e:
        return e.to_dict()

    results: list[dict[str, Any]] = []
    error_result: dict[str, Any] | None = None

    try:
        async with session._ws:
            for act in actions:
                result = await session.dispatch(act)
                results.append(result)
            # Compact final state — always append so agent knows where it left Chrome
            final = await session.do_page_context()
    except CDPError as e:
        error_result = e.to_dict()
        final = {}
    except Exception as e:
        error_result = {"success": False, "error_code": "UNKNOWN", "error": str(e)}
        final = {}

    if error_result:
        return {**error_result, "results": results}

    return {
        "success": True,
        "tab_id": session.tab_id,
        "url": final.get("url", ""),
        "title": final.get("title", ""),
        "results": results,
    }
