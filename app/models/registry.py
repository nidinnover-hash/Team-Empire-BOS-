from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache

import app.models as models_pkg


@lru_cache(maxsize=1)
def load_all_models() -> None:
    """Import all model modules so SQLAlchemy metadata is fully registered."""
    for mod in pkgutil.iter_modules(models_pkg.__path__):
        name = mod.name
        if name.startswith("_") or name in {"registry"}:
            continue
        importlib.import_module(f"{models_pkg.__name__}.{name}")
