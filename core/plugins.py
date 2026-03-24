"""Load third-party runners from ~/.local/share/just/plugins/*.py."""

import importlib.util
import sys
from pathlib import Path

from core.config import DATA_DIR

_PLUGINS_DIR = DATA_DIR / "plugins"


def discover_plugin_runners() -> list:
    _PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    out: list = []
    for path in sorted(_PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        mod_name = f"just_user_plugin_{path.stem}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:
            print(f"[just/plugins] {path.name}: {e}", file=sys.stderr)
            continue
        if hasattr(mod, "get_runners"):
            try:
                out.extend(mod.get_runners())
            except Exception as e:
                print(f"[just/plugins] get_runners {path.name}: {e}", file=sys.stderr)
        elif hasattr(mod, "RUNNERS"):
            try:
                out.extend(mod.RUNNERS)
            except Exception as e:
                print(f"[just/plugins] RUNNERS {path.name}: {e}", file=sys.stderr)
    return out
