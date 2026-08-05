try:
    import unreal
except ModuleNotFoundError:
    unreal = None


def show_camera_export_dialog(camera_bindings, get_display_name_fn, default_output_path):
    import tkinter as tk
    from tkinter import filedialog

    try:
        from exUE5.spawnable_diagnostics import _format_binding_id
    except Exception:
        try:
            from spawnable_diagnostics import _format_binding_id
        except Exception:
            _format_binding_id = lambda x: str(x) if x is not None else ""

    result = {
        "cancelled": True,
        "camera_binding_ids": set(),
        "output_path": default_output_path,
        "export_cameras": False,
    }

    root = tk.Tk()
    root.title("Eksport kamer")
    root.geometry("520x420")
    root.configure(bg="#2b2b2b")

    enable_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        root,
        text="Eksportuj kamery",
        variable=enable_var,
        bg="#2b2b2b",
        fg="white",
        selectcolor="#2b2b2b",
        anchor="w",
    ).pack(anchor="w", padx=10, pady=(10, 4))

    import os

    default_dir, default_file = os.path.split(default_output_path)
    default_base, default_ext = os.path.splitext(default_file)
    if not default_base:
        default_base = "KAMERA_TRANS"

    file_name_var = tk.StringVar(value=default_base)
    folder_var = tk.StringVar(value=default_dir or ".")
    path_var = tk.StringVar(value=os.path.join(folder_var.get(), f"{file_name_var.get()}.fbx"))

    def _update_path_display(*args):
        file_name = os.path.splitext(file_name_var.get())[0]
        folder = folder_var.get() or "."
        path_var.set(os.path.join(folder, f"{file_name}.fbx"))

    file_name_var.trace_add("write", _update_path_display)
    folder_var.trace_add("write", _update_path_display)

    filename_frame = tk.Frame(root, bg="#2b2b2b")
    filename_frame.pack(fill="x", padx=10, pady=(0, 4))
    tk.Label(filename_frame, text="Nazwa pliku:", bg="#2b2b2b", fg="white", font=("Segoe UI", 10)).pack(anchor="w")
    file_name_entry = tk.Entry(filename_frame, textvariable=file_name_var, width=40, bg="#1e1e1e", fg="white", insertbackground="white")
    file_name_entry.pack(side="left", fill="x", expand=True)
    tk.Label(filename_frame, text=".fbx", bg="#2b2b2b", fg="white").pack(side="left", padx=(6, 0))

    folder_frame = tk.Frame(root, bg="#2b2b2b")
    folder_frame.pack(fill="x", padx=10, pady=(0, 8))
    tk.Label(folder_frame, text="Folder docelowy:", bg="#2b2b2b", fg="white", font=("Segoe UI", 10)).pack(anchor="w")
    folder_entry = tk.Entry(folder_frame, textvariable=folder_var, width=40, bg="#1e1e1e", fg="white", insertbackground="white")
    folder_entry.pack(side="left", fill="x", expand=True)

    def browse():
        chosen = filedialog.askdirectory()
        if chosen:
            folder_var.set(chosen)

    tk.Button(folder_frame, text="...", command=browse, width=3).pack(side="left", padx=(6, 0))

    path_label = tk.Label(root, textvariable=path_var, bg="#2b2b2b", fg="#a0a0a0", font=("Segoe UI", 9))
    path_label.pack(anchor="w", padx=10, pady=(0, 8))

    tk.Label(
        root,
        text="Kamery w sekwencji:",
        bg="#2b2b2b",
        fg="white",
        font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w", padx=10, pady=(4, 4))

    cam_vars = {}
    list_frame = tk.Frame(root, bg="#2b2b2b")
    list_frame.pack(fill="both", expand=True, padx=10)

    if camera_bindings:
        for index, binding in enumerate(camera_bindings):
            name = get_display_name_fn(binding)
            bid_raw = getattr(binding, "binding_id", None)
            bid = _format_binding_id(bid_raw) or name
            var = tk.BooleanVar(value=True)
            cam_vars[bid] = (var, name)
            tk.Checkbutton(
                list_frame,
                text=name,
                variable=var,
                bg="#2b2b2b",
                fg="white",
                selectcolor="#2b2b2b",
                anchor="w",
            ).pack(fill="x")
    else:
        tk.Label(
            list_frame,
            text="Brak kamer w sekwencji.",
            bg="#2b2b2b",
            fg="white",
            anchor="w",
        ).pack(fill="x")

    def confirm():
        result["cancelled"] = False
        result["export_cameras"] = bool(enable_var.get())
        output_folder = folder_var.get() or "."
        file_name = os.path.splitext(file_name_var.get())[0]
        result["output_path"] = os.path.join(output_folder, f"{file_name}.fbx")
        result["camera_binding_ids"] = {bid for bid, (var, _) in cam_vars.items() if var.get()}
        root.quit()
        root.destroy()

    def cancel():
        root.quit()
        root.destroy()

    btn_frame = tk.Frame(root, bg="#2b2b2b")
    btn_frame.pack(fill="x", padx=10, pady=10)
    tk.Button(btn_frame, text="Zapisz", command=confirm, width=12).pack(side="right")
    tk.Button(btn_frame, text="Anuluj", command=cancel, width=12).pack(side="right", padx=6)
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.mainloop()

    return None if result["cancelled"] else result
