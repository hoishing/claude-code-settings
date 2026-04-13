---
name: fingerprint-browser
description: Anti-detection browser automation using fingerprint-chromium + Rebrowser. Use when standard browser automation (agent-browser) is blocked by Cloudflare, bot detection, or WAFs. Provides same snapshot/ref workflow as agent-browser with C++ fingerprint spoofing and CDP signal masking. Triggers include "use fingerprint browser", "bypass cloudflare", "anti-detect browser", "stealth browser", or when agent-browser fails due to bot detection.
allowed-tools: Bash(uv run*fingerprint.py:*), Bash(fingerprint:*)
---

# Anti-Detection Browser Automation with fingerprint-browser

Uses **fingerprint-chromium** (C++ engine-level fingerprint spoofing) + **rebrowser-playwright** (CDP signal masking) to bypass bot detection systems including Cloudflare.

## Platform support

The script detects the host platform and configures the browser automatically:

| Platform | Browser | Fingerprint spoofing |
|----------|---------|----------------------|
| macOS (arm64 / x86_64) | `~/.fingerprint-browser/chromium/Chromium.app/Contents/MacOS/Chromium` (fingerprint-chromium) | full (engine-level + CDP) |
| Linux x86_64 | `~/.fingerprint-browser/chromium/chrome` (fingerprint-chromium) | full (engine-level + CDP) |
| Linux aarch64 | rebrowser-playwright bundled chromium (no upstream fingerprint-chromium aarch64 build) | CDP masking only |
| Windows | `~/.fingerprint-browser/chromium/chrome.exe` | full (engine-level + CDP) |

If the platform-specific fingerprint-chromium binary is missing, the script falls back to rebrowser-playwright's bundled chromium — CDP signal masking still applies, but `--fingerprint=*` engine-level args are dropped. Install fingerprint-chromium from https://github.com/adryfish/fingerprint-chromium/releases into `~/.fingerprint-browser/chromium/` to enable full spoofing.

**Python 3.13+ required** on Linux aarch64: greenlet segfaults under Python 3.12 on that platform.

## Core Workflow

Every automation follows the same pattern as agent-browser:

1. **Navigate**: `fingerprint open <url>`
2. **Snapshot**: `fingerprint snapshot -i` (get element refs like `@e1`, `@e2`)
3. **Interact**: Use refs to click, fill, select
4. **Re-snapshot**: After navigation or DOM changes, get fresh refs

```bash
FP=~/.agents/skills/fingerprint-browser/scripts/fingerprint.py

uv run "$FP" open https://example.com/form
uv run "$FP" snapshot -i
# Output: - link "Sign In" [ref=e1]
#         - textbox "Email" [ref=e2]
#         - textbox "Password" [ref=e3]
#         - button "Submit" [ref=e4]

uv run "$FP" fill @e2 "user@example.com"
uv run "$FP" fill @e3 "password123"
uv run "$FP" click @e4
uv run "$FP" wait --load networkidle
uv run "$FP" snapshot -i  # Check result
```

## Command Chaining

Commands can be chained with `&&`. The browser persists between commands via a background daemon.

```bash
# Chain open + wait + snapshot
uv run "$FP" open https://example.com && uv run "$FP" wait --load networkidle && uv run "$FP" snapshot -i

# Chain multiple interactions
uv run "$FP" fill @e2 "user@example.com" && uv run "$FP" fill @e3 "password" && uv run "$FP" click @e4
```

## Essential Commands

```bash
# Navigation
uv run "$FP" open <url>              # Navigate (auto-prepends https://)
uv run "$FP" close                   # Close browser and daemon

# Snapshot
uv run "$FP" snapshot -i             # Interactive elements with refs (recommended)
uv run "$FP" snapshot                # Full accessibility tree with refs

# Interaction (use @refs from snapshot)
uv run "$FP" click @e1               # Click element
uv run "$FP" fill @e2 "text"         # Clear and type text
uv run "$FP" type @e2 "text"         # Type without clearing
uv run "$FP" select @e1 "option"     # Select dropdown option
uv run "$FP" press Enter             # Press key
uv run "$FP" scroll down 500         # Scroll page

# Get information
uv run "$FP" get text @e1            # Get element text
uv run "$FP" get url                 # Get current URL
uv run "$FP" get title               # Get page title
uv run "$FP" get value @e1           # Get input value

# Wait
uv run "$FP" wait @e1                # Wait for element
uv run "$FP" wait --load networkidle # Wait for network idle
uv run "$FP" wait --url "**/page"    # Wait for URL pattern
uv run "$FP" wait --text "Success"   # Wait for text
uv run "$FP" wait 2000               # Wait milliseconds

# Capture
uv run "$FP" screenshot              # Screenshot to temp dir
uv run "$FP" screenshot page.png     # Screenshot to specific path
```

## Anti-Detection Features

- **C++ fingerprint spoofing**: Canvas, WebGL, AudioContext, fonts, navigator, hardware — all spoofed at engine level
- **CDP signal masking**: `Runtime.enable` and other automation-revealing CDP commands removed by rebrowser-playwright
- **WebRTC leak prevention**: `--disable-non-proxied-udp` prevents IP leaks
- **navigator.webdriver = false**: Automatically masked by fingerprint-chromium
- **Randomized fingerprint**: Each session gets a unique fingerprint seed

## Global Options

```bash
uv run "$FP" --proxy "http://user:pass@proxy:port" open <url>  # Use proxy
uv run "$FP" --headed open <url>                                 # Force headed mode (show browser window)
uv run "$FP" --no-fallback open <url>                            # Disable auto fallback to headed
uv run "$FP" --seed 12345 open <url>                             # Fixed fingerprint seed
```

## Automatic Headed Fallback

By default, the browser runs in **headless** mode. If a bot challenge is detected on `open` (Cloudflare interstitial, "Verify you are human", etc.), the browser automatically restarts in **headed** mode and retries. This gives you the speed of headless for normal sites with the detection-resistance of headed when needed.

Use `--no-fallback` to disable this behavior, or `--headed` to always start headed.

## Ref Lifecycle

Refs (`@e1`, `@e2`, etc.) are invalidated when the page changes. Always re-snapshot after:
- Clicking links or buttons that navigate
- Form submissions
- Dynamic content loading

## When to Use This vs agent-browser

| Scenario | Use |
|----------|-----|
| Normal websites, no bot detection | `agent-browser` |
| Cloudflare-protected sites | `fingerprint` |
| Sites blocking automation tools | `fingerprint` |
| Bot detection test sites | `fingerprint` |
| Need video recording, tabs, network interception | `agent-browser` |

## Troubleshooting

### Daemon not responding
```bash
uv run "$FP" close
# Wait a moment, then retry your command
```

### Ref not found
```bash
# Re-snapshot to get fresh refs
uv run "$FP" snapshot -i
```

### Still detected by Cloudflare
- Add a residential proxy: `--proxy "http://user:pass@residential-proxy:port"`
- Use headed mode (default) instead of headless
- Ensure fingerprint-chromium binary is up to date

## Deep-Dive Documentation

| Reference | When to Use |
|-----------|-------------|
| [references/commands.md](references/commands.md) | Full command reference |
