import threading
from pathlib import Path

try:
    import unreal
except ModuleNotFoundError:
    unreal = None

try:
    from exUE5.debug_console import push_log
except ModuleNotFoundError:
    from debug_console import push_log


def _log(message):
    thread_name = threading.current_thread().name
    formatted = f"[exUE5][{thread_name}] {message}"
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


if unreal is not None:
    _log(f"spawnable_diagnostics module imported from {Path(__file__).resolve()}")


def _normalize_guid_string(value):
    """Reduce any GUID-ish representation to a canonical lowercase hex
    string with no separators/braces, so values coming from different
    formatting paths (conv_guid_to_string, export_text, raw a/b/c/d fields,
    plain str()) can be compared reliably.

    This is the fix for the spawnable-matching bug: _format_binding_id used
    to return differently-shaped strings depending on which branch
    succeeded (e.g. "22CF7447-4C78-097B-CA35-43BC4361BD2F" from
    conv_guid_to_string vs "186C510E42D7B61584A4F48202DC2C5C" from the
    a/b/c/d fallback), so `binding_id_str in spawnable_ids` was comparing
    apples to oranges and never matched even for the correct spawnable.
    """
    if value is None:
        return None
    text = str(value).strip()
    # Strip anything that isn't a hex digit (dashes, braces, parens, quotes,
    # tuple formatting like "(1234, 5678, ...)").
    hex_only = "".join(ch for ch in text if ch in "0123456789abcdefABCDEF")
    if not hex_only:
        return None
    return hex_only.lower()


def _format_binding_id(binding_id):
    if binding_id is None:
        return None

    candidates = []

    if unreal is not None:
        try:
            system_lib = getattr(unreal, "SystemLibrary", None)
            if system_lib is not None and hasattr(system_lib, "conv_guid_to_string"):
                guid_str = system_lib.conv_guid_to_string(binding_id)
                if guid_str:
                    candidates.append(str(guid_str))
        except Exception:
            pass

    try:
        if hasattr(binding_id, "export_text") and callable(getattr(binding_id, "export_text")):
            guid_str = binding_id.export_text()
            if guid_str:
                candidates.append(str(guid_str))
    except Exception:
        pass

    try:
        fields = tuple(getattr(binding_id, field, None) for field in ("a", "b", "c", "d"))
        if all(field is not None for field in fields):
            # Format each 32-bit field as 8 hex digits (matching how UE
            # itself renders a Guid), not Python's default str(tuple).
            try:
                candidates.append("".join(f"{int(f) & 0xFFFFFFFF:08X}" for f in fields))
            except Exception:
                candidates.append(str(fields))
    except Exception:
        pass

    try:
        if hasattr(binding_id, "get_editor_property") and callable(getattr(binding_id, "get_editor_property")):
            fields = tuple(binding_id.get_editor_property(field) for field in ("a", "b", "c", "d"))
            if all(field is not None for field in fields):
                try:
                    candidates.append("".join(f"{int(f) & 0xFFFFFFFF:08X}" for f in fields))
                except Exception:
                    candidates.append(str(fields))
    except Exception:
        pass

    candidates.append(str(binding_id))

    # Return the first candidate that yields a usable normalized hex form.
    for candidate in candidates:
        normalized = _normalize_guid_string(candidate)
        if normalized:
            return normalized

    return str(binding_id)


def _get_display_name(item):
    for attr_name in ("get_name", "get_display_name", "get_object_name", "get_path_name"):
        method = getattr(item, attr_name, None)
        if callable(method):
            try:
                value = method()
            except Exception:
                continue
            if value:
                return str(value)
    return str(item)


def _filter_sequence_items(items, config):
    items = list(items)
    total = len(items)

    if config.get("include_all_bindings", True):
        _log(f"_filter_sequence_items -> include_all_bindings=True, keeping all {total} item(s)")
        return items

    keywords = []
    if config.get("include_body", False):
        keywords.extend(["body", "bone", "skeleton", "metahuman"])
    if config.get("include_face", False):
        keywords.extend(["face", "blendshape", "morph"])
    if config.get("include_cameras", False):
        keywords.extend(["camera", "cam"])
    if config.get("include_control_rigs", False):
        keywords.extend(["controlrig", "control rig", "rig"])
    if config.get("include_subsequences", False):
        keywords.extend(["sequence", "subsequence"])

    if not keywords:
        _log(f"_filter_sequence_items -> no include_* flags set, keeping all {total} item(s)")
        return items

    filtered = []
    for item in items:
        name = _get_display_name(item).lower()
        if any(keyword in name for keyword in keywords):
            filtered.append(item)

    _log(f"_filter_sequence_items -> keywords={keywords} before={total} after={len(filtered)}")

    if total and not filtered:
        _log(
            "WARNING: filter matched 0 of {} item(s) for keywords {} -- this "
            "config combination would export an EMPTY/INCOMPLETE FBX. Check "
            "whether the real binding/track names actually contain these "
            "keywords, or set include_all_bindings=true.".format(total, keywords)
        )

    return filtered


def _get_spawnable_binding_ids(sequence):
    spawnable_ids = set()
    if not sequence:
        return spawnable_ids
    if unreal is not None:
        _log(f"spawnable_diagnostics imported from {Path(__file__).resolve()}")
    if not hasattr(sequence, "get_spawnables"):
        _log(
            "_get_spawnable_binding_ids -> sequence has no get_spawnables() "
            "on this engine build; cannot check for the known Spawnable "
            "camera/mesh export bug on this run."
        )
        return spawnable_ids
    try:
        spawnables = list(sequence.get_spawnables())
        for spawnable in spawnables:
            binding_id = getattr(spawnable, "binding_id", None)
            binding_id_str = _format_binding_id(binding_id)
            if binding_id_str is not None:
                spawnable_ids.add(binding_id_str)
        _log(
            f"_get_spawnable_binding_ids -> found {len(spawnables)} "
            f"spawnable(s) in sequence, {len(spawnable_ids)} with a usable binding_id"
        )
    except Exception as exc:
        _log(f"_get_spawnable_binding_ids ERROR: {exc}")
    return spawnable_ids


def _diagnose_spawn_track(binding):
    result = {
        "has_spawn_track": False,
        "key_count": 0,
        "values": [],
        "will_likely_hit_bug": False,
    }
    try:
        tracks = []
        if hasattr(binding, "get_tracks"):
            try:
                tracks = list(binding.get_tracks())
                _log(f"_diagnose_spawn_track -> inspect {len(tracks)} tracks")
            except Exception as exc:
                _log(f"_diagnose_spawn_track get_tracks() failed: {exc}")
                return result

        spawn_track = None
        for track in tracks:
            try:
                track_class = track.get_class()
                if track_class and hasattr(track_class, "get_name"):
                    track_name = track_class.get_name() or ""
                    if "SpawnTrack" in track_name:
                        spawn_track = track
                        break
            except Exception:
                continue

        if not spawn_track:
            return result

        result["has_spawn_track"] = True
        sections = []
        if hasattr(spawn_track, "get_sections"):
            try:
                sections = list(spawn_track.get_sections())
            except Exception as exc:
                _log(f"_diagnose_spawn_track get_sections() failed: {exc}")
                return result

        for section in sections:
            channels = []
            if hasattr(section, "get_channels"):
                try:
                    channels = list(section.get_channels())
                except Exception as exc:
                    _log(f"_diagnose_spawn_track get_channels() failed: {exc}")
                    continue
            for channel in channels:
                keys = []
                if hasattr(channel, "get_keys"):
                    try:
                        keys = list(channel.get_keys())
                    except Exception as exc:
                        _log(f"_diagnose_spawn_track channel.get_keys() failed: {exc}")
                        continue
                for key in keys:
                    value = None
                    if hasattr(key, "get_value"):
                        try:
                            value = key.get_value()
                        except Exception:
                            value = None
                    elif hasattr(key, "value"):
                        value = getattr(key, "value")
                    if value is not None:
                        result["values"].append(value)
        result["key_count"] = len(result["values"])
        result["will_likely_hit_bug"] = result["key_count"] <= 1 or len(set(result["values"])) <= 1
    except Exception as exc:
        _log(f"_diagnose_spawn_track ERROR (non-fatal): {exc}")
    return result


def _warn_about_spawnable_export_bug(sequence, bindings, all_bindings=None):
    _log(f"spawnable_diagnostics._warn_about_spawnable_export_bug invoked from {Path(__file__).resolve()}")
    spawnable_ids = _get_spawnable_binding_ids(sequence)
    if not spawnable_ids:
        return []

    _log(f"DEBUG spawnable_ids={list(spawnable_ids)}")

    # Determine the full set of bindings in the sequence if the caller did
    # not provide them. Import locally to avoid circular imports.
    if all_bindings is None:
        try:
            try:
                from exUE5.exporter_core import collect_all_bindings
            except ModuleNotFoundError:
                from exporter_core import collect_all_bindings
            all_bindings = collect_all_bindings(sequence)
        except Exception as exc:
            _log(f"_warn_about_spawnable_export_bug: failed to collect all_bindings: {exc}")
            all_bindings = list(bindings)

    full_spawnables = []
    for b in all_bindings:
        bid = getattr(b, "binding_id", None)
        bid_s = _format_binding_id(bid) if bid is not None else None
        if bid_s and bid_s in spawnable_ids:
            full_spawnables.append(_get_display_name(b))

    export_spawnables = []
    # Keep legacy per-export inspection as well
    flagged = []
    for binding in bindings:
        binding_id = getattr(binding, "binding_id", None)
        binding_id_str = _format_binding_id(binding_id) if binding_id is not None else None
        name = _get_display_name(binding)
        match = binding_id_str in spawnable_ids if binding_id_str is not None else False
        _log(
            f"DEBUG binding='{name}' raw_id={binding_id!r} formatted_id={binding_id_str!r} match={match}"
        )
        if binding_id is not None and match:
            flagged.append(name)
            export_spawnables.append(name)
            diagnosis = _diagnose_spawn_track(binding)
            if diagnosis["has_spawn_track"]:
                if diagnosis["will_likely_hit_bug"]:
                    _log(
                        f"WARNING: binding '{name}' is a Spawnable. Spawn Track diagnostic: "
                        f"keys={diagnosis['key_count']}, values={diagnosis['values']}. "
                        "Verdict=TRAFI W BUG (brak toggle na Spawn Tracku)."
                    )
                else:
                    _log(
                        f"WARNING: binding '{name}' is a Spawnable. Spawn Track diagnostic: "
                        f"keys={diagnosis['key_count']}, values={diagnosis['values']}. "
                        "Verdict=PRAWDOPODOBNIE OK (ma toggle-like keys)."
                    )
            else:
                _log(
                    f"WARNING: binding '{name}' is a Spawnable but no Spawn Track could be diagnosed. "
                    "Verdict=BRAK DANYCH; bug may still be relevant."
                )
            _log(
                f"WARNING: -> Fix for '{name}': RMB on the track in Sequencer -> 'Convert to Possessable', "
                "then re-export."
            )

    # Log a concise summary comparing full sequence spawnables vs those in export
    try:
        _log(
            f"Sequence contains {len(full_spawnables)} spawnable binding(s): {full_spawnables}. "
            f"In export: {export_spawnables}"
        )
    except Exception:
        pass

    if flagged:
        _log(
            f"EXPORT WARNING: {len(flagged)} spawnable binding(s) detected "
            f"({', '.join(flagged)}) - verify the exported FBX contains their "
            "mesh/camera data, not just an empty transform."
        )
    else:
        _log(
            f"_warn_about_spawnable_export_bug -> sequence has {len(spawnable_ids)} "
            "spawnable(s), but none of them matched a binding in this export "
            "(they may be filtered out, or binding_id comparison didn't match)."
        )
    return flagged


def diagnose_camera_export_issue(sequence=None):
    """Log a user-facing diagnosis for camera-like Spawnables in the current sequence."""
    try:
        try:
            from exUE5.exporter_core import get_current_sequence, collect_all_bindings
        except ModuleNotFoundError:
            from exporter_core import get_current_sequence, collect_all_bindings
    except Exception:
        get_current_sequence = None
        collect_all_bindings = None

    if sequence is None:
        if get_current_sequence is None:
            _log("DIAGNOSIS: exporter_core import failed; cannot diagnose camera issues")
            return []
        sequence = get_current_sequence()

    if not sequence:
        _log("DIAGNOSIS: no current sequence available")
        return []

    bindings = collect_all_bindings(sequence)
    spawnable_ids = _get_spawnable_binding_ids(sequence)
    results = []

    for binding in bindings:
        name = _get_display_name(binding)
        class_name = ""
        try:
            if hasattr(binding, "get_class") and callable(binding.get_class):
                class_obj = binding.get_class()
                if hasattr(class_obj, "get_name"):
                    class_name = class_obj.get_name() or ""
        except Exception:
            class_name = ""

        class_lower = class_name.lower()
        name_lower = name.lower()
        is_spawnable = False
        binding_id = getattr(binding, "binding_id", None)
        if binding_id is not None and _format_binding_id(binding_id) in spawnable_ids:
            is_spawnable = True

        is_camera_like = any(token in class_lower or token in name_lower for token in ("camera", "cinecamera", "cameracomponent"))
        if not (is_spawnable or is_camera_like):
            continue

        diagnosis = _diagnose_spawn_track(binding)
        if not is_spawnable:
            verdict = "NIE JEST SPAWNABLE — bug nie dotyczy"
        elif diagnosis["will_likely_hit_bug"]:
            verdict = "TRAFI W BUG"
        else:
            verdict = "PRAWDOPODOBNIE OK"

        summary = {
            "name": name,
            "is_spawnable": is_spawnable,
            "is_camera_like": is_camera_like,
            "diagnosis": diagnosis,
            "verdict": verdict,
        }
        results.append(summary)
        _log(
            f"DIAG: binding='{name}' spawnable={is_spawnable} camera_like={is_camera_like} "
            f"spawn_track={diagnosis['has_spawn_track']} keys={diagnosis['key_count']} values={diagnosis['values']} verdict={verdict}"
        )

    if not results:
        _log("DIAGNOSIS: no camera-like bindings or spawnables found in the current sequence")
    return results


def _classify_binding(name, is_spawnable):
    import re
    try:
        name_text = str(name)
    except Exception:
        name_text = ""
    name_lower = name_text.lower()
    norm = re.sub(r"[^0-9a-z\s]", " ", name_lower)

    camera_tokens = ("camera", "cam", "sensor", "focal", "focus", "aperture", "filmback", "film back", "lens", "focal length")
    face_tokens = ("face", "blendshape", "blend shape", "blend", "morph", "jaw", "eye", "eyebrow", "lip", "mouth")
    body_tokens = ("body", "bone", "skeleton", "metahuman", "mesh", "character", "spine", "hip", "chest")
    control_tokens = ("controlrig", "control rig", "rig")

    if any(token in norm for token in face_tokens):
        category = "Face"
    elif any(token in norm for token in body_tokens):
        category = "Body"
    elif any(token in norm for token in camera_tokens):
        category = "Camera"
    elif any(token in norm for token in control_tokens):
        category = "Control Rig"
    else:
        category = "Inne"

    if is_spawnable:
        category += "  (Spawnable)"
    return category


def _sort_priority(name, is_spawnable=False):
    category = _classify_binding(name, is_spawnable)
    if category.startswith("Face"):
        return (0, name.lower())
    if category.startswith("Body"):
        return (1, name.lower())
    if category.startswith("Camera"):
        return (2, name.lower())
    if category.startswith("Control Rig"):
        return (3, name.lower())
    return (4, name.lower())


def _frame_to_int(frame):
    """Best-effort konwersja FrameNumber/FrameTime/int na zwykły int."""
    if frame is None:
        return None
    if hasattr(frame, "value"):
        try:
            return int(frame.value)
        except Exception:
            pass
    if hasattr(frame, "frame_number"):
        try:
            return _frame_to_int(frame.frame_number)
        except Exception:
            pass
    try:
        return int(frame)
    except Exception:
        return None


def _make_frame_number(frame_int):
    if unreal is not None and hasattr(unreal, "FrameNumber"):
        try:
            return unreal.FrameNumber(frame_int)
        except Exception:
            pass
    return frame_int


def _get_sequence_range_frames(sequence):
    """Zwraca (start, end) jako zwykłe inty dla zakresu odtwarzania sekwencji,
    albo (None, None) jeśli nie da się ich odczytać. `end` jest korygowany o -1,
    bo get_playback_end() jest zazwyczaj EXCLUSIVE (klatka ZA ostatnią)."""
    start = end = None
    try:
        if hasattr(sequence, "get_playback_start"):
            start = _frame_to_int(sequence.get_playback_start())
    except Exception:
        start = None
    try:
        if hasattr(sequence, "get_playback_end"):
            end = _frame_to_int(sequence.get_playback_end())
            if end is not None:
                end -= 1
    except Exception:
        end = None
    return start, end


def _apply_spawnable_auto_fix_if_needed(sequence, bindings, config, fix_state):
    """UWAGA - dla eksportu KAMER (camera_export.py) ta funkcja jest
    WYCOFANA: próba naprawy bugu Spawnable+FBX-export przez dopisywanie
    tymczasowych kluczy na Spawn Tracku nie zadziałała w testach - plik
    wychodził jeszcze mniejszy niż źle działający oryginał (prawdopodobnie
    skracała okno spawnu zamiast je wydłużać). camera_export.py nie
    importuje już tej funkcji; poprawna naprawa dla kamer to programowa
    konwersja Spawnable->Possessable przed eksportem, patrz
    camera_export._convert_spawnables_to_possessables (analogicznie do
    ręcznego testu kontrolnego użytkownika: "Convert Selected Binding(s)
    To... -> Possessable" + Export).

    Funkcja NADAL JEST UŻYWANA przez główny eksporter (exporter_core.py,
    body/face) jako opcjonalny fix kontrolowany flagą
    "auto_fix_spawnable_camera_bug" w config.json (domyślnie false) -
    dlatego nie została usunięta, tylko odpięta od ścieżki kamer.

    Dodaje tymczasowe klucze na Spawn Tracku dla Spawnable bindingów, u których
    zdiagnozowano znany bug UE5.8 (Spawn Track ma <=1 klucz / same identyczne
    wartości -> silnik nie bake'uje animacji na cały zakres eksportu, tylko
    zwraca jedną statyczną klatkę - patrz `_diagnose_spawn_track`).

    WAŻNE: poprzednia wersja tej funkcji dodawała nowy klucz na TEJ SAMEJ
    klatce co ostatni istniejący klucz, więc de facto nadpisywała go tą samą
    wartością i key_count się nie zmieniał (no-op, bug nie był naprawiany).
    Ta wersja dodaje klucze na początku i końcu zakresu odtwarzania sekwencji
    (z tą samą wartością spawn=True, więc stan "zespawnowany" się nie zmienia),
    żeby Spawn Track miał >1 klucz pokrywający cały eksportowany zakres.
    """
    if not config.get("auto_fix_spawnable_camera_bug", False):
        return

    if not sequence:
        return

    spawnable_ids = _get_spawnable_binding_ids(sequence)
    if not spawnable_ids:
        return

    range_start, range_end = _get_sequence_range_frames(sequence)

    for binding in bindings:
        binding_id = getattr(binding, "binding_id", None)
        if binding_id is None or _format_binding_id(binding_id) not in spawnable_ids:
            continue
        diagnosis = _diagnose_spawn_track(binding)
        if not diagnosis["will_likely_hit_bug"]:
            continue

        name = _get_display_name(binding)
        candidate_channels = []
        try:
            tracks = list(binding.get_tracks()) if hasattr(binding, "get_tracks") else []
            for track in tracks:
                class_name = ""
                try:
                    class_obj = track.get_class()
                    if hasattr(class_obj, "get_name"):
                        class_name = class_obj.get_name() or ""
                except Exception:
                    class_name = ""
                if "SpawnTrack" not in class_name:
                    continue
                sections = []
                if hasattr(track, "get_sections"):
                    sections = list(track.get_sections())
                for section in sections:
                    if hasattr(section, "get_channels"):
                        candidate_channels.extend(list(section.get_channels()))
        except Exception as exc:
            _log(f"_apply_spawnable_auto_fix_if_needed failed while inspecting binding '{name}': {exc}")
            continue

        for channel in candidate_channels:
            if not hasattr(channel, "add_key") or not hasattr(channel, "get_keys"):
                continue
            try:
                current_keys = list(channel.get_keys())
            except Exception as exc:
                _log(f"_apply_spawnable_auto_fix_if_needed get_keys failed: {exc}")
                continue
            if not current_keys:
                continue

            reference_key = current_keys[-1]
            value = None
            if hasattr(reference_key, "get_value"):
                value = reference_key.get_value()
            elif hasattr(reference_key, "value"):
                value = getattr(reference_key, "value")
            if value is None:
                continue

            existing_frames = set()
            for key in current_keys:
                frame_attr = getattr(key, "frame_number", None)
                if frame_attr is None and hasattr(key, "get_time"):
                    try:
                        frame_attr = key.get_time()
                    except Exception:
                        frame_attr = None
                frame_int = _frame_to_int(frame_attr)
                if frame_int is not None:
                    existing_frames.add(frame_int)

            target_frames = set()
            if range_start is not None:
                target_frames.add(range_start)
            if range_end is not None:
                target_frames.add(range_end)
            if not target_frames:
                # Brak dostępu do zakresu sekwencji - fallback: klatka tuż za
                # ostatnim istniejącym kluczem, żeby key_count na pewno wzrósł.
                fallback = max(existing_frames) + 1 if existing_frames else 1
                target_frames.add(fallback)

            for frame_int in sorted(target_frames):
                if frame_int in existing_frames:
                    # Na tej klatce już jest realny klucz użytkownika - nie
                    # dotykamy go, żeby przy sprzątaniu (_remove_spawnable_auto_fix)
                    # przypadkiem go nie usunąć.
                    continue
                try:
                    channel.add_key(_make_frame_number(frame_int), value)
                    fix_state.append((channel, frame_int, value))
                    _log(
                        f"[exUE5][FLOW] auto_fix_spawnable_camera_bug: dodano tymczasowy klucz "
                        f"Spawn Track na klatce {frame_int} (binding='{name}', value={value})."
                    )
                except Exception as exc:
                    _log(f"_apply_spawnable_auto_fix_if_needed add_key failed for '{name}' @ {frame_int}: {exc}")


def _remove_spawnable_auto_fix(fix_state):
    """Sprzątanie dla _apply_spawnable_auto_fix_if_needed - wycofane tylko
    ze ścieżki eksportu kamer (camera_export.py), wciąż używane przez
    exporter_core.py dla głównego eksportu body/face (patrz notatka
    powyżej w _apply_spawnable_auto_fix_if_needed)."""
    if not fix_state:
        return
    for channel, frame_int, value in reversed(fix_state):
        removed = False
        try:
            if hasattr(channel, "remove_key"):
                channel.remove_key(_make_frame_number(frame_int))
                removed = True
        except Exception as exc:
            _log(f"_remove_spawnable_auto_fix remove_key failed: {exc}")
        if not removed:
            try:
                if hasattr(channel, "remove_key_at_frame"):
                    channel.remove_key_at_frame(_make_frame_number(frame_int))
            except Exception as exc:
                _log(f"_remove_spawnable_auto_fix remove_key_at_frame failed: {exc}")
    fix_state.clear()