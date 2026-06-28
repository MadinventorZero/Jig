# PyInstaller spec — Windows build
# Run on a Windows machine: pyinstaller mad_platform.spec
# Output: dist/Mad Automation Platform/ (folder) + Mad Automation Platform.exe inside it
# No installation required — run the .exe from anywhere.

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("ui/",      "ui/"),
        ("sources/", "sources/"),
        ("engine/",  "engine/"),
        ("audit/",   "audit/"),
    ],
    hiddenimports=[
        "webview",
        "webview.platforms.winforms",
        "pystray",
        "pystray._win32",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "mss",
        "mss.windows",
        "yaml",
        "jinja2",
        "jinja2.ext",
        "anthropic",
        "playwright",
        "playwright.sync_api",
        "cv2",
        "winotify",
        "pkg_resources",
        "pkg_resources.extern",
        "google.auth",
        "google.oauth2",
        "googleapiclient",
        "pyautogui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "rumps",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Mad Automation Platform",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,              # no console window — critical flag
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="ui/assets/app.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Mad Automation Platform",
)
