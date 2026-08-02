import sys
from pathlib import Path
import importlib

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent
for path in (str(ROOT), str(PARENT)):
    if path not in sys.path:
        sys.path.insert(0, path)

# Force reload of modules to avoid stale UI/state cache in Unreal.
# This must include the dialog and helper modules, otherwise the editor keeps
# old Tk objects alive in sys.modules even when source files were edited.
for module_name in (
    'exporter',
    'menu',
    'selection_dialog',
    'menu_utils',
    'debug_console',
    'cleanup_menu',
    'exUE5.exporter',
    'exUE5.menu',
    'exUE5.selection_dialog',
    'exUE5.menu_utils',
    'exUE5.debug_console',
    'exUE5.cleanup_menu',
    'exUE5.exporter_core',
    'exUE5.spawnable_diagnostics',
    'exUE5.ui_dialogs',
):
    if module_name in sys.modules:
        del sys.modules[module_name]

try:
    import exUE5.selection_dialog as selection_dialog_module
    import exUE5.menu_utils as menu_utils_module
    import exUE5.debug_console as debug_console_module
    import exUE5.cleanup_menu as cleanup_menu_module
    import exUE5.menu as menu_module
    import exUE5.exporter as exporter_module
    importlib.reload(selection_dialog_module)
    importlib.reload(menu_utils_module)
    importlib.reload(debug_console_module)
    importlib.reload(cleanup_menu_module)
    importlib.reload(menu_module)
    importlib.reload(exporter_module)
    install_menu = menu_module.install_menu
    uninstall_menu = menu_module.uninstall_menu
except ModuleNotFoundError:
    try:
        from exUE5.menu import install_menu, uninstall_menu
        import exUE5.exporter as exporter_module
        importlib.reload(exporter_module)
    except ModuleNotFoundError:
        try:
            from menu import install_menu, uninstall_menu
        except Exception as exc:
            raise RuntimeError(
                f"[exUE5] install.py: nie udalo sie zaimportowac menu.py "
                f"(prawdopodobny blad skladni/logiki WEWNATRZ menu.py, "
                f"nie problem ze sciezka importu): {exc}"
            ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"[exUE5] install.py: blad podczas importu exUE5.menu / "
            f"exUE5.exporter (prawdopodobny blad skladni/logiki wewnatrz "
            f"tych plikow, nie problem ze sciezka importu): {exc}"
        ) from exc
except Exception as exc:
    raise RuntimeError(
        f"[exUE5] install.py: nieoczekiwany blad podczas importu "
        f"exUE5.menu / exUE5.exporter (sprawdz skladnie/logike w tych "
        f"plikach - to NIE jest problem ze sciezka importu): {exc}"
    ) from exc


def install():
    install_menu()


def uninstall():
    uninstall_menu()
    print("[exUE5] PLUGSY Exporter menu registration removed (if it existed)")


def reinstall():
    uninstall_menu()
    install_menu()
    print("[exUE5] Reinstalled exporter menu")


if __name__ == "__main__":
    reinstall()
