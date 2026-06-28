# Running the Platform

Three modes. Use the one that fits the context.

---

## 1. Development mode — plain Python

```bash
# From the repo root (venv active)
python run.py
# or
make run
```

On **macOS**: if `rumps` is installed, the app starts as a menu bar app — no Dock icon, no terminal window. Click the menu bar icon to open the dashboard. If `rumps` is not installed, the window appears directly and the terminal stays open.

On **Windows**: if `pystray` is installed, the app starts in the system tray. Otherwise the window appears directly.

On either platform, the shell that launched it stays occupied. Close the app to free the terminal, or run it in a background process (`python run.py &` on Mac/Linux).

### With the alias bundle (recommended for Mac development)

```bash
make alias
# or
python bundle_mac.py py2app --alias
open "dist/Mad Automation Platform.app"
```

The alias build creates a `.app` that symlinks back to source files — code changes are live without rebuilding. This gives you the full bundled experience (menu bar, no terminal, proper app name) while still being able to edit code directly.

---

## 2. Bundled app — production

See [bundling.md](bundling.md) for how to build. Once built:

**macOS:**
```bash
open "dist/Mad Automation Platform.app"
# or double-click in Finder
```

**Windows:**
```
dist\Mad Automation Platform\Mad Automation Platform.exe
```

Both run from wherever they sit — no installation required. Copy to `/Applications` (Mac) or `%PROGRAMFILES%` (Windows) if you want Spotlight/Launchpad/Start Menu to find them, but it's optional.

The bundled app starts as a menu bar / system tray app. No terminal. No Python process visible.

---

## 3. Headless CLI — scheduled runs

`run_flow.py` is the CLI entry point for launchd-triggered and Task Scheduler runs. It does not open any UI.

```bash
# Run a flow directly
python run_flow.py --flow-id booking_bh --profile-id <id>

# Validate a flow without running it
python run_flow.py --flow-id booking_bh --validate

# List all available flows
python run_flow.py --list-flows

# Resume a failed run from its last checkpoint
python run_flow.py --resume-run <run_id>

# Show the browser window (useful for debugging)
python run_flow.py --flow-id booking_bh --profile-id <id> --show-browser

# Stream live events to stdout
python run_flow.py --flow-id booking_bh --profile-id <id> --log-events
```

When the platform is bundled, scheduled runs still invoke `run_flow.py` directly via the venv Python (not the bundled app). The scheduler writes launchd plists / Task Scheduler tasks that call:

```
.venv/bin/python run_flow.py --flow-id <id> --profile-id <id>
```

This keeps scheduled execution independent of whether the UI app is open.

---

## Menu bar / tray controls

| Action | macOS | Windows |
|--------|-------|---------|
| Open dashboard | Click menu bar icon → Open Dashboard | Double-click tray icon |
| Hide dashboard | Click menu bar icon → Open Dashboard (toggles) | Right-click tray → hide |
| Run BH flow now | Click menu bar icon → Run Beverly Hills Flow | — |
| Quit | Click menu bar icon → Quit | Right-click tray → Quit |

---

## Status icons

The menu bar / tray icon changes state to reflect what the platform is doing:

| Icon | Meaning |
|------|---------|
| Default (dark "M") | Idle — no flows running |
| Green tint | A flow is currently executing |
| Red tint | Last flow run failed — open dashboard to inspect |

---

## Logs

All run events are written to SQLite at `data/platform.db`. Flow run stdout/stderr from launchd-triggered runs are written to:

```
data/logs/<schedule_id>-out.log
data/logs/<schedule_id>-err.log
```

The dashboard's History view reads from SQLite — it shows the same information regardless of how the run was started.
