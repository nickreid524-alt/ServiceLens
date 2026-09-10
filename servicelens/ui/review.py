"""The intelligence and review screen.

The one place that answers "why is this flagged?" in full. For each finding
it shows three separate things, because they answer different questions:

    the **action** - what someone should now do,
    the **evidence** - the values on this record that triggered it,
    the **rule** - the general condition, and the threshold in force.

A reviewer who disagrees with a flag can therefore see whether the record is
wrong, or the policy is.
"""

from __future__ import annotations

import tkinter as tk

from ..analysis import ALL_RULES
from ..domain.models import Domain, Severity
from .theme import Palette, Theme, queue_colour, severity_colours
from .widgets import (
    Card,
    Pill,
    ScrollArea,
    divider,
    empty_note,
    field_row,
    section_label,
)

SEVERITY_ACCENT = {
    Severity.CRITICAL: Palette.CRITICAL,
    Severity.WARNING: Palette.WARNING,
    Severity.INFORMATION: Palette.INFORMATION,
}


def _date(value) -> str:
    return value.strftime("%d %b %Y") if value else "-"


def _money(value) -> str:
    return f"${value:,.2f}" if value is not None else "-"


def _threshold_label(name: str) -> str:
    return name.replace("_", " ").capitalize()


class Review(tk.Frame):
    """A ranked worklist beside a full explanation of one record."""

    def __init__(self, parent, theme: Theme) -> None:
        super().__init__(parent, bg=Palette.SURFACE)
        self.theme = theme
        self.analysis = None
        self.selected = None
        self.queue_filter = "All queues"

        pad = theme.px(16)
        outer = tk.Frame(self, bg=Palette.SURFACE)
        outer.pack(fill="both", expand=True, padx=pad, pady=pad)

        self.list_card = Card(outer, theme)
        self.list_card.pack(side="left", fill="both",
                            padx=(0, theme.px(14)))
        self.list_card.configure(width=theme.px(330))
        self.list_card.pack_propagate(False)

        self.detail_card = Card(outer, theme)
        self.detail_card.pack(side="left", fill="both", expand=True)

        self._build_list()
        self.detail_area = ScrollArea(self.detail_card.body, theme,
                                      background=Palette.CARD)
        self.detail_area.pack(fill="both", expand=True)

    # -- worklist -------------------------------------------------------

    def _build_list(self) -> None:
        theme = self.theme
        self.list_heading = self.list_card.heading("Review queue", "")
        body = self.list_card.content(pad=False)

        self.queue_bar = tk.Frame(body, bg=Palette.CARD)
        self.queue_bar.pack(fill="x", padx=theme.px(14),
                            pady=(0, theme.px(8)))

        self.list_area = ScrollArea(body, theme, background=Palette.CARD)
        self.list_area.pack(fill="both", expand=True)

    def _queue_options(self, analysis) -> list:
        counts = dict(analysis.metrics.by_queue)
        queues = [("All queues", sum(
            1 for a in analysis.assessments if a.findings))]
        queues += [(q, c) for q, c in analysis.metrics.by_queue
                   if c and q != "Routine Operations"]
        return queues

    def _fill_queue_bar(self, analysis) -> None:
        theme = self.theme
        for child in self.queue_bar.winfo_children():
            child.destroy()
        # Chips are laid out in rows that wrap, because queue names are
        # words and a single row would clip the later ones.
        available = theme.px(300)
        row = None
        used = 0
        for name, count in self._queue_options(analysis):
            text = f"{name}  {count}"
            width = theme.tiny.measure(text) + theme.px(18)
            if row is None or used + width > available:
                row = tk.Frame(self.queue_bar, bg=Palette.CARD)
                row.pack(fill="x", pady=(0, theme.px(3)))
                used = 0
            active = name == self.queue_filter
            chip = tk.Label(
                row, text=text, font=theme.tiny, cursor="hand2",
                bg=Palette.ACCENT if active else Palette.SURFACE,
                fg=Palette.ON_DARK if active else Palette.MUTED,
                padx=theme.px(7), pady=theme.px(3))
            chip.pack(side="left", padx=(0, theme.px(4)))
            chip.bind("<Button-1>",
                      lambda _e, n=name: self._choose_queue(n))
            used += width

    def _choose_queue(self, name: str) -> None:
        self.queue_filter = name
        self._fill_queue_bar(self.analysis)
        self._fill_list()

    def _worklist(self) -> list:
        ranked = self.analysis.attention()
        if self.queue_filter != "All queues":
            ranked = [a for a in ranked if a.queue == self.queue_filter]
        return ranked

    def _fill_list(self) -> None:
        theme = self.theme
        for child in self.list_area.interior.winfo_children():
            child.destroy()

        records = self._worklist()
        self.list_heading.winfo_children()[1].configure(
            text=f"{len(records):,} flagged") if len(
            self.list_heading.winfo_children()) > 1 else None

        if not records:
            tk.Label(self.list_area.interior,
                     text="No flagged work in this queue.",
                     font=theme.small, bg=Palette.CARD, fg=Palette.SUBTLE,
                     anchor="w").pack(fill="x", padx=theme.px(14),
                                      pady=theme.px(10))
            return

        for assessment in records[:250]:
            self._list_row(assessment)

        if len(records) > 250:
            tk.Label(self.list_area.interior,
                     text=f"{len(records) - 250:,} more - narrow the queue "
                          "or use the Work Orders screen.",
                     font=theme.tiny, bg=Palette.CARD, fg=Palette.SUBTLE,
                     anchor="w", wraplength=theme.px(290)).pack(
                fill="x", padx=theme.px(14), pady=theme.px(8))

    def _list_row(self, assessment) -> None:
        theme = self.theme
        selected = assessment is self.selected
        background = Palette.ACCENT_SOFT if selected else Palette.CARD
        accent = SEVERITY_ACCENT.get(assessment.severity, Palette.SUBTLE)

        row = tk.Frame(self.list_area.interior, bg=background, cursor="hand2")
        row.pack(fill="x")
        tk.Frame(row, bg=accent, width=theme.px(3)).pack(side="left", fill="y")

        inner = tk.Frame(row, bg=background)
        inner.pack(side="left", fill="x", expand=True,
                   padx=theme.px(10), pady=theme.px(6))

        top = tk.Frame(inner, bg=background)
        top.pack(fill="x")
        tk.Label(top, text=assessment.work_order.identity,
                 font=theme.small_bold, bg=background,
                 fg=Palette.TEXT).pack(side="left")
        age = (f"{assessment.age}d" if assessment.age is not None else "-")
        tk.Label(top, text=age, font=theme.tiny, bg=background,
                 fg=Palette.MUTED).pack(side="right")

        tk.Label(inner, text=assessment.work_order.description or "-",
                 font=theme.tiny, bg=background, fg=Palette.MUTED,
                 anchor="w", justify="left",
                 wraplength=theme.px(260)).pack(fill="x")
        tk.Label(inner,
                 text=f"{len(assessment.findings)} finding"
                      f"{'s' if len(assessment.findings) != 1 else ''}"
                      f"  ·  {assessment.queue}",
                 font=theme.tiny, bg=background, fg=accent,
                 anchor="w").pack(fill="x")

        tk.Frame(self.list_area.interior, bg=Palette.BORDER,
                 height=1).pack(fill="x")

        for widget in [row, inner, top] + inner.winfo_children() \
                + top.winfo_children():
            widget.bind("<Button-1>",
                        lambda _e, a=assessment: self.select(a))

    # -- detail ---------------------------------------------------------

    def refresh(self, analysis) -> None:
        self.analysis = analysis
        ranked = analysis.attention()
        if self.selected not in ranked:
            self.selected = ranked[0] if ranked else None
        self._fill_queue_bar(analysis)
        self._fill_list()
        self._fill_detail()

    def select(self, assessment) -> None:
        self.selected = assessment
        self._fill_list()
        self._fill_detail()

    def _fill_detail(self) -> None:
        theme = self.theme
        for child in self.detail_area.interior.winfo_children():
            child.destroy()
        body = tk.Frame(self.detail_area.interior, bg=Palette.CARD)
        body.pack(fill="both", expand=True, padx=theme.px(18),
                  pady=theme.px(16))

        if self.selected is None:
            tk.Label(body, text="Select a work order",
                     font=theme.heading, bg=Palette.CARD,
                     fg=Palette.TEXT, anchor="w").pack(fill="x")
            empty_note(body, theme,
                       "Nothing on this board is currently flagged, or the "
                       "chosen queue is empty. Pick another queue on the "
                       "left, or open the Work Orders screen to browse "
                       "every record.")
            return

        self._detail_header(body)
        self._detail_routing(body)
        self._detail_findings(body)
        self._detail_record(body)

    def _detail_header(self, parent) -> None:
        theme = self.theme
        assessment = self.selected
        work_order = assessment.work_order

        tk.Label(parent, text=work_order.identity, font=theme.heading,
                 bg=Palette.CARD, fg=Palette.TEXT, anchor="w").pack(fill="x")
        tk.Label(parent, text=work_order.description or "No description "
                                                        "recorded",
                 font=theme.body, bg=Palette.CARD, fg=Palette.MUTED,
                 anchor="w", justify="left",
                 wraplength=theme.px(620)).pack(fill="x",
                                                pady=(theme.px(2), 0))

        chips = tk.Frame(parent, bg=Palette.CARD)
        chips.pack(fill="x", pady=(theme.px(10), 0))

        severity = assessment.severity
        if severity is not None:
            foreground, background = severity_colours(severity.label)
            Pill(chips, theme, severity.label.upper(), foreground,
                 background).pack(side="left", padx=(0, theme.px(6)))
        else:
            Pill(chips, theme, "NO FINDINGS", Palette.CLEAR,
                 Palette.CLEAR_SOFT).pack(side="left", padx=(0, theme.px(6)))

        Pill(chips, theme, assessment.queue, Palette.ON_DARK,
             queue_colour(assessment.queue)).pack(side="left",
                                                  padx=(0, theme.px(6)))
        if work_order.priority:
            Pill(chips, theme, work_order.priority.label).pack(
                side="left", padx=(0, theme.px(6)))
        status = (work_order.status.label if work_order.status
                  else work_order.raw_status or "No status")
        Pill(chips, theme, status).pack(side="left", padx=(0, theme.px(6)))
        if assessment.age is not None:
            Pill(chips, theme, f"{assessment.age} days open").pack(
                side="left")

    def _detail_routing(self, parent) -> None:
        theme = self.theme
        assessment = self.selected
        divider(parent, theme, 12)
        section_label(parent, theme, "Routing")
        field_row(parent, theme, "Owning team", assessment.team,
                  wrap=theme.px(560))
        field_row(parent, theme, "Why this team", assessment.routing_reason,
                  Palette.MUTED, wrap=theme.px(560))
        field_row(parent, theme, "Action queue", assessment.queue,
                  queue_colour(assessment.queue), wrap=theme.px(560))

    def _detail_findings(self, parent) -> None:
        theme = self.theme
        assessment = self.selected
        divider(parent, theme, 12)

        operational = [f for f in assessment.findings
                       if f.domain is not Domain.DATA_QUALITY]
        integrity = [f for f in assessment.findings
                     if f.domain is Domain.DATA_QUALITY]

        section_label(parent, theme,
                      f"Recommended actions ({len(operational)})")
        if operational:
            for finding in operational:
                self._finding_block(parent, finding)
        else:
            empty_note(parent, theme,
                       "No operational rule applies to this work order.")

        section_label(parent, theme,
                      f"Record integrity ({len(integrity)})")
        if integrity:
            for finding in integrity:
                self._finding_block(parent, finding)
        else:
            empty_note(parent, theme,
                       "The record is internally consistent: its dates, "
                       "status and identifiers agree with each other.")

    def _finding_block(self, parent, finding) -> None:
        theme = self.theme
        accent = SEVERITY_ACCENT.get(finding.severity, Palette.SUBTLE)
        _, soft = severity_colours(finding.severity.label)

        block = tk.Frame(parent, bg=Palette.BORDER)
        block.pack(fill="x", pady=theme.px(4))
        inner = tk.Frame(block, bg=Palette.CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        strip = tk.Frame(inner, bg=Palette.CARD)
        strip.pack(fill="x")
        tk.Frame(strip, bg=accent, width=theme.px(3)).pack(side="left",
                                                           fill="y")
        content = tk.Frame(strip, bg=Palette.CARD)
        content.pack(side="left", fill="x", expand=True,
                     padx=theme.px(12), pady=theme.px(10))

        title_row = tk.Frame(content, bg=Palette.CARD)
        title_row.pack(fill="x")
        tk.Label(title_row, text=finding.title, font=theme.body_bold,
                 bg=Palette.CARD, fg=Palette.TEXT).pack(side="left")
        Pill(title_row, theme, finding.severity.label.upper(), accent,
             soft).pack(side="right")
        tk.Label(title_row, text=finding.domain.label, font=theme.tiny,
                 bg=Palette.CARD, fg=Palette.SUBTLE).pack(
            side="right", padx=(0, theme.px(8)))

        tk.Label(content, text=finding.message, font=theme.small,
                 bg=Palette.CARD, fg=Palette.TEXT, anchor="w",
                 justify="left", wraplength=theme.px(560)).pack(
            fill="x", pady=(theme.px(4), 0))

        self._evidence(content, "Evidence", finding.basis)

        rule = ALL_RULES.by_key(finding.key)
        if rule is not None:
            self._evidence(content, "Rule", rule.explanation)
            if rule.limits:
                thresholds = self.analysis.policy.thresholds
                text = "   ".join(
                    f"{_threshold_label(name)}: "
                    f"{getattr(thresholds, name)}"
                    for name in rule.limits if hasattr(thresholds, name))
                self._evidence(content, "In force", text)
            if rule.reads:
                self._evidence(content, "Reads", ", ".join(rule.reads))

    def _evidence(self, parent, label: str, text: str) -> None:
        theme = self.theme
        row = tk.Frame(parent, bg=Palette.CARD)
        row.pack(fill="x", pady=(theme.px(3), 0))
        tk.Label(row, text=label.upper(), font=theme.tiny, bg=Palette.CARD,
                 fg=Palette.SUBTLE, anchor="nw", width=9).pack(side="left",
                                                               anchor="n")
        tk.Label(row, text=text, font=theme.tiny, bg=Palette.CARD,
                 fg=Palette.MUTED, anchor="w", justify="left",
                 wraplength=theme.px(500)).pack(side="left", fill="x",
                                                expand=True)

    def _detail_record(self, parent) -> None:
        theme = self.theme
        work_order = self.selected.work_order
        divider(parent, theme, 12)

        columns = tk.Frame(parent, bg=Palette.CARD)
        columns.pack(fill="x")
        left = tk.Frame(columns, bg=Palette.CARD)
        left.pack(side="left", fill="both", expand=True,
                  padx=(0, theme.px(12)))
        right = tk.Frame(columns, bg=Palette.CARD)
        right.pack(side="left", fill="both", expand=True)

        section_label(left, theme, "Asset and place")
        for label, value in (
                ("Asset", work_order.asset_id),
                ("Asset name", work_order.asset_name),
                ("Category", work_order.asset_category.label
                 if work_order.asset_category else ""),
                ("Site", work_order.site),
                ("Department", work_order.department),
                ("Meter reading",
                 f"{work_order.meter_reading:,.0f}"
                 if work_order.meter_reading is not None else "")):
            field_row(left, theme, label, value, wrap=theme.px(230))

        section_label(left, theme, "Assignment")
        for label, value in (
                ("Type", work_order.assignment_type.label
                 if work_order.assignment_type else ""),
                ("Reported team", work_order.assigned_team),
                ("Technician", work_order.assigned_technician),
                ("Vendor", work_order.vendor),
                ("Work type", work_order.work_type.label
                 if work_order.work_type else "")):
            field_row(left, theme, label, value, wrap=theme.px(230))

        section_label(right, theme, "Dates")
        for label, value in (
                ("Requested", _date(work_order.requested_date)),
                ("Opened", _date(work_order.opened_date)),
                ("Scheduled", _date(work_order.scheduled_date)),
                ("Due", _date(work_order.due_date)),
                ("Completed", _date(work_order.completed_date)),
                ("Last update", _date(work_order.last_update_date))):
            field_row(right, theme, label, value, wrap=theme.px(230))

        section_label(right, theme, "Cost")
        field_row(right, theme, "Estimated", _money(work_order.estimated_cost),
                  wrap=theme.px(230))
        field_row(right, theme, "Actual", _money(work_order.actual_cost),
                  wrap=theme.px(230))

        section_label(right, theme, "Source")
        field_row(right, theme, "Worksheet row", str(work_order.row_number),
                  wrap=theme.px(230))
        field_row(right, theme, "Reported as of",
                  _date(self.analysis.as_of), wrap=theme.px(230))

        section_label(parent, theme, "Last note")
        tk.Label(parent, text=work_order.last_note or "No note recorded.",
                 font=theme.small, bg=Palette.CARD,
                 fg=Palette.TEXT if work_order.last_note else Palette.SUBTLE,
                 anchor="w", justify="left",
                 wraplength=theme.px(620)).pack(fill="x")
