#!/usr/bin/env python3
"""Entry point called by the platform launcher."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

import app

app.main()
