import os
import json
import threading
import traceback

try:
    import unreal
except ModuleNotFoundError:
    unreal = None

try:
    from exUE5.debug_console import push_log
except ModuleNotFoundError:
    from debug_console import push_log

try:
    from exUE5.spawnable_diagnostics import (
        _get_display_name,
        _filter_sequence_items,
        _warn_about_spawnable_export_bug,
        _apply_spawnable_auto_fix_if_needed,
        _remove_spawnable_auto_fix,
    )
except ModuleNotFoundError:
    from spawnable_diagnostics import (
        _get_display_name,
        _filter_sequence_items,
        _warn_about_spawnable_export_bug,
        _apply_spawnable_auto_fix_if_needed,
        _remove_spawnable_auto_fix,
    )


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


def load_config(config_path=None):
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _try_call(obj, method_names, *args, **kwargs):
    for method_name in method_names:
        method = getattr(obj, method_name, None)
        if not callable(method):
            continue
        try:
            result = method(*args, **kwargs)
            _log(f"_try_call {obj.__class__.__name__}.{method_name} -> {result}")
            return result
        except Exception as exc:
            _log(f"_try_call {obj.__class__.__name__}.{method_name} failed: {exc}")
    return None


def _is_level_sequence_object(obj):
    if not obj:
        return False

    try:
        if hasattr(unreal, 'LevelSequence') and isinstance(obj, unreal.LevelSequence):
            return True
    except Exception:
        pass

    try:
        if hasattr(unreal, 'MovieSceneSequence') and isinstance(obj, unreal.MovieSceneSequence):
            return True
    except Exception:
        pass

    try:
        if hasattr(obj, 'get_class') and callable(getattr(obj, 'get_class')):
            class_name = obj.get_class().get_name()
            if class_name and 'Sequence' in class_name:
                return True
    except Exception:
        pass

    try:
        if hasattr(obj, 'asset_class'):
            return 'LevelSequence' in str(obj.asset_class) or 'MovieSceneSequence' in str(obj.asset_class)
    except Exception:
        pass

    try:
        if hasattr(obj, 'get_tag_value'):
            tag_value = obj.get_tag_value('AssetClass')
            if tag_value and ('LevelSequence' in str(tag_value) or 'MovieSceneSequence' in str(tag_value)):
                return True
    except Exception:
        pass

    try:
        if hasattr(obj, 'get_path_name') and callable(obj.get_path_name):
            path_name = obj.get_path_name()
            if path_name and ('LevelSequence' in str(path_name) or 'MovieSceneSequence' in str(path_name)):
                return True
    except Exception:
        pass

    try:
        if hasattr(obj, 'get_editor_property'):
            asset_class = obj.get_editor_property('asset_class')
            if asset_class and ('LevelSequence' in str(asset_class) or 'MovieSceneSequence' in str(asset_class)):
                return True
    except Exception:
        pass

    return False


def _find_sequence_in_container(container):
    if not container:
        return None

    if _is_level_sequence_object(container):
        return container

    if isinstance(container, dict):
        for value in container.values():
            sequence = _find_sequence_in_container(value)
            if sequence:
                return sequence
        return None

    if isinstance(container, (list, tuple, set)):
        for item in container:
            sequence = _find_sequence_in_container(item)
            if sequence:
                return sequence
        return None

    try:
        for attribute_name in ('asset', 'asset_data', 'sequence', 'root_sequence', 'parent_sequence', 'movie_scene_sequence'):
            if hasattr(container, 'get_editor_property'):
                try:
                    value = container.get_editor_property(attribute_name)
                    sequence = _find_sequence_in_container(value)
                    if sequence:
                        return sequence
                except Exception:
                    continue
    except Exception:
        pass

    return None


def _get_current_sequence_from_open_assets():
    try:
        if hasattr(unreal, 'AssetEditorSubsystem'):
            asset_subsystem = unreal.AssetEditorSubsystem()
            assets = _try_call(asset_subsystem, [
                'get_all_editor_assets',
                'get_open_editor_assets',
                'get_editor_assets',
                'get_all_editor_asset',
            ])
            sequence = _find_sequence_in_container(assets)
            if sequence:
                _log(f"get_current_sequence fallback open asset -> {sequence}")
                return sequence
    except Exception as exc:
        _log(f"get_current_sequence open asset fallback ERROR: {exc}")
    _log("get_current_sequence fallback open assets -> no LevelSequence found")
    return None


def _get_current_sequence_from_selected_assets():
    try:
        if hasattr(unreal, 'EditorUtilitySubsystem'):
            utility_subsystem = unreal.EditorUtilitySubsystem()
            assets = _try_call(utility_subsystem, [
                'get_selected_assets',
                'get_selected_asset',
                'get_selected_assets_from_content_browser',
            ])
            sequence = _find_sequence_in_container(assets)
            if sequence:
                _log(f"get_current_sequence fallback selected asset -> {sequence}")
                return sequence

        if hasattr(unreal, 'AssetEditorSubsystem'):
            asset_subsystem = unreal.AssetEditorSubsystem()
            assets = _try_call(asset_subsystem, [
                'get_selected_assets',
                'get_selected_asset',
            ])
            sequence = _find_sequence_in_container(assets)
            if sequence:
                _log(f"get_current_sequence fallback selected asset (AssetEditorSubsystem) -> {sequence}")
                return sequence

        if hasattr(unreal, 'EditorAssetLibrary'):
            assets = _try_call(unreal.EditorAssetLibrary, [
                'get_selected_assets',
                'get_selected_asset',
            ])
            sequence = _find_sequence_in_container(assets)
            if sequence:
                _log(f"get_current_sequence fallback selected asset (EditorAssetLibrary) -> {sequence}")
                return sequence
    except Exception as exc:
        _log(f"get_current_sequence selected asset fallback ERROR: {exc}")
    _log("get_current_sequence fallback selected assets -> no LevelSequence found")
    return None


def _get_current_sequence_from_actors():
    try:
        if hasattr(unreal, 'LevelSequenceActor') and hasattr(unreal, 'GameplayStatics'):
            world = get_world()
            if world:
                actors = _try_call(unreal.GameplayStatics, ['get_all_actors_of_class', 'get_all_actors_of_class'], world, unreal.LevelSequenceActor)
                if actors:
                    for actor in actors:
                        sequence = None
                        if hasattr(actor, 'get_sequence'):
                            sequence = actor.get_sequence()
                        elif hasattr(actor, 'sequence'):
                            try:
                                sequence = actor.sequence
                            except Exception:
                                sequence = None
                        if _is_level_sequence_object(sequence):
                            _log(f"get_current_sequence fallback actor -> {sequence}")
                            return sequence
    except Exception as exc:
        _log(f"get_current_sequence actor fallback ERROR: {exc}")
    _log("get_current_sequence fallback actors -> no sequence found")
    return None


def _get_current_sequence_from_sequence_editor():
    try:
        if hasattr(unreal, 'LevelSequenceEditorBlueprintLibrary'):
            sequence = _try_call(unreal.LevelSequenceEditorBlueprintLibrary, [
                'get_current_level_sequence',
                'get_current_sequence',
                'get_current_sequence_asset',
                'get_active_sequence',
            ])
            if sequence and _is_level_sequence_object(sequence):
                _log(f"get_current_sequence via LevelSequenceEditorBlueprintLibrary active -> {sequence}")
                return sequence
    except Exception as exc:
        _log(f"get_current_sequence sequence editor fallback ERROR: {exc}")
    return None


def _get_current_sequence_from_sequencer_subsystems():
    try:
        candidates = [
            ('SequencerTools.get_current_level_sequence', unreal.SequencerTools if hasattr(unreal, 'SequencerTools') else None, ['get_current_level_sequence', 'get_current_sequence', 'get_active_sequence']),
        ]
        for label, module, methods in candidates:
            if module is None:
                continue
            sequence = _try_call(module, methods)
            if sequence and _is_level_sequence_object(sequence):
                _log(f"get_current_sequence via {label} -> {sequence}")
                return sequence
    except Exception as exc:
        _log(f"get_current_sequence sequencer subsystem fallback ERROR: {exc}")
    return None


def get_current_sequence():
    try:
        sequence = _get_current_sequence_from_sequence_editor()
        if sequence:
            _log(f"get_current_sequence -> {sequence}")
            return sequence

        sequence = _get_current_sequence_from_sequencer_subsystems()
        if sequence:
            _log(f"get_current_sequence -> {sequence}")
            return sequence
    except Exception as exc:
        _log(f"get_current_sequence ERROR: {exc}")

    sequence = _get_current_sequence_from_open_assets()
    if sequence:
        _log("get_current_sequence -> found sequence via open assets")
        return sequence

    sequence = _get_current_sequence_from_selected_assets()
    if sequence:
        _log("get_current_sequence -> found sequence via selected assets")
        return sequence

    sequence = _get_current_sequence_from_actors()
    if sequence:
        _log("get_current_sequence -> found sequence via LevelSequenceActor")
        return sequence

    _log("get_current_sequence -> no current sequence found")
    return None


def get_world():
    try:
        subsystem = unreal.UnrealEditorSubsystem()
        if subsystem and hasattr(subsystem, "get_editor_world"):
            world = subsystem.get_editor_world()
            if world:
                _log(f"get_world -> {world}")
                return world
    except Exception as exc:
        _log(f"get_world via UnrealEditorSubsystem ERROR: {exc}")

    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        _log(f"get_world -> {world}")
        return world
    except Exception as exc:
        _log(f"get_world ERROR: {exc}")
        return None


def collect_all_bindings(sequence):
    if not sequence:
        _log("collect_all_bindings -> no sequence")
        return []
    try:
        bindings = list(sequence.get_bindings())
        _log(f"collect_all_bindings -> count={len(bindings)}")
        return bindings
    except Exception as exc:
        _log(f"collect_all_bindings ERROR: {exc}")
        return []


def collect_all_tracks(sequence):
    if not sequence:
        _log("collect_all_tracks -> no sequence")
        return []

    for method_name in ("get_tracks", "get_master_tracks", "get_all_tracks"):
        method = getattr(sequence, method_name, None)
        if not callable(method):
            continue
        try:
            tracks = list(method())
            _log(f"collect_all_tracks -> using {method_name}(), count={len(tracks)}")
            return tracks
        except Exception as exc:
            _log(f"collect_all_tracks -> {method_name}() failed: {exc}")

    _log(
        "collect_all_tracks -> no working get_tracks()/get_master_tracks/"
        "get_all_tracks() method found on this sequence/engine build -- "
        "master tracks (e.g. Camera Cut Track) will NOT be included in the "
        "export. This does not affect bindings/body/camera animation "
        "themselves, but may affect anything that depends on the Camera "
        "Cut track specifically."
    )
    return []


def build_output_path(config=None, filename=None, folder=None):
    if config is None:
        config = {}

    output_dir = folder or config.get("default_output_folder") or os.path.join(os.path.expanduser("~"), "Exports")
    output_dir = os.path.expanduser(str(output_dir)) if output_dir else os.path.join(os.path.expanduser("~"), "Exports")
    if folder:
        os.makedirs(output_dir, exist_ok=True)
    elif not os.path.isdir(output_dir):
        output_dir = os.path.join(os.path.expanduser("~"), "Exports")
        os.makedirs(output_dir, exist_ok=True)

    if filename is None:
        filename = config.get("default_output_filename", "exported_sequence.fbx")

    if not filename.lower().endswith(".fbx"):
        filename = f"{filename}.fbx"

    return os.path.join(output_dir, filename)


def _prompt_for_output_path(default_dir):
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.asksaveasfilename(
            title="Wybierz miejsce zapisu FBX",
            initialdir=default_dir,
            initialfile="exported_sequence.fbx",
            defaultextension=".fbx",
            filetypes=[("FBX files", "*.fbx")],
        )
        root.destroy()
        return path or None
    except Exception as exc:
        _log(f"save dialog ERROR: {exc}")
        return None


def _resolve_output_path(output_path, config=None):
    if output_path:
        return output_path

    if config is None:
        config = {}

    output_dir = config.get("default_output_folder") or os.path.join(os.path.expanduser("~"), "Exports")
    output_dir = os.path.expanduser(str(output_dir)) if output_dir else os.path.join(os.path.expanduser("~"), "Exports")
    if not os.path.isdir(output_dir):
        output_dir = os.path.join(os.path.expanduser("~"), "Exports")
    os.makedirs(output_dir, exist_ok=True)

    if config.get("show_save_dialog", True):
        dialog_path = _prompt_for_output_path(output_dir)
        if dialog_path:
            return dialog_path

    filename = config.get("default_output_filename", "exported_sequence.fbx")
    return build_output_path(config=config, filename=filename, folder=output_dir)


def _make_frame_time(frame: int):
    if hasattr(unreal, 'FrameNumber'):
        try:
            return unreal.FrameNumber(frame)
        except Exception:
            pass
    if hasattr(unreal, 'FrameTime'):
        try:
            return unreal.FrameTime(frame)
        except Exception:
            pass
    return frame


def _save_sequence_playhead(sequence):
    if not sequence:
        return None

    if hasattr(unreal.LevelSequenceEditorBlueprintLibrary, 'get_current_time'):
        try:
            current = unreal.LevelSequenceEditorBlueprintLibrary.get_current_time()
            _log(f"Saved current sequence time: {current}")
            return current
        except Exception as exc:
            _log(f"get_current_time failed: {exc}")

    if hasattr(unreal.LevelSequenceEditorBlueprintLibrary, 'get_current_frame'):
        try:
            current = unreal.LevelSequenceEditorBlueprintLibrary.get_current_frame()
            _log(f"Saved current sequence frame: {current}")
            return current
        except Exception as exc:
            _log(f"get_current_frame failed: {exc}")

    return None


def _restore_sequence_playhead(sequence, saved_time):
    if not sequence or saved_time is None:
        return False

    if hasattr(unreal.LevelSequenceEditorBlueprintLibrary, 'set_current_time'):
        try:
            unreal.LevelSequenceEditorBlueprintLibrary.set_current_time(saved_time)
            _log(f"Restored sequence time: {saved_time}")
            return True
        except Exception as exc:
            _log(f"set_current_time failed: {exc}")

    if hasattr(unreal.LevelSequenceEditorBlueprintLibrary, 'set_current_frame'):
        try:
            if hasattr(saved_time, 'frame_number'):
                frame = int(saved_time.frame_number)
            else:
                frame = int(saved_time)
            unreal.LevelSequenceEditorBlueprintLibrary.set_current_frame(_make_frame_time(frame))
            _log(f"Restored sequence frame: {frame}")
            return True
        except Exception as exc:
            _log(f"set_current_frame failed: {exc}")
    return False


def _filter_by_explicit_selection(items, selected, get_display_name_fn=_get_display_name, get_binding_id_fn=None):
    """
    Filter items by an explicit user selection. `selected` may be a set of
    stable binding ids (preferred) or a set of display names (legacy).
    If `get_binding_id_fn` is provided it will be used to extract the
    stable id for comparison.
    """
    if selected is None:
        return items
    if not selected:
        _log("_filter_by_explicit_selection -> selected empty, returning []")
        return []

    if get_binding_id_fn is None:
        get_binding_id_fn = lambda item: str(getattr(item, "binding_id", ""))

    item_names = [get_display_name_fn(item) for item in items]
    item_ids = [get_binding_id_fn(item) for item in items]

    # Match if either the stable id or the display name is present in the
    # selection set. This keeps backward compatibility with older callers
    # that still supply display-name based selections.
    filtered = [item for item in items if (get_binding_id_fn(item) in selected) or (get_display_name_fn(item) in selected)]
    filtered_names = [get_display_name_fn(item) for item in filtered]

    try:
        sel_sorted = sorted(selected)
    except Exception:
        sel_sorted = list(selected)

    _log(
        f"_filter_by_explicit_selection -> selected={sel_sorted} | "
        f"items_before={item_names} | items_after={filtered_names}"
    )
    return filtered


def _binding_matches_name(binding, needle_tokens):
    if binding is None:
        return False
    try:
        display_name = _get_display_name(binding)
    except Exception:
        display_name = str(binding)
    if not display_name:
        return False
    lowered = str(display_name).lower()
    return any(token in lowered for token in needle_tokens)


def _is_metahuman_body_binding(binding):
    return _binding_matches_name(binding, (
        "body", "metahuman", "pelvis", "spine", "clavicle", "neck", "head",
        "upperarm", "lowerarm", "hand", "skeleton", "root"
    ))


def _is_metahuman_face_binding(binding):
    return _binding_matches_name(binding, (
        "face", "facial", "jaw", "lip", "brow", "mouth", "cheek", "nose",
        "eye", "blendshape", "morph", "teeth", "cartilage"
    ))


def _log_runtime_merge_probe(sequence, bindings, selection=None):
    selected_ids = set((selection or {}).get("binding_ids") or []) if selection else set()
    if not selected_ids:
        selected_ids = set((selection or {}).get("binding_names") or []) if selection else set()

    selected_items = []
    for binding in bindings:
        try:
            binding_id = str(getattr(binding, "binding_id", ""))
        except Exception:
            binding_id = ""
        display_name = _get_display_name(binding)
        if binding_id in selected_ids or display_name in selected_ids:
            selected_items.append(binding)

    body_items = [item for item in selected_items if _is_metahuman_body_binding(item)]
    face_items = [item for item in selected_items if _is_metahuman_face_binding(item)]
    has_settings = hasattr(unreal, "SkeletalMeshMergeSettings")
    has_utilities = hasattr(unreal, "SkeletalMeshMergeUtilities")
    merge_requested = bool((selection or {}).get("merge_body_face"))

    _log(
        "[exUE5][FLOW] merge_probe "
        f"dialog_selection.merge_body_face={merge_requested} "
        f"selected_binding_ids={sorted(selected_ids)} "
        f"selected_body_bindings={len(body_items)} "
        f"selected_face_bindings={len(face_items)} "
        f"has_SkeletalMeshMergeSettings={has_settings} "
        f"has_SkeletalMeshMergeUtilities={has_utilities}"
    )

    if not merge_requested:
        _log("[exUE5][FLOW] merge_decision=skipped reason=checkbox_off")
    elif not selected_ids:
        _log("[exUE5][FLOW] merge_decision=skipped reason=no_selected_binding_ids")
    elif not body_items or not face_items:
        _log("[exUE5][FLOW] merge_decision=skipped reason=missing_body_or_face_selection")
    elif not (has_settings or has_utilities):
        _log("[exUE5][FLOW] merge_decision=skipped reason=api_unavailable")
    else:
        _log("[exUE5][FLOW] merge_decision=activated reason=runtime_api_available")


def _try_prepare_ue5_body_face_merge(sequence, bindings, selection=None):
    _log_runtime_merge_probe(sequence, bindings, selection)

    if not sequence or not bindings:
        return list(bindings), False, "no bindings"

    if not selection or not selection.get("merge_body_face"):
        return list(bindings), False, "merge disabled"

    selected_ids = set(selection.get("binding_ids") or [])
    if not selected_ids:
        selected_ids = set(selection.get("binding_names") or [])
    if not selected_ids:
        _log("[exUE5][FLOW] merge_decision=skipped reason=no_selected_binding_ids")
        return list(bindings), False, "no selected binding ids"

    selected_items = []
    for binding in bindings:
        try:
            binding_id = str(getattr(binding, "binding_id", ""))
        except Exception:
            binding_id = ""
        display_name = _get_display_name(binding)
        if binding_id in selected_ids or display_name in selected_ids:
            selected_items.append(binding)

    body_items = [item for item in selected_items if _is_metahuman_body_binding(item)]
    face_items = [item for item in selected_items if _is_metahuman_face_binding(item)]

    if not body_items or not face_items:
        _log("[exUE5][FLOW] merge_decision=skipped reason=missing_body_or_face_selection")
        return list(bindings), False, "missing body or face selection"

    has_settings = hasattr(unreal, "SkeletalMeshMergeSettings")
    has_utilities = hasattr(unreal, "SkeletalMeshMergeUtilities")
    if not (has_settings or has_utilities):
        _log("[exUE5][FLOW] merge_decision=skipped reason=api_unavailable")
        return list(bindings), False, "api unavailable"

    _log(
        "[exUE5][FLOW] merge_decision=deferred reason=runtime_api_detected_waiting_for_validation"
    )
    return list(bindings), False, "deferred until runtime validation"


def build_export_params(sequence, output_path, config=None, selection=None, auto_fix_state=None):
    if config is None:
        config = {}

    _log(f"build_export_params -> output_path={output_path}")
    _log(f"build_export_params -> config={config}")
    _log(
        "[exUE5][FLOW] selection=input "
        f"selection={selection} "
        f"selection_has_binding_ids={bool((selection or {}).get('binding_ids'))} "
        f"selection_has_track_names={bool((selection or {}).get('track_names'))} "
        f"selection_merge_body_face={bool((selection or {}).get('merge_body_face'))}"
    )

    params = unreal.SequencerExportFBXParams()
    params.sequence = sequence
    params.root_sequence = sequence
    params.world = get_world()
    params.fbx_file_name = output_path

    all_bindings = collect_all_bindings(sequence)
    bindings = list(all_bindings)
    tracks = collect_all_tracks(sequence)
    _log(f"[exUE5][FLOW] pre_filter_bindings={len(bindings)} pre_filter_tracks={len(tracks)}")

    if selection is not None:
        binding_selector = selection.get("binding_ids") if selection.get("binding_ids") is not None else selection.get("binding_names")
        bindings = _filter_by_explicit_selection(bindings, binding_selector, _get_display_name)
        tracks = _filter_by_explicit_selection(tracks, selection.get("track_names"), _get_display_name)
        _log(
            "[exUE5][FLOW] after_selection_filter "
            f"selected_ids={sorted(set(selection.get('binding_ids') or []))} "
            f"filtered_bindings={len(bindings)} filtered_tracks={len(tracks)}"
        )
    else:
        bindings = _filter_sequence_items(bindings, config)
        tracks = _filter_sequence_items(tracks, config)
        _log("[exUE5][FLOW] after_config_filter bindings={len(bindings)} tracks={len(tracks)}")

    bindings, merge_applied, merge_reason = _try_prepare_ue5_body_face_merge(sequence, bindings, selection)
    if merge_applied:
        _log(f"[exUE5][FLOW] merge_decision=applied reason={merge_reason}")
    else:
        _log(f"[exUE5][FLOW] merge_decision=skipped reason={merge_reason}")

    _apply_spawnable_auto_fix_if_needed(sequence, bindings, config, auto_fix_state or [])
    _log("[exUE5][FLOW] before_spawnable_check bindings={len(bindings)}")
    flagged_spawnables = _warn_about_spawnable_export_bug(sequence, bindings, all_bindings)
    _log(f"[exUE5][FLOW] after_spawnable_check flagged_spawnables={len(flagged_spawnables)}")

    _log(f"build_export_params -> bindings={len(bindings)} tracks={len(tracks)}")
    params.bindings = bindings
    params.tracks = tracks
    _log(f"[exUE5][FLOW] export_params_ready bindings={len(params.bindings)} tracks={len(params.tracks)} output={output_path}")

    return params, flagged_spawnables


def export_current_sequence(output_path=None, config=None, selection=None):
    if config is None:
        config = load_config()

    _log("=== EXPORT START ===")
    _log(
        "[exUE5][FLOW] export_action_start "
        f"selection={selection} "
        f"output_path={output_path} "
        f"config_keys={sorted(config.keys()) if isinstance(config, dict) else type(config).__name__}"
    )

    output_path = _resolve_output_path(output_path, config)
    _log(f"output_path={output_path}")

    sequence = get_current_sequence()
    if not sequence:
        _log("EXPORT FAILED: Brak aktualnie otwartego Level Sequence.")
        raise RuntimeError("Brak aktualnie otwartego Level Sequence.")

    world = get_world()
    if not world:
        _log("EXPORT FAILED: Brak aktywnego World/Level.")
        raise RuntimeError("Brak aktywnego World/Level.")

    saved_time = _save_sequence_playhead(sequence)
    auto_fix_state = []
    _log("[exUE5][FLOW] calling_build_export_params")
    params, flagged_spawnables = build_export_params(sequence, output_path, config, selection=selection, auto_fix_state=auto_fix_state)
    _log("[exUE5][FLOW] returned_from_build_export_params")
    _log(
        "[exUE5][FLOW] pre_export_action "
        f"sequence={sequence} "
        f"binding_count={len(params.bindings) if params else 0} "
        f"track_count={len(params.tracks) if params else 0} "
        f"flagged_spawnables={len(flagged_spawnables)}"
    )

    try:
        _log("Calling unreal.SequencerTools.export_level_sequence_fbx(params)...")
        success = unreal.SequencerTools.export_level_sequence_fbx(params)
        _log(f"export_level_sequence_fbx returned: {success}")
    except Exception as exc:
        _log(f"EXPORT FAILED: {exc}")
        _log(traceback.format_exc())
        raise RuntimeError(f"Błąd wywołania eksportu: {exc}") from exc
    finally:
        if saved_time is not None:
            _restore_sequence_playhead(sequence, saved_time)
        _remove_spawnable_auto_fix(auto_fix_state)

    if not success:
        _log("EXPORT FAILED: Eksport FBX zakończył się niepowodzeniem.")
        raise RuntimeError("Eksport FBX zakończył się niepowodzeniem.")

    if flagged_spawnables:
        _log(
            f"=== SPAWNABLE CHECK: UWAGA: eksport zawierał {len(flagged_spawnables)} Spawnable binding(ów): "
            f"{flagged_spawnables}. Jeśli w Blenderze widzisz zdublowane obiekty (np. CubeXX, CubeYY zamiast jednego Cube) — to jest ten bug. "
            "Fix: w Sequencerze PPM na tracku -> Convert to Possessable -> re-export. ==="
        )
    else:
        _log(
            "=== SPAWNABLE CHECK: Brak Spawnable bindingów w eksporcie — jeśli mimo to widzisz duplikaty w Blenderze, "
            "to inny problem, nie ten znany bug. ==="
        )

    result = {
        "success": True,
        "sequence": sequence.get_name(),
        "output_path": output_path,
        "world": world.get_name() if hasattr(world, "get_name") else None,
        "flagged_spawnables": flagged_spawnables,
    }
    _log(f"EXPORT SUCCESS: {result}")
    return result


