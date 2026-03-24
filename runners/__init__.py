"""
Auto-discovery for runner modules.

Each module in runners/ should define a `RUNNERS` list of runner class instances,
or a `get_runners()` function that returns such a list.

To add a new runner:
  1. Create a file in runners/ (e.g. runners/myrunner.py)
  2. Define a class with a `match(self, query: str) -> list[SearchResult]` method
  3. Add `RUNNERS = [MyRunner()]` at module level
"""

import importlib
import logging
import os
import pkgutil
import sys
from pathlib import Path

_LOG = logging.getLogger("just.runners")

from core.plugins import discover_plugin_runners

_RUNNERS_CACHE: list | None = None


def discover_runners(*, _reload: bool = False) -> list:
    """Import all modules in the runners package, then user plugins."""
    global _RUNNERS_CACHE
    if (
        _RUNNERS_CACHE is not None
        and not _reload
        and not os.environ.get("JUST_RELOAD_RUNNERS")
    ):
        return _RUNNERS_CACHE

    all_runners: list = []
    pkg_path = str(Path(__file__).parent)

    for _, module_name, _ in pkgutil.iter_modules([pkg_path]):
        if module_name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"runners.{module_name}")
        except Exception as e:
            _LOG.warning("Failed to load runners.%s: %s", module_name, e)
            _LOG.debug("runners.%s import traceback", module_name, exc_info=True)
            continue

        if hasattr(mod, "get_runners"):
            all_runners.extend(mod.get_runners())
        elif hasattr(mod, "RUNNERS"):
            all_runners.extend(mod.RUNNERS)

    all_runners.extend(discover_plugin_runners())
    _RUNNERS_CACHE = all_runners
    return all_runners
