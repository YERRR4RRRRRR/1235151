import sys
from pathlib import Path

try:
    import unreal
except ModuleNotFoundError:
    unreal = None

try:
    from exUE5.menu_utils import _log, _try_call, _try_remove_menu_member
except ModuleNotFoundError:
    from menu_utils import _log, _try_call, _try_remove_menu_member

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent
for path in (str(ROOT), str(PARENT)):
    if path not in sys.path:
        sys.path.insert(0, path)

# Single source of truth for every top-level menu registration name that has
# ever been used by this plugin. Includes the oldest pre-rename "Exporter"
# name (before it became "PLUGSY_Exporter") so a leftover registration from
# an older editor session still gets cleaned up. menu.py imports this same
# constant instead of keeping its own separate list.
MENU_NAMES_TO_CLEAN = (
    'MainFrame.MainMenu.PLUGSY_Exporter',
    'LevelEditor.MainMenu.PLUGSY_Exporter',
    'MainFrame.MainMenu.Plugsy_Exporter',
    'MainFrame.MainMenu.Exporter',
    'LevelEditor.MainMenu.Exporter',
    # One-time defensive entry: a earlier bug in menu.py's add_sub_menu()
    # call passed an already-full path as the (relative-expected) `name`
    # argument, doubling the prefix and registering menus under this name
    # instead of the correct one above. Kept here so any leftover orphan
    # from before that fix still gets swept up.
    'MainFrame.MainMenu.MainFrame.MainMenu.PLUGSY_Exporter',
)




def _clear_exporter_section(menu_obj):
    if not menu_obj:
        return

    section_names = ('PLUGSY_Exporter', 'PLUGSY Exporter', 'Exporter')
    for section_name in section_names:
        _log(f"Clearing section/member: {section_name}")
        _try_remove_menu_member(menu_obj, section_name)

    for entry_name in ('ExportFBX', 'Export Sequence FBX', 'DiagnoseExport', 'DebugConsole'):
        _log(f"Clearing submenu entry: {entry_name}")
        _try_remove_menu_member(menu_obj, entry_name)


def cleanup_exporter_menu():
    """Remove stale PLUGSY Exporter menu registrations and leftover submenu entries."""
    if unreal is None:
        _log("unreal module not available")
        return False

    if not hasattr(unreal, 'ToolMenus'):
        _log("ToolMenus API not available")
        return False

    menus = unreal.ToolMenus.get()
    if menus is None:
        _log("ToolMenus.get() returned None")
        return False

    removed_any = False

    for name in MENU_NAMES_TO_CLEAN:
        _log(f"Checking registration for menu: {name}")
        try:
            is_registered = getattr(menus, 'is_menu_registered', lambda x: False)(name)
            _log(f"is_menu_registered('{name}') -> {is_registered}")
        except Exception as exc:
            _log(f"Failed is_menu_registered({name}): {exc}")
            is_registered = False

        try:
            removed = _try_call(menus, ['remove_menu', 'unregister_menu'], name)
            if removed is not None:
                _log(f"Attempted removal for menu '{name}', result: {removed}")
                removed_any = True
            else:
                _log(f"No remove/unregister method succeeded for '{name}'")
        except Exception as exc:
            _log(f"Failed removing menu {name}: {exc}")

    try:
        _log("Looking for MainFrame.MainMenu container")
        main_menu = _try_call(menus, ['extend_menu', 'get_menu', 'find_menu'], 'MainFrame.MainMenu')
        _log(f"MainFrame.MainMenu object -> {main_menu}")
        if main_menu:
            _clear_exporter_section(main_menu)
            removed_any = True
    except Exception as exc:
        _log(f"Could not inspect MainFrame.MainMenu: {exc}")

    try:
        _log("Looking for LevelEditor.MainMenu container")
        level_menu = _try_call(menus, ['extend_menu', 'get_menu', 'find_menu'], 'LevelEditor.MainMenu')
        _log(f"LevelEditor.MainMenu object -> {level_menu}")
        if level_menu:
            _clear_exporter_section(level_menu)
            removed_any = True
    except Exception as exc:
        _log(f"Could not inspect LevelEditor.MainMenu: {exc}")

    try:
        if hasattr(menus, 'refresh_all_widgets'):
            menus.refresh_all_widgets()
            _log('Refreshed widgets after cleanup')
    except Exception as exc:
        _log(f"Could not refresh widgets: {exc}")

    if removed_any:
        _log('Cleanup complete: removed stale PLUGSY Exporter menus or entries.')
    else:
        _log('Cleanup complete: no PLUGSY Exporter menu data found.')
    return removed_any


if __name__ == '__main__':
    cleanup_exporter_menu()
