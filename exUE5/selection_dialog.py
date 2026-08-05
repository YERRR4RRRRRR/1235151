try:
    from .spawnable_diagnostics import _format_binding_id
except Exception:
    from spawnable_diagnostics import _format_binding_id


# ---------------------------------------------------------------------------
# Klasyfikacja bindingów.
#
# Uproszczone do trzech grup (patrz show_selection_dialog):
#   - Face  -- zawsze eksportowana, nie da się jej odznaczyć w GUI
#   - Body  -- zawsze eksportowana, nie da się jej odznaczyć w GUI
#   - Inne  -- wszystko pozostałe (Control Rig, Blueprinty, nierozpoznane
#              bindingi); jedyna grupa z checkboxami, chowana domyślnie za
#              rozwijanym nagłówkiem i sortowana alfabetycznie
#
# Kamery NIE trafiają tutaj w ogóle -- mają własne okno EXPORT CAMERA
# (camera_dialog.py) i są odfiltrowywane z tej listy przez
# _is_camera_only_name w show_selection_dialog, tak jak wcześniej.
# ---------------------------------------------------------------------------

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


def _classify_binding(name):
    """Zwraca "Face", "Body" albo "Inne" -- patrz komentarz na górze pliku.
    Face sprawdzana jest przed Body celowo (tak jak w oryginalnej wersji),
    bo część tokenów (np. "head") mogłaby inaczej trafić w złą kategorię
    dla bindingów opisujących mimikę twarzy."""
    if _binding_looks_like_face(name):
        return "Face"
    if _binding_looks_like_body(name):
        return "Body"
    return "Inne"


def resolve_selected_targets(items, selection, id_getter, label_getter):
    """Resolve a selection list into matching items and rejected tokens.

    The selection may contain stable IDs or display labels. Matching preserves
    the order of first successful matches and deduplicates repeated item
    selections.
    """
    if selection is None:
        return [], []

    matched = []
    rejected = []
    seen_items = set()

    for token in selection:
        if token is None:
            continue

        match = None
        for item in items:
            try:
                item_id = id_getter(item)
            except Exception:
                item_id = None
            try:
                item_label = label_getter(item)
            except Exception:
                item_label = None

            if item_id == token or item_label == token:
                match = item
                break

        if match is None:
            rejected.append(token)
            continue

        if match in seen_items:
            continue

        seen_items.add(match)
        matched.append(match)

    return matched, rejected


def _dialog_log(message, level="INFO"):
    try:
        from .debug_console import push_log
    except Exception:
        try:
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


def _is_camera_only_name(name):
    if not name:
        return False
    normalized = name.lower()
    if "br_1real" in normalized:
        return False
    camera_tokens = ("camera", "cam", "sensor", "focal", "focus", "aperture", "filmback", "film back", "lens", "focal length", "kam")
    face_tokens = ("face", "blendshape", "blend shape", "blend", "morph", "jaw", "eye", "eyebrow", "lip", "mouth")
    body_tokens = ("body", "bone", "skeleton", "metahuman", "mesh", "character", "spine", "hip", "chest")
    if any(token in normalized for token in camera_tokens):
        if any(token in normalized for token in face_tokens):
            return False
        if any(token in normalized for token in body_tokens):
            return False
        return True
    return False


def show_selection_dialog(bindings, tracks, get_display_name_fn, get_binding_id_fn=None, spawnable_ids=None):
    import tkinter as tk
    from tkinter import ttk

    try:
        from exUE5 import ui_style
    except ModuleNotFoundError:
        import ui_style

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
                label = tk.Label(tw, text=self.text, justify='left', background="#2e2e33", foreground="#e8e8ea", relief='solid', borderwidth=1, font=ui_style.FONTS["small"])
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
        get_binding_id_fn = lambda item: _format_binding_id(getattr(item, "binding_id", None)) or ""

    root = tk.Tk()
    ui_style.apply_theme(root, title="Wybierz elementy do eksportu", min_size=(460, 380))
    ui_style.apply_geometry(root, 600, 560)

    result = {"cancelled": True, "binding_ids": set(), "binding_names": set()}

    # --- Sklasyfikuj bindingi: kamery odpadają całkowicie (mają własne okno
    # EXPORT CAMERA), Face/Body trafiają do grup zawsze-eksportowanych,
    # wszystko inne trafia do rozwijanej, alfabetycznej listy "Inne". ---
    face_items = []
    body_items = []
    other_items = []

    for binding in (bindings or []):
        name = get_display_name_fn(binding)
        if _is_camera_only_name(name):
            continue
        bid = get_binding_id_fn(binding) or ""
        category = _classify_binding(name)
        entry = (bid, name, bid in spawnable_ids)
        if category == "Face":
            face_items.append(entry)
        elif category == "Body":
            body_items.append(entry)
        else:
            other_items.append(entry)

    face_items.sort(key=lambda e: e[1].lower())
    body_items.sort(key=lambda e: e[1].lower())
    other_items.sort(key=lambda e: e[1].lower())

    _dialog_log(
        f"selection_dialog_classified face={len(face_items)} body={len(body_items)} "
        f"inne={len(other_items)} (tracks input ignored -- Tracki section removed)",
        level="INFO",
    )

    # --- Nagłówek: Face/Body są zawsze w eksporcie, bez checkboxów. ---
    header_frame = ui_style.frame(root)
    header_frame.pack(fill="x", padx=12, pady=(12, 4))

    ui_style.label(
        header_frame,
        text="Face i Body są eksportowane automatycznie (nie da się ich odznaczyć).",
        muted=True,
    ).pack(anchor="w")

    auto_frame = ui_style.frame(root)
    auto_frame.pack(fill="x", padx=12, pady=(6, 0))

    def _auto_group_row(parent, label_text, items):
        ui_style.section_label(parent, label_text, count=len(items)).pack(anchor="w", pady=(4, 2))
        if items:
            names = ", ".join(name for _, name, _ in items)
            names_label = ui_style.label(parent, text=names, muted=True)
            names_label.configure(wraplength=ui_style.scaled(root, 560), justify="left")
            names_label.pack(anchor="w", pady=(0, 2))
        else:
            ui_style.label(parent, text="(brak w tej sekwencji)", muted=True).pack(anchor="w", pady=(0, 2))

    _auto_group_row(auto_frame, "Body", body_items)
    _auto_group_row(auto_frame, "Face", face_items)

    ui_style.divider(root).pack(fill="x", padx=12, pady=(10, 8))

    # --- "Inne" -- jedyna rozwijana, wyboru-wymagająca kategoria, zawsze
    # posortowana alfabetycznie. Zwinięta domyślnie; klik nagłówka pokazuje
    # zawartość. ---
    inne_header_frame = ui_style.frame(root)
    inne_header_frame.pack(fill="x", padx=12)

    inne_expanded = tk.BooleanVar(value=False)

    def _inne_header_text():
        arrow = "\u25bc" if inne_expanded.get() else "\u25b6"
        return f"{arrow}  Inne  ({len(other_items)})"

    inne_toggle_btn = ui_style.button(
        inne_header_frame,
        text=_inne_header_text(),
        command=lambda: _toggle_inne(),
        primary=False,
    )
    inne_toggle_btn.configure(anchor="w")
    inne_toggle_btn.pack(fill="x")

    list_width = 560
    list_height = 260

    inne_list_wrap = ui_style.frame(root)

    inne_canvas = ui_style.canvas(
        inne_list_wrap,
        width=ui_style.scaled(root, list_width),
        height=ui_style.scaled(root, list_height),
        bg=ui_style.PALETTE["bg_elevated"],
    )
    inne_scrollbar = ttk.Scrollbar(inne_list_wrap, orient="vertical", command=inne_canvas.yview)
    inne_frame = ui_style.frame(inne_canvas, width=ui_style.scaled(root, list_width), bg=ui_style.PALETTE["bg_elevated"])
    inne_frame.bind("<Configure>", lambda e: inne_canvas.configure(scrollregion=inne_canvas.bbox("all")))
    inne_canvas.create_window((0, 0), window=inne_frame, anchor="nw", width=ui_style.scaled(root, list_width))
    inne_canvas.configure(yscrollcommand=inne_scrollbar.set)

    def _on_inne_mousewheel(event):
        inne_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    inne_canvas.bind("<Enter>", lambda _e: inne_canvas.bind_all("<MouseWheel>", _on_inne_mousewheel))
    inne_canvas.bind("<Leave>", lambda _e: inne_canvas.unbind_all("<MouseWheel>"))

    def _toggle_inne():
        inne_expanded.set(not inne_expanded.get())
        inne_toggle_btn.configure(text=_inne_header_text())
        if inne_expanded.get():
            inne_list_wrap.pack(fill="both", expand=True, padx=12, pady=(6, 8))
            inne_canvas.pack(side="left", fill="both", expand=True)
            inne_scrollbar.pack(side="right", fill="y")
        else:
            inne_canvas.pack_forget()
            inne_scrollbar.pack_forget()
            inne_list_wrap.pack_forget()

    inne_vars = {}

    if other_items:
        for index, (bid, name, is_spawn) in enumerate(other_items):
            var = tk.BooleanVar(value=True)
            # Unique internal key so duplicate binding ids/names don't
            # collide and overwrite each other's checkbox state.
            key = f"{bid}:{index}"
            inne_vars[key] = (var, name, bid)
            suffix = "  (Spawnable)" if is_spawn else ""
            cb = ui_style.checkbutton(inne_frame, text=f"{name}{suffix}", variable=var, bg=ui_style.PALETTE["bg_elevated"])
            cb.pack(fill="x", padx=6, pady=1)
            try:
                _ToolTip(cb, f"binding_id: {bid}")
            except Exception:
                pass
    else:
        ui_style.label(inne_frame, text="Brak innych bindingów.", muted=True, bg=ui_style.PALETTE["bg_elevated"]).pack(
            anchor="w", padx=6, pady=(6, 4)
        )

    # --- Dolny pasek przycisków ---
    button_frame = ui_style.frame(root)
    button_frame.pack(fill="x", padx=12, pady=(4, 12), side="bottom")

    def select_all(value):
        for var, _, _ in list(inne_vars.values()):
            var.set(value)
        _update_confirm_state()

    def _update_confirm_state():
        selected_inne = sum(1 for var, _, _ in inne_vars.values() if var.get())
        total = len(face_items) + len(body_items) + selected_inne
        confirm_button.config(state="normal" if total else "disabled")

    for _, (var, _, _) in inne_vars.items():
        var.trace_add("write", lambda *args: _update_confirm_state())

    def confirm():
        result["cancelled"] = False
        binding_ids = set()
        binding_names = set()
        for bid, name, _is_spawn in face_items + body_items:
            binding_names.add(name)
            if bid:
                binding_ids.add(bid)
        for _, (var, name, bid) in inne_vars.items():
            if var.get():
                binding_names.add(name)
                if bid:
                    binding_ids.add(bid)
        result["binding_ids"] = binding_ids
        result["binding_names"] = binding_names
        _dialog_log(
            f"selection_confirm selected_binding_ids={sorted(result['binding_ids'])} "
            f"selected_binding_names={sorted(result['binding_names'])} "
            f"(auto face={len(face_items)} body={len(body_items)}, inne_selected="
            f"{sum(1 for var, _, _ in inne_vars.values() if var.get())}/{len(inne_vars)})",
            level="INFO",
        )
        root.quit()
        root.destroy()

    def cancel():
        root.quit()
        root.destroy()

    ui_style.button(button_frame, text="Zaznacz wszystko (Inne)", command=lambda: select_all(True), primary=False).pack(side="left")
    ui_style.button(button_frame, text="Odznacz wszystko (Inne)", command=lambda: select_all(False), primary=False).pack(side="left", padx=6)
    confirm_button = ui_style.button(button_frame, text="Eksportuj wybrane", command=confirm, primary=True)
    confirm_button.pack(side="right")
    ui_style.button(button_frame, text="Anuluj", command=cancel, primary=False).pack(side="right", padx=6)

    _update_confirm_state()

    root.protocol("WM_DELETE_WINDOW", cancel)

    _dialog_log(
        f"selection_dialog rendered face={len(face_items)} (auto) body={len(body_items)} (auto) "
        f"inne={len(inne_vars)} (collapsed, alphabetical)",
        level="INFO",
    )

    root.mainloop()

    return None if result["cancelled"] else {
        "binding_ids": result.get("binding_ids", set()),
        "binding_names": result.get("binding_names", set()),
    }
