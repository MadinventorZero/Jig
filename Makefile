# Mad Automation Platform — build and run targets
PYTHON := .venv/bin/python
PYTHON_WIN := .venv\Scripts\python.exe

.PHONY: run alias bundle-mac bundle-win icons clean install

## ── Development ──────────────────────────────────────────────────────────────

run:
	$(PYTHON) run.py

# macOS: build .app with symlinks — code changes are live, no rebuild needed
alias:
	$(PYTHON) bundle_mac.py py2app --alias
	@echo "Built: dist/Mad Automation Platform.app (alias mode)"
	@echo "Run:   open 'dist/Mad Automation Platform.app'"

## ── Production bundles ───────────────────────────────────────────────────────

# macOS: self-contained .app — run from anywhere, no install required
bundle-mac:
	@which py2app > /dev/null 2>&1 || $(PYTHON) -m pip install py2app
	$(PYTHON) bundle_mac.py py2app
	@echo "Built: dist/Mad Automation Platform.app"
	@echo "Run:   open 'dist/Mad Automation Platform.app'"

# Windows: run this target on a Windows machine
bundle-win:
	$(PYTHON_WIN) -m pip install pyinstaller
	$(PYTHON_WIN) -m PyInstaller mad_platform.spec
	@echo Built: dist/Mad Automation Platform/Mad Automation Platform.exe

## ── Assets ───────────────────────────────────────────────────────────────────

# Generate placeholder icons (no source image needed)
icons:
	$(PYTHON) scripts/make_icons.py --placeholder

# Generate icons from your own 1024x1024 PNG: make icons-from SOURCE=path/to/icon.png
icons-from:
	$(PYTHON) scripts/make_icons.py --source $(SOURCE)

## ── Setup ────────────────────────────────────────────────────────────────────

install:
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m playwright install chromium

## ── Cleanup ──────────────────────────────────────────────────────────────────

clean:
	rm -rf build dist
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
