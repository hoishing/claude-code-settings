# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "rebrowser-playwright",
# ]
# ///
"""
fingerprint — Anti-detection browser automation CLI.

Uses fingerprint-chromium (C++ fingerprint spoofing) + rebrowser-playwright (CDP signal masking)
to provide an LLM-friendly browser automation tool with @eN ref-based element selection.

Daemon architecture: first `open` spawns the browser; subsequent commands connect via Unix socket.
"""

import argparse
import asyncio
import json
import os
import random
import re
import signal
import socket
import struct
import sys
import tempfile
from pathlib import Path

# --- Configuration ---
HOME_DIR = Path.home() / ".fingerprint-browser"
SOCKET_PATH = HOME_DIR / "daemon.sock"
PID_FILE = HOME_DIR / "daemon.pid"
REFS_FILE = HOME_DIR / "refs.json"
CHROMIUM_PATH = HOME_DIR / "chromium" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"

INTERACTIVE_ROLES = frozenset({
    "link", "button", "textbox", "checkbox", "radio", "combobox", "listbox",
    "menuitem", "menuitemcheckbox", "menuitemradio", "option", "searchbox",
    "slider", "spinbutton", "switch", "tab", "treeitem",
})

CONTAINER_ROLES = frozenset({
    "heading", "cell", "row", "rowgroup", "table", "list", "listitem",
    "navigation", "main", "banner", "contentinfo", "complementary", "form",
    "region", "article", "section", "group", "toolbar", "menu", "menubar",
    "tablist", "tabpanel", "tree", "treegrid", "grid", "gridcell",
    "paragraph", "blockquote", "figure", "dialog", "alertdialog", "alert",
    "status", "log", "marquee", "timer", "tooltip",
})

INPUT_ROLES = frozenset({
    "textbox", "searchbox", "combobox", "spinbutton", "slider",
})


# ========================
# Snapshot Parser
# ========================

def parse_aria_snapshot(text: str, interactive_only: bool = False):
    """Parse aria_snapshot() output, assign @eN refs to interactive elements."""
    lines = text.split("\n")
    refs = {}
    ref_counter = 1
    output_lines = []
    role_name_counts: dict[tuple[str, str], int] = {}

    # First pass: count role+name combos for nth disambiguation
    for line in lines:
        parsed = _parse_line(line)
        if parsed and parsed["role"] in INTERACTIVE_ROLES:
            key = (parsed["role"], parsed["name"])
            role_name_counts[key] = role_name_counts.get(key, 0) + 1

    # Track seen counts for nth assignment
    role_name_seen: dict[tuple[str, str], int] = {}
    # Track parent indent for grouping in -i mode
    last_container_line: str | None = None
    last_container_indent = ""

    for line in lines:
        parsed = _parse_line(line)
        if not parsed:
            if not interactive_only:
                if not line.strip().startswith("- /"):
                    output_lines.append(line)
            continue

        role = parsed["role"]
        name = parsed["name"]
        attrs = parsed["attrs"]
        indent = parsed["indent"]

        if role in INTERACTIVE_ROLES:
            key = (role, name)
            nth = role_name_seen.get(key, 0)
            role_name_seen[key] = nth + 1

            ref_id = f"e{ref_counter}"
            ref_counter += 1
            refs[ref_id] = {
                "role": role,
                "name": name,
                "nth": nth if role_name_counts.get(key, 1) > 1 else 0,
                "needs_nth": role_name_counts.get(key, 1) > 1,
            }

            # In -i mode, show parent container for context
            if interactive_only and last_container_line is not None:
                if indent.startswith(last_container_indent) and len(indent) > len(last_container_indent):
                    output_lines.append(last_container_line)
                    last_container_line = None  # Only emit once per group

            # Format output line — flatten indentation in -i mode
            if interactive_only:
                display_indent = ""
            else:
                display_indent = indent
            parts = [f"{display_indent}- {role}"]
            if name:
                parts.append(f' "{name}"')
            if attrs:
                parts.append(f" [{attrs}, ref={ref_id}]")
            else:
                parts.append(f" [ref={ref_id}]")
            output_lines.append("".join(parts))
        elif interactive_only:
            # In -i mode, remember containers for grouping context
            if role in CONTAINER_ROLES and name:
                last_container_line = f"- {role} \"{name}\""
                if attrs:
                    last_container_line += f" [{attrs}]"
                last_container_indent = indent
        else:
            parts = [f"{indent}- {role}"]
            if name:
                parts.append(f' "{name}"')
            if attrs:
                parts.append(f" [{attrs}]")
            output_lines.append("".join(parts))

    return "\n".join(output_lines), refs


def _parse_line(line: str) -> dict | None:
    """Parse a single aria_snapshot line into role, name, attrs."""
    # Match: <indent>- <role> "name" [attrs]:
    # or:    <indent>- <role> "name":
    # or:    <indent>- <role>:
    # or:    <indent>- <role> "name"
    m = re.match(r'^(\s*)- (\w+)(.*)', line)
    if not m:
        return None

    indent = m.group(1)
    role = m.group(2)
    rest = m.group(3).rstrip().rstrip(":")

    # Skip non-role lines
    if role in ("text", "img", "image"):
        return {"role": role, "name": "", "attrs": "", "indent": indent}

    # Extract name from quotes
    name = ""
    name_match = re.search(r'"([^"]*)"', rest)
    if name_match:
        name = name_match.group(1)

    # Extract attrs from brackets
    attrs = ""
    attrs_match = re.search(r'\[([^\]]*)\]', rest)
    if attrs_match:
        attrs = attrs_match.group(1)

    return {"role": role, "name": name, "attrs": attrs, "indent": indent}


# ========================
# Daemon Server
# ========================

class BrowserDaemon:
    def __init__(self, proxy: str | None = None, headed: bool = True, fingerprint_seed: int | None = None):
        self.proxy = proxy
        self.headed = headed
        self.seed = fingerprint_seed or random.randint(100000, 999999999)
        self.playwright = None
        self.browser = None
        self.page = None
        self.refs: dict[str, dict] = {}

    async def start(self):
        from rebrowser_playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()

        launch_args = [
            f"--fingerprint={self.seed}",
            "--fingerprint-platform=macos",
            "--fingerprint-brand=Chrome",
            "--disable-non-proxied-udp",
            "--disable-blink-features=AutomationControlled",
        ]

        launch_kwargs = {
            "executable_path": str(CHROMIUM_PATH),
            "args": launch_args,
            "headless": not self.headed,
        }

        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}

        self.browser = await self.playwright.chromium.launch(**launch_kwargs)
        self.page = await self.browser.new_page()

    async def handle_command(self, cmd: dict) -> dict:
        action = cmd.get("action", "")
        try:
            match action:
                case "open":
                    return await self._open(cmd["url"])
                case "snapshot":
                    return await self._snapshot(cmd.get("interactive", False))
                case "click":
                    return await self._click(cmd["ref"])
                case "fill":
                    return await self._fill(cmd["ref"], cmd["text"])
                case "type":
                    return await self._type_text(cmd["ref"], cmd["text"])
                case "select":
                    return await self._select(cmd["ref"], cmd["values"])
                case "press":
                    return await self._press(cmd["key"])
                case "scroll":
                    return await self._scroll(cmd.get("direction", "down"), cmd.get("amount", 300))
                case "screenshot":
                    return await self._screenshot(cmd.get("path"))
                case "wait":
                    return await self._wait(cmd)
                case "get":
                    return await self._get(cmd)
                case "close":
                    return await self._close()
                case _:
                    return {"error": f"Unknown action: {action}"}
        except Exception as e:
            return {"error": str(e)}

    async def _open(self, url: str) -> dict:
        if not url.startswith(("http://", "https://", "file://", "data:", "about:")):
            url = "https://" + url
        await self.page.goto(url, wait_until="domcontentloaded")
        # Wait briefly for potential challenge redirects
        await self.page.wait_for_timeout(2000)
        title = await self.page.title()
        challenged = await self._detect_challenge(title, self.page.url)
        result = {"ok": True, "title": title, "url": self.page.url}
        if challenged:
            result["challenged"] = True
        return result

    async def _detect_challenge(self, title: str, url: str) -> bool:
        """Detect if the page is a bot challenge/interstitial."""
        title_lower = title.lower()
        challenge_titles = [
            "just a moment",          # Cloudflare interstitial
            "attention required",     # Cloudflare block
            "access denied",          # Generic WAF
            "checking your browser",  # Cloudflare
            "verify you are human",   # Cloudflare Turnstile
            "please wait",            # Generic challenge
            "security check",         # Generic WAF
            "one more step",          # Cloudflare
        ]
        for phrase in challenge_titles:
            if phrase in title_lower:
                return True
        # Check URL for challenge indicators
        if "challenge" in url.lower() or "/cdn-cgi/" in url:
            return True
        # Check DOM for Cloudflare challenge elements
        try:
            has_challenge = await self.page.evaluate("""() => {
                // Cloudflare Turnstile iframe
                if (document.querySelector('iframe[src*="challenges.cloudflare.com"]')) return true;
                // Cloudflare interstitial markers
                if (document.querySelector('#challenge-running, #challenge-form, #cf-challenge-running')) return true;
                // Cloudflare "checking your browser" spinner
                if (document.querySelector('.cf-browser-verification')) return true;
                // Ray ID in body (Cloudflare block page)
                const body = document.body?.innerText || '';
                if (body.includes('Ray ID:') && body.includes('Cloudflare')) return true;
                return false;
            }""")
            if has_challenge:
                return True
        except Exception:
            pass
        return False

    async def _snapshot(self, interactive: bool) -> dict:
        raw = await self.page.locator("body").aria_snapshot()
        text, refs = parse_aria_snapshot(raw, interactive_only=interactive)
        self.refs = refs
        # Save refs to file for cross-process access
        REFS_FILE.write_text(json.dumps(refs))
        title = await self.page.title()
        header = f"Page: {title}\nURL: {self.page.url}\n"
        return {"ok": True, "snapshot": header + text}

    async def _resolve_ref(self, ref_str: str):
        ref_id = ref_str.lstrip("@")
        info = self.refs.get(ref_id)
        if not info:
            raise ValueError(f"Ref @{ref_id} not found. Run `fingerprint snapshot -i` first.")
        locator = self.page.get_by_role(info["role"], name=info["name"] if info["name"] else None)
        if info.get("needs_nth"):
            locator = locator.nth(info["nth"])
        return locator

    async def _click(self, ref: str) -> dict:
        loc = await self._resolve_ref(ref)
        await loc.click()
        return {"ok": True}

    async def _fill(self, ref: str, text: str) -> dict:
        loc = await self._resolve_ref(ref)
        await loc.fill(text)
        return {"ok": True}

    async def _type_text(self, ref: str, text: str) -> dict:
        loc = await self._resolve_ref(ref)
        await loc.type(text)
        return {"ok": True}

    async def _select(self, ref: str, values: list[str]) -> dict:
        loc = await self._resolve_ref(ref)
        await loc.select_option(values)
        return {"ok": True}

    async def _press(self, key: str) -> dict:
        await self.page.keyboard.press(key)
        return {"ok": True}

    async def _scroll(self, direction: str, amount: int) -> dict:
        dy = amount if direction == "down" else -amount
        dx = amount if direction == "right" else (-amount if direction == "left" else 0)
        if direction in ("up", "down"):
            dx = 0
        await self.page.mouse.wheel(dx, dy)
        return {"ok": True}

    async def _screenshot(self, path: str | None) -> dict:
        if not path:
            path = os.path.join(tempfile.gettempdir(), "fingerprint-screenshot.png")
        path = os.path.expanduser(path)
        await self.page.screenshot(path=path)
        return {"ok": True, "path": path}

    async def _wait(self, cmd: dict) -> dict:
        if "ref" in cmd:
            loc = await self._resolve_ref(cmd["ref"])
            await loc.wait_for(timeout=cmd.get("timeout", 30000))
        elif "load" in cmd:
            await self.page.wait_for_load_state(cmd["load"])
        elif "url" in cmd:
            await self.page.wait_for_url(cmd["url"])
        elif "ms" in cmd:
            await self.page.wait_for_timeout(cmd["ms"])
        elif "text" in cmd:
            await self.page.get_by_text(cmd["text"]).wait_for(timeout=cmd.get("timeout", 30000))
        return {"ok": True}

    async def _get(self, cmd: dict) -> dict:
        what = cmd.get("what", "")
        if what == "url":
            return {"ok": True, "value": self.page.url}
        elif what == "title":
            return {"ok": True, "value": await self.page.title()}
        elif what == "text":
            loc = await self._resolve_ref(cmd["ref"])
            text = await loc.text_content()
            return {"ok": True, "value": text}
        elif what == "value":
            loc = await self._resolve_ref(cmd["ref"])
            val = await loc.input_value()
            return {"ok": True, "value": val}
        elif what == "html":
            loc = await self._resolve_ref(cmd["ref"])
            html = await loc.inner_html()
            return {"ok": True, "value": html}
        return {"error": f"Unknown get target: {what}"}

    async def _close(self) -> dict:
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        return {"ok": True, "closed": True}


async def run_daemon(proxy: str | None, headed: bool, seed: int | None):
    """Run the daemon server on a Unix socket."""
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    daemon = BrowserDaemon(proxy=proxy, headed=headed, fingerprint_seed=seed)
    await daemon.start()

    PID_FILE.write_text(str(os.getpid()))

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            header = await asyncio.wait_for(reader.readexactly(4), timeout=5.0)
            msg_len = struct.unpack(">I", header)[0]
            msg_data = await asyncio.wait_for(reader.readexactly(msg_len), timeout=5.0)
            cmd = json.loads(msg_data.decode())

            result = await asyncio.wait_for(daemon.handle_command(cmd), timeout=60.0)

            resp = json.dumps(result).encode()
            writer.write(struct.pack(">I", len(resp)) + resp)
            await writer.drain()
        except asyncio.TimeoutError:
            resp = json.dumps({"error": "Command timed out"}).encode()
            writer.write(struct.pack(">I", len(resp)) + resp)
            await writer.drain()
        except Exception as e:
            try:
                resp = json.dumps({"error": str(e)}).encode()
                writer.write(struct.pack(">I", len(resp)) + resp)
                await writer.drain()
            except:
                pass
        finally:
            writer.close()
            # Check if browser was closed
            if daemon.browser is None or not daemon.browser.is_connected():
                # Give time for response to flush, then stop
                await asyncio.sleep(0.1)
                asyncio.get_event_loop().stop()

    server = await asyncio.start_unix_server(handle_client, path=str(SOCKET_PATH))

    try:
        await server.serve_forever()
    except asyncio.CancelledError:
        pass
    finally:
        server.close()
        SOCKET_PATH.unlink(missing_ok=True)
        PID_FILE.unlink(missing_ok=True)


def send_command(cmd: dict, timeout: float = 90.0) -> dict:
    """Send a command to the running daemon."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(str(SOCKET_PATH))
    msg = json.dumps(cmd).encode()
    sock.sendall(struct.pack(">I", len(msg)) + msg)

    # Read response with length prefix
    header = _recv_exact(sock, 4)
    resp_len = struct.unpack(">I", header)[0]
    data = _recv_exact(sock, resp_len)
    sock.close()
    return json.loads(data.decode())


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from socket."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Daemon connection lost")
        buf += chunk
    return buf


def is_daemon_running() -> bool:
    if not SOCKET_PATH.exists():
        return False
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(str(SOCKET_PATH))
        sock.close()
        return True
    except (ConnectionRefusedError, FileNotFoundError):
        SOCKET_PATH.unlink(missing_ok=True)
        return False


def start_daemon_background(proxy: str | None, headed: bool, seed: int | None):
    """Fork a daemon process in the background."""
    pid = os.fork()
    if pid == 0:
        # Child: detach and run daemon
        os.setsid()
        # Redirect stdout/stderr to devnull
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.close(devnull)
        try:
            asyncio.run(run_daemon(proxy, headed, seed))
        finally:
            os._exit(0)
    else:
        # Parent: wait for daemon to be ready
        import time
        for _ in range(100):  # up to 10 seconds
            time.sleep(0.1)
            if is_daemon_running():
                return
        print("Error: Daemon failed to start", file=sys.stderr)
        sys.exit(1)


def ensure_daemon(proxy: str | None, headed: bool, seed: int | None):
    """Ensure daemon is running, start if not."""
    if not is_daemon_running():
        start_daemon_background(proxy, headed, seed)


def stop_daemon():
    """Stop the daemon by sending close command."""
    if is_daemon_running():
        try:
            send_command({"action": "close"})
        except:
            pass
    # Clean up stale files
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text())
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
        PID_FILE.unlink(missing_ok=True)
    SOCKET_PATH.unlink(missing_ok=True)


# ========================
# CLI Entry Point
# ========================

def format_result(result: dict, action: str) -> str:
    """Format a command result for human-readable output."""
    if "error" in result:
        return f"Error: {result['error']}"

    match action:
        case "open":
            return f"\u2713 {result.get('title', 'Untitled')}\n  {result.get('url', '')}"
        case "snapshot":
            return result.get("snapshot", "")
        case "screenshot":
            return f"\u2713 Screenshot saved to {result.get('path', '?')}"
        case "get":
            return result.get("value", "")
        case "close":
            return "\u2713 Browser closed"
        case _:
            if result.get("ok"):
                return "\u2713 Done"
            return json.dumps(result)


def main():
    parser = argparse.ArgumentParser(
        prog="fingerprint",
        description="Anti-detection browser automation CLI",
    )
    parser.add_argument("--proxy", help="Proxy server URL")
    parser.add_argument("--headed", action="store_true", help="Force headed mode (show browser window)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default)")
    parser.add_argument("--no-fallback", action="store_true", help="Disable automatic fallback to headed mode on challenge detection")
    parser.add_argument("--seed", type=int, help="Fingerprint seed (random if omitted)")

    sub = parser.add_subparsers(dest="command")

    # open
    p_open = sub.add_parser("open", help="Navigate to URL")
    p_open.add_argument("url")

    # snapshot
    p_snap = sub.add_parser("snapshot", help="Get page accessibility snapshot")
    p_snap.add_argument("-i", "--interactive", action="store_true", help="Interactive elements only")

    # click
    p_click = sub.add_parser("click", help="Click element")
    p_click.add_argument("ref", help="Element ref (e.g. @e1)")

    # fill
    p_fill = sub.add_parser("fill", help="Clear and type text")
    p_fill.add_argument("ref")
    p_fill.add_argument("text")

    # type
    p_type = sub.add_parser("type", help="Type text without clearing")
    p_type.add_argument("ref")
    p_type.add_argument("text")

    # select
    p_sel = sub.add_parser("select", help="Select dropdown option")
    p_sel.add_argument("ref")
    p_sel.add_argument("values", nargs="+")

    # press
    p_press = sub.add_parser("press", help="Press key")
    p_press.add_argument("key")

    # scroll
    p_scroll = sub.add_parser("scroll", help="Scroll page")
    p_scroll.add_argument("direction", choices=["up", "down", "left", "right"], default="down", nargs="?")
    p_scroll.add_argument("amount", type=int, default=300, nargs="?")

    # screenshot
    p_ss = sub.add_parser("screenshot", help="Take screenshot")
    p_ss.add_argument("path", nargs="?", help="Output path (default: temp dir)")

    # wait
    p_wait = sub.add_parser("wait", help="Wait for condition")
    p_wait.add_argument("target", nargs="?", help="@ref, milliseconds, or omit for flags")
    p_wait.add_argument("--load", "-l", help="Wait for load state (networkidle, load, domcontentloaded)")
    p_wait.add_argument("--url", "-u", help="Wait for URL pattern")
    p_wait.add_argument("--text", "-t", help="Wait for text to appear")

    # get
    p_get = sub.add_parser("get", help="Get information")
    p_get.add_argument("what", choices=["text", "url", "title", "value", "html"])
    p_get.add_argument("ref", nargs="?", help="Element ref for text/value/html")

    # close
    sub.add_parser("close", help="Close browser")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Headed if explicitly requested, otherwise headless (default)
    headed = args.headed

    # Handle close specially
    if args.command == "close":
        stop_daemon()
        print(format_result({"ok": True, "closed": True}, "close"))
        return

    # Ensure daemon is running
    ensure_daemon(args.proxy, headed, args.seed)

    # Build command
    cmd = _build_command(args)

    result = send_command(cmd)

    # Fallback: if open detected a challenge and we're headless, retry headed
    if (
        args.command == "open"
        and result.get("challenged")
        and not headed
        and not args.no_fallback
    ):
        print(f"! Challenge detected (\"{result.get('title', '?')}\"), restarting in headed mode...")
        stop_daemon()
        import time
        time.sleep(0.5)
        ensure_daemon(args.proxy, True, args.seed)
        result = send_command(cmd)
        if result.get("challenged"):
            print("! Still challenged in headed mode — may need a residential proxy")

    print(format_result(result, args.command))


def _build_command(args) -> dict:
    """Build a daemon command dict from parsed CLI args."""
    match args.command:
        case "open":
            return {"action": "open", "url": args.url}
        case "snapshot":
            return {"action": "snapshot", "interactive": args.interactive}
        case "click":
            return {"action": "click", "ref": args.ref}
        case "fill":
            return {"action": "fill", "ref": args.ref, "text": args.text}
        case "type":
            return {"action": "type", "ref": args.ref, "text": args.text}
        case "select":
            return {"action": "select", "ref": args.ref, "values": args.values}
        case "press":
            return {"action": "press", "key": args.key}
        case "scroll":
            return {"action": "scroll", "direction": args.direction, "amount": args.amount}
        case "screenshot":
            return {"action": "screenshot", "path": args.path}
        case "wait":
            if args.load:
                return {"action": "wait", "load": args.load}
            elif args.url:
                return {"action": "wait", "url": args.url}
            elif args.text:
                return {"action": "wait", "text": args.text}
            elif args.target:
                if args.target.startswith("@"):
                    return {"action": "wait", "ref": args.target}
                else:
                    return {"action": "wait", "ms": int(args.target)}
            else:
                print("Error: wait requires a target or --load/--url/--text flag")
                sys.exit(1)
        case "get":
            cmd = {"action": "get", "what": args.what}
            if args.ref:
                cmd["ref"] = args.ref
            return cmd
    return {}


if __name__ == "__main__":
    main()
