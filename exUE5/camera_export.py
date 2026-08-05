import os

try:
    import unreal
except ModuleNotFoundError:
    unreal = None

try:
    from exUE5.spawnable_diagnostics import (
        _get_display_name,
        _format_binding_id,
        _get_spawnable_binding_ids,
    )
except ModuleNotFoundError:
    from spawnable_diagnostics import (
        _get_display_name,
        _format_binding_id,
        _get_spawnable_binding_ids,
    )

try:
    from exUE5.exporter_core import get_world
except ModuleNotFoundError:
    try:
        from exporter_core import get_world
    except ModuleNotFoundError:
        get_world = None


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


def _resolve_camera_bindings(sequence, camera_binding_ids):
    """Znajdź w sekwencji bindingi kamer odpowiadające zaznaczonym ID.

    To jest dokładnie ta sama identyfikacja bindingu, której UE5 używa po
    kliknięciu PPM na tracku w Sequencerze i wybraniu "Export..." (patrz
    11.png) - dopasowanie po sformatowanym binding_id, surowym binding_id
    lub nazwie wyświetlanej.
    """
    bindings = []
    if unreal is None or sequence is None:
        return bindings

    binding_list = sequence.get_bindings()
    unreal.log(f"[exUE5][FLOW] camera_export resolving camera bindings for {len(binding_list)} bindings")
    unreal.log(f"[exUE5][FLOW] camera_export camera_binding_ids={camera_binding_ids}")

    normalized_camera_binding_ids = set(str(item) for item in camera_binding_ids)
    for binding in binding_list:
        raw_binding_id = getattr(binding, "binding_id", None)
        bid = _format_binding_id(raw_binding_id) or ""
        raw_bid_str = str(raw_binding_id) if raw_binding_id is not None else ""
        name = _get_display_name(binding)
        if bid in normalized_camera_binding_ids or raw_bid_str in normalized_camera_binding_ids or name in normalized_camera_binding_ids:
            bindings.append(binding)
            unreal.log(f"[exUE5][FLOW] camera_export matched binding '{name}' id='{bid}'")
        else:
            unreal.log(f"[exUE5][FLOW] camera_export skipping binding '{name}'")

    unreal.log(f"[exUE5][FLOW] camera_export resolved {len(bindings)} camera bindings")
    return bindings


def _resolve_camera_actors(sequence, camera_binding_ids):
    """Zapasowa (legacy) rezolucja aktorów kamer - używana WYŁĄCZNIE gdy w
    sekwencji nie da się dopasować żadnego bindingu (patrz
    _export_camera_actors_legacy). Ta ścieżka NIE odzwierciedla 1:1
    natywnego eksportu z Sequencera.
    """
    actors = []
    if unreal is None or sequence is None:
        return actors

    lib = unreal.LevelSequenceEditorBlueprintLibrary
    binding_list = sequence.get_bindings()
    normalized_camera_binding_ids = set(str(item) for item in camera_binding_ids)
    for binding in binding_list:
        raw_binding_id = getattr(binding, "binding_id", None)
        bid = _format_binding_id(raw_binding_id) or ""
        raw_bid_str = str(raw_binding_id) if raw_binding_id is not None else ""
        name = _get_display_name(binding)
        if bid not in normalized_camera_binding_ids and raw_bid_str not in normalized_camera_binding_ids and name not in normalized_camera_binding_ids:
            continue
        try:
            proxy = unreal.SequencerBindingProxy(binding.binding_id, sequence)
            bound = lib.get_bound_objects(proxy) if hasattr(lib, "get_bound_objects") else []
        except Exception as exc:
            unreal.log(f"[exUE5][WARNING] camera_export: nie udało się rozwiązać bindingu '{name}': {exc}")
            bound = []
        for obj in bound:
            if isinstance(obj, unreal.Actor) and _is_camera_actor(obj):
                actors.append(obj)
    if not actors:
        actors = _get_selected_camera_actors()
    unreal.log(f"[exUE5][FLOW] camera_export (legacy) resolved {len(actors)} camera actors")
    return actors


def _sanitize_filename(filename):
    import re
    sanitized = re.sub(r"[^0-9A-Za-z._-]", "_", filename or "camera")
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("._-") or "camera"


def _build_native_fbx_export_options():
    """Zbuduje unreal.FbxExportOption z ustawieniami IDENTYCZNYMI jak w oknie
    "FBX Export Options" pokazanym po PPM -> Export na kamerze w Sequencerze
    (patrz 22.png). Każde pole ustawiane jest defensywnie (hasattr), żeby
    skrypt nie wysypał się na starszych wersjach silnika, w których część
    tych opcji jeszcze nie istnieje.
    """
    options = unreal.FbxExportOption()

    def _set(name, value):
        try:
            if hasattr(options, name):
                setattr(options, name, value)
                unreal.log(f"[exUE5][FLOW] camera_export option {name}={value}")
            else:
                unreal.log(f"[exUE5][WARNING] camera_export: opcja '{name}' niedostępna w tej wersji silnika (pomijam)")
        except Exception as exc:
            unreal.log(f"[exUE5][WARNING] camera_export: nie udało się ustawić opcji '{name}': {exc}")

    # --- Exporter ---
    if hasattr(unreal, "FbxExportCompatibility") and hasattr(unreal.FbxExportCompatibility, "FBX_2013"):
        _set("fbx_export_compatibility", unreal.FbxExportCompatibility.FBX_2013)

    # --- Exporter > Advanced ---
    _set("ascii", False)
    _set("force_front_x_axis", False)

    # --- Mesh ---
    _set("vertex_color", False)
    _set("level_of_detail", False)

    # --- Static Mesh ---
    _set("collision", False)
    _set("export_source_mesh", False)

    # --- Skeletal Mesh ---
    _set("export_morph_targets", False)

    # --- Animation ---
    _set("export_preview_mesh", True)
    _set("map_skeletal_motion_to_root", False)
    _set("export_local_time", True)

    # --- Animation > Advanced ---
    if hasattr(unreal, "MovieSceneBakeType"):
        if hasattr(unreal.MovieSceneBakeType, "BAKE_TRANSFORMS"):
            _set("bake_camera_and_light_animation", unreal.MovieSceneBakeType.BAKE_TRANSFORMS)
        else:
            unreal.log("[exUE5][WARNING] camera_export: MovieSceneBakeType.BAKE_TRANSFORMS niedostępne na tej wersji silnika")
        if hasattr(unreal.MovieSceneBakeType, "NONE"):
            _set("bake_actor_animation", unreal.MovieSceneBakeType.NONE)

    # --- Material ---
    if hasattr(unreal, "FbxMaterialBakeMode") and hasattr(unreal.FbxMaterialBakeMode, "DISABLED"):
        _set("bake_material_inputs", unreal.FbxMaterialBakeMode.DISABLED)

    # --- Material > Default Material Bake Size (1024x1024, Auto Detect ON) ---
    # Nie ma to wpływu na eksport dopóki Bake Material Inputs = Disabled,
    # ustawiane wyłącznie dla pełnej zgodności z oknem dialogowym z 22.png.
    try:
        if hasattr(options, "default_material_bake_size"):
            bake_size = options.default_material_bake_size
            if hasattr(bake_size, "auto_detect"):
                bake_size.auto_detect = True
            if hasattr(bake_size, "size") and hasattr(unreal, "IntPoint"):
                bake_size.size = unreal.IntPoint(1024, 1024)
            options.default_material_bake_size = bake_size
            unreal.log("[exUE5][FLOW] camera_export option default_material_bake_size=1024x1024 auto_detect=True")
    except Exception as exc:
        unreal.log(f"[exUE5][WARNING] camera_export: nie udało się ustawić default_material_bake_size: {exc}")

    return options


def _get_level_sequence_editor_subsystem():
    """Zwraca unreal.LevelSequenceEditorSubsystem albo None, jeśli nie jest
    dostępny na tej wersji silnika (defensywnie - żeby brak subsystemu nie
    wysypał eksportu, tylko spowodował fallback bez konwersji)."""
    if unreal is None:
        return None
    try:
        return unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
    except Exception as exc:
        unreal.log(f"[exUE5][ERROR] camera_export: nie udało się pobrać LevelSequenceEditorSubsystem: {exc}")
        return None


def _convert_spawnables_to_possessables(sequence, bindings):
    """Naprawa właściwa dla znanego bugu UE5.8: jeśli binding kamery jest
    Spawnable, export_level_sequence_fbx wywołany z automatyzacji/Pythona
    (poza normalnym scrubowaniem playheadu przez usera) potrafi zbake'ować
    animację o zerowej długości (statyczna jednoklatkowa transformacja -
    patrz diagnoza w treści zgłoszenia). Test kontrolny użytkownika
    potwierdził, że ręczna konwersja PPM -> "Convert Selected Binding(s)
    To... -> Possessable" + eksport działa poprawnie - więc robimy
    programowo dokładnie to samo, PRZED wywołaniem
    export_level_sequence_fbx, dla każdej zaznaczonej kamery Spawnable.

    WAŻNE: convert_to_possessable() zwraca NOWY MovieSceneBindingProxy
    (nowy GUID) - stary binding_id spawnable'a przestaje być poprawny po
    konwersji. Dlatego trzeba (a) użyć NOWEGO proxy do samego eksportu, i
    (b) zapamiętać ten NOWY proxy (nie stary), żeby po eksporcie
    przywrócić Spawnable dokładnie tej kamery.

    Zwraca (export_bindings, conversion_records):
    - export_bindings: lista bindingów 1:1 z `bindings`, ale ze
      Spawnable'ami zamienionymi na ich nowe Possessable-odpowiedniki.
    - conversion_records: lista {"name", "possessable_binding"} - TYLKO
      dla bindingów, które faktycznie skonwertowano (używana do
      przywracania w finally).
    """
    export_bindings = []
    conversion_records = []

    if unreal is None or sequence is None:
        return list(bindings), conversion_records

    spawnable_ids = _get_spawnable_binding_ids(sequence)
    if not spawnable_ids:
        # Żadna kamera w sekwencji nie jest Spawnable - nic do konwersji.
        return list(bindings), conversion_records

    subsystem = _get_level_sequence_editor_subsystem()
    if subsystem is None or not hasattr(subsystem, "convert_to_possessable"):
        unreal.log(
            "[exUE5][WARNING] camera_export: LevelSequenceEditorSubsystem.convert_to_possessable "
            "niedostępny na tej wersji silnika - eksportuję bez konwersji (kamery Spawnable mogą "
            "wyjść jako statyczna jednoklatkowa transformacja - znany bug UE5.8)."
        )
        return list(bindings), conversion_records

    for binding in bindings:
        binding_id = getattr(binding, "binding_id", None)
        name = _get_display_name(binding)

        if binding_id is None or _format_binding_id(binding_id) not in spawnable_ids:
            # Możliwe (Possessable) - eksportujemy bez zmian.
            export_bindings.append(binding)
            continue

        unreal.log(
            f"[exUE5][FLOW] camera_export: binding '{name}' jest Spawnable - konwertuję na "
            "Possessable przed eksportem (fix UE5.8: Spawnable + automatyzacja Python -> "
            "statyczna klatka bez animacji)."
        )
        try:
            possessable_binding = subsystem.convert_to_possessable(binding)
        except Exception as exc:
            unreal.log(
                f"[exUE5][ERROR] camera_export: konwersja Spawnable->Possessable nie powiodła się "
                f"dla '{name}': {exc}. Eksportuję oryginalny binding (może dać statyczną klatkę)."
            )
            export_bindings.append(binding)
            continue

        if possessable_binding is None:
            unreal.log(
                f"[exUE5][WARNING] camera_export: convert_to_possessable zwróciło None dla '{name}' "
                "- eksportuję oryginalny binding bez konwersji."
            )
            export_bindings.append(binding)
            continue

        export_bindings.append(possessable_binding)
        conversion_records.append({"name": name, "possessable_binding": possessable_binding})
        unreal.log(f"[exUE5][FLOW] camera_export: '{name}' skonwertowana na Possessable OK.")

    return export_bindings, conversion_records


def _restore_spawnables_after_export(conversion_records):
    """Przywraca stan Spawnable dla każdej kamery skonwertowanej przez
    `_convert_spawnables_to_possessables`. Każdy wpis jest przywracany
    NIEZALEŻNIE (własny try/except) - błąd przy przywracaniu jednej kamery
    nie może zablokować przywrócenia pozostałych, zgodnie z wymogiem
    eksportu wielu kamer naraz."""
    if not conversion_records:
        return

    subsystem = _get_level_sequence_editor_subsystem()
    if subsystem is None or not hasattr(subsystem, "convert_to_spawnable"):
        names = [record["name"] for record in conversion_records]
        unreal.log(
            "[exUE5][ERROR] camera_export: nie można przywrócić stanu Spawnable po eksporcie - "
            f"LevelSequenceEditorSubsystem.convert_to_spawnable niedostępny. Kamery pozostały "
            f"jako Possessable, przywróć je ręcznie w Sequencerze: {names}"
        )
        return

    for record in conversion_records:
        name = record["name"]
        possessable_binding = record["possessable_binding"]
        try:
            restored = subsystem.convert_to_spawnable(possessable_binding)
            if restored:
                unreal.log(f"[exUE5][FLOW] camera_export: '{name}' przywrócona do Spawnable OK.")
            else:
                unreal.log(
                    f"[exUE5][WARNING] camera_export: convert_to_spawnable dla '{name}' zwróciło "
                    "puste/None - kamera może zostać jako Possessable, sprawdź ręcznie w Sequencerze."
                )
        except Exception as exc:
            unreal.log(
                f"[exUE5][ERROR] camera_export: przywrócenie Spawnable dla '{name}' nie powiodło się: "
                f"{exc}. TA kamera zostaje jako Possessable - pozostałe kamery nie są tym dotknięte."
            )


def _export_camera_bindings_native(sequence, bindings, output_path):
    """Eksport 1:1 z natywnym PPM -> Export w Sequencerze.

    Używa DOKŁADNIE tego samego wywołania silnika co reszta pluginu do
    eksportu głównego (exporter_core.build_export_params /
    unreal.SequencerTools.export_level_sequence_fbx), tylko z bindingami
    ograniczonymi do zaznaczonych kamer. Wszystkie zaznaczone kamery trafiają
    do JEDNEGO pliku FBX - dokładnie tak jak w Sequencerze przy zaznaczeniu
    wielu tracków i kliknięciu Export.
    """
    world = None
    if get_world is not None:
        try:
            world = get_world()
        except Exception:
            world = None
    if world is None:
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
        except Exception:
            world = None

    # Znany bug UE5.8: jeśli binding kamery jest Spawnable,
    # export_level_sequence_fbx wywołany z automatyzacji/Pythona (poza
    # normalnym scrubowaniem playheadu przez usera w edytorze) nie
    # ewaluuje spawnu poprawnie na cały zakres eksportu, więc zamiast
    # animacji dostajemy jedną statyczną klatkę (patrz diagnoza w opisie
    # zgłoszenia + test kontrolny: ręczna konwersja na Possessable +
    # ręczny eksport działa poprawnie). Naprawiamy to konwertując KAŻDĄ
    # zaznaczoną kamerę Spawnable na Possessable przed eksportem, i
    # przywracając Spawnable po (w finally, per-kamera - patrz
    # _restore_spawnables_after_export).
    export_bindings, conversion_records = _convert_spawnables_to_possessables(sequence, bindings)

    params = unreal.SequencerExportFBXParams()
    params.world = world
    params.sequence = sequence
    params.root_sequence = sequence
    params.bindings = export_bindings
    params.tracks = []
    params.fbx_file_name = os.path.normpath(output_path)
    params.override_options = _build_native_fbx_export_options()

    unreal.log(
        "[exUE5][FLOW] camera_export native export bindings="
        f"{[_get_display_name(b) for b in export_bindings]} filename={params.fbx_file_name}"
    )

    try:
        success = bool(unreal.SequencerTools.export_level_sequence_fbx(params))
        unreal.log(f"[exUE5][FLOW] camera_export native export result={success}")
        return success
    finally:
        _restore_spawnables_after_export(conversion_records)


def _run_single_camera_export(actor, output_path, options, show_dialog, prompt):
    task = unreal.AssetExportTask()
    task.object = actor
    task.filename = os.path.normpath(output_path)
    task.selected = False
    task.automated = not prompt
    task.prompt = prompt
    task.replace_identical = True
    task.options = options
    return bool(unreal.Exporter.run_asset_export_task(task))


def _export_camera_actors_legacy(sequence, camera_binding_ids, output_path, show_dialog):
    """Zapasowa metoda eksportu przez AssetExportTask na Actorze.

    Używana WYŁĄCZNIE gdy w sekwencji nie udało się dopasować żadnego
    bindingu kamery (np. selekcja z GUI wskazuje na coś spoza sekwencji).
    Ta ścieżka NIE jest tożsama z natywnym PPM -> Export w Sequencerze -
    jest zachowana jako siatka bezpieczeństwa, żeby eksport nie failował
    całkowicie w nietypowych przypadkach.
    """
    actors = _resolve_camera_actors(sequence, camera_binding_ids)
    if not actors:
        raise RuntimeError(
            "Nie znaleziono żadnego aktora kamery w świecie dla zaznaczonych bindingów. "
            "Sprawdź, czy Spawnable jest zespawnowany w bieżącej klatce."
        )
    actor_labels = [a.get_actor_label() for a in actors]
    options = _build_native_fbx_export_options()

    output_dir = os.path.dirname(output_path)

    if len(actors) == 1:
        output_file = os.path.normpath(output_path)
        unreal.log(f"[exUE5][FLOW] camera_export (legacy) exporting single camera actor: {actor_labels[0]}")
        return _run_single_camera_export(actors[0], output_file, options, show_dialog, show_dialog)

    prefix = os.path.splitext(os.path.basename(output_path))[0] or "KAMERA_TRANS"
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

        if not output_path:
            raise RuntimeError("Nie podano output_path dla eksportu kamery")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as exc:
                unreal.log(f"[exUE5][ERROR] camera_export: nie udało się utworzyć folderu '{output_dir}': {exc}")
                raise

        bindings = _resolve_camera_bindings(sequence, camera_binding_ids)
        if bindings:
            # Dokładnie ta sama ścieżka co natywny PPM -> Export w
            # Sequencerze: jeden plik FBX, ustawienia 1:1 z 22.png,
            # eksport w pełni automatyczny (bez żadnych okienek).
            return _export_camera_bindings_native(sequence, bindings, output_path)

        unreal.log(
            "[exUE5][WARNING] camera_export: nie znaleziono bindingów kamer w sekwencji dla podanych ID, "
            "przechodzę na zapasową metodę eksportu przez zaznaczone aktory "
            "(UWAGA: ta ścieżka może nie odzwierciedlać 1:1 natywnego eksportu z Sequencera)."
        )
        return _export_camera_actors_legacy(sequence, camera_binding_ids, output_path, show_dialog)
    finally:
        if saved_time is not None and hasattr(lib, "set_current_time"):
            try:
                lib.set_current_time(saved_time)
            except Exception:
                pass