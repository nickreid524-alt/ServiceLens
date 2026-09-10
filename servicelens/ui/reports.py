"""Reporting.

Export is not built yet. Rather than showing buttons that look like they
work, this screen shows exactly what each report would contain, computed
live from the current analysis, and states plainly that writing the file is
still to come. The preview is real; only the export is pending.
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path

from ..domain.models import Domain, Severity
from .theme import Palette, Theme
from .widgets import Card, FlatButton, ScrollArea, divider, section_label


class Reports(tk.Frame):
    """Previews of the reports ServiceLens will be able to write."""

    def __init__(self, parent, theme: Theme) -> None:
        super().__init__(parent, bg=Palette.SURFACE)
        self.theme = theme
        self.area = ScrollArea(self, theme)
        self.area.pack(fill="both", expand=True)

    def refresh(self, analysis) -> None:
        theme = self.theme
        for child in self.area.interior.winfo_children():
            child.destroy()
        holder = tk.Frame(self.area.interior, bg=Palette.SURFACE)
        holder.pack(fill="both", expand=True, padx=theme.px(16),
                    pady=theme.px(16))

        self._notice(holder)
        self._previews(holder, analysis)

    def _notice(self, parent) -> None:
        theme = self.theme
        card = Card(parent, theme)
        card.pack(fill="x")
        body = card.content()
        tk.Label(body, text="Export is not implemented yet",
                 font=theme.subheading, bg=Palette.CARD,
                 fg=Palette.TEXT, anchor="w").pack(fill="x")
        tk.Label(
            body,
            text="Writing PDF and CSV files is the next piece of work. The "
                 "summaries below are not mock-ups - they are computed from "
                 "the workbook currently loaded, and are what each export "
                 "will contain. The controls are shown disabled rather than "
                 "hidden so the intended scope is visible.",
            font=theme.small, bg=Palette.CARD, fg=Palette.MUTED, anchor="w",
            justify="left", wraplength=theme.px(760)).pack(
            fill="x", pady=(theme.px(4), 0))

    def _previews(self, parent, analysis) -> None:
        theme = self.theme
        metrics = analysis.metrics

        by_domain = dict(metrics.domain_counts)
        integrity_total = by_domain.get(Domain.DATA_QUALITY.label, 0)
        queues = [(q, c) for q, c in metrics.by_queue
                  if q != "Routine Operations"]

        reports = (
            (
                "Review pack",
                "PDF",
                "Every flagged work order with its findings, the evidence "
                "behind each one, and the action requested.",
                (
                    (f"{metrics.with_findings:,}", "work orders included"),
                    (f"{metrics.findings_total:,}", "findings"),
                    (f"{metrics.critical:,}", "critical"),
                    (f"{len(queues)}", "queues covered"),
                ),
            ),
            (
                "Exception summary",
                "PDF",
                "One page per queue: how much work sits in it, its age "
                "profile, and the teams it belongs to.",
                (
                    (f"{sum(c for _, c in queues):,}", "records across "
                                                       "queues"),
                    (f"{metrics.warning:,}", "warnings"),
                    (f"{metrics.information:,}", "information"),
                    (f"{len(metrics.team_summaries)}", "teams"),
                ),
            ),
            (
                "Data quality report",
                "PDF",
                "Records whose own dates, status or identifiers do not agree "
                "with each other, with the worksheet row for each.",
                (
                    (f"{integrity_total:,}", "integrity findings"),
                    (f"{metrics.undated:,}", "undatable records"),
                    (f"{analysis.exclusions.total_excluded:,}",
                     "rows excluded"),
                    ("yes" if analysis.exclusions.reconciles() else "no",
                     "totals reconcile"),
                ),
            ),
            (
                "Current result set",
                "CSV",
                "Whatever the Work Orders screen is currently showing, "
                "exported for a spreadsheet.",
                (
                    (f"{metrics.total:,}", "records available"),
                    (f"{metrics.open_count:,}", "open"),
                    (f"{metrics.completed_count:,}", "completed"),
                    (f"{len(analysis.imported.schema.matched)}",
                     "columns mapped"),
                ),
            ),
        )

        grid = tk.Frame(parent, bg=Palette.SURFACE)
        grid.pack(fill="both", expand=True, pady=(theme.px(14), 0))
        grid.columnconfigure(0, weight=1, uniform="reports")
        grid.columnconfigure(1, weight=1, uniform="reports")

        for index, (title, kind, description, figures) in enumerate(reports):
            card = Card(grid, theme)
            card.grid(row=index // 2, column=index % 2, sticky="nsew",
                      padx=(0, theme.px(7)) if index % 2 == 0
                      else (theme.px(7), 0),
                      pady=(0 if index < 2 else theme.px(14), 0))
            card.heading(title, kind)
            body = card.content()

            tk.Label(body, text=description, font=theme.small,
                     bg=Palette.CARD, fg=Palette.MUTED, anchor="w",
                     justify="left", wraplength=theme.px(340)).pack(fill="x")

            figures_row = tk.Frame(body, bg=Palette.CARD)
            figures_row.pack(fill="x", pady=(theme.px(10), theme.px(6)))
            for column, (value, label) in enumerate(figures):
                cell = tk.Frame(figures_row, bg=Palette.CARD)
                cell.grid(row=0, column=column, sticky="w",
                          padx=(0, theme.px(16)))
                tk.Label(cell, text=value, font=theme.subheading,
                         bg=Palette.CARD, fg=Palette.TEXT,
                         anchor="w").pack(fill="x")
                tk.Label(cell, text=label, font=theme.tiny, bg=Palette.CARD,
                         fg=Palette.SUBTLE, anchor="w").pack(fill="x")

            divider(body, theme, 4)
            actions = tk.Frame(body, bg=Palette.CARD)
            actions.pack(fill="x")
            FlatButton(actions, theme, f"Write {kind}", enabled=False,
                       kind="quiet").pack(side="left")
            tk.Label(actions, text="not yet available", font=theme.tiny,
                     bg=Palette.CARD, fg=Palette.SUBTLE).pack(
                side="left", padx=(theme.px(8), 0))

        self._source(parent, analysis)

    def _source(self, parent, analysis) -> None:
        theme = self.theme
        card = Card(parent, theme)
        card.pack(fill="x", pady=(theme.px(14), 0))
        card.heading("What a report would be based on",
                     "provenance travels with the numbers")
        body = card.content()
        imported = analysis.imported
        source = Path(imported.source_path) if imported.source_path else None
        # The folder name and file name are the useful part of the
        # provenance; the rest of the path is the operator's own machine.
        shown = (f"...{os.sep}{source.parent.name}{os.sep}{source.name}"
                 if source else "not recorded")
        lines = (
            ("Workbook", shown),
            ("Worksheet", imported.sheet_name or "-"),
            ("Header row", str(imported.header_row)),
            ("Rows read", f"{imported.rows_read:,}"),
            ("Schema", imported.schema.summary()),
            ("Reporting date", analysis.as_of.strftime("%d %B %Y")),
            ("Exclusions", analysis.exclusions.summary()),
        )
        for label, value in lines:
            row = tk.Frame(body, bg=Palette.CARD)
            row.pack(fill="x", pady=theme.px(2))
            tk.Label(row, text=label, font=theme.small, bg=Palette.CARD,
                     fg=Palette.MUTED, width=16, anchor="w").pack(side="left")
            tk.Label(row, text=value, font=theme.small, bg=Palette.CARD,
                     fg=Palette.TEXT, anchor="w", justify="left",
                     wraplength=theme.px(640)).pack(side="left", fill="x",
                                                    expand=True)
