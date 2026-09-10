"""Reporting.

Three exports, each shown with the figures it will actually contain,
computed live from the loaded analysis. Nothing is written until the user
picks a destination, and the source workbook is never touched.
"""

from __future__ import annotations

import os
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import filedialog, messagebox

from .. import reporting
from ..domain.models import Domain
from ..reporting import csv_export, exception_register, review_pack
from .theme import Palette, Theme
from .widgets import Card, FlatButton, ScrollArea, divider

CSV_SCOPES = (
    ("all", "All retained records"),
    ("flagged", "Flagged records only"),
    ("view", "Current Work Orders view"),
)


class Reports(tk.Frame):
    """Preview, choose a destination, export."""

    def __init__(self, parent, theme: Theme, current_view=None) -> None:
        super().__init__(parent, bg=Palette.SURFACE)
        self.theme = theme
        self.current_view = current_view
        self.analysis = None
        self.last_result = None
        self.csv_scope = tk.StringVar(value="all")
        self.area = ScrollArea(self, theme)
        self.area.pack(fill="both", expand=True)

    # -- rendering ------------------------------------------------------

    def refresh(self, analysis) -> None:
        theme = self.theme
        self.analysis = analysis
        for child in self.area.interior.winfo_children():
            child.destroy()
        holder = tk.Frame(self.area.interior, bg=Palette.SURFACE)
        holder.pack(fill="both", expand=True, padx=theme.px(16),
                    pady=theme.px(16))

        self._intro(holder, analysis)
        self._cards(holder, analysis)
        self._status(holder)
        self._source(holder, analysis)

    def _intro(self, parent, analysis) -> None:
        theme = self.theme
        facts = reporting.ReportContext(analysis)
        card = Card(parent, theme)
        card.pack(fill="x")
        body = card.content()
        tk.Label(body, text="Exports", font=theme.subheading,
                 bg=Palette.CARD, fg=Palette.TEXT, anchor="w").pack(fill="x")
        tk.Label(
            body,
            text="Every figure below is computed from the workbook currently "
                 "loaded. Choosing an export opens a save dialog; nothing is "
                 "written until you pick a destination. The source workbook "
                 "is only ever read from.",
            font=theme.small, bg=Palette.CARD, fg=Palette.MUTED, anchor="w",
            justify="left", wraplength=theme.px(760)).pack(
            fill="x", pady=(theme.px(4), 0))
        if facts.is_synthetic:
            tk.Label(
                body,
                text="This dataset declares itself synthetic, so every "
                     "export will carry that disclosure.",
                font=theme.small_bold, bg=Palette.CARD, fg=Palette.WARNING,
                anchor="w", justify="left",
                wraplength=theme.px(760)).pack(fill="x",
                                               pady=(theme.px(6), 0))

    def _cards(self, parent, analysis) -> None:
        theme = self.theme
        metrics = analysis.metrics
        integrity = sum(1 for a in analysis.assessments
                        if any(f.domain is Domain.DATA_QUALITY
                               for f in a.findings))
        queues = [(q, c) for q, c in metrics.by_queue
                  if c and q != "Routine Operations"]

        grid = tk.Frame(parent, bg=Palette.SURFACE)
        grid.pack(fill="both", expand=True, pady=(theme.px(14), 0))
        grid.columnconfigure(0, weight=1, uniform="reports")
        grid.columnconfigure(1, weight=1, uniform="reports")

        self._card(
            grid, 0, 0, "Review pack", "PDF",
            "A management narrative: board condition, where work sits, how "
            "it is aging, then the most urgent records with the evidence "
            "and the action requested for each.",
            ((f"{metrics.with_findings:,}", "flagged"),
             (f"{metrics.findings_total:,}", "findings"),
             (f"{metrics.critical:,}", "critical"),
             (f"{review_pack.DEFAULT_DETAIL_RECORDS}", "detailed in full")),
            "Save review pack...", self.export_review_pack)

        self._card(
            grid, 0, 1, "Exception register", "PDF",
            "Every flagged work order, grouped by the queue it was routed "
            "to, with the recommended action on each line.",
            ((f"{metrics.with_findings:,}", "work orders"),
             (f"{len(queues)}", "queues"),
             (f"{metrics.warning:,}", "warnings"),
             (f"{integrity:,}", "with integrity issues")),
            "Save exception register...", self.export_exception_register)

        card = self._card(
            grid, 1, 0, "Work order export", "CSV",
            "One row per work order: the canonical fields as read, plus the "
            "severity, queue, team, aging, vendor state and cost signals "
            "ServiceLens derived from them.",
            ((f"{len(csv_export.HEADERS)}", "columns"),
             (f"{metrics.total:,}", "retained"),
             (f"{metrics.with_findings:,}", "flagged"),
             (f"{self._scoped_count():,}", "in current scope")),
            "Save CSV...", self.export_csv, columns=2)
        self._scope_chooser(card)

    def _card(self, parent, row, column, title, kind, description, figures,
              action_label, action, columns: int = 1):
        theme = self.theme
        card = Card(parent, theme)
        card.grid(row=row, column=column,
                  columnspan=columns, sticky="nsew",
                  padx=(0, theme.px(7)) if column == 0 else (theme.px(7), 0),
                  pady=(0 if row == 0 else theme.px(14), 0))
        card.heading(title, kind)
        body = card.content()

        tk.Label(body, text=description, font=theme.small, bg=Palette.CARD,
                 fg=Palette.MUTED, anchor="w", justify="left",
                 wraplength=theme.px(340 * columns)).pack(fill="x")

        row_frame = tk.Frame(body, bg=Palette.CARD)
        row_frame.pack(fill="x", pady=(theme.px(10), theme.px(6)))
        for index, (value, label) in enumerate(figures):
            cell = tk.Frame(row_frame, bg=Palette.CARD)
            cell.grid(row=0, column=index, sticky="w",
                      padx=(0, theme.px(16)))
            tk.Label(cell, text=value, font=theme.subheading,
                     bg=Palette.CARD, fg=Palette.TEXT,
                     anchor="w").pack(fill="x")
            tk.Label(cell, text=label, font=theme.tiny, bg=Palette.CARD,
                     fg=Palette.SUBTLE, anchor="w").pack(fill="x")

        divider(body, theme, 4)
        actions = tk.Frame(body, bg=Palette.CARD)
        actions.pack(fill="x")
        FlatButton(actions, theme, action_label, command=action).pack(
            side="left")
        return body

    def _scope_chooser(self, body) -> None:
        theme = self.theme
        row = tk.Frame(body, bg=Palette.CARD)
        row.pack(fill="x", pady=(theme.px(8), 0))
        tk.Label(row, text="SCOPE", font=theme.tiny, bg=Palette.CARD,
                 fg=Palette.SUBTLE).pack(side="left", padx=(0, theme.px(8)))
        for value, label in CSV_SCOPES:
            tk.Radiobutton(
                row, text=label, value=value, variable=self.csv_scope,
                font=theme.small, bg=Palette.CARD, fg=Palette.TEXT,
                activebackground=Palette.CARD, activeforeground=Palette.TEXT,
                selectcolor=Palette.CARD, highlightthickness=0,
                borderwidth=0, command=self._refresh_scope_count).pack(
                side="left", padx=(0, theme.px(12)))
        self.scope_note = tk.Label(
            row, text="", font=theme.tiny, bg=Palette.CARD, fg=Palette.MUTED)
        self.scope_note.pack(side="left")
        self._refresh_scope_count()

    def _status(self, parent) -> None:
        theme = self.theme
        card = Card(parent, theme)
        card.pack(fill="x", pady=(theme.px(14), 0))
        card.heading("Last export", "")
        body = card.content()
        self.status_label = tk.Label(
            body, text="Nothing exported in this session.",
            font=theme.small, bg=Palette.CARD, fg=Palette.SUBTLE,
            anchor="w", justify="left", wraplength=theme.px(700))
        self.status_label.pack(fill="x")
        if self.last_result is not None:
            self._show_result(self.last_result)

    def _source(self, parent, analysis) -> None:
        theme = self.theme
        facts = reporting.ReportContext(analysis)
        card = Card(parent, theme)
        card.pack(fill="x", pady=(theme.px(14), 0))
        card.heading("What an export is based on",
                     "provenance travels with the numbers")
        body = card.content()
        for label, value in facts.provenance():
            row = tk.Frame(body, bg=Palette.CARD)
            row.pack(fill="x", pady=theme.px(2))
            tk.Label(row, text=label, font=theme.small, bg=Palette.CARD,
                     fg=Palette.MUTED, width=20, anchor="w").pack(side="left")
            tk.Label(row, text=value, font=theme.small, bg=Palette.CARD,
                     fg=Palette.TEXT, anchor="w", justify="left",
                     wraplength=theme.px(620)).pack(side="left", fill="x",
                                                    expand=True)

    # -- scope ----------------------------------------------------------

    def _scoped(self) -> list:
        """The assessments the CSV will contain, for the chosen scope."""
        if self.analysis is None:
            return []
        scope = self.csv_scope.get()
        if scope == "flagged":
            return [a for a in self.analysis.assessments if a.findings]
        if scope == "view" and self.current_view is not None:
            return list(self.current_view())
        return list(self.analysis.assessments)

    def _scoped_count(self) -> int:
        return len(self._scoped())

    def _refresh_scope_count(self) -> None:
        if hasattr(self, "scope_note"):
            self.scope_note.configure(
                text=f"{self._scoped_count():,} rows will be written")

    # -- exporting ------------------------------------------------------

    def _destination(self, default_name: str, kind: str, extension: str):
        stamp = datetime.now().strftime("%Y%m%d")
        base, suffix = os.path.splitext(default_name)
        return filedialog.asksaveasfilename(
            parent=self,
            title=f"Save {kind}",
            defaultextension=extension,
            initialfile=f"{base}_{stamp}{suffix}",
            filetypes=[(kind, f"*{extension}"), ("All files", "*.*")])

    def _run(self, action, default_name: str, kind: str,
             extension: str) -> None:
        """Ask for a destination, write, and report what happened."""
        if self.analysis is None:
            return
        path = self._destination(default_name, kind, extension)
        if not path:
            return
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            result = action(path)
        except OSError as error:
            self.configure(cursor="")
            messagebox.showerror(
                "Could not write the file",
                f"{error.strerror or error}\n\nThe file may be open in "
                "another application, or the folder may be read-only.")
            return
        except Exception as error:  # noqa: BLE001 - never fail silently
            self.configure(cursor="")
            messagebox.showerror(
                "The export failed",
                f"{type(error).__name__}: {error}\n\n"
                f"{traceback.format_exc(limit=3)}")
            return
        finally:
            self.configure(cursor="")

        self.last_result = result
        self._show_result(result)
        messagebox.showinfo(
            "Export complete",
            f"{result.kind} written.\n\n{result.name}\n{result.describe()}")

    def _show_result(self, result) -> None:
        self.status_label.configure(
            text=f"{result.kind}: {result.name}  -  {result.describe()}",
            fg=Palette.TEXT)

    def export_review_pack(self) -> None:
        self._run(lambda path: reporting.write_review_pack(
            self.analysis, path),
            review_pack.DEFAULT_FILENAME, "PDF review pack", ".pdf")

    def export_exception_register(self) -> None:
        self._run(lambda path: reporting.write_exception_register(
            self.analysis, path),
            exception_register.DEFAULT_FILENAME, "PDF exception register",
            ".pdf")

    def export_csv(self) -> None:
        scoped = self._scoped()
        self._run(lambda path: reporting.write_csv(
            self.analysis, path, scoped),
            csv_export.DEFAULT_FILENAME, "CSV export", ".csv")
