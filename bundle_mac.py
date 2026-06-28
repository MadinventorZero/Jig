"""
py2app build script — macOS .app bundle.

Development (symlinks, no rebuild on code change):
    python bundle_mac.py py2app --alias

Production (self-contained, distributable):
    python bundle_mac.py py2app

Output: dist/Mad Automation Platform.app
Run from anywhere — no installation required.
"""
from setuptools import setup

APP      = ["run.py"]
OPTIONS  = {
    "argv_emulation": False,   # must be False for pywebview apps
    "plist": {
        "CFBundleName":               "Mad Automation Platform",
        "CFBundleDisplayName":        "Mad Automation Platform",
        "CFBundleIdentifier":         "com.madautomation.platform",
        "CFBundleVersion":            "4.0.0",
        "CFBundleShortVersionString": "4.0",
        "NSHighResolutionCapable":    True,
        "LSMinimumSystemVersion":     "13.0",
        "LSUIElement":                True,   # menu bar only — no Dock icon
    },
    "packages": [
        "webview",
        "engine",
        "sources",
        "audit",
        "rumps",
        "yaml",
        "jinja2",
        "anthropic",
        "google",
        "googleapiclient",
        "playwright",
        "mss",
        "PIL",
    ],
    "includes": [
        "pkg_resources",
        "cv2",
        "pyautogui",
    ],
    "excludes": [
        "tkinter",
        "matplotlib",
        "pystray",
        "winotify",
        "test",
    ],
    "iconfile": "ui/assets/app.icns",
}

setup(
    app=APP,
    name="Mad Automation Platform",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
