# Bundling

One codebase. Two bundles. Build on the platform you're targeting.

---

## Prerequisites

Run the standard setup first (once per machine):

```bash
# macOS or Windows
python setup.py        # creates .venv, installs deps, downloads Playwright browser
```

Then generate icon assets (once, or whenever you update the icon):

```bash
# Generates placeholder icons (no source image needed)
make icons
# or
python scripts/make_icons.py --placeholder

# Use your own 1024x1024 PNG
python scripts/make_icons.py --source path/to/icon.png
```

---

## macOS — py2app

### Install py2app

```bash
pip install py2app
# or
make bundle-mac   # installs py2app automatically if missing
```

### Development alias build (recommended for daily use)

Creates a `.app` that symlinks back to source — code changes are live without rebuilding.

```bash
make alias
# or
python bundle_mac.py py2app --alias
open "dist/Mad Automation Platform.app"
```

The alias `.app` only works on the build machine. Use the production build for anything you want to move or share.

### Production build

Fully self-contained `.app`. No Python installation required on the target machine.

```bash
make bundle-mac
# or
python bundle_mac.py py2app
```

Output: `dist/Mad Automation Platform.app`

Run from anywhere — no installation required:

```bash
open "dist/Mad Automation Platform.app"
# or double-click in Finder
```

Optional: copy to `/Applications` so Spotlight and Launchpad find it:

```bash
cp -r "dist/Mad Automation Platform.app" /Applications/
```

### First run on a new machine

macOS Gatekeeper will block an app that isn't notarized. For a personal tool:

1. Right-click `Mad Automation Platform.app` in Finder
2. Click **Open**
3. Click **Open** in the dialog

After the first open, it launches normally.

Playwright's browser (`~/.cache/ms-playwright/chromium-*`) must exist on the machine. It's installed during `setup.py` but if distributing to a new machine, run once:

```bash
python -m playwright install chromium
```

### Icon source files

| File | Used for |
|------|---------|
| `ui/assets/app.icns` | App bundle icon (Dock, Finder) |
| `ui/assets/menubar_icon.png` | Status bar — idle state (22×22) |
| `ui/assets/menubar_icon@2x.png` | Status bar — idle state retina (44×44) |
| `ui/assets/menubar_running.png` | Status bar — running state (22×22) |
| `ui/assets/menubar_error.png` | Status bar — error state (22×22) |

To replace the placeholder icons with your own artwork, run:

```bash
python scripts/make_icons.py --source your_icon_1024x1024.png
```

Then rebuild the bundle.

### Updating the bundle

After any code change, the alias build picks up changes automatically. For a production build, re-run `make bundle-mac`. The build takes 30–90 seconds depending on dependency count.

---

## Windows — PyInstaller

Run these commands on a **Windows machine** (not on Mac).

### Install PyInstaller

```bash
pip install pyinstaller
```

### Build

```bash
make bundle-win
# or
python -m PyInstaller mad_platform.spec
```

Output: `dist\Mad Automation Platform\Mad Automation Platform.exe`

Run from anywhere — no installation required. The entire `dist\Mad Automation Platform\` folder is the distributable; the `.exe` inside it is the entry point.

### First run on a new Windows machine

Playwright's browser must be installed:

```bash
python -m playwright install chromium
```

The Task Scheduler tasks written by `engine/scheduler.py` target the `.venv\Scripts\python.exe` path. If moving to a new machine, re-save any schedules from the UI to regenerate the task with the correct path.

### Windows-specific dependencies

These are installed automatically by `pip install -r requirements.txt` on Windows (the `sys_platform` markers in requirements.txt restrict them to Windows only):

| Package | Purpose |
|---------|---------|
| `pystray` | System tray icon and menu |
| `winotify` | Windows toast notifications |
| `Pillow` | Required by pystray for icon rendering |
| `mss` | Cross-platform screen capture (replaces Quartz on Windows) |

### Console window

`console=False` in `mad_platform.spec` suppresses the console window entirely. If you need to see stdout for debugging, temporarily change this to `console=True` and rebuild.

---

## What the bundle contains

Both bundles include:

- The Python runtime
- All dependencies from `requirements.txt` (platform-appropriate subset)
- `ui/` — HTML/JS/CSS
- `sources/` — flow YAMLs, block definitions, custom actions
- `engine/` — all engine modules

Both bundles **exclude**:

- `data/` — runtime data stays local to each machine, never bundled
- `.venv/` — the bundle has its own embedded Python
- Gmail OAuth credentials — always stored at `~/.mad_automation_platform/`

---

## Build targets summary

| Command | Platform | Output | Install required? |
|---------|----------|--------|-------------------|
| `make alias` | macOS (dev) | `dist/Mad Automation Platform.app` (symlinked) | No |
| `make bundle-mac` | macOS | `dist/Mad Automation Platform.app` | No |
| `make bundle-win` | Windows | `dist\Mad Automation Platform\*.exe` | No |
| `make run` | Either (dev) | — (runs from source) | No |
| `make icons` | Either | `ui/assets/*.icns, *.ico, *.png` | No |
