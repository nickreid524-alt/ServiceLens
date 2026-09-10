"""Colours, type and scaling.

Two rules keep the interface consistent:

* **Colour is a token, never a literal.** Views name `Palette.CRITICAL`,
  never a hex string, so the whole application changes in one place.
* **Geometry is scaled, type is not.** Windows reports its scaling factor and
  Tk already sizes point-based fonts for it, so fonts are declared in points
  and left alone. Everything measured in pixels - padding, bar heights,
  column widths - goes through `Theme.px`.
"""

from __future__ import annotations

import ctypes
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk


class Palette:
    """A restrained navy and slate system with four status accents."""

    # Navigation rail
    INK = "#0F1A28"
    INK_HOVER = "#1A2A3D"
    INK_ACTIVE = "#21374F"
    INK_LINE = "#22364C"
    INK_TEXT = "#93A7BE"
    INK_DIM = "#6A7F97"

    # Content surfaces
    SURFACE = "#F4F6F9"
    CARD = "#FFFFFF"
    STRIPE = "#FAFBFC"
    BORDER = "#DCE2EA"
    BORDER_STRONG = "#C4CEDA"

    # Type
    TEXT = "#16202D"
    MUTED = "#6B7A8D"
    SUBTLE = "#94A3B4"
    ON_DARK = "#FFFFFF"

    # Accent
    ACCENT = "#2C6E9B"
    ACCENT_DEEP = "#21587D"
    ACCENT_SOFT = "#E8F0F6"

    # Status
    CRITICAL = "#B4372E"
    CRITICAL_SOFT = "#FBEDEC"
    WARNING = "#B3781A"
    WARNING_SOFT = "#FDF4E6"
    INFORMATION = "#3E7AA6"
    INFORMATION_SOFT = "#EDF4F9"
    CLEAR = "#2E7D5B"
    CLEAR_SOFT = "#EBF5F0"


SEVERITY_COLOUR = {
    "Critical": (Palette.CRITICAL, Palette.CRITICAL_SOFT),
    "Warning": (Palette.WARNING, Palette.WARNING_SOFT),
    "Information": (Palette.INFORMATION, Palette.INFORMATION_SOFT),
}

QUEUE_COLOUR = {
    "Immediate Review": Palette.CRITICAL,
    "Data Quality": Palette.INFORMATION,
    "Vendor Follow-up": Palette.ACCENT,
    "Cost Review": Palette.WARNING,
    "Preventive Maintenance": Palette.CLEAR,
    "Maintenance Planning": Palette.ACCENT_DEEP,
    "Routine Operations": Palette.SUBTLE,
}

FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"


def enable_dpi_awareness() -> None:
    """Tell Windows this process scales itself.

    Without this the window is rendered at 96 DPI and stretched by the
    compositor, which is what makes desktop Python applications look soft on
    a high-resolution display. Safe to call on any platform: anything other
    than Windows simply has no such API and is ignored.
    """
    for library, function, argument in (
            ("shcore", "SetProcessDpiAwareness", 1),
            ("user32", "SetProcessDPIAware", None)):
        try:
            module = getattr(ctypes, "windll", None)
            if module is None:
                return
            handler = getattr(getattr(module, library), function)
            handler(argument) if argument is not None else handler()
            return
        except (AttributeError, OSError):
            continue


class Theme:
    """Scaling, fonts and ttk styling for one application window."""

    def __init__(self, root: tk.Misc, scale: float | None = None) -> None:
        self.root = root
        if scale is not None:
            # Testing at a scaling factor this machine is not set to.
            self.ratio = scale
            root.tk.call("tk", "scaling", scale * 96.0 / 72.0)
        else:
            self.ratio = round(root.winfo_fpixels("1i") / 96.0, 4) or 1.0
        self._fonts: dict = {}
        self._configure_styles()

    # -- geometry ------------------------------------------------------

    def px(self, value: float) -> int:
        """Device pixels for a value expressed at 100% scaling."""
        return max(1, int(round(value * self.ratio)))

    # -- type ----------------------------------------------------------

    def font(self, size: int = 10, weight: str = "normal",
             family: str = FAMILY) -> tkfont.Font:
        key = (family, size, weight)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(
                root=self.root, family=family, size=size, weight=weight)
        return self._fonts[key]

    @property
    def body(self) -> tkfont.Font:
        return self.font(10)

    @property
    def body_bold(self) -> tkfont.Font:
        return self.font(10, "bold")

    @property
    def small(self) -> tkfont.Font:
        return self.font(9)

    @property
    def small_bold(self) -> tkfont.Font:
        return self.font(9, "bold")

    @property
    def tiny(self) -> tkfont.Font:
        return self.font(8)

    @property
    def heading(self) -> tkfont.Font:
        return self.font(15, "bold")

    @property
    def subheading(self) -> tkfont.Font:
        return self.font(11, "bold")

    @property
    def figure(self) -> tkfont.Font:
        return self.font(22, "bold")

    @property
    def figure_small(self) -> tkfont.Font:
        return self.font(16, "bold")

    @property
    def mono(self) -> tkfont.Font:
        return self.font(9, family=MONO_FAMILY)

    # -- ttk -----------------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:  # pragma: no cover - theme always present on Win
            pass

        row_height = self.px(26)
        style.configure(
            "SL.Treeview",
            background=Palette.CARD,
            fieldbackground=Palette.CARD,
            foreground=Palette.TEXT,
            rowheight=row_height,
            borderwidth=0,
            font=self.body,
        )
        style.configure(
            "SL.Treeview.Heading",
            background=Palette.SURFACE,
            foreground=Palette.MUTED,
            font=self.small_bold,
            relief="flat",
            padding=(self.px(8), self.px(6)),
        )
        style.map("SL.Treeview.Heading",
                  background=[("active", Palette.ACCENT_SOFT)])
        style.map("SL.Treeview",
                  background=[("selected", Palette.ACCENT_SOFT)],
                  foreground=[("selected", Palette.TEXT)])
        style.layout("SL.Treeview", [
            ("SL.Treeview.treearea", {"sticky": "nswe"})])

        style.configure("SL.Vertical.TScrollbar",
                        background=Palette.BORDER,
                        troughcolor=Palette.SURFACE,
                        bordercolor=Palette.SURFACE,
                        arrowcolor=Palette.MUTED,
                        relief="flat", borderwidth=0)
        style.configure("SL.Horizontal.TScrollbar",
                        background=Palette.BORDER,
                        troughcolor=Palette.SURFACE,
                        bordercolor=Palette.SURFACE,
                        arrowcolor=Palette.MUTED,
                        relief="flat", borderwidth=0)

        style.configure("SL.TCombobox",
                        fieldbackground=Palette.CARD,
                        background=Palette.CARD,
                        foreground=Palette.TEXT,
                        bordercolor=Palette.BORDER,
                        arrowcolor=Palette.MUTED,
                        selectbackground=Palette.CARD,
                        selectforeground=Palette.TEXT,
                        padding=(self.px(6), self.px(4)))
        self.root.option_add("*TCombobox*Listbox.background", Palette.CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", Palette.TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground",
                             Palette.ACCENT_SOFT)
        self.root.option_add("*TCombobox*Listbox.selectForeground",
                             Palette.TEXT)
        self.root.option_add("*TCombobox*Listbox.font", self.body)


def severity_colours(label: str) -> tuple:
    """Foreground and background for a severity label."""
    return SEVERITY_COLOUR.get(label, (Palette.MUTED, Palette.SURFACE))


def queue_colour(name: str) -> str:
    return QUEUE_COLOUR.get(name, Palette.ACCENT)
