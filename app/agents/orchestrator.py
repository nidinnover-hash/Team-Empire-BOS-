"""Compatibility wrapper for the extracted Brain Engine drafting module."""

import importlib
import sys

_real = importlib.import_module("app.engines.brain.drafting")
sys.modules[__name__] = _real
