import os

try:
    import unreal
except ModuleNotFoundError:
    unreal = None

try:
    from exUE5.debug_console import open_debug_console, get_log_index
except ModuleNotFoundError:
    from debug_console import open_debug_console, get_log_index

try:
    from exUE5.exporter_core import export_current_sequence
except ModuleNotFoundError:
    from exporter_core import export_current_sequence

try:
    from exUE5.menu_utils import _log as _log_ui
except ModuleNotFoundError:
    try:
        from menu_utils import _log as _log_ui
    except ModuleNotFoundError:
        def _log_ui(message):
            print(f"[exUE5] {message}")

try:
    from exUE5 import ui_style
except ModuleNotFoundError:
    import ui_style


def _show_export_dialog(config):
    """Show a Tkinter dialog to choose filename and destination folder."""
    try:
        import tkinter as tk
        from tkinter import filedialog, ttk
    except Exception as exc:
        if unreal is not None:
            unreal.log(f"[exUE5] Tkinter dialog unavailable: {exc}")
        return None

    root = tk.Tk()
    ui_style.apply_theme(root, title="Export Sequence FBX", min_size=(480, 280))
    ui_style.apply_geometry(root, 560, 300)

    default_filename = config.get("default_output_filename", "exported_sequence.fbx") or "exported_sequence.fbx"
    default_folder = config.get("default_output_folder") or os.path.join(os.path.expanduser("~"), "Exports")
    if not default_folder:
        default_folder = os.path.join(os.path.expanduser("~"), "Exports")

    filename_var = tk.StringVar(value=default_filename)
    folder_var = tk.StringVar(value=default_folder)
    output_path_var = tk.StringVar(value=os.path.join(folder_var.get(), filename_var.get()))
    result = {"filename": None, "folder": None}

    def choose_folder():
        folder = filedialog.askdirectory(initialdir=folder_var.get(), title="Wybierz folder zapisu")
        if folder:
            folder_var.set(folder)

    def update_output_preview(*args):
        output_path_var.set(os.path.join(folder_var.get(), filename_var.get()))

    filename_var.trace_add("write", update_output_preview)
    folder_var.trace_add("write", update_output_preview)

    def confirm():
        typed = filename_var.get().strip()
        # Backstop: if the typed value looks like leftover characters glued
        # onto the original default filename (e.g. the field wasn't fully
        # replaced before typing), fall back to the clean default instead
        # of exporting a garbled filename.
        if typed and typed != default_filename and typed.lower().endswith(default_filename.lower()) and typed.lower() != default_filename.lower():
            _log_ui(f"Filename '{typed}' looks like corrupted default text, using '{default_filename}' instead")
            typed = default_filename
        # Ensure a sane extension
        if typed and not typed.lower().endswith('.fbx'):
            typed = typed + '.fbx'

        result["filename"] = (typed or default_filename)
        result["folder"] = folder_var.get().strip() or default_folder
        root.quit()
        root.destroy()

    def cancel():
        result["filename"] = None
        result["folder"] = None
        root.quit()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", cancel)

    ttk.Label(root, text="Nazwa pliku:").grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))
    filename_entry = ttk.Entry(root, textvariable=filename_var, width=52, style="TEntry")
    filename_entry.grid(row=1, column=0, columnspan=2, padx=14, pady=(0, 6), sticky="ew")

    def _select_all_on_focus(event):
        # Defer selection until idle; clicking triggers ButtonPress after
        # FocusIn which would otherwise cancel the selection. after_idle
        # ensures the selection persists so typing replaces the whole text.
        try:
            event.widget.after_idle(lambda: (event.widget.select_range(0, "end"), event.widget.icursor("end")))
        except Exception:
            # Fallback to immediate selection if after_idle isn't available
            event.widget.select_range(0, "end")
            event.widget.icursor("end")

    filename_entry.bind("<FocusIn>", _select_all_on_focus)

    ttk.Label(root, text="Folder docelowy:").grid(row=3, column=0, sticky="w", padx=14, pady=(0, 6))
    folder_entry = ttk.Entry(root, textvariable=folder_var, width=44, style="TEntry")
    folder_entry.grid(row=4, column=0, padx=14, pady=(0, 6), sticky="ew")
    ttk.Button(root, text="Browse", command=choose_folder).grid(row=4, column=1, padx=(6, 14), pady=(0, 6), sticky="w")

    ttk.Label(root, textvariable=output_path_var, foreground="white").grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))

    ttk.Button(root, text="GO EXPORT", command=confirm, width=18).grid(row=6, column=0, padx=14, pady=(6, 14), sticky="w")
    ttk.Button(root, text="Cancel", command=cancel, width=14, style="Secondary.TButton").grid(row=6, column=1, padx=(6, 14), pady=(6, 14), sticky="e")

    version_label = ttk.Label(root, text="v1.8 — każda zmiana w kodzie = nowa wersja", foreground=ui_style.PALETTE["fg_muted"])
    version_label.grid(row=7, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))

    root.columnconfigure(0, weight=1)
    root.columnconfigure(1, weight=0)
    root.mainloop()

    if result["filename"] is None and result["folder"] is None:
        return None
    return result


def _show_export_progress(output_path, config, selection=None):
    try:
        import threading
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        if unreal is not None:
            unreal.log(f"[exUE5] Tkinter progress dialog unavailable: {exc}")
        return

    unreal.log(f"[exUE5] _show_export_progress running in thread: {threading.current_thread().name}")
    status = {
        "done": False,
        "success": False,
        "message": "Starting export...",
    }

    root = tk.Tk()
    ui_style.apply_theme(root, title="Export Sequence FBX", min_size=(440, 220))
    ui_style.apply_geometry(root, 560, 260)

    ttk.Label(root, text="Trwa eksport...").pack(padx=16, pady=(18, 8), anchor="w")
    progress = ttk.Progressbar(root, style="Horizontal.TProgressbar", mode="indeterminate", length=472)
    progress.pack(padx=16, pady=(0, 14), fill="x")
    progress.start(10)

    status_label = ttk.Label(root, text=status["message"])
    status_label.pack(padx=16, pady=(0, 12), anchor="w")

    button_frame = ttk.Frame(root, style="TFrame")
    button_frame.pack(fill="x", padx=16, pady=(0, 14))

    ok_button = ttk.Button(button_frame, text="OK", state="disabled", command=root.destroy, width=16)
    ok_button.pack(side="right")

    def show_logs():
        try:
            open_debug_console(root, since_index=start_log_index)
        except Exception as exc:
            unreal.log(f"[exUE5] Could not open debug console: {exc}")

    ttk.Button(button_frame, text="Pokaż logi", command=show_logs, width=16, style="Secondary.TButton").pack(side="left")

    # Capture the current log index so the debug console opened from this
    # progress dialog will show only logs emitted after the export started.
    try:
        start_log_index = get_log_index()
    except Exception:
        start_log_index = None

    def check_status():
        status_label.config(text=status["message"])
        if status["done"]:
            progress.stop()
            ok_button.config(state="normal")
            if status["success"]:
                status_label.config(text="Eksport zakończony pomyślnie.")
            else:
                status_label.config(text=status["message"])
        else:
            root.after(100, check_status)

    def run_export_worker():
        # Run the export from the same Tk/Unreal main event loop to avoid
        # cross-thread access to Unreal's Python API. This is the safest path
        # for this plugin even though the UI may briefly freeze while the export
        # is in progress.
        try:
            unreal.log(f"[exUE5] run_export started on thread: {threading.current_thread().name}")
            result = export_current_sequence(output_path, config, selection=selection)
            status["success"] = True
            if result and result.get("flagged_spawnables"):
                status["message"] = (
                    f"Eksport zakończony pomyślnie. UWAGA: wykryto {len(result['flagged_spawnables'])} "
                    "Spawnable binding(ów). Sprawdź Output Log i Debug Console."
                )
            else:
                status["message"] = "Eksport zakończony pomyślnie. Brak Spawnable bindingów w eksporcie."
        except Exception as exc:
            status["success"] = False
            status["message"] = f"Błąd eksportu: {exc}"
        finally:
            status["done"] = True

    root.after(0, run_export_worker)
    root.after(100, check_status)
    root.mainloop()


def _show_camera_export_progress(output_path, config, sequence, camera_binding_ids):
    try:
        import threading
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        if unreal is not None:
            unreal.log(f"[exUE5] Tkinter camera progress dialog unavailable: {exc}")
        return

    unreal.log(f"[exUE5] _show_camera_export_progress running")
    status = {
        "done": False,
        "success": False,
        "message": "Rozpoczynam eksport kamery...",
    }

    root = tk.Tk()
    ui_style.apply_theme(root, title="Export Camera FBX", min_size=(440, 220))
    ui_style.apply_geometry(root, 560, 260)

    ttk.Label(root, text="Trwa eksport kamery...").pack(padx=16, pady=(18, 8), anchor="w")
    progress = ttk.Progressbar(root, style="Horizontal.TProgressbar", mode="indeterminate", length=472)
    progress.pack(padx=16, pady=(0, 14), fill="x")
    progress.start(10)

    status_label = ttk.Label(root, text=status["message"])
    status_label.pack(padx=16, pady=(0, 12), anchor="w")

    button_frame = ttk.Frame(root, style="TFrame")
    button_frame.pack(fill="x", padx=16, pady=(0, 14))

    ok_button = ttk.Button(button_frame, text="OK", state="disabled", command=root.destroy, width=16)
    ok_button.pack(side="right")

    def show_logs():
        try:
            open_debug_console(root, since_index=start_log_index)
        except Exception as exc:
            unreal.log(f"[exUE5] Could not open camera debug console: {exc}")

    ttk.Button(button_frame, text="Pokaż logi", command=show_logs, width=16, style="Secondary.TButton").pack(side="left")

    try:
        start_log_index = get_log_index()
    except Exception:
        start_log_index = None

    def check_status():
        status_label.config(text=status["message"])
        if status["done"]:
            progress.stop()
            ok_button.config(state="normal")
            if status["success"]:
                status_label.config(text="Eksport kamery zakończony pomyślnie.")
            else:
                status_label.config(text=status["message"])
        else:
            root.after(100, check_status)

    def run_camera_export_worker():
        try:
            unreal.log(f"[exUE5] run_camera_export_worker started")
            try:
                from exUE5.camera_export import export_cameras_fbx
            except ModuleNotFoundError:
                from camera_export import export_cameras_fbx

            success = export_cameras_fbx(sequence, camera_binding_ids, output_path, show_dialog=False)
            status["success"] = bool(success)
            if status["success"]:
                status["message"] = "Eksport kamery zakończony pomyślnie."
            else:
                status["message"] = "Eksport kamery nie powiódł się. Sprawdź logi."
        except Exception as exc:
            status["success"] = False
            status["message"] = f"Błąd eksportu kamery: {exc}"
            unreal.log(f"[exUE5] ERROR _show_camera_export_progress: {exc}")
        finally:
            status["done"] = True

    root.after(0, run_camera_export_worker)
    root.after(100, check_status)
    root.mainloop()