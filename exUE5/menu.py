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


try:
    from exUE5.exporter_core import load_config, build_output_path
    from exUE5.spawnable_diagnostics import diagnose_camera_export_issue, _get_display_name
except ModuleNotFoundError:
    from exporter_core import load_config, build_output_path
    from spawnable_diagnostics import diagnose_camera_export_issue, _get_display_name

try:
    from exUE5.cleanup_menu import MENU_NAMES_TO_CLEAN
except ModuleNotFoundError:
    from cleanup_menu import MENU_NAMES_TO_CLEAN

try:
    from exUE5.debug_console import open_debug_console
except ModuleNotFoundError:
    from debug_console import open_debug_console

try:
    from exUE5.selection_dialog import show_selection_dialog
except ModuleNotFoundError:
    from selection_dialog import show_selection_dialog

try:
    from exUE5.camera_dialog import show_camera_export_dialog
except ModuleNotFoundError:
    from camera_dialog import show_camera_export_dialog

try:
    from exUE5.camera_export import _is_camera_binding, export_cameras_fbx
except ModuleNotFoundError:
    from camera_export import _is_camera_binding, export_cameras_fbx

try:
    from exUE5.ui_dialogs import _show_export_dialog, _show_export_progress, _show_camera_export_progress
except ModuleNotFoundError:
    from ui_dialogs import _show_export_dialog, _show_export_progress, _show_camera_export_progress

try:
    from exUE5.menu_utils import _log, _try_remove_menu_member, _clear_menu_entries
except ModuleNotFoundError:
    from menu_utils import _log, _try_remove_menu_member, _clear_menu_entries

# Zawsze podbij wersję po każdej zmianie w kodzie.
PLUGIN_VERSION = "v1.8"


def _reload_ui_style():
    """Odświeża w pamięci moduł exUE5.ui_style tuż przed otwarciem dialogu.

    Unreal Editor trzyma jeden, długo działający proces Pythona -- moduł raz
    zaimportowany do sys.modules NIE jest automatycznie ponownie wczytywany
    z dysku, nawet jeśli plik .py się zmienił. Skutek: po edycji ui_style.py
    (np. dodaniu nowej funkcji jak apply_geometry) moduły, które już wcześniej
    zaimportowały ui_style w tej samej sesji edytora (camera_dialog.py,
    ui_dialogs.py, selection_dialog.py, debug_console.py), dalej trzymają
    starą wersję w pamięci i rzucają
    "AttributeError: module 'exUE5.ui_style' has no attribute '...'" -- mimo
    że plik na dysku jest już poprawny -- dopóki ktoś ręcznie nie zrestartuje
    edytora.

    importlib.reload() podmienia zawartość modułu W MIEJSCU (ten sam obiekt
    modułu zostaje w sys.modules), więc wszystkie miejsca trzymające
    referencję do tego obiektu (np. `from exUE5 import ui_style` w innych
    plikach) od razu widzą nowe atrybuty -- bez potrzeby restartu edytora.
    Wywoływane na starcie każdego handlera menu, więc zawsze łapie
    najświeższą wersję pliku z dysku.
    """
    import importlib

    module = sys.modules.get("exUE5.ui_style") or sys.modules.get("ui_style")
    if module is None:
        # Jeszcze nie zaimportowany w tej sesji -- pierwszy import i tak
        # przeczyta aktualną wersję z dysku, więc nie ma czego przeładowywać.
        return
    try:
        importlib.reload(module)
    except Exception as exc:
        _log(f"[exUE5] Nie udało się przeładować ui_style: {exc}")


def _clear_existing_exporter_menu(menus, main_menu):
    for name in MENU_NAMES_TO_CLEAN:
        try:
            if menus.is_menu_registered(name):
                _log(f"Removing old exporter registration: {name}")
                menus.remove_menu(name)
        except Exception as exc:
            _log(f"Failed to remove old exporter registration {name}: {exc}")
        try:
            if hasattr(menus, 'unregister_menu'):
                menus.unregister_menu(name)
                _log(f"Unregistered old exporter menu: {name}")
        except Exception as exc:
            _log(f"Failed to unregister old exporter menu {name}: {exc}")

    if main_menu:
        _try_remove_menu_member(main_menu, "PLUGSY_Exporter")
        _try_remove_menu_member(main_menu, "ExportFBX")
        _clear_menu_entries(main_menu)
        try:
            if hasattr(menus, 'refresh_all_widgets'):
                menus.refresh_all_widgets()
                _log("Refreshed widgets after clearing existing menu")
        except Exception as exc:
            _log(f"Failed to refresh widgets after clearing existing menu: {exc}")


# Local dialog wrappers removed. Use ui_dialogs.py exports directly.





_camera_export_settings = None


def _run_camera_dialog():
    global _camera_export_settings

    if unreal is None:
        raise RuntimeError("unreal module not available")

    unreal.log("[exUE5] _run_camera_dialog() started")
    _reload_ui_style()
    config = load_config()
    try:
        from exUE5.exporter import get_current_sequence
    except ModuleNotFoundError:
        from exporter import get_current_sequence

    sequence = get_current_sequence()
    if not sequence:
        unreal.log("[exUE5] Brak aktywnej sekwencji dla dialogu kamer")
        return

    camera_bindings = [b for b in sequence.get_bindings() if _is_camera_binding(b)]
    filename = getattr(sequence, "get_name", None)
    if callable(filename):
        base_name = filename()
    else:
        base_name = str(sequence)
    default_output_path = build_output_path(config=config, filename=f"{base_name}_KAMERA_TRANS.fbx")

    result = show_camera_export_dialog(camera_bindings, _get_display_name, default_output_path)
    if result is not None:
        # The dialog no longer has a separate "export cameras" enable
        # checkbox -- it exists solely to configure and confirm the camera
        # export, so a non-cancelled result always means "go".
        _camera_export_settings = result
        unreal.log(f"[exUE5] Ustawienia eksportu kamer zapisane: {result}")
        try:
            unreal.log("[exUE5] Running camera export with UE5 FBX dialog")
            export_cameras_fbx(
                sequence,
                result.get("camera_binding_ids", set()),
                result.get("output_path"),
                show_dialog=True,
            )
        except Exception as exc:
            unreal.log(f"[exUE5] ERROR Camera export failed from dialog: {exc}")


def _run_export():
    """Export callback function"""
    if unreal is None:
        raise RuntimeError("unreal module not available")

    _reload_ui_style()
    config = load_config()

    unreal.log("[exUE5] Menu callback _run_export() invoked")

    dialog_result = _show_export_dialog(config)
    if not dialog_result:
        unreal.log("[exUE5] Export cancelled by user")
        return

    filename = dialog_result.get("filename")
    folder = dialog_result.get("folder")
    output_path = build_output_path(config=config, filename=filename, folder=folder)
    unreal.log(f"[exUE5] Selected output path: {output_path}")

    selection = None
    if config.get("use_selection_dialog", False):
        try:
            from exUE5.exporter import get_current_sequence, collect_all_bindings, collect_all_tracks
        except ModuleNotFoundError:
            from exporter import get_current_sequence, collect_all_bindings, collect_all_tracks

        sequence = get_current_sequence()
        if sequence:
            bindings = collect_all_bindings(sequence)
            tracks = collect_all_tracks(sequence)
            spawnable_ids = []
            try:
                from exUE5.spawnable_diagnostics import _get_spawnable_binding_ids
            except ModuleNotFoundError:
                from spawnable_diagnostics import _get_spawnable_binding_ids
            spawnable_ids = _get_spawnable_binding_ids(sequence)
            selection = show_selection_dialog(
                bindings,
                tracks,
                _get_display_name,
                spawnable_ids=set(spawnable_ids),
            )
            unreal.log(f"[exUE5] Selection dialog returned: {selection}")
            if selection is None:
                unreal.log("[exUE5] Export cancelled by user in selection dialog")
                return
        else:
            unreal.log("[exUE5] No current sequence found; skipping selection dialog")

    try:
        _show_export_progress(output_path, config, selection=selection)
    except Exception as exc:
        unreal.log(f"[exUE5] ERROR Export failed: {exc}")
        return

    if _camera_export_settings:
        unreal.log("[exUE5] Starting camera export after main export")
        try:
            from exUE5.exporter import get_current_sequence
        except ModuleNotFoundError:
            from exporter import get_current_sequence

        sequence = get_current_sequence()
        if sequence:
            try:
                _show_camera_export_progress(
                    _camera_export_settings.get("output_path"),
                    config,
                    sequence,
                    _camera_export_settings.get("camera_binding_ids", set()),
                )
            except Exception as exc:
                unreal.log(f"[exUE5] ERROR Camera export failed: {exc}")


def _run_diagnose_export():
    _reload_ui_style()
    try:
        diagnose_camera_export_issue()
    except Exception as exc:
        unreal.log(f"[exUE5] Diagnose Export Issues failed: {exc}")


def _run_debug_console():
    _reload_ui_style()
    try:
        open_debug_console()
    except Exception as exc:
        unreal.log(f"[exUE5] Debug console failed: {exc}")


def install_menu():
    """Install the PLUGSY Exporter menu on the main menu bar.

    Menu registration is disabled by default to avoid collisions in UE.
    Set enable_menu_integration to true in config.json to re-enable it.
    """
    config = load_config()
    if not config.get("enable_menu_integration", False):
        if unreal is not None:
            unreal.log("[exUE5] Menu integration disabled in config.json; skipping menu registration")
        return

    if unreal is None:
        raise RuntimeError("unreal module not available")

    unreal.log("[exUE5] ========== INSTALL MENU START ==========")
    
    if not hasattr(unreal, "ToolMenus"):
        unreal.log("[exUE5] ERROR: ToolMenus not available")
        return

    try:
        unreal.log("[exUE5] 1. Getting ToolMenus singleton...")
        menus = unreal.ToolMenus.get()
        unreal.log("[exUE5]    OK Got ToolMenus")
        
        unreal.log("[exUE5] 2. Getting MainFrame.MainMenu...")
        main_menu = menus.extend_menu("MainFrame.MainMenu")
        
        if not main_menu:
            unreal.log("[exUE5] ERROR: Could not extend MainFrame.MainMenu")
            return
        
        unreal.log("[exUE5]    OK Got main menu bar")
        
        unreal.log("[exUE5] 3. Cleaning existing PLUGSY_Exporter registration before install...")
        uninstall_menu()
        _clear_existing_exporter_menu(menus, main_menu)
        
        unreal.log("[exUE5] 4. Creating PLUGSY_Exporter submenu...")
        # NOTE: `name` must be RELATIVE to the parent menu (`main_menu`,
        # i.e. 'MainFrame.MainMenu') -- UE automatically prefixes it with
        # the parent's own full path. Passing the already-full path here
        # produced a doubled registration:
        # 'MainFrame.MainMenu.MainFrame.MainMenu.PLUGSY_Exporter', which no
        # cleanup code elsewhere (which correctly checks for the
        # non-doubled name) could ever find or remove -- so every install
        # silently stacked a new duplicate submenu instead of replacing it.
        exporter_submenu = main_menu.add_sub_menu(
            owner="exUE5",
            section_name="PLUGSY_Exporter",
            name="PLUGSY_Exporter",
            label=f"PLUGSY Exporter {PLUGIN_VERSION}",
            tool_tip="PLUGSY export tools"
        )
        
        if not exporter_submenu:
            unreal.log("[exUE5] ERROR: add_sub_menu returned None")
            return
        
        menu_name = getattr(exporter_submenu, "menu_name", "N/A")
        unreal.log("[exUE5]    OK Submenu created successfully")
        unreal.log(f"[exUE5] Zarejestrowana nazwa menu: {menu_name}")
        if menu_name != "N/A" and str(menu_name) not in MENU_NAMES_TO_CLEAN:
            unreal.log(
                f"[exUE5]    WARNING: registered menu name '{menu_name}' is "
                f"not in MENU_NAMES_TO_CLEAN -- future cleanup/uninstall "
                f"calls won't find it. If you see this, the naming bug is "
                f"back; check the add_sub_menu() call above."
            )
        
        unreal.log("[exUE5] 5. Adding 'Export Sequence FBX' entry to submenu...")
        _clear_menu_entries(exporter_submenu)
        
        if _try_remove_menu_member(exporter_submenu, "ExportFBX"):
            unreal.log("[exUE5] Removed existing ExportFBX entry from submenu before re-adding")

        export_entry = unreal.ToolMenuEntry(name="ExportFBX", type=unreal.MultiBlockType.MENU_ENTRY)
        export_entry.set_label(config.get("tool_name", "Export Sequence FBX"))
        export_entry.set_tool_tip("Export current Level Sequence to FBX")
        export_entry.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "from exUE5.menu import _run_export; _run_export()"
        )
        exporter_submenu.add_menu_entry("PLUGSY_Exporter", export_entry)
        unreal.log("[exUE5]    OK Entry added to submenu (section='PLUGSY_Exporter', entry name='ExportFBX')")

        camera_entry = unreal.ToolMenuEntry(name="ExportCamera", type=unreal.MultiBlockType.MENU_ENTRY)
        camera_entry.set_label(config.get("camera_tool_name", "EXPORT CAMERA"))
        camera_entry.set_tool_tip("Otwórz dialog eksportu kamer")
        camera_entry.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "from exUE5.menu import _run_camera_dialog; _run_camera_dialog()"
        )
        exporter_submenu.add_menu_entry("PLUGSY_Exporter", camera_entry)
        unreal.log("[exUE5]    OK Entry added to submenu (section='PLUGSY_Exporter', entry name='ExportCamera')")

        diagnose_entry = unreal.ToolMenuEntry(name="DiagnoseExport", type=unreal.MultiBlockType.MENU_ENTRY)
        diagnose_entry.set_label("Diagnose Export Issues")
        diagnose_entry.set_tool_tip("Log camera/spawnable export diagnostics")
        diagnose_entry.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "from exUE5.menu import _run_diagnose_export; _run_diagnose_export()"
        )
        exporter_submenu.add_menu_entry("PLUGSY_Exporter", diagnose_entry)
        unreal.log("[exUE5]    OK Entry added to submenu (section='PLUGSY_Exporter', entry name='DiagnoseExport')")

        debug_entry = unreal.ToolMenuEntry(name="DebugConsole", type=unreal.MultiBlockType.MENU_ENTRY)
        debug_entry.set_label("Debug Console")
        debug_entry.set_tool_tip("Open live debug console")
        debug_entry.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "from exUE5.menu import _run_debug_console; _run_debug_console()"
        )
        exporter_submenu.add_menu_entry("PLUGSY_Exporter", debug_entry)
        unreal.log("[exUE5]    OK Entry added to submenu (section='PLUGSY_Exporter', entry name='DebugConsole')")
        
        unreal.log("[exUE5] 6. Refreshing menu widgets...")
        menus.refresh_all_widgets()
        unreal.log("[exUE5]    OK Widgets refreshed")
        
        unreal.log("[exUE5] ========== INSTALL MENU SUCCESS ==========")
        unreal.log("[exUE5] OK Menu installed - 'PLUGSY Exporter' should appear on menu bar!")
        
    except Exception as e:
        unreal.log("[exUE5] ========== INSTALL MENU FAILED ==========")
        unreal.log(f"[exUE5] ERROR: {e}")
        import traceback
        unreal.log(traceback.format_exc())


def uninstall_menu():
    """Uninstall the PLUGSY Exporter menu."""
    if unreal is None or not hasattr(unreal, "ToolMenus"):
        return

    try:
        menus = unreal.ToolMenus.get()
        removed = False
        for name in MENU_NAMES_TO_CLEAN:
            try:
                if menus.is_menu_registered(name):
                    menus.remove_menu(name)
                    unreal.log(f"[exUE5] Removed menu registration: {name}")
                    removed = True
            except Exception as exc:
                unreal.log(f"[exUE5] Could not remove menu {name}: {exc}")
        if removed:
            menus.refresh_all_widgets()
            unreal.log("[exUE5] Menu uninstalled")
        else:
            unreal.log("[exUE5] No PLUGSY_Exporter menu registered")
    except Exception as e:
        unreal.log(f"[exUE5] Uninstall error: {e}")
        import traceback
        unreal.log(traceback.format_exc())