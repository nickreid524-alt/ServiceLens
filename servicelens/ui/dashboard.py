"""The operational overview.

Deliberately short. A dashboard that shows everything shows nothing, so this
answers six questions and then hands over to the queues:

    how much work is open, how much of it is critical, how much has aged,
    what preventive maintenance is due, what is sitting with vendors, and
    what it is all costing.
"""

from __future__ import annotations

import tkinter as tk

from ..domain.models import Severity
from .theme import Palette, Theme, queue_colour
from .widgets import (
    BarChart,
    Card,
    MetricTile,
    ScrollArea,
    SplitBar,
)


def money(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    if value >= 10_000:
        return f"${value / 1000:,.0f}k"
    return f"${value:,.0f}"


class Dashboard(tk.Frame):
    """Headline numbers, five distributions, and what to look at first."""

    def __init__(self, parent, theme: Theme, on_open_record=None) -> None:
        super().__init__(parent, bg=Palette.SURFACE)
        self.theme = theme
        self.on_open_record = on_open_record
        self.area = ScrollArea(self, theme)
        self.area.pack(fill="both", expand=True)
        self.canvas_body = self.area.interior

    def refresh(self, analysis) -> None:
        for child in self.canvas_body.winfo_children():
            child.destroy()
        theme = self.theme
        pad = theme.px(16)

        holder = tk.Frame(self.canvas_body, bg=Palette.SURFACE)
        holder.pack(fill="both", expand=True, padx=pad, pady=pad)

        self._tiles(holder, analysis)
        self._distributions(holder, analysis)
        self._attention(holder, analysis)

    # -- headline figures ----------------------------------------------

    def _tiles(self, parent, analysis) -> None:
        theme = self.theme
        metrics = analysis.metrics
        limits = analysis.policy.thresholds

        critical = sum(1 for a in analysis.assessments
                       if a.severity is Severity.CRITICAL)
        aged = sum(1 for a in analysis.assessments
                   if a.work_order.is_open and a.age is not None
                   and a.age >= limits.aging_days)
        preventive = (metrics.rule_counts.get("pm_overdue", 0)
                      + metrics.rule_counts.get("pm_due_soon", 0))
        overdue_pm = metrics.rule_counts.get("pm_overdue", 0)
        vendor = dict(metrics.by_queue).get("Vendor Follow-up", 0)
        contracted = sum(1 for a in analysis.assessments
                         if a.work_order.is_open
                         and a.team == "Contracted Services")

        row = tk.Frame(parent, bg=Palette.SURFACE)
        row.pack(fill="x")

        tiles = (
            ("Open work orders", f"{metrics.open_count:,}",
             f"of {metrics.total:,} retained", Palette.TEXT),
            ("Critical", f"{critical:,}",
             f"{critical / metrics.total:.1%} of the board"
             if metrics.total else "", Palette.CRITICAL),
            ("Aged past planning", f"{aged:,}",
             f"open {limits.aging_days}+ days", Palette.WARNING),
            ("Preventive due", f"{preventive:,}",
             f"{overdue_pm:,} already overdue", Palette.CLEAR),
            ("With vendors", f"{contracted:,}",
             f"{vendor:,} need chasing", Palette.ACCENT),
            ("Open cost", money(metrics.open_cost),
             f"{money(metrics.actual_cost)} spent to date", Palette.TEXT),
        )
        for index, (label, value, note, accent) in enumerate(tiles):
            tile = MetricTile(row, theme, label, value, note, accent,
                              compact=True)
            tile.grid(row=0, column=index, sticky="nsew",
                      padx=(0 if index == 0 else theme.px(10), 0))
            row.columnconfigure(index, weight=1, uniform="tiles")

    # -- distributions --------------------------------------------------

    def _distributions(self, parent, analysis) -> None:
        theme = self.theme
        metrics = analysis.metrics
        gap = theme.px(14)

        grid = tk.Frame(parent, bg=Palette.SURFACE)
        grid.pack(fill="both", expand=True, pady=(gap, 0))
        grid.columnconfigure(0, weight=1, uniform="cols")
        grid.columnconfigure(1, weight=1, uniform="cols")

        # Severity mix, as one proportional bar.
        severity = Card(grid, theme)
        severity.grid(row=0, column=0, sticky="nsew", padx=(0, gap // 2))
        severity.heading("Findings by severity",
                         f"{metrics.findings_total:,} raised")
        SplitBar(severity.content(), theme, [
            ("Critical", metrics.critical, Palette.CRITICAL),
            ("Warning", metrics.warning, Palette.WARNING),
            ("Information", metrics.information, Palette.INFORMATION),
        ]).pack(fill="x")

        # Exception share, so severity is read against the whole board.
        share = Card(grid, theme)
        share.grid(row=0, column=1, sticky="nsew", padx=(gap // 2, 0))
        share.heading("Board condition",
                      f"{metrics.exception_rate:.0%} carrying a finding")
        SplitBar(share.content(), theme, [
            ("Clean", metrics.clean, Palette.CLEAR),
            ("Flagged", metrics.with_findings, Palette.WARNING),
        ]).pack(fill="x")

        charts = (
            ("Routing queues", "where work is directed",
             metrics.by_queue, queue_colour, 0, 0),
            ("Aging of open work", "days since opened",
             metrics.by_aging_band, Palette.ACCENT, 0, 1),
            ("Work by team", "ownership after routing",
             metrics.by_team, Palette.ACCENT_DEEP, 1, 0),
            ("Work by priority", "as recorded in the export",
             metrics.by_priority, Palette.ACCENT, 1, 1),
        )
        board = tk.Frame(parent, bg=Palette.SURFACE)
        board.pack(fill="both", expand=True, pady=(gap, 0))
        board.columnconfigure(0, weight=1, uniform="cols")
        board.columnconfigure(1, weight=1, uniform="cols")

        for title, note, rows, colour, row_index, column in charts:
            card = Card(board, theme)
            card.grid(row=row_index, column=column, sticky="nsew",
                      padx=(0, gap // 2) if column == 0 else (gap // 2, 0),
                      pady=(0 if row_index == 0 else gap, 0))
            card.heading(title, note)
            BarChart(card.content(), theme, rows, colour=colour,
                     max_rows=8).pack(fill="both", expand=True)

    # -- what to look at first ------------------------------------------

    def _attention(self, parent, analysis) -> None:
        theme = self.theme
        card = Card(parent, theme)
        card.pack(fill="x", pady=(theme.px(14), 0))
        card.heading("Needs attention first",
                     "ranked by severity, then by how much is wrong, "
                     "then by age")
        body = card.content()

        ranked = analysis.attention(limit=6)
        if not ranked:
            tk.Label(body, text="Nothing is currently flagged.",
                     font=theme.small, bg=Palette.CARD,
                     fg=Palette.SUBTLE, anchor="w").pack(fill="x")
            return

        for assessment in ranked:
            self._attention_row(body, assessment)

    def _attention_row(self, parent, assessment) -> None:
        theme = self.theme
        work_order = assessment.work_order
        severity = assessment.severity
        colour = {
            Severity.CRITICAL: Palette.CRITICAL,
            Severity.WARNING: Palette.WARNING,
            Severity.INFORMATION: Palette.INFORMATION,
        }.get(severity, Palette.SUBTLE)

        row = tk.Frame(parent, bg=Palette.CARD, cursor="hand2")
        row.pack(fill="x", pady=theme.px(2))

        tk.Frame(row, bg=colour, width=theme.px(3)).pack(
            side="left", fill="y", padx=(0, theme.px(10)))

        left = tk.Frame(row, bg=Palette.CARD)
        left.pack(side="left", fill="x", expand=True)

        heading = tk.Frame(left, bg=Palette.CARD)
        heading.pack(fill="x")
        tk.Label(heading, text=work_order.identity, font=theme.small_bold,
                 bg=Palette.CARD, fg=Palette.TEXT).pack(side="left")
        tk.Label(heading, text=f"  {work_order.description}",
                 font=theme.small, bg=Palette.CARD, fg=Palette.MUTED,
                 anchor="w").pack(side="left", fill="x", expand=True)

        finding = assessment.findings[0]
        tk.Label(left, text=finding.message, font=theme.small,
                 bg=Palette.CARD, fg=colour, anchor="w",
                 justify="left").pack(fill="x")

        right = tk.Frame(row, bg=Palette.CARD)
        right.pack(side="right", padx=(theme.px(12), 0))
        age = f"{assessment.age}d" if assessment.age is not None else "-"
        tk.Label(right, text=assessment.queue, font=theme.small,
                 bg=Palette.CARD, fg=Palette.MUTED).pack(side="right",
                                                         padx=theme.px(10))
        tk.Label(right, text=age, font=theme.small_bold, bg=Palette.CARD,
                 fg=Palette.TEXT).pack(side="right")

        if self.on_open_record is not None:
            for widget in (row, left, heading, right):
                widget.bind("<Button-1>",
                            lambda _e, a=assessment: self.on_open_record(a))
            for widget in left.winfo_children() + heading.winfo_children():
                widget.bind("<Button-1>",
                            lambda _e, a=assessment: self.on_open_record(a))
