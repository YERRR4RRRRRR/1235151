try:
    import unreal
except ModuleNotFoundError:
    unreal = None

try:
    from exUE5.debug_console import push_log
except ModuleNotFoundError:
    from debug_console import push_log


def _log(message):
    formatted = f"[exUE5] {message}"
    level = "INFO"
    upper_message = formatted.upper()
    if "ERROR" in upper_message or "FAILED" in upper_message:
        level = "ERROR"
    elif "WARNING" in upper_message:
        level = "WARNING"

    if unreal is not None:
        try:
            unreal.log(formatted)
        except Exception:
            pass

    try:
        push_log(formatted, level=level)
    except Exception:
        pass

    if unreal is None:
        print(formatted)


def _try_remove_menu_member(menu_obj, name):
    if not menu_obj:
        return False

    method_names = [
        "remove_menu_entry",
        "remove_entry",
        "remove_sub_menu",
        "remove_submenu",
        "remove_menu",
        "remove_section",
        "remove_section_by_name",
        "remove_menu_section",
        "remove_menu_entry_by_name",
    ]

    for method_name in method_names:
        method = getattr(menu_obj, method_name, None)
        if callable(method):
            try:
                method(name)
                _log(f"Removed menu member '{name}' using {method_name}")
                return True
            except Exception as exc:
                _log(f"Could not remove menu member '{name}' with {method_name}: {exc}")
    return False


def _try_call(obj, method_names, *args, **kwargs):
    for method_name in method_names:
        method = getattr(obj, method_name, None)
        if not callable(method):
            continue
        try:
            return method(*args, **kwargs)
        except Exception as exc:
            _log(f"_try_call {obj.__class__.__name__}.{method_name} failed: {exc}")
    return None


def _get_menu_entry_label(entry):
    if not entry:
        return None
    for getter in ('get_label', 'get_name', 'get_tool_tip', 'get_section_name'):
        if hasattr(entry, getter):
            try:
                value = getattr(entry, getter)()
                if value:
                    return str(value)
            except Exception:
                continue
    return getattr(entry, 'name', None) or getattr(entry, 'label', None)


def _clear_menu_entries(menu_obj):
    if not menu_obj:
        return

    def _clear_entries_from_menu(target_menu):
        if not target_menu:
            return

        entries = []
        if hasattr(target_menu, 'get_menu_entries'):
            try:
                entries = target_menu.get_menu_entries()
            except Exception as exc:
                _log(f"get_menu_entries failed on target_menu: {exc}")
        elif hasattr(target_menu, 'get_entries'):
            try:
                entries = target_menu.get_entries()
            except Exception as exc:
                _log(f"get_entries failed on target_menu: {exc}")

        for entry in entries:
            entry_name = None
            if hasattr(entry, 'get_name'):
                try:
                    entry_name = entry.get_name()
                except Exception:
                    entry_name = None
            if not entry_name:
                entry_name = getattr(entry, 'name', None)
            entry_label = _get_menu_entry_label(entry)
            if entry_name in ('ExportFBX',) or entry_label in ('Export Sequence FBX', 'ExportFBX'):
                remove_name = entry_name or entry_label
                _log(f"Removing duplicate entry '{remove_name}' (label={entry_label})")
                _try_remove_menu_member(target_menu, remove_name)
                _try_remove_menu_member(target_menu, 'ExportFBX')
                _try_remove_menu_member(target_menu, 'Export Sequence FBX')

    if hasattr(menu_obj, 'get_sections'):
        try:
            sections = menu_obj.get_sections()
        except Exception as exc:
            _log(f"get_sections failed on menu_obj: {exc}")
            sections = []
    elif hasattr(menu_obj, 'find_section'):
        sections = []
        try:
            for section_name in ('PLUGSY_Exporter', 'Exporter'):
                section = menu_obj.find_section(section_name)
                if section:
                    sections.append(section)
        except Exception as exc:
            _log(f"find_section failed on menu_obj: {exc}")
    else:
        sections = []

    for section in sections:
        if section:
            _clear_entries_from_menu(section)

    _clear_entries_from_menu(menu_obj)
