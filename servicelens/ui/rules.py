"""The rule catalogue.

Rendered entirely from the live `Rule` objects and the policy in force. There
is no second description of the rules anywhere in the interface, so this
screen and the engine cannot disagree. Change a threshold in
`config.py` and this screen reports the new value on the next launch.
"""

from __future__ import annotations

import tkinter as tk

from ..analysis import ALL_RULES
from ..domain import directives, integrity
from .theme import Palette, Theme, severity_colours
from .widgets import Card, ScrollArea, divider


ABBREVIATIONS = {"pm": "PM"}


def threshold_label(name: str) -> str:
    """A policy field name as a phrase: `stale_days` -> `Stale days`."""
    words = name.split("_")
    first = ABBREVIATIONS.get(words[0], words[0].capitalize())
    rest = [ABBREVIATIONS.get(word, word) for word in words[1:]]
    return " ".join([first] + rest)


def threshold_value(value) -> str:
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{value:,.0f}" if isinstance(value, (int, float)) else str(value)


class Rules(tk.Frame):
    """Every rule, what fires it, and the limits currently in force."""

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

        self._policy(holder, analysis)
        counts = analysis.metrics.rule_counts
        self._section(holder, "Operational rules",
                      "Work that needs someone to act.",
                      directives.DIRECTIVE_RULES, analysis, counts)
        self._section(holder, "Record integrity rules",
                      "Whether the record is consistent enough to act on.",
                      integrity.INTEGRITY_RULES, analysis, counts)
        self._pipeline(holder, analysis)

    # -- policy ---------------------------------------------------------

    def _policy(self, parent, analysis) -> None:
        theme = self.theme
        card = Card(parent, theme)
        card.pack(fill="x")
        card.heading(
            "Operating policy",
            f"{len(ALL_RULES)} rules, every threshold from one place")
        body = card.content()

        tk.Label(
            body,
            text="Rules hold no numbers of their own. Every limit below is "
                 "read from the policy at evaluation time, and this screen "
                 "reads the same objects the engine does - so what is shown "
                 "here is what is being applied.",
            font=theme.small, bg=Palette.CARD, fg=Palette.MUTED, anchor="w",
            justify="left", wraplength=theme.px(760)).pack(fill="x")

        thresholds = analysis.policy.thresholds
        grid = tk.Frame(body, bg=Palette.CARD)
        grid.pack(fill="x", pady=(theme.px(10), 0))
        fields = [name for name in vars(type(thresholds)).get(
            "__dataclass_fields__", {})]
        if not fields:  # dataclass fields live on the instance's class
            fields = list(thresholds.__dataclass_fields__)

        for index, name in enumerate(fields):
            cell = tk.Frame(grid, bg=Palette.CARD)
            cell.grid(row=index // 4, column=index % 4, sticky="w",
                      padx=(0, theme.px(22)), pady=theme.px(3))
            tk.Label(cell, text=threshold_value(getattr(thresholds, name)),
                     font=theme.subheading, bg=Palette.CARD, fg=Palette.TEXT,
                     anchor="w").pack(fill="x")
            tk.Label(cell, text=threshold_label(name), font=theme.tiny,
                     bg=Palette.CARD, fg=Palette.SUBTLE,
                     anchor="w").pack(fill="x")

    # -- rules ----------------------------------------------------------

    def _section(self, parent, title: str, note: str, rule_set,
                 analysis, counts) -> None:
        theme = self.theme
        card = Card(parent, theme)
        card.pack(fill="x", pady=(theme.px(14), 0))
        card.heading(title, note)
        body = card.content()

        header = tk.Frame(body, bg=Palette.CARD)
        header.pack(fill="x")
        for text, width in (("RULE", 26), ("DOMAIN", 15), ("SEVERITY", 12),
                            ("IN FORCE", 26), ("FIRED", 8)):
            tk.Label(header, text=text, font=theme.tiny, bg=Palette.CARD,
                     fg=Palette.SUBTLE, width=width,
                     anchor="w").pack(side="left")
        divider(body, theme, 3)

        thresholds = analysis.policy.thresholds
        for rule in rule_set:
            self._rule_row(body, rule, thresholds, counts.get(rule.key, 0))

    def _rule_row(self, parent, rule, thresholds, fired: int) -> None:
        theme = self.theme
        foreground, background = severity_colours(rule.severity.label)

        row = tk.Frame(parent, bg=Palette.CARD)
        row.pack(fill="x", pady=theme.px(4))

        top = tk.Frame(row, bg=Palette.CARD)
        top.pack(fill="x")

        tk.Label(top, text=rule.title, font=theme.small_bold,
                 bg=Palette.CARD, fg=Palette.TEXT, width=26,
                 anchor="w").pack(side="left")
        tk.Label(top, text=rule.domain.label, font=theme.small,
                 bg=Palette.CARD, fg=Palette.MUTED, width=15,
                 anchor="w").pack(side="left")

        tk.Label(top, text=rule.severity.label.upper(), font=theme.tiny,
                 bg=background, fg=foreground, width=12,
                 padx=theme.px(6), pady=theme.px(2)).pack(
            side="left", padx=(0, theme.px(10)))

        limits = [name for name in rule.limits if hasattr(thresholds, name)]
        text = "   ".join(
            f"{threshold_label(name)} {threshold_value(getattr(thresholds, name))}"
            for name in limits) or "no threshold"
        tk.Label(top, text=text, font=theme.small, bg=Palette.CARD,
                 fg=Palette.TEXT if limits else Palette.SUBTLE, width=30,
                 anchor="w").pack(side="left")

        tk.Label(top, text=f"{fired:,}" if fired else "-",
                 font=theme.small_bold, bg=Palette.CARD,
                 fg=Palette.TEXT if fired else Palette.SUBTLE, width=8,
                 anchor="w").pack(side="left")

        tk.Label(row, text=rule.explanation, font=theme.tiny,
                 bg=Palette.CARD, fg=Palette.MUTED, anchor="w",
                 justify="left", wraplength=theme.px(700)).pack(
            fill="x", pady=(theme.px(1), 0))
        tk.Label(row, text="Reads: " + ", ".join(rule.reads),
                 font=theme.tiny, bg=Palette.CARD, fg=Palette.SUBTLE,
                 anchor="w", justify="left",
                 wraplength=theme.px(700)).pack(fill="x")

    # -- pipeline -------------------------------------------------------

    def _pipeline(self, parent, analysis) -> None:
        theme = self.theme
        card = Card(parent, theme)
        card.pack(fill="x", pady=(theme.px(14), 0))
        card.heading("Processing order",
                     "every workbook runs through these stages, in order")
        body = card.content()

        stages = (
            ("1. Read",
             "Opened through the standard library, for reading only. No code "
             "path in ServiceLens writes to a source file."),
            ("2. Map columns",
             "Headers are matched to the canonical schema through an alias "
             "layer, so different export formats reach the same fields. "
             f"This import: {analysis.imported.schema.summary()}."),
            ("3. Normalize",
             "Dates, money and vocabularies are parsed. A value that cannot "
             "be read becomes empty and is reported, never guessed."),
            ("4. Exclude",
             "Configured exclusions are applied and counted, so rows read "
             "always equal rows excluded plus rows retained. "
             f"This import: {analysis.exclusions.summary()}."),
            ("5. Evaluate",
             f"All {len(ALL_RULES)} rules run against every retained record. "
             "Nothing is suppressed by age or by severity."),
            ("6. Route",
             "Ownership follows the record; the action queue follows the "
             "findings. A critical finding outranks every other queue."),
            ("7. Measure",
             "Totals, distributions and rankings are computed once from the "
             "assessed records."),
        )
        for label, text in stages:
            row = tk.Frame(body, bg=Palette.CARD)
            row.pack(fill="x", pady=theme.px(3))
            tk.Label(row, text=label, font=theme.small_bold, bg=Palette.CARD,
                     fg=Palette.TEXT, width=16, anchor="nw").pack(
                side="left", anchor="n")
            tk.Label(row, text=text, font=theme.small, bg=Palette.CARD,
                     fg=Palette.MUTED, anchor="w", justify="left",
                     wraplength=theme.px(660)).pack(side="left", fill="x",
                                                    expand=True)
