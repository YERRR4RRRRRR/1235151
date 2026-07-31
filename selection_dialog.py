try:
    import unreal
except ModuleNotFoundError:
    unreal = None


def _classify_binding(name, is_spawnable):
    import re
    # Normalize to a lower-case, alphanumeric+space representation to avoid
    # accidental token mismatches caused by punctuation, newlines, or object
    # metadata strings coming from engine objects.
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
    # Emit a temporary debug log so the classification can be diagnosed in-editor.
    try:
        try:
            # Prefer package-style import when used as a plugin
            from exUE5.debug_console import push_log
        except Exception:
            from debug_console import push_log
    except Exception:
        push_log = None

    if push_log:
        try:
            push_log(f"CLASSIFY: '{name_text}' -> {category}", level="INFO")
        except Exception:
            pass

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


def _dialog_log(message, level="INFO"):
    try:
        try:
            from exUE5.debug_console import push_log
        except Exception:
            from debug_console import push_log
    except Exception:
        push_log = None

    formatted = f"[exUE5][FLOW] {message}"
    if push_log:
        try:
            push_log(formatted, level=level)
        except Exception:
            pass
    print(formatted)


def show_selection_dialog(bindings, tracks, get_display_name_fn, get_binding_id_fn=None, spawnable_ids=None):
    import tkinter as tk
    from tkinter import ttk

    # Lightweight tooltip helper for Tkinter widgets. Keeps UI dependency
    # local to this dialog so the rest of the plugin doesn't import Tk.
    class _ToolTip:
        def __init__(self, widget, text):
            self.widget = widget
            self.text = text
            self.tipwindow = None
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

        def _enter(self, event=None):
            if self.tipwindow or not self.text:
                return
            x = event.x_root + 12 if event else self.widget.winfo_rootx() + 12
            y = event.y_root + 12 if event else self.widget.winfo_rooty() + 12
            try:
                self.tipwindow = tw = tk.Toplevel(self.widget)
                tw.wm_overrideredirect(True)
                tw.wm_geometry(f"+{x}+{y}")
                label = tk.Label(tw, text=self.text, justify='left', background="#ffffe0", relief='solid', borderwidth=1, font=("Segoe UI", 8))
                label.pack(ipadx=4, ipady=2)
            except Exception:
                self.tipwindow = None

        def _leave(self, event=None):
            if self.tipwindow:
                try:
                    self.tipwindow.destroy()
                except Exception:
                    pass
                self.tipwindow = None

    spawnable_ids = spawnable_ids or set()
    if get_binding_id_fn is None:
        get_binding_id_fn = lambda item: str(getattr(item, "binding_id", ""))
    root = tk.Tk()
    root.title("Wybierz elementy do eksportu")
    root.geometry("560x520")
    root.configure(bg="#2b2b2b")

    result = {"cancelled": True, "binding_names": set(), "track_names": set(), "merge_body_face": False}

    top_frame = tk.Frame(root, bg="#2b2b2b")
    top_frame.pack(fill="x", padx=10, pady=(10, 6))

    merge_var = tk.BooleanVar(value=False)
    merge_checkbox = tk.Checkbutton(
        top_frame,
        text="Połącz Body + Face przed eksportem",
        variable=merge_var,
        bg="#2b2b2b",
        fg="white",
        selectcolor="#2b2b2b",
        anchor="w",
        state="normal",
    )
    merge_checkbox.pack(fill="x")

    def _binding_looks_like_body(name):
        lowered = (name or "").lower()
        return any(token in lowered for token in (
            "body", "metahuman", "pelvis", "spine", "clavicle", "neck", "head",
            "upperarm", "lowerarm", "hand", "armature", "skeleton", "root"
        ))

    def _binding_looks_like_face(name):
        lowered = (name or "").lower()
        return any(token in lowered for token in (
            "face", "facial", "jaw", "lip", "brow", "mouth", "cheek", "nose",
            "eye", "blendshape", "morph", "teeth", "cartilage"
        ))

    list_width = 500
    list_height = 360

    canvas = tk.Canvas(root, bg="#2b2b2b", highlightthickness=0, width=list_width, height=list_height)
    scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
    frame = tk.Frame(canvas, bg="#2b2b2b", width=list_width)
    # NOTE: previously called frame.pack_propagate(False) here with only
    # `width` set (no `height`). That locks the frame to its default,
    # near-zero requested height instead of letting it grow to fit the
    # packed binding/track checkboxes -- so every checkbox was created
    # correctly in memory but rendered invisible (blank canvas below the
    # "Połącz Body + Face" checkbox). The canvas above already provides the
    # fixed-size "viewport" (list_width x list_height); this inner frame
    # must be left free to size itself naturally so canvas.bbox("all") in
    # the <Configure> handler below computes a correct scrollregion.
    frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=frame, anchor="nw", width=list_width)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 8))
    scrollbar.pack(side="right", fill="y", pady=(0, 8))
    root.update_idletasks()

    binding_vars = {}
    if bindings:
        tk.Label(frame, text="Bindingi:", bg="#2b2b2b", fg="white", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        sorted_bindings = sorted(
            bindings,
            key=lambda item: _sort_priority(get_display_name_fn(item), get_binding_id_fn(item) in spawnable_ids),
        )
        for binding in sorted_bindings:
            name = get_display_name_fn(binding)
            bid = get_binding_id_fn(binding) or ""
            is_spawn = bid in spawnable_ids
            var = tk.BooleanVar(value=True)
            # Key the checkbox state by the stable binding id instead of the
            # display name to avoid collisions when multiple bindings share names.
            binding_vars[bid] = (var, name)
            label = f"{name}   [{_classify_binding(name, is_spawn)}]"
            cb = tk.Checkbutton(frame, text=label, variable=var, bg="#2b2b2b", fg="white", selectcolor="#2b2b2b", anchor="w")
            cb.pack(fill="x")
            # Attach a tooltip showing the binding id for easier debugging.
            try:
                _ToolTip(cb, f"binding_id: {bid}")
            except Exception:
                pass
    else:
        tk.Label(frame, text="Brak bindingów w aktywnej sekwencji.", bg="#2b2b2b", fg="#d0d0d0", font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 4))

    track_vars = {}
    if tracks:
        tk.Label(frame, text="Tracki:", bg="#2b2b2b", fg="white", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 4))
        sorted_tracks = sorted(tracks, key=lambda item: get_display_name_fn(item).lower())
        for track in sorted_tracks:
            name = get_display_name_fn(track)
            var = tk.BooleanVar(value=True)
            track_vars[name] = var
            tk.Checkbutton(frame, text=name, variable=var, bg="#2b2b2b", fg="white", selectcolor="#2b2b2b", anchor="w").pack(fill="x")
    else:
        tk.Label(frame, text="Brak tracków do eksportu.", bg="#2b2b2b", fg="#d0d0d0", font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 4))

    def _refresh_merge_enabled_state():
        selected_ids = {bid for bid, (var, name) in binding_vars.items() if var.get()}
        selected_names = {name for bid, (var, name) in binding_vars.items() if var.get()}
        has_body = any(_binding_looks_like_body(name) for name in selected_names)
        has_face = any(_binding_looks_like_face(name) for name in selected_names)
        _dialog_log(
            f"selection_refresh selected_ids={sorted(selected_ids)} selected_names={sorted(selected_names)} "
            f"has_body={has_body} has_face={has_face} merge_checkbox_enabled={True}",
            level="INFO",
        )
        # Keep the checkbox available for explicit manual use. Runtime validation
        # still prevents unsafe merge attempts when the actual Body + Face
        # selection is not present.
        merge_checkbox.configure(state="normal")
        if not has_body or not has_face:
            merge_var.set(False)

    for bid, (var, name) in binding_vars.items():
        var.trace_add("write", lambda *args, _refresh_merge_enabled_state=_refresh_merge_enabled_state: _refresh_merge_enabled_state())

    button_frame = tk.Frame(root, bg="#2b2b2b")
    button_frame.pack(fill="x", padx=10, pady=(0, 10))

    def select_all(value):
        for entry in list(binding_vars.values()):
            var = entry[0]
            var.set(value)
        for var in list(track_vars.values()):
            var.set(value)

    def confirm():
        result["cancelled"] = False
        result["binding_ids"] = {bid for bid, (var, name) in binding_vars.items() if var.get()}
        result["track_names"] = {name for name, var in track_vars.items() if var.get()}
        result["merge_body_face"] = bool(merge_var.get() and merge_checkbox.cget("state") != "disabled")
        _dialog_log(
            f"selection_confirm selected_binding_ids={sorted(result['binding_ids'])} "
            f"selected_track_names={sorted(result['track_names'])} merge_body_face={result['merge_body_face']}",
            level="INFO",
        )
        root.quit()
        root.destroy()

    def cancel():
        root.quit()
        root.destroy()

    tk.Button(button_frame, text="Zaznacz wszystko", command=lambda: select_all(True)).pack(side="left")
    tk.Button(button_frame, text="Odznacz wszystko", command=lambda: select_all(False)).pack(side="left", padx=6)
    tk.Button(button_frame, text="Eksportuj wybrane", command=confirm).pack(side="right")
    tk.Button(button_frame, text="Anuluj", command=cancel).pack(side="right", padx=6)

    root.protocol("WM_DELETE_WINDOW", cancel)

    _dialog_log(
        f"selection_dialog rendered {len(binding_vars)} binding checkboxes, "
        f"{len(track_vars)} track checkboxes",
        level="INFO",
    )

    root.mainloop()

    return None if result["cancelled"] else {
        "binding_ids": result.get("binding_ids", set()),
        "track_names": result["track_names"],
        "merge_body_face": result.get("merge_body_face", False),
    }