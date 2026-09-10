"""The application window: navigation, header, and the screens inside it.

The shell owns the current `Analysis` and nothing else. It knows how to load
a workbook and which screen is showing; every number on every screen comes
from the domain, not from here.

Screens are refreshed lazily. Building five screens over two thousand
records on every import would make loading feel slow for four screens nobody
is looking at, so a new analysis marks them all stale and each is rebuilt the
first time it is shown.
"""

from __future__ import annotations

import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox

from .. import APP_NAME, APP_TAGLINE
from ..analysis import analyze_workbook
from ..ingestion.xlsx import WorkbookError
from .dashboard import Dashboard
from .reports import Reports
from .review import Review
from .rules import Rules
from .theme import Palette, Theme
from .widgets import Card, FlatButton, NavItem
from .work_orders import WorkOrders

DEMO_WORKBOOK = "servicelens_demo_workbook.xlsx"
MINIMUM_SIZE = (1180, 720)


def project_root() -> Path:
    """The repository root, so the demo workbook can be found beside it."""
    return Path(__file__).resolve().parents[2]


class Application(tk.Tk):
    """The ServiceLens desktop window."""

    def __init__(self, scale: float | None = None) -> None:
        super().__init__()
        self.theme = Theme(self, scale)
        theme = self.theme

        self.title(f"{APP_NAME} - {APP_TAGLINE}")
        self.configure(bg=Palette.SURFACE)
        self.minsize(theme.px(MINIMUM_SIZE[0]), theme.px(MINIMUM_SIZE[1]))
        self.geometry(f"{theme.px(1440)}x{theme.px(880)}")

        self.analysis = None
        self.current = ""
        self._stale: set = set()

        self._build_rail()
        self._build_main()
        self._build_views()
        self._show_empty()

    # -- chrome ---------------------------------------------------------

    def _build_rail(self) -> None:
        theme = self.theme
        rail = tk.Frame(self, bg=Palette.INK, width=theme.px(214))
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)

        brand = tk.Frame(rail, bg=Palette.INK)
        brand.pack(fill="x", pady=(theme.px(22), theme.px(18)),
                   padx=theme.px(17))
        tk.Label(brand, text=APP_NAME, font=theme.font(18, "bold"),
                 bg=Palette.INK, fg=Palette.ON_DARK, anchor="w").pack(
            fill="x")
        tk.Label(brand, text=APP_TAGLINE.upper(), font=theme.tiny,
                 bg=Palette.INK, fg=Palette.INK_DIM, anchor="w").pack(
            fill="x")

        tk.Frame(rail, bg=Palette.INK_LINE, height=1).pack(
            fill="x", padx=theme.px(17))

        self.nav: dict = {}
        holder = tk.Frame(rail, bg=Palette.INK)
        holder.pack(fill="x", pady=theme.px(12))
        for key, label in (("dashboard", "Dashboard"),
                           ("work_orders", "Work Orders"),
                           ("review", "Intelligence"),
                           ("reports", "Reports"),
                           ("rules", "Rules")):
            item = NavItem(holder, theme, label,
                           lambda k=key: self.show(k))
            item.pack(fill="x")
            self.nav[key] = item

        actions = tk.Frame(rail, bg=Palette.INK)
        actions.pack(fill="x", padx=theme.px(17), pady=theme.px(14))
        FlatButton(actions, theme, "Open workbook...",
                   command=self.open_workbook).pack(fill="x")
        self.demo_button = FlatButton(
            actions, theme, "Load demonstration data",
            command=self.load_demo, kind="rail")
        self.demo_button.pack(fill="x", pady=(theme.px(8), 0))

        footer = tk.Frame(rail, bg=Palette.INK)
        footer.pack(side="bottom", fill="x", padx=theme.px(17),
                    pady=theme.px(16))
        tk.Label(footer, text="Local-first. Nothing leaves this machine.",
                 font=theme.tiny, bg=Palette.INK, fg=Palette.INK_DIM,
                 anchor="w", justify="left",
                 wraplength=theme.px(180)).pack(fill="x")

    def _build_main(self) -> None:
        theme = self.theme
        main = tk.Frame(self, bg=Palette.SURFACE)
        main.pack(side="left", fill="both", expand=True)

        header = tk.Frame(main, bg=Palette.CARD)
        header.pack(fill="x")
        inner = tk.Frame(header, bg=Palette.CARD)
        inner.pack(fill="x", padx=theme.px(16), pady=theme.px(12))

        self.screen_title = tk.Label(
            inner, text="Dashboard", font=theme.heading, bg=Palette.CARD,
            fg=Palette.TEXT, anchor="w")
        self.screen_title.pack(side="left")

        self.source_line = tk.Label(
            inner, text="No workbook loaded", font=theme.small,
            bg=Palette.CARD, fg=Palette.MUTED, anchor="e", justify="right")
        self.source_line.pack(side="right")

        tk.Frame(main, bg=Palette.BORDER, height=1).pack(fill="x")

        self.content = tk.Frame(main, bg=Palette.SURFACE)
        self.content.pack(fill="both", expand=True)

    def _build_views(self) -> None:
        theme = self.theme
        self.views = {
            "dashboard": Dashboard(self.content, theme,
                                   on_open_record=self.open_record),
            "work_orders": WorkOrders(self.content, theme,
                                      on_open_record=self.open_record),
            "review": Review(self.content, theme),
            "reports": Reports(self.content, theme),
            "rules": Rules(self.content, theme),
        }
        self.titles = {
            "dashboard": "Operational overview",
            "work_orders": "Work orders",
            "review": "Intelligence and review",
            "reports": "Reports",
            "rules": "Rules and policy",
        }
        self.empty = self._build_empty()

    def _build_empty(self) -> tk.Frame:
        theme = self.theme
        frame = tk.Frame(self.content, bg=Palette.SURFACE)
        card = Card(frame, theme)
        card.pack(padx=theme.px(120), pady=theme.px(80), fill="x")
        body = card.content()
        inner = tk.Frame(body, bg=Palette.CARD)
        inner.pack(fill="x", pady=theme.px(18), padx=theme.px(10))

        tk.Label(inner, text="Load a work order export",
                 font=theme.font(19, "bold"), bg=Palette.CARD,
                 fg=Palette.TEXT, anchor="w").pack(fill="x")
        tk.Label(
            inner,
            text="ServiceLens reads an Excel export of your work orders and "
                 "turns it into exception queues, risk signals and routing "
                 "recommendations. Your file is only ever read from, never "
                 "written to.\n\n"
                 "Column names do not have to match exactly - a work order "
                 "number can be called Work Order, WO Number or Job Number, "
                 "and an asset can be Equipment, Unit or Asset Tag. Anything "
                 "ServiceLens cannot place is reported rather than ignored.\n\n"
                 "No workbook to hand? Load the synthetic demonstration "
                 "dataset. Every value in it is invented.",
            font=theme.body, bg=Palette.CARD, fg=Palette.MUTED, anchor="w",
            justify="left", wraplength=theme.px(620)).pack(
            fill="x", pady=(theme.px(8), theme.px(18)))

        actions = tk.Frame(inner, bg=Palette.CARD)
        actions.pack(fill="x")
        FlatButton(actions, theme, "Open workbook...",
                   command=self.open_workbook).pack(side="left")
        FlatButton(actions, theme, "Load demonstration data",
                   command=self.load_demo, kind="ghost").pack(
            side="left", padx=(theme.px(10), 0))
        return frame

    # -- navigation -----------------------------------------------------

    def _show_empty(self) -> None:
        for view in self.views.values():
            view.pack_forget()
        self.empty.pack(fill="both", expand=True)
        for item in self.nav.values():
            item.set_active(False)

    def show(self, key: str) -> None:
        if self.analysis is None:
            return
        self.empty.pack_forget()
        for name, view in self.views.items():
            if name != key:
                view.pack_forget()

        if key in self._stale:
            self.configure(cursor="watch")
            self.update_idletasks()
            try:
                self.views[key].refresh(self.analysis)
            finally:
                self.configure(cursor="")
            self._stale.discard(key)

        self.views[key].pack(fill="both", expand=True)
        self.current = key
        self.screen_title.configure(text=self.titles[key])
        for name, item in self.nav.items():
            item.set_active(name == key)

    def open_record(self, assessment) -> None:
        """Jump to the review screen with one record selected."""
        self.show("review")
        self.views["review"].select(assessment)

    # -- loading --------------------------------------------------------

    def open_workbook(self) -> None:
        path = filedialog.askopenfilename(
            title="Open work order export",
            filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")])
        if path:
            self.load(path)

    def load_demo(self) -> None:
        path = project_root() / "demo" / DEMO_WORKBOOK
        if not path.exists():
            if not messagebox.askyesno(
                    "Generate demonstration data",
                    "The demonstration workbook has not been generated yet.\n\n"
                    "Generate it now? It is written to demo/ and contains "
                    "only synthetic records."):
                return
            self.configure(cursor="watch")
            self.update_idletasks()
            try:
                from ..demo import generator
                records = generator.Generator()
                generator.write(path, records.generate(), records.reference)
            except Exception as error:  # noqa: BLE001 - reported to the user
                self.configure(cursor="")
                messagebox.showerror(
                    "Could not generate demonstration data", str(error))
                return
            self.configure(cursor="")
        self.load(str(path))

    def load(self, path: str) -> None:
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            analysis = analyze_workbook(path)
        except WorkbookError as error:
            self.configure(cursor="")
            messagebox.showerror("Could not read this workbook", str(error))
            return
        except Exception as error:  # noqa: BLE001 - never die silently
            self.configure(cursor="")
            messagebox.showerror(
                "Unexpected problem reading this workbook",
                f"{type(error).__name__}: {error}\n\n"
                f"{traceback.format_exc(limit=3)}")
            return
        finally:
            self.configure(cursor="")

        self.analysis = analysis
        self._stale = set(self.views)
        self._update_source_line()
        self.show(self.current or "dashboard")

    def _update_source_line(self) -> None:
        imported = self.analysis.imported
        metrics = self.analysis.metrics
        name = Path(imported.source_path).name or "workbook"
        schema = imported.schema
        parts = [
            name,
            f"{metrics.total:,} work orders",
            f"as of {self.analysis.as_of.strftime('%d %b %Y')}",
        ]
        if schema.unmapped_headers:
            parts.append(f"{len(schema.unmapped_headers)} column"
                         f"{'s' if len(schema.unmapped_headers) != 1 else ''}"
                         " not recognized")
        self.source_line.configure(text="   ·   ".join(parts))


def run(scale: float | None = None, workbook: str | None = None) -> None:
    """Launch the application."""
    application = Application(scale)
    if workbook:
        application.after(60, lambda: application.load(workbook))
    application.mainloop()
