try:
    import unreal
except ModuleNotFoundError:
    unreal = None


def show_camera_export_dialog(camera_bindings, get_display_name_fn, default_output_path):
    import os
    import tkinter as tk
    from tkinter import filedialog, messagebox

    try:
        from exUE5 import ui_style
    except ModuleNotFoundError:
        import ui_style

    try:
        from exUE5.exporter_core import save_config
    except ModuleNotFoundError:
        from exporter_core import save_config

    try:
        from exUE5.spawnable_diagnostics import _format_binding_id
    except Exception:
        try:
            from spawnable_diagnostics import _format_binding_id
        except Exception:
            _format_binding_id = lambda x: str(x) if x is not None else ""

    try:
        from exUE5.camera_export import _is_camera_component_name
    except Exception:
        try:
            from camera_export import _is_camera_component_name
        except Exception:
            _is_camera_component_name = lambda name: False

    # CameraComponent sub-bindings are excluded totally from this dialog --
    # they duplicate the parent camera actor binding and, if exported alone,
    # produce an orphaned component with no transform. camera_bindings is
    # normally already filtered upstream (menu.py uses _is_camera_binding,
    # which itself excludes them), but this list is filtered again here
    # defensively so it can never appear regardless of caller.
    camera_bindings = [
        b for b in (camera_bindings or [])
        if not _is_camera_component_name(get_display_name_fn(b))
    ]

    result = {
        "cancelled": True,
        "camera_binding_ids": set(),
        "output_path": default_output_path,
    }

    root = tk.Tk()
    ui_style.apply_theme(root, title="Eksport kamer", min_size=(440, 360))
    ui_style.apply_geometry(root, 560, 460)

    # Pole nazwy pliku startuje PUSTE -- wymaga wpisania nazwy przed
    # eksportem. Rozszerzenie ".fbx" to osobna, stała etykieta obok pola
    # (patrz niżej), więc nie da się jej zmienić ani skasować.
    default_dir, _default_file = os.path.split(default_output_path)

    file_name_var = tk.StringVar(value="")
    # Folder domyślnie pusty, dopóki nie zostanie zapamiętany z poprzedniego
    # uruchomienia (config.json -> default_output_folder). Za pierwszym
    # razem trzeba go wybrać ręcznie.
    folder_var = tk.StringVar(value=default_dir or "")
    path_var = tk.StringVar(value="")

    def _update_path_display(*args):
        file_name = os.path.splitext(file_name_var.get())[0].strip()
        display_name = f"{file_name}.fbx" if file_name else "<wpisz nazwę>.fbx"
        display_folder = folder_var.get().strip() or "<wybierz folder>"
        path_var.set(os.path.join(display_folder, display_name))

    file_name_var.trace_add("write", _update_path_display)
    folder_var.trace_add("write", _update_path_display)
    _update_path_display()
    file_name_var.trace_add("write", lambda *args: _update_confirm_state())
    folder_var.trace_add("write", lambda *args: _update_confirm_state())

    filename_frame = ui_style.frame(root)
    filename_frame.pack(fill="x", padx=12, pady=(14, 4))
    ui_style.label(filename_frame, text="Nazwa pliku:").pack(anchor="w")
    file_name_entry = ui_style.entry(filename_frame, textvariable=file_name_var, width=40)
    file_name_entry.pack(side="left", fill="x", expand=True, ipady=3)
    ui_style.label(filename_frame, text=".fbx", muted=True).pack(side="left", padx=(6, 0))

    folder_frame = ui_style.frame(root)
    folder_frame.pack(fill="x", padx=12, pady=(0, 8))
    ui_style.label(folder_frame, text="Folder docelowy:").pack(anchor="w")
    folder_entry = ui_style.entry(folder_frame, textvariable=folder_var, width=40)
    folder_entry.pack(side="left", fill="x", expand=True, ipady=3)

    def browse():
        chosen = filedialog.askdirectory()
        if chosen:
            folder_var.set(chosen)

    ui_style.button(folder_frame, text="...", command=browse, primary=False, padx=10).pack(side="left", padx=(6, 0))

    path_label = ui_style.label(root, textvariable=path_var, muted=True)
    path_label.configure(font=ui_style.FONTS["small"])
    path_label.pack(anchor="w", padx=12, pady=(0, 8))

    ui_style.divider(root).pack(fill="x", padx=12, pady=(0, 8))

    ui_style.section_label(root, "Kamery w sekwencji", count=len(camera_bindings)).pack(
        anchor="w", padx=12, pady=(0, 6)
    )

    cam_vars = {}
    list_frame = ui_style.frame(root)
    list_frame.pack(fill="both", expand=True, padx=12)

    def _update_confirm_state():
        has_selection = any(var.get() for var, _, _ in cam_vars.values())
        has_name = bool(os.path.splitext(file_name_var.get())[0].strip())
        has_folder = bool(folder_var.get().strip())
        confirm_button.config(state="normal" if (has_selection and has_name and has_folder) else "disabled")

    if camera_bindings:
        sorted_bindings = sorted(camera_bindings, key=lambda b: (get_display_name_fn(b) or "").lower())
        for index, binding in enumerate(sorted_bindings):
            name = get_display_name_fn(binding)
            bid_raw = getattr(binding, "binding_id", None)
            bid = _format_binding_id(bid_raw) or name
            var = tk.BooleanVar(value=True)
            # Unique internal key so duplicate binding ids/names don't clobber
            # each other's checkbox state.
            key = f"{bid}:{index}"
            cam_vars[key] = (var, name, bid)
            cb = ui_style.checkbutton(list_frame, text=name, variable=var)
            cb.pack(fill="x", pady=1)
            var.trace_add("write", lambda *args: _update_confirm_state())
    else:
        ui_style.label(
            list_frame,
            text="Brak kamer w sekwencji.",
            muted=True,
        ).pack(fill="x", pady=(4, 0))

    def confirm():
        file_name = os.path.splitext(file_name_var.get())[0].strip()
        output_folder = folder_var.get().strip()

        if not file_name:
            messagebox.showerror("Brak nazwy pliku", "Podaj nazwę pliku przed eksportem kamer.", parent=root)
            return
        if not output_folder:
            messagebox.showerror("Brak folderu", "Wybierz folder docelowy przed eksportem kamer.", parent=root)
            return

        result["cancelled"] = False
        result["output_path"] = os.path.join(output_folder, f"{file_name}.fbx")
        result["camera_binding_ids"] = {bid for _, (var, _, bid) in cam_vars.items() if var.get()}

        # Zapamiętaj folder w config.json, żeby przy kolejnym uruchomieniu
        # GUI był już wypełniony automatycznie.
        try:
            save_config({"default_output_folder": output_folder})
        except Exception as exc:
            if unreal is not None:
                unreal.log(f"[exUE5] Nie udało się zapisać folderu docelowego: {exc}")

        root.quit()
        root.destroy()

    def cancel():
        root.quit()
        root.destroy()

    btn_frame = ui_style.frame(root)
    btn_frame.pack(fill="x", padx=12, pady=12)
    confirm_button = ui_style.button(btn_frame, text="Eksportuj kamerę", command=confirm, primary=True)
    confirm_button.pack(side="right")
    ui_style.button(btn_frame, text="Anuluj", command=cancel, primary=False).pack(side="right", padx=6)
    root.protocol("WM_DELETE_WINDOW", cancel)

    _update_confirm_state()

    root.mainloop()

    return None if result["cancelled"] else result
