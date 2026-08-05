import os

try:
    import unreal
except ModuleNotFoundError:
    unreal = None

try:
    from exUE5.spawnable_diagnostics import _get_display_name, _format_binding_id
except ModuleNotFoundError:
    from spawnable_diagnostics import _get_display_name, _format_binding_id


def _is_camera_binding(binding):
    if binding is None:
        return False
    try:
        name = _get_display_name(binding)
    except Exception:
        name = str(binding)
    if not name:
        return False
    lowered = str(name).lower()
    tokens = (
        "camera",
        "cam",
        "sensor",
        "focal",
        "focus",
        "aperture",
        "filmback",
        "film back",
        "lens",
        "focal length",
        "kam",
    )
    return any(token in lowered for token in tokens)


def _is_camera_actor(obj):
    if obj is None:
        return False
    try:
        cls_name = obj.get_class().get_name().lower()
    except Exception:
        cls_name = ""
    try:
        name = _get_display_name(obj).lower()
    except Exception:
        name = ""
    return "camera" in cls_name or "camera" in name or "cinecamera" in cls_name or "cine" in cls_name


def _get_selected_camera_actors():
    actors = []
    if unreal is None:
        return actors
    try:
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        selected = list(actor_subsystem.get_selected_level_actors())
    except Exception:
        selected = list(unreal.EditorLevelLibrary.get_selected_level_actors())
    for obj in selected:
        if _is_camera_actor(obj):
            actors.append(obj)
    unreal.log(f"[exUE5][FLOW] camera_export selected camera actors count={len(actors)}")
    return actors


def _resolve_camera_actors(sequence, camera_binding_ids):
    actors = []
    if unreal is None or sequence is None:
        return actors

    lib = unreal.LevelSequenceEditorBlueprintLibrary
    binding_list = sequence.get_bindings()
    unreal.log(f"[exUE5][FLOW] camera_export resolving camera actors for {len(binding_list)} bindings")
    unreal.log(f"[exUE5][FLOW] camera_export camera_binding_ids={camera_binding_ids}")

    normalized_camera_binding_ids = set(str(item) for item in camera_binding_ids)
    for binding in binding_list:
        raw_binding_id = getattr(binding, "binding_id", None)
        bid = _format_binding_id(raw_binding_id) or ""
        raw_bid_str = str(raw_binding_id) if raw_binding_id is not None else ""
        name = _get_display_name(binding)
        unreal.log(
            f"[exUE5][FLOW] camera_export checking binding '{name}' id='{bid}' raw_id='{raw_bid_str}'"
        )
        if bid not in normalized_camera_binding_ids and raw_bid_str not in normalized_camera_binding_ids and name not in normalized_camera_binding_ids:
            unreal.log(f"[exUE5][FLOW] camera_export skipping binding '{name}'")
            continue
        try:
            proxy = unreal.SequencerBindingProxy(binding.binding_id, sequence)
            bound = lib.get_bound_objects(proxy) if hasattr(lib, "get_bound_objects") else []
            unreal.log(f"[exUE5][FLOW] camera_export bound objects count={len(bound)} for binding '{name}'")
        except Exception as exc:
            _log = lambda message: print(message) if unreal is None else unreal.log(message)
            _log(f"[exUE5][WARNING] camera_export: nie udało się rozwiązać bindingu '{name}': {exc}")
            bound = []
        for obj in bound:
            try:
                obj_label = obj.get_actor_label() if hasattr(obj, "get_actor_label") else str(obj)
            except Exception:
                obj_label = str(obj)
            unreal.log(f"[exUE5][FLOW] camera_export bound object type={type(obj).__name__} label={obj_label}")
            if isinstance(obj, unreal.Actor) and _is_camera_actor(obj):
                actors.append(obj)
                unreal.log(f"[exUE5][FLOW] camera_export added actor '{obj_label}'")
            else:
                unreal.log(f"[exUE5][FLOW] camera_export skipped non-camera object '{obj_label}'")
    if not actors:
        unreal.log("[exUE5][FLOW] camera_export no sequence-bound camera actors found, falling back to selected actors")
        actors = _get_selected_camera_actors()
    unreal.log(f"[exUE5][FLOW] camera_export resolved {len(actors)} camera actors")
    return actors


def _sanitize_filename(filename):
    import re
    sanitized = re.sub(r"[^0-9A-Za-z._-]", "_", filename or "camera")
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("._-") or "camera"


def _run_single_camera_export(actor, output_path, options, show_dialog, prompt):
    task = unreal.AssetExportTask()
    task.object = actor
    task.filename = os.path.normpath(output_path)
    task.selected = False
    task.automated = not prompt
    task.prompt = prompt
    task.replace_identical = True
    task.options = options
    unreal.log(
        f"[exUE5][FLOW] camera_export task.object={actor} filename={task.filename} "
        f"automated={task.automated} prompt={task.prompt}"
    )
    return bool(unreal.Exporter.run_asset_export_task(task))


def export_cameras_fbx(sequence, camera_binding_ids, output_path, show_dialog=True):
    if unreal is None:
        raise RuntimeError("unreal module not available")

    lib = unreal.LevelSequenceEditorBlueprintLibrary
    saved_time = None
    if hasattr(lib, "get_current_time"):
        try:
            saved_time = lib.get_current_time()
        except Exception:
            saved_time = None

    try:
        unreal.log(f"[exUE5][FLOW] camera_export start binding_ids={camera_binding_ids} output_path={output_path}")
        if hasattr(lib, "set_current_time") and hasattr(sequence, "get_playback_start"):
            try:
                lib.set_current_time(sequence.get_playback_start())
            except Exception:
                pass

        actors = _resolve_camera_actors(sequence, camera_binding_ids)
        if not actors:
            raise RuntimeError(
                "Nie znaleziono żadnego aktora kamery w świecie dla zaznaczonych bindingów. "
                "Sprawdź, czy Spawnable jest zespawnowany w bieżącej klatce."
            )
        actor_labels = [a.get_actor_label() for a in actors]
        unreal.log(f"[exUE5][FLOW] camera_export resolved actors={actor_labels}")

        options = unreal.FbxExportOption()
        options.export_local_time = True
        options.export_preview_mesh = True
        options.export_morph_targets = False
        if hasattr(unreal, "MovieSceneBakeType") and hasattr(unreal.MovieSceneBakeType, "BAKE_TRANSFORMS"):
            options.bake_camera_and_light_animation = unreal.MovieSceneBakeType.BAKE_TRANSFORMS
            if hasattr(options, "bake_actor_animation"):
                options.bake_actor_animation = unreal.MovieSceneBakeType.NONE
        else:
            unreal.log("[exUE5][WARNING] camera_export: MovieSceneBakeType.BAKE_TRANSFORMS niedostępne na tej wersji silnika")
        unreal.log(
            f"[exUE5][FLOW] camera_export options export_local_time={options.export_local_time} "
            f"export_preview_mesh={getattr(options, 'export_preview_mesh', None)} "
            f"bake_camera_and_light_animation={getattr(options, 'bake_camera_and_light_animation', None)} "
            f"bake_actor_animation={getattr(options, 'bake_actor_animation', None)}"
        )

        if not output_path:
            raise RuntimeError("Nie podano output_path dla eksportu kamery")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as exc:
                unreal.log(f"[exUE5][ERROR] camera_export: nie udało się utworzyć folderu '{output_dir}': {exc}")
                raise

        if len(actors) == 1:
            output_file = os.path.normpath(output_path)
            unreal.log(f"[exUE5][FLOW] camera_export exporting single camera actor: {actor_labels[0]}")
            return _run_single_camera_export(actors[0], output_file, options, show_dialog, show_dialog)

        prefix = os.path.splitext(os.path.basename(output_path))[0]
        if not prefix:
            prefix = "KAMERA_TRANS"
        success = True
        actor_name_counts = {}
        for index, actor in enumerate(actors):
            label = actor.get_actor_label() if hasattr(actor, "get_actor_label") else f"camera_{index}"
            safe_label = _sanitize_filename(label)
            count = actor_name_counts.get(safe_label, 0) + 1
            actor_name_counts[safe_label] = count
            if count > 1:
                safe_label = f"{safe_label}_{count}"
            output_file = os.path.join(output_dir or os.getcwd(), f"{prefix}_{safe_label}.fbx")
            prompt = show_dialog and index == 0
            if not _run_single_camera_export(actor, output_file, options, show_dialog, prompt):
                success = False
        return success
    finally:
        if saved_time is not None and hasattr(lib, "set_current_time"):
            try:
                lib.set_current_time(saved_time)
            except Exception:
                pass
