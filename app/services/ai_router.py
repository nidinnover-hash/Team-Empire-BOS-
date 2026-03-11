"""Compatibility wrapper for the extracted Brain Engine router module.

All AI router logic now lives in app.engines.brain.router.
This module makes sys.modules point here to the actual module so that
`from app.services import ai_router` and
`from app.services.ai_router import _private_name` both work,
AND monkeypatch.setattr(ai_router, "_call_provider", fake) patches
the real function used by call_ai().
"""

import importlib
import sys

# Re-export for type checkers (at runtime sys.modules replace below wins)
from app.engines.brain.router import call_ai as call_ai

# Import the real module
_real = importlib.import_module("app.engines.brain.router")

# Replace this module in sys.modules with the real one, so all imports
# of `app.services.ai_router` resolve to `app.engines.brain.router`.
sys.modules[__name__] = _real
