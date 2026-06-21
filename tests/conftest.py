"""Shared pytest setup: run Qt headless so GUI tests need no display."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
