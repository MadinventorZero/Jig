#!/bin/bash
# Mad Booking Agent — macOS setup bootstrap
# Installs pyenv if needed, pins Python from .python-version, then runs setup.py
cd "$(dirname "$0")" || {
    echo "ERROR: Could not change to script directory."
    read -rp "  Press Enter to exit..."
    exit 1
}

echo ""
echo "======================================"
echo "  Mad Booking Agent — Setup"
echo "======================================"
echo ""

fail() {
    local msg="$1"
    local fix="${2:-}"
    echo ""
    echo "  ERROR: $msg"
    if [ -n "$fix" ]; then
        echo ""
        echo "  $fix"
    fi
    echo ""
    read -rp "  Press Enter to exit..."
    exit 1
}

# --- Read required Python version ---
if [ ! -f ".python-version" ]; then
    fail ".python-version file not found." "Re-clone the repository to restore it."
fi
REQUIRED_PY=$(tr -d '[:space:]' < .python-version)
if [ -z "$REQUIRED_PY" ]; then
    fail ".python-version is empty." "Re-clone the repository to restore it."
fi
echo "  Target Python: $REQUIRED_PY"
echo ""

# --- Locate pyenv ---
PYENV_CMD=""
for candidate in \
    "$(command -v pyenv 2>/dev/null)" \
    /opt/homebrew/bin/pyenv \
    /usr/local/bin/pyenv \
    "$HOME/.pyenv/bin/pyenv"; do
    if [ -x "$candidate" ]; then
        PYENV_CMD="$candidate"
        break
    fi
done

# --- Install pyenv via Homebrew if not found ---
if [ -z "$PYENV_CMD" ]; then
    echo "  pyenv not found. Attempting install via Homebrew..."
    echo ""

    BREW=""
    for brew_path in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        [ -f "$brew_path" ] && BREW="$brew_path" && break
    done

    if [ -n "$BREW" ]; then
        "$BREW" install pyenv || fail \
            "Homebrew failed to install pyenv." \
            "Try manually: brew install pyenv  then re-run this script."
        for candidate in /opt/homebrew/bin/pyenv /usr/local/bin/pyenv; do
            [ -x "$candidate" ] && PYENV_CMD="$candidate" && break
        done
    fi

    if [ -z "$PYENV_CMD" ]; then
        fail \
            "pyenv not found and could not be installed automatically." \
            "Option A — Install Homebrew, then re-run this script:
    https://brew.sh

  Option B — Install pyenv directly, then re-run this script:
    https://github.com/pyenv/pyenv#installation"
    fi
fi

echo "  Found pyenv: $PYENV_CMD"
echo ""

# --- Resolve pyenv root ---
PYENV_ROOT=$("$PYENV_CMD" root 2>/dev/null)
if [ -z "$PYENV_ROOT" ]; then
    fail "Could not determine pyenv root directory." "Verify pyenv is intact: $PYENV_CMD root"
fi

# --- Install required Python if missing ---
PYTHON_CMD="$PYENV_ROOT/versions/$REQUIRED_PY/bin/python3"
if [ ! -x "$PYTHON_CMD" ]; then
    echo "  Python $REQUIRED_PY not installed. Installing (this may take a few minutes)..."
    echo ""
    "$PYENV_CMD" install "$REQUIRED_PY" || fail \
        "pyenv failed to install Python $REQUIRED_PY." \
        "Try manually: pyenv install $REQUIRED_PY
  If you see a build error, install Xcode Command Line Tools first:
    xcode-select --install"
fi

if [ ! -x "$PYTHON_CMD" ]; then
    fail "Python $REQUIRED_PY was installed but binary not found." \
         "Expected: $PYTHON_CMD — try: pyenv install $REQUIRED_PY --force"
fi

echo "  Using: $("$PYTHON_CMD" --version 2>&1)"
echo ""

"$PYTHON_CMD" setup.py
SETUP_EXIT=$?
if [ "$SETUP_EXIT" -ne 0 ]; then
    echo ""
    echo "  Setup did not complete (exit code $SETUP_EXIT)."
    echo "  See the error above, then re-run this script."
    echo ""
    read -rp "  Press Enter to exit..."
    exit "$SETUP_EXIT"
fi
