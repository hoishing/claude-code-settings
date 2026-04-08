# Command Reference

Complete reference for all fingerprint-browser commands.

All commands use the pattern:
```bash
FP=~/.agents/skills/fingerprint-browser/scripts/fingerprint.py
uv run "$FP" <command> [options]
```

## Navigation

```bash
uv run "$FP" open <url>      # Navigate to URL
                              # Auto-prepends https:// if no protocol given
                              # Supports: https://, http://, file://, data:, about:
uv run "$FP" close            # Close browser and stop daemon
```

## Snapshot (page analysis)

```bash
uv run "$FP" snapshot         # Full accessibility tree with refs
uv run "$FP" snapshot -i      # Interactive elements only (recommended)
```

### Snapshot Output Format

```
Page: Example Site
URL: https://example.com

- link "Home" [ref=e1]
- link "Products" [ref=e2]
- button "Sign In" [ref=e3]
- textbox "Email" [ref=e4]
- textbox "Password" [ref=e5]
- button "Log In" [ref=e6]
```

Interactive roles that receive refs: link, button, textbox, checkbox, radio, combobox, listbox, menuitem, option, searchbox, slider, spinbutton, switch, tab, treeitem.

## Interactions (use @refs from snapshot)

```bash
uv run "$FP" click @e1            # Click element
uv run "$FP" fill @e2 "text"      # Clear input and type text
uv run "$FP" type @e2 "text"      # Type without clearing
uv run "$FP" select @e1 "value"   # Select dropdown option
uv run "$FP" select @e1 "a" "b"   # Select multiple options
uv run "$FP" press Enter           # Press key
uv run "$FP" press Control+a       # Key combination
uv run "$FP" scroll down 500       # Scroll page (default: down 300px)
uv run "$FP" scroll up 500         # Scroll up
```

## Get Information

```bash
uv run "$FP" get text @e1     # Get element text content
uv run "$FP" get value @e1    # Get input value
uv run "$FP" get html @e1     # Get innerHTML
uv run "$FP" get title        # Get page title
uv run "$FP" get url          # Get current URL
```

## Screenshots

```bash
uv run "$FP" screenshot              # Save to temp directory
uv run "$FP" screenshot path.png     # Save to specific path
```

## Wait

```bash
uv run "$FP" wait @e1                     # Wait for element to appear
uv run "$FP" wait 2000                    # Wait milliseconds
uv run "$FP" wait --text "Success"        # Wait for text to appear
uv run "$FP" wait --url "**/dashboard"    # Wait for URL pattern
uv run "$FP" wait --load networkidle      # Wait for network idle
uv run "$FP" wait --load load             # Wait for load event
uv run "$FP" wait --load domcontentloaded # Wait for DOMContentLoaded
```

## Global Options

```bash
uv run "$FP" --proxy <url> ...       # Proxy server (http, https, socks5)
uv run "$FP" --headless ...          # Run headless (not recommended for anti-detection)
uv run "$FP" --headed ...            # Show browser window (default)
uv run "$FP" --seed <int> ...        # Fixed fingerprint seed for reproducibility
```

## Daemon Architecture

The browser runs as a background daemon process, communicating via Unix socket at `~/.fingerprint-browser/daemon.sock`. The first command (`open`) starts the daemon automatically. Subsequent commands connect to it.

```bash
# Daemon starts automatically on first command
uv run "$FP" open https://example.com

# All subsequent commands reuse the same browser
uv run "$FP" snapshot -i
uv run "$FP" click @e1

# Close stops the daemon
uv run "$FP" close
```

### Daemon Files

| Path | Purpose |
|------|---------|
| `~/.fingerprint-browser/daemon.sock` | Unix socket for IPC |
| `~/.fingerprint-browser/daemon.pid` | Daemon process ID |
| `~/.fingerprint-browser/refs.json` | Current ref mappings |
| `~/.fingerprint-browser/chromium/` | fingerprint-chromium binary |

## Anti-Detection Details

### What Gets Spoofed (C++ engine level)

| Signal | Spoofed By |
|--------|-----------|
| Canvas fingerprint | fingerprint-chromium |
| WebGL renderer/vendor | fingerprint-chromium |
| AudioContext | fingerprint-chromium |
| Font list | fingerprint-chromium |
| navigator.webdriver | fingerprint-chromium |
| navigator.hardwareConcurrency | fingerprint-chromium |
| navigator.deviceMemory | fingerprint-chromium |
| Client Hints | fingerprint-chromium |
| Runtime.enable CDP | rebrowser-playwright |
| Console.enable CDP | rebrowser-playwright |
| sourceURL annotations | rebrowser-playwright |

### Proxy Support

For best anti-detection results, use a residential proxy:

```bash
uv run "$FP" --proxy "http://user:pass@residential-proxy:8080" open https://target.com
```

Proxy is set at browser launch and applies to all subsequent commands in the session. To change proxy, close and reopen with new proxy.
