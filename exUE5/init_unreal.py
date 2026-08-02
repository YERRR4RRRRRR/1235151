"""Editor startup hook for the exUE5 / PLUGSY Exporter plugin.

Unreal Engine automatically executes any file named `init_unreal.py` that it
finds on the Python sys.path when the editor starts. Until now this project
had no such hook, so the PLUGSY Exporter menu only appeared after someone
manually ran Tools -> Execute Python Script -> install.py in every new
editor session, and it never survived a restart.

HOW TO ENABLE THIS FILE
------------------------
Unreal only picks up `init_unreal.py` automatically from folders that are
already on its Python search path. Do ONE of the following:

1. (Simplest) Keep this file next to `install.py` / `menu.py` (i.e. in the
   parent folder that contains the `exUE5` package), then add that parent
   folder under:
       Edit -> Project Settings -> Plugins -> Python -> Additional Paths
   and restart the editor.

2. Or place it in a `Content/Python` folder that your project/plugin
   already scans by convention, making sure the `exUE5` package is still
   importable from there (e.g. keep it alongside this file, or keep the
   parent folder on Additional Paths as in option 1).

This hook still respects `config.json`'s `enable_menu_integration` flag --
if that is false, `install_menu()` is a no-op, so it is safe to leave this
startup hook in place even while menu integration is disabled.
"""

import sys
from pathlib import Path

try:
    import unreal
except ModuleNotFoundError:
    unreal = None

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent
for path in (str(ROOT), str(PARENT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _startup_log(message):
    if unreal is not None:
        try:
            unreal.log(f"[exUE5.init_unreal] {message}")
            return
        except Exception:
            pass
    print(f"[exUE5.init_unreal] {message}")


def _register_on_startup():
    try:
        try:
            from exUE5.menu import install_menu
        except ModuleNotFoundError:
            from menu import install_menu
        install_menu()
        _startup_log("Startup menu registration attempted - see [exUE5] logs above for the result.")
    except Exception as exc:
        # Startup hooks must never raise: an uncaught exception here can
        # interrupt the rest of Unreal's editor startup sequence for
        # unrelated systems. Log it and move on instead.
        _startup_log(f"ERROR during startup menu registration: {exc}")
        import traceback
        _startup_log(traceback.format_exc())


_register_on_startup()
