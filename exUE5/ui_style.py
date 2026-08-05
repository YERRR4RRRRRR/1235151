"""
Centralny moduł stylu GUI dla pluginu exUE5.

Jedna zmiana wyglądu całego pluginu = edycja PALETTE / FONTS poniżej.
Wszystkie okna (camera_dialog, selection_dialog, debug_console, ui_dialogs)
importują ten moduł i wołają apply_theme(root) zamiast same sobie ustawiać
kolory/fonty -- dzięki temu nie ma rozjazdów wyglądu między oknami.

Ten plik naprawia też realną przyczynę "złego skalowania", a nie tylko
kosmetykę:

1. Brak DPI-awareness procesu (Unreal Editor embedded Python nigdy tego nie
   ustawia) -> na monitorach 4K / skalowaniu Windows 125-150-200% Windows
   renderuje okno Tk w rozdzielczości "kłamanej" (bitmap-scaled), więc tekst
   i przyciski wychodzą drobne i rozmyte. enable_dpi_awareness() ustawia to
   raz na proces, PRZED stworzeniem pierwszego tk.Tk().
2. Sztywne `root.geometry("520x260")` + `resizable(False, False)` w kilku
   oknach -> okno nie mogło się w ogóle przeskalować, więc na wysokim DPI
   zostawało "ściśnięte". apply_theme() włącza resizable + realną skalę Tk
   (na podstawie wykrytego DPI ekranu), a minsize() pilnuje żeby okno nie
   dało się skurczyć poniżej czytelnego rozmiaru.
3. Nawet z resizable + `tk scaling` ustawionym, jawne wartości pikselowe
   (root.geometry("600x560"), tk.Canvas(width=500)) same się NIE skalują --
   `tk scaling` dotyczy tylko fontów i domyślnych, jednostko-zależnych
   rozmiarów ttk. Na 4K/150% te dwie rzeczy się rozjeżdżały: fonty i
   przyciski były już poprawnie większe, ale samo okno/canvas zostawały w
   niezmienionym, za małym rozmiarze -- więc treść (listy bindingów,
   przyciski na dole) była ucinana mimo że "skalowanie" niby działało.
   Użyj `apply_geometry(root, w, h)` zamiast `root.geometry(f"{w}x{h}")` i
   `scaled(root, value)` dla wszelkich innych jawnych rozmiarów pikselowych
   (np. Canvas width/height) -- patrz definicje poniżej.
"""

import sys

# ---------------------------------------------------------------------------
# Paleta / fonty -- edytuj tylko tutaj, żeby zmienić wygląd całego pluginu
# ---------------------------------------------------------------------------

PALETTE = {
    "bg": "#18181c",             # tło głównego okna
    "bg_panel": "#212127",       # tło paneli / list / ramek
    "bg_elevated": "#28282f",    # tło "uniesionych" kart / rozwijanych sekcji
    "bg_input": "#131316",       # tło pól tekstowych
    "fg": "#f1f1f3",             # główny tekst
    "fg_muted": "#9d9da7",       # tekst drugorzędny (ścieżki, wersja, hinty)
    "fg_subtle": "#6c6c76",      # tekst trzeciorzędny (liczniki, disabled-ish)
    "accent": "#45b579",         # zielony akcent -- przyciski główne
    "accent_hover": "#54cc8c",
    "accent_active": "#358f5f",
    "accent_soft": "#22352a",    # subtelne tło dla rozwiniętych/aktywnych sekcji
    "danger": "#c0392b",
    "danger_hover": "#d9483a",
    "border": "#34343c",
    "divider": "#2a2a31",
    "warning": "#e0c341",
    "error": "#e05555",
    "success": "#5bbf5b",
    "console_bg": "#0f0f12",
}

FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"

FONTS = {
    "base": (FONT_FAMILY, 10),
    "small": (FONT_FAMILY, 9),
    "bold": (FONT_FAMILY, 10, "bold"),
    "title": (FONT_FAMILY, 12, "bold"),
    "section": (FONT_FAMILY, 9, "bold"),
    "mono": (FONT_MONO, 9),
}

_DPI_DONE = False


def enable_dpi_awareness():
    """Włącza DPI-awareness procesu.

    Powinno być wywołane RAZ, PRZED stworzeniem pierwszego tk.Tk() w procesie
    (apply_theme() woła to automatycznie jako zabezpieczenie, ale najlepiej
    wywołać to jawnie na starcie pluginu -- patrz init_unreal.py).
    Bezpieczne przy wielokrotnym wywołaniu: po pierwszym razie jest no-opem.
    """
    global _DPI_DONE
    if _DPI_DONE:
        return
    _DPI_DONE = True

    if sys.platform != "win32":
        return

    try:
        import ctypes
    except Exception:
        return

    # Kolejność od najlepszej do najbardziej kompatybilnej -- pierwsza, która
    # się uda, wygrywa.
    try:
        # Windows 10 1703+: pełna świadomość per-monitor (najlepsza jakość,
        # poprawnie reaguje nawet na przenoszenie okna między monitorami
        # o różnym DPI).
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        # Windows 8.1+
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        # Windows Vista+ fallback
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _apply_scaling(root):
    """Ustawia realną skalę Tk na podstawie wykrytego DPI ekranu, żeby fonty
    i widgety miały ten sam fizyczny rozmiar niezależnie od tego czy Windows
    ma ustawione 100%, 125%, 150% czy 200% skalowania."""
    try:
        dpi = root.winfo_fpixels("1i")
        if dpi > 0:
            root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass


def get_scale_factor(root):
    """Zwraca współczynnik skalowania względem "standardowych" 96 DPI
    (Windows 100%).

    WAŻNE: `tk scaling` (ustawiane przez _apply_scaling powyżej) skaluje
    tylko fonty i domyślne, jednostko-zależne rozmiary widgetów ttk -- NIE
    skaluje jawnych wartości pikselowych typu `root.geometry("600x560")`
    albo `tk.Canvas(width=500)`. Na monitorze 4K ze skalowaniem Windows
    150% te dwie rzeczy się rozjeżdżają: fonty/przyciski są poprawnie
    powiększone, ale okno i canvasy zostają w oryginalnym, za małym
    rozmiarze -- więc treść jest ucinana. Użyj tego współczynnika (razem z
    `scaled()` / `apply_geometry()` poniżej) wszędzie tam, gdzie w kodzie
    dialogu pojawia się jawna wartość w pikselach.
    """
    try:
        dpi = root.winfo_fpixels("1i")
        if dpi > 0:
            return dpi / 96.0
    except Exception:
        pass
    return 1.0


def scaled(root, value):
    """Przelicza pojedynczą wartość pikselową na aktualne DPI ekranu."""
    try:
        return max(1, int(round(value * get_scale_factor(root))))
    except Exception:
        return value


def apply_geometry(root, width, height):
    """DPI-świadomy odpowiednik `root.geometry(f"{width}x{height}")`.

    Używaj tego zamiast wołać `root.geometry(...)` bezpośrednio ze stałymi
    pikselowymi -- patrz komentarz w get_scale_factor() powyżej. Wywołuj PO
    apply_theme(), żeby `tk scaling` był już ustawiony.
    """
    w = scaled(root, width)
    h = scaled(root, height)
    root.geometry(f"{w}x{h}")
    return w, h


def apply_theme(root, title=None, min_size=(360, 200), resizable=True):
    """Stosuje wspólny motyw do okna: DPI-scaling, tło, styl ttk, możliwość
    skalowania okna. Wywołaj RAZ, zaraz po stworzeniu root / Toplevel,
    najlepiej przed dodaniem widgetów.

    root       -- tk.Tk() lub tk.Toplevel()
    title      -- opcjonalny tytuł okna
    min_size   -- (szerokość, wysokość) minimalny rozmiar okna, żeby nie dało
                  się go skurczyć do nieczytelnego rozmiaru; None = bez limitu
    resizable  -- czy okno ma się dać skalować (domyślnie tak -- to jest
                  główna naprawa problemu ze skalowaniem)
    """
    enable_dpi_awareness()  # no-op jeśli już zrobione; siatka bezpieczeństwa
    _apply_scaling(root)

    if title:
        root.title(title)

    root.configure(bg=PALETTE["bg"])
    root.resizable(bool(resizable), bool(resizable))

    if min_size:
        try:
            # min_size is specified in "logical" 96-DPI pixels, same as every
            # apply_geometry() call -- scale it the same way so a HiDPI window
            # can't be shrunk below a physically-readable size either.
            w, h = min_size
            root.minsize(scaled(root, w), scaled(root, h))
        except Exception:
            try:
                root.minsize(*min_size)
            except Exception:
                pass

    _apply_ttk_style(root)
    return root


def _apply_ttk_style(root):
    from tkinter import ttk

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure("TFrame", background=PALETTE["bg"])
    style.configure("TLabel", background=PALETTE["bg"], foreground=PALETTE["fg"], font=FONTS["base"])
    style.configure("TCheckbutton", background=PALETTE["bg"], foreground=PALETTE["fg"], font=FONTS["base"])
    style.map("TCheckbutton", background=[("active", PALETTE["bg"])])

    style.configure(
        "TButton",
        background=PALETTE["accent"],
        foreground=PALETTE["fg"],
        borderwidth=0,
        focusthickness=0,
        padding=(14, 7),
        font=FONTS["base"],
    )
    style.map(
        "TButton",
        background=[
            ("disabled", PALETTE["border"]),
            ("pressed", PALETTE["accent_active"]),
            ("active", PALETTE["accent_hover"]),
        ],
        foreground=[("disabled", PALETTE["fg_muted"])],
    )

    # Drugorzędny przycisk (np. "Anuluj") -- mniej wyrazisty niż akcja główna
    style.configure(
        "Secondary.TButton",
        background=PALETTE["bg_panel"],
        foreground=PALETTE["fg"],
        borderwidth=1,
        padding=(14, 7),
        font=FONTS["base"],
    )
    style.map("Secondary.TButton", background=[("active", PALETTE["border"]), ("pressed", PALETTE["border"])])

    style.configure(
        "TEntry",
        fieldbackground=PALETTE["bg_input"],
        foreground=PALETTE["fg"],
        insertcolor=PALETTE["fg"],
        padding=6,
    )
    style.map("TEntry", fieldbackground=[("disabled", PALETTE["bg_panel"])])

    style.configure("TMenubutton", background=PALETTE["accent"], foreground=PALETTE["fg"])

    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=PALETTE["bg_panel"],
        background=PALETTE["accent"],
        bordercolor=PALETTE["bg"],
        lightcolor=PALETTE["accent_hover"],
        darkcolor=PALETTE["accent_active"],
    )

    style.configure(
        "Vertical.TScrollbar",
        background=PALETTE["bg_panel"],
        troughcolor=PALETTE["bg"],
        bordercolor=PALETTE["bg"],
        arrowcolor=PALETTE["fg"],
    )


# ---------------------------------------------------------------------------
# Fabryki widgetów tk.* -- część okien używa "surowego" tk zamiast ttk
# (listy checkboxów, dynamiczne formularze). Jedno miejsce definiujące
# wygląd zamiast powtarzania bg=/fg=/font= przy każdym widgecie.
# ---------------------------------------------------------------------------

def frame(parent, **kwargs):
    import tkinter as tk
    kwargs.setdefault("bg", PALETTE["bg"])
    return tk.Frame(parent, **kwargs)


def label(parent, text="", muted=False, bold=False, **kwargs):
    import tkinter as tk
    kwargs.setdefault("bg", PALETTE["bg"])
    kwargs.setdefault("fg", PALETTE["fg_muted"] if muted else PALETTE["fg"])
    kwargs.setdefault("font", FONTS["bold"] if bold else FONTS["base"])
    return tk.Label(parent, text=text, **kwargs)


def entry(parent, **kwargs):
    import tkinter as tk
    kwargs.setdefault("bg", PALETTE["bg_input"])
    kwargs.setdefault("fg", PALETTE["fg"])
    kwargs.setdefault("insertbackground", PALETTE["fg"])
    kwargs.setdefault("relief", "flat")
    kwargs.setdefault("highlightthickness", 1)
    kwargs.setdefault("highlightbackground", PALETTE["border"])
    kwargs.setdefault("highlightcolor", PALETTE["accent"])
    kwargs.setdefault("font", FONTS["base"])
    return tk.Entry(parent, **kwargs)


def checkbutton(parent, **kwargs):
    import tkinter as tk
    kwargs.setdefault("bg", PALETTE["bg"])
    kwargs.setdefault("fg", PALETTE["fg"])
    kwargs.setdefault("selectcolor", PALETTE["bg_panel"])
    kwargs.setdefault("activebackground", PALETTE["bg"])
    kwargs.setdefault("activeforeground", PALETTE["fg"])
    kwargs.setdefault("font", FONTS["base"])
    kwargs.setdefault("anchor", "w")
    return tk.Checkbutton(parent, **kwargs)


def button(parent, text="", primary=True, **kwargs):
    """Płaski przycisk tk.Button z hover-em (jeden .configure() na event,
    więc brak migotania/lagów przy najechaniu myszką)."""
    import tkinter as tk

    bg = PALETTE["accent"] if primary else PALETTE["bg_panel"]
    hover = PALETTE["accent_hover"] if primary else PALETTE["border"]
    fg = PALETTE["fg"]

    kwargs.setdefault("relief", "flat")
    kwargs.setdefault("borderwidth", 0)
    kwargs.setdefault("padx", 14)
    kwargs.setdefault("pady", 6)
    kwargs.setdefault("font", FONTS["base"])
    kwargs.setdefault("cursor", "hand2")

    btn = tk.Button(parent, text=text, bg=bg, fg=fg, activebackground=hover, activeforeground=fg, **kwargs)

    def _enter(_event):
        if str(btn["state"]) != "disabled":
            btn.configure(bg=hover)

    def _leave(_event):
        if str(btn["state"]) != "disabled":
            btn.configure(bg=bg)

    btn.bind("<Enter>", _enter)
    btn.bind("<Leave>", _leave)
    return btn


def canvas(parent, **kwargs):
    import tkinter as tk
    kwargs.setdefault("bg", PALETTE["bg"])
    kwargs.setdefault("highlightthickness", 0)
    return tk.Canvas(parent, **kwargs)


def divider(parent, **kwargs):
    """Cienka pozioma linia oddzielająca sekcje (np. nagłówek od listy)."""
    import tkinter as tk
    kwargs.setdefault("bg", PALETTE["divider"])
    kwargs.setdefault("height", 1)
    kwargs.setdefault("bd", 0)
    kwargs.setdefault("highlightthickness", 0)
    return tk.Frame(parent, **kwargs)


def section_label(parent, text, count=None, **kwargs):
    """Nagłówek sekcji/kategorii (np. "BODY", "FACE", "INNE") -- spójny
    wygląd dla wszystkich grupowań list bindingów w oknach eksportu."""
    display_text = text.upper()
    if count is not None:
        display_text = f"{display_text}  ({count})"
    kwargs.setdefault("bg", PALETTE["bg"])
    kwargs.setdefault("fg", PALETTE["fg_muted"])
    kwargs.setdefault("font", FONTS["section"])
    import tkinter as tk
    return tk.Label(parent, text=display_text, anchor="w", **kwargs)
