"""The work order explorer.

A dense, sortable table over the whole retained set, with the filters an
operations reviewer actually reaches for. Filtering is done by the domain's
own `Filter`, so what the table shows and what a report would contain can
never diverge.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..domain import filters as domain_filters
from ..domain.models import QUEUES, SEVERITY_ORDER, Severity, TEAMS
from .theme import Palette, Theme
from .widgets import Card, FlatButton

ANY = "All"

COLUMNS = (
    ("severity", "SEV", 54, "center"),
    ("work_order", "Work Order", 118, "w"),
    ("asset", "Asset", 92, "w"),
    ("description", "Description", 210, "w"),
    ("site", "Site", 148, "w"),
    ("team", "Team", 132, "w"),
    ("status", "Status", 96, "w"),
    ("priority", "Priority", 72, "w"),
    ("age", "Age", 50, "e"),
    ("queue", "Queue", 136, "w"),
    ("findings", "Flags", 48, "e"),
)

SEVERITY_ABBREVIATION = {
    "Critical": "CRIT",
    "Warning": "WARN",
    "Information": "INFO",
}


class WorkOrders(tk.Frame):
    """Search, filter, sort and select."""

    def __init__(self, parent, theme: Theme, on_select=None,
                 on_open_record=None) -> None:
        super().__init__(parent, bg=Palette.SURFACE)
        self.theme = theme
        self.on_select = on_select
        self.on_open_record = on_open_record
        self.analysis = None
        self.visible: list = []
        self._by_iid: dict = {}
        self._sort = ("severity", True)

        self._build()

    # -- construction ---------------------------------------------------

    def _build(self) -> None:
        theme = self.theme
        pad = theme.px(16)

        outer = tk.Frame(self, bg=Palette.SURFACE)
        outer.pack(fill="both", expand=True, padx=pad, pady=pad)

        self.filter_card = Card(outer, theme)
        self.filter_card.pack(fill="x")
        self._build_filters(self.filter_card.content())

        self.table_card = Card(outer, theme)
        self.table_card.pack(fill="both", expand=True, pady=(theme.px(12), 0))
        self._build_table(self.table_card.content(pad=False))

    def _build_filters(self, parent) -> None:
        theme = self.theme
        self.variables: dict = {}

        first = tk.Frame(parent, bg=Palette.CARD)
        first.pack(fill="x", pady=(theme.px(2), theme.px(6)))

        tk.Label(first, text="SEARCH", font=theme.tiny, bg=Palette.CARD,
                 fg=Palette.SUBTLE).pack(side="left", padx=(0, theme.px(6)))
        self.search = tk.StringVar()
        entry = tk.Entry(first, textvariable=self.search, font=theme.body,
                         relief="flat", bg=Palette.SURFACE, fg=Palette.TEXT,
                         insertbackground=Palette.TEXT,
                         width=int(34))
        entry.pack(side="left", ipady=theme.px(4), padx=(0, theme.px(14)))
        self.search.trace_add("write", lambda *_: self.apply())

        self.open_only = tk.BooleanVar(value=True)
        self.flagged_only = tk.BooleanVar(value=False)
        for text, variable in (("Open work only", self.open_only),
                               ("Flagged only", self.flagged_only)):
            tk.Checkbutton(
                first, text=text, variable=variable, font=theme.small,
                bg=Palette.CARD, fg=Palette.TEXT, activebackground=Palette.CARD,
                activeforeground=Palette.TEXT, selectcolor=Palette.CARD,
                highlightthickness=0, borderwidth=0,
                command=self.apply).pack(side="left", padx=(0, theme.px(12)))

        self.count_label = tk.Label(first, text="", font=theme.small,
                                    bg=Palette.CARD, fg=Palette.MUTED)
        self.count_label.pack(side="right")

        second = tk.Frame(parent, bg=Palette.CARD)
        second.pack(fill="x")
        for name, label in (("queue", "Queue"), ("team", "Team"),
                            ("status", "Status"), ("priority", "Priority"),
                            ("site", "Site"), ("vendor", "Vendor"),
                            ("severity", "Severity"), ("aging", "Aging")):
            self._dropdown(second, name, label)

        FlatButton(second, theme, "Reset", command=self.reset,
                   kind="quiet").pack(side="right")

    def _dropdown(self, parent, name: str, label: str) -> None:
        theme = self.theme
        holder = tk.Frame(parent, bg=Palette.CARD)
        holder.pack(side="left", padx=(0, theme.px(10)))
        tk.Label(holder, text=label.upper(), font=theme.tiny,
                 bg=Palette.CARD, fg=Palette.SUBTLE, anchor="w").pack(fill="x")
        variable = tk.StringVar(value=ANY)
        box = ttk.Combobox(holder, textvariable=variable, state="readonly",
                           style="SL.TCombobox", font=theme.small,
                           width=15, values=[ANY])
        box.pack()
        box.bind("<<ComboboxSelected>>", lambda _e: self.apply())
        self.variables[name] = (variable, box)

    def _build_table(self, parent) -> None:
        theme = self.theme
        holder = tk.Frame(parent, bg=Palette.CARD)
        holder.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            holder, style="SL.Treeview", show="headings", selectmode="browse",
            columns=[key for key, _, _, _ in COLUMNS])
        vertical = ttk.Scrollbar(holder, orient="vertical",
                                 style="SL.Vertical.TScrollbar",
                                 command=self.tree.yview)
        horizontal = ttk.Scrollbar(parent, orient="horizontal",
                                   style="SL.Horizontal.TScrollbar",
                                   command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set,
                            xscrollcommand=horizontal.set)

        for key, title, width, anchor in COLUMNS:
            self.tree.heading(key, text=title,
                              command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=theme.px(width), anchor=anchor,
                             stretch=(key == "description"),
                             minwidth=theme.px(40))

        self.tree.tag_configure("critical", background=Palette.CRITICAL_SOFT,
                                foreground=Palette.TEXT)
        self.tree.tag_configure("warning", background=Palette.WARNING_SOFT,
                                foreground=Palette.TEXT)
        self.tree.tag_configure("information", foreground=Palette.TEXT)
        self.tree.tag_configure("clear", foreground=Palette.TEXT)
        self.tree.tag_configure("stripe", background=Palette.STRIPE)

        vertical.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        horizontal.pack(fill="x")

        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self.tree.bind("<Double-1>", self._opened)
        self.tree.bind("<Return>", self._opened)

    # -- data -----------------------------------------------------------

    def refresh(self, analysis) -> None:
        self.analysis = analysis
        self._populate_dropdowns(analysis)
        self.apply()

    def _populate_dropdowns(self, analysis) -> None:
        sites = sorted({a.work_order.site for a in analysis.assessments
                        if a.work_order.site})
        vendors = sorted({a.work_order.vendor for a in analysis.assessments
                          if a.work_order.vendor})
        statuses = [label for label, _ in analysis.metrics.by_status
                    if label != "(blank)"]
        priorities = [label for label, _ in analysis.metrics.by_priority
                      if label != "(blank)"]
        bands = [label for label, _ in analysis.metrics.by_aging_band]

        options = {
            "queue": list(QUEUES),
            "team": list(TEAMS),
            "status": sorted(statuses),
            "priority": priorities,
            "site": sites,
            "vendor": vendors,
            "severity": [s.label for s in SEVERITY_ORDER],
            "aging": bands,
        }
        for name, values in options.items():
            variable, box = self.variables[name]
            box.configure(values=[ANY] + values)
            if variable.get() not in ([ANY] + values):
                variable.set(ANY)

    def _criteria(self) -> domain_filters.Filter:
        def chosen(name):
            value = self.variables[name][0].get()
            return frozenset() if value == ANY else frozenset({value})

        return domain_filters.Filter(
            search=self.search.get().strip(),
            queues=chosen("queue"),
            teams=chosen("team"),
            statuses=chosen("status"),
            priorities=chosen("priority"),
            sites=chosen("site"),
            severities=chosen("severity"),
            open_only=self.open_only.get(),
            with_findings_only=self.flagged_only.get(),
        )

    def apply(self) -> None:
        if self.analysis is None:
            return
        theme = self.theme
        rows = domain_filters.apply_filter(self.analysis.assessments,
                                           self._criteria())

        vendor = self.variables["vendor"][0].get()
        if vendor != ANY:
            rows = [a for a in rows if a.work_order.vendor == vendor]

        band = self.variables["aging"][0].get()
        if band != ANY:
            from ..domain.metrics import band_for
            rows = [a for a in rows
                    if a.work_order.is_open and band_for(a.age) == band]

        self.visible = self._sorted(rows)
        self._fill()
        total = len(self.analysis.assessments)
        self.count_label.configure(
            text=f"Showing {len(self.visible):,} of {total:,} work orders")

    def _sorted(self, rows) -> list:
        key, descending = self._sort
        blank = ""

        def sort_key(assessment):
            work_order = assessment.work_order
            if key == "severity":
                severity = assessment.severity
                return (severity.rank if severity else 9,
                        -len(assessment.findings))
            if key == "age":
                return (assessment.age if assessment.age is not None else -1,)
            if key == "findings":
                return (len(assessment.findings),)
            if key == "priority":
                return (work_order.priority.rank
                        if work_order.priority else 9,)
            return {
                "work_order": (work_order.work_order_id,),
                "asset": (work_order.asset_id,),
                "description": (work_order.description.casefold(),),
                "site": (work_order.site.casefold(),),
                "team": (assessment.team,),
                "status": (work_order.status.label
                           if work_order.status else blank,),
                "queue": (assessment.queue,),
            }.get(key, (blank,))

        # Severity and priority already rank most-urgent-first, so their
        # natural order is the descending one a reader expects.
        reverse = descending
        if key in ("severity", "priority"):
            reverse = not descending
        return sorted(rows, key=sort_key, reverse=reverse)

    def _sort_by(self, key: str) -> None:
        current, descending = self._sort
        self._sort = (key, not descending if key == current else True)
        for column, title, _, _ in COLUMNS:
            marker = ""
            if column == key:
                marker = "  v" if self._sort[1] else "  ^"
            self.tree.heading(column, text=title + marker)
        self.visible = self._sorted(self.visible)
        self._fill()

    def _fill(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._by_iid.clear()
        for index, assessment in enumerate(self.visible):
            work_order = assessment.work_order
            severity = assessment.severity
            tags = [severity.name.casefold() if severity else "clear"]
            if index % 2 and severity not in (Severity.CRITICAL,
                                              Severity.WARNING):
                tags.append("stripe")
            iid = self.tree.insert("", "end", values=(
                SEVERITY_ABBREVIATION.get(
                    severity.label if severity else "", "OK"),
                work_order.identity,
                work_order.asset_id or "-",
                work_order.description or "-",
                work_order.site or "-",
                assessment.team,
                work_order.status.label if work_order.status
                else (work_order.raw_status or "(blank)"),
                work_order.priority.label if work_order.priority else "-",
                f"{assessment.age}" if assessment.age is not None else "-",
                assessment.queue,
                len(assessment.findings) or "",
            ), tags=tags)
            self._by_iid[iid] = assessment

    # -- selection ------------------------------------------------------

    def _current(self):
        selection = self.tree.selection()
        return self._by_iid.get(selection[0]) if selection else None

    def _selected(self, _event) -> None:
        assessment = self._current()
        if assessment is not None and self.on_select is not None:
            self.on_select(assessment)

    def _opened(self, _event) -> None:
        assessment = self._current()
        if assessment is not None and self.on_open_record is not None:
            self.on_open_record(assessment)

    def reset(self) -> None:
        self.search.set("")
        self.open_only.set(True)
        self.flagged_only.set(False)
        for variable, _ in self.variables.values():
            variable.set(ANY)
        self.apply()

    def focus_queue(self, queue: str) -> None:
        """Open the explorer already filtered to one queue."""
        self.reset()
        self.variables["queue"][0].set(queue)
        self.open_only.set(False)
        self.apply()
