import threading
import time
from collections import deque

try:
    import unreal
except ModuleNotFoundError:
    unreal = None

_LOG_LOCK = threading.Lock()
_LOG_BUFFER = deque(maxlen=2000)


def push_log(message, level="INFO"):
    """Append a log entry for the live debug console."""
    with _LOG_LOCK:
        _LOG_BUFFER.append((time.strftime("%H:%M:%S"), level, str(message)))


def get_new_logs(since_index):
    with _LOG_LOCK:
        total = len(_LOG_BUFFER)
        if total <= 0:
            return [], 0
        start = max(0, min(since_index, total))
        entries = list(_LOG_BUFFER)
        new_entries = entries[start:]
        return new_entries, total


def get_log_index():
    """Return the current index/length of the log buffer."""
    with _LOG_LOCK:
        return len(_LOG_BUFFER)


class DebugConsoleWindow:
    def __init__(self, master=None, since_index=None):
        import tkinter as tk

        try:
            from exUE5 import ui_style
        except ModuleNotFoundError:
            import ui_style

        self._own_root = master is None
        self.root = tk.Toplevel(master) if master else tk.Tk()
        ui_style.apply_theme(self.root, title="PLUGSY Exporter -- Debug Console", min_size=(520, 300))
        ui_style.apply_geometry(self.root, 820, 460)
        self._ui = ui_style

        if since_index is None:
            self._last_index = len(_LOG_BUFFER)
        else:
            # Clamp to current buffer length so we never start past the end.
            with _LOG_LOCK:
                total = len(_LOG_BUFFER)
            self._last_index = max(0, min(since_index, total))
        self._paused = False

        toolbar = ui_style.frame(self.root)
        toolbar.pack(fill="x", padx=10, pady=(10, 6))

        self.pause_var = tk.BooleanVar(value=False)
        ui_style.checkbutton(
            toolbar,
            text="Pauza autoscroll",
            variable=self.pause_var,
            command=self._toggle_pause,
        ).pack(side="left")

        ui_style.button(toolbar, text="Wyczyść", command=self._clear, primary=False).pack(side="left", padx=6)
        ui_style.button(toolbar, text="Zapisz do pliku", command=self._save_to_file, primary=False).pack(side="left")

        self.text = tk.Text(
            self.root,
            bg=ui_style.PALETTE["console_bg"],
            fg="#d4d4d4",
            insertbackground="white",
            font=ui_style.FONTS["mono"],
            state="disabled",
            wrap="none",
            relief="flat",
            highlightthickness=1,
            highlightbackground=ui_style.PALETTE["border"],
        )
        self.text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.text.tag_config("WARNING", foreground=ui_style.PALETTE["warning"])
        self.text.tag_config("ERROR", foreground=ui_style.PALETTE["error"])

        self._poll()

    def _toggle_pause(self):
        self._paused = self.pause_var.get()

    def _clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def _save_to_file(self):
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(defaultextension=".log", filetypes=[("Log files", "*.log"), ("All files", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.text.get("1.0", "end"))

    def _poll(self):
        new_entries, total = get_new_logs(self._last_index)
        if new_entries and not self._paused:
            self._last_index = total
            self.text.configure(state="normal")
            for ts, level, msg in new_entries:
                tag = level if level in ("WARNING", "ERROR") else None
                line = f"[{ts}] {msg}\n"
                if tag:
                    self.text.insert("end", line, tag)
                else:
                    self.text.insert("end", line)
            self.text.see("end")
            self.text.configure(state="disabled")
        elif total > self._last_index:
            self._last_index = total
        self.root.after(300, self._poll)

    def show(self):
        if self._own_root:
            self.root.mainloop()


def open_debug_console(master=None, since_index=None):
    return DebugConsoleWindow(master, since_index=since_index)
