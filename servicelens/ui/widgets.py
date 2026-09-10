"""Reusable interface pieces.

Everything here is plain tkinter drawn against `Theme`. Charts are Canvas
work rather than a plotting library, which keeps the dependency list empty
and keeps full control over how a bar reads at three different scalings.
"""

from __future__ import annotations

import tkinter as tk

from .theme import Palette, Theme


class Card(tk.Frame):
    """A white panel with a hairline border - the basic content container."""

    def __init__(self, parent, theme: Theme, **kwargs) -> None:
        super().__init__(parent, bg=Palette.BORDER, **kwargs)
        self.theme = theme
        self.body = tk.Frame(self, bg=Palette.CARD)
        self.body.pack(fill="both", expand=True, padx=1, pady=1)

    def heading(self, title: str, note: str = "") -> tk.Frame:
        """A title row inside the card. Returns the row for extra controls."""
        pad = self.theme.px(14)
        row = tk.Frame(self.body, bg=Palette.CARD)
        row.pack(fill="x", padx=pad, pady=(pad, self.theme.px(4)))
        tk.Label(row, text=title, font=self.theme.subheading,
                 bg=Palette.CARD, fg=Palette.TEXT).pack(side="left")
        if note:
            tk.Label(row, text=note, font=self.theme.small,
                     bg=Palette.CARD, fg=Palette.MUTED).pack(
                side="left", padx=(self.theme.px(8), 0))
        return row

    def content(self, pad: bool = True) -> tk.Frame:
        """The area beneath the heading that callers fill."""
        inset = self.theme.px(14) if pad else 0
        frame = tk.Frame(self.body, bg=Palette.CARD)
        frame.pack(fill="both", expand=True, padx=inset,
                   pady=(0, inset if pad else 0))
        return frame


class Pill(tk.Label):
    """A compact status chip."""

    def __init__(self, parent, theme: Theme, text: str,
                 foreground: str = Palette.MUTED,
                 background: str = Palette.SURFACE, **kwargs) -> None:
        super().__init__(
            parent, text=text, font=theme.small_bold,
            bg=background, fg=foreground,
            padx=theme.px(8), pady=theme.px(3), **kwargs)


class MetricTile(Card):
    """One headline number with a label and an optional qualifier."""

    def __init__(self, parent, theme: Theme, label: str, value: str,
                 note: str = "", accent: str = Palette.TEXT,
                 compact: bool = False) -> None:
        super().__init__(parent, theme)
        pad = theme.px(12 if compact else 14)
        holder = tk.Frame(self.body, bg=Palette.CARD)
        holder.pack(fill="both", expand=True, padx=pad, pady=pad)

        tk.Label(holder, text=label.upper(), font=theme.tiny,
                 bg=Palette.CARD, fg=Palette.SUBTLE,
                 anchor="w").pack(fill="x")
        tk.Label(holder, text=value,
                 font=theme.figure_small if compact else theme.figure,
                 bg=Palette.CARD, fg=accent, anchor="w").pack(
            fill="x", pady=(theme.px(2), 0))
        if note:
            tk.Label(holder, text=note, font=theme.small, bg=Palette.CARD,
                     fg=Palette.MUTED, anchor="w").pack(fill="x")


class BarChart(tk.Canvas):
    """A horizontal bar chart: label, bar, value.

    Horizontal because category names in maintenance data are words, not
    codes, and a vertical chart would either truncate them or turn them on
    their side.
    """

    def __init__(self, parent, theme: Theme, rows=(), colour=Palette.ACCENT,
                 max_rows: int = 8, show_zero: bool = True) -> None:
        self.theme = theme
        self.rows = list(rows)
        self.colour = colour
        self.max_rows = max_rows
        self.show_zero = show_zero
        height = theme.px(26) * min(max_rows, max(1, len(self.rows)))
        super().__init__(parent, bg=Palette.CARD, highlightthickness=0,
                         height=height)
        self.bind("<Configure>", lambda _event: self._draw())

    def set_rows(self, rows) -> None:
        self.rows = list(rows)
        self.configure(height=self.theme.px(26)
                       * min(self.max_rows, max(1, len(self.rows))))
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        theme = self.theme
        rows = [r for r in self.rows if self.show_zero or r[1]][:self.max_rows]
        if not rows:
            self.create_text(theme.px(4), theme.px(10), anchor="w",
                             text="Nothing to show", font=theme.small,
                             fill=Palette.SUBTLE)
            return

        width = max(self.winfo_width(), theme.px(240))
        label_width = theme.px(140)
        value_width = theme.px(46)
        track_left = label_width + theme.px(8)
        track_right = width - value_width
        track = max(track_right - track_left, theme.px(20))
        largest = max((count for _, count in rows), default=0) or 1
        step = theme.px(26)
        bar_height = theme.px(11)

        for index, (label, count) in enumerate(rows):
            middle = index * step + step / 2
            self.create_text(
                0, middle, anchor="w", font=theme.small, fill=Palette.TEXT,
                text=self._fit(str(label), label_width - theme.px(6)))
            self.create_rectangle(
                track_left, middle - bar_height / 2,
                track_left + track, middle + bar_height / 2,
                fill=Palette.SURFACE, outline="")
            filled = track * (count / largest)
            if count:
                colour = (self.colour(label) if callable(self.colour)
                          else self.colour)
                self.create_rectangle(
                    track_left, middle - bar_height / 2,
                    track_left + max(filled, theme.px(2)),
                    middle + bar_height / 2, fill=colour, outline="")
            self.create_text(width, middle, anchor="e", font=theme.small_bold,
                             fill=Palette.TEXT, text=f"{count:,}")

    def _fit(self, text: str, limit: int) -> str:
        font = self.theme.small
        if font.measure(text) <= limit:
            return text
        while text and font.measure(text + "...") > limit:
            text = text[:-1]
        return text + "..."


class SplitBar(tk.Canvas):
    """A single stacked bar with a legend beneath it.

    Used where the parts sum to a meaningful whole - severity mix, open
    against completed - and the proportion matters more than the values.
    """

    def __init__(self, parent, theme: Theme, segments=()) -> None:
        self.theme = theme
        self.segments = list(segments)
        super().__init__(parent, bg=Palette.CARD, highlightthickness=0,
                         height=theme.px(58))
        self.bind("<Configure>", lambda _event: self._draw())

    def set_segments(self, segments) -> None:
        self.segments = list(segments)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        theme = self.theme
        width = max(self.winfo_width(), theme.px(200))
        total = sum(value for _, value, _ in self.segments)
        top, height = theme.px(4), theme.px(16)

        if not total:
            self.create_rectangle(0, top, width, top + height,
                                  fill=Palette.SURFACE, outline="")
            self.create_text(0, top + height + theme.px(16), anchor="w",
                             text="Nothing recorded", font=theme.small,
                             fill=Palette.SUBTLE)
            return

        offset = 0.0
        for _, value, colour in self.segments:
            if not value:
                continue
            span = width * (value / total)
            self.create_rectangle(offset, top, offset + span, top + height,
                                  fill=colour, outline="")
            offset += span

        legend_y = top + height + theme.px(17)
        cursor = 0
        for label, value, colour in self.segments:
            box = theme.px(9)
            self.create_rectangle(cursor, legend_y - box / 2,
                                  cursor + box, legend_y + box / 2,
                                  fill=colour, outline="")
            text = f"{label} {value:,}"
            self.create_text(cursor + box + theme.px(5), legend_y, anchor="w",
                             text=text, font=theme.small, fill=Palette.MUTED)
            cursor += box + theme.px(9) + theme.small.measure(text) \
                + theme.px(14)


class ScrollArea(tk.Frame):
    """A vertically scrolling container with a mouse wheel bound to it."""

    def __init__(self, parent, theme: Theme,
                 background: str = Palette.SURFACE) -> None:
        super().__init__(parent, bg=background)
        self.theme = theme
        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical",
                                      command=self.canvas.yview,
                                      bg=background, troughcolor=background,
                                      activebackground=Palette.BORDER_STRONG,
                                      relief="flat", borderwidth=0,
                                      width=theme.px(12))
        self.interior = tk.Frame(self.canvas, bg=background)
        self._window = self.canvas.create_window(
            (0, 0), window=self.interior, anchor="nw")

        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.interior.bind("<Configure>", self._on_interior)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.bind_all_wheel()

    def _on_scroll(self, first, last) -> None:
        # Hide the scrollbar when everything already fits.
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scrollbar.pack_forget()
        else:
            self.scrollbar.pack(side="right", fill="y")
        self.scrollbar.set(first, last)

    def _on_interior(self, _event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def bind_all_wheel(self) -> None:
        for widget in (self.canvas, self.interior):
            widget.bind("<Enter>", lambda _e: self._wheel(True))
            widget.bind("<Leave>", lambda _e: self._wheel(False))

    def _wheel(self, active: bool) -> None:
        if active:
            self.canvas.bind_all("<MouseWheel>", self._scroll)
        else:
            self.canvas.unbind_all("<MouseWheel>")

    def _scroll(self, event) -> None:
        if self.canvas.bbox("all") is None:
            return
        first, last = self.canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


class FlatButton(tk.Label):
    """A button drawn as a label, so its colours are fully controlled."""

    def __init__(self, parent, theme: Theme, text: str, command=None,
                 kind: str = "primary", enabled: bool = True,
                 **kwargs) -> None:
        self.theme = theme
        self.command = command
        self.kind = kind
        self.enabled = enabled
        super().__init__(
            parent, text=text, font=theme.small_bold,
            padx=theme.px(14), pady=theme.px(7), **kwargs)
        self._paint()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _e: self._paint(hover=True))
        self.bind("<Leave>", lambda _e: self._paint())

    def _colours(self, hover: bool) -> tuple:
        if not self.enabled:
            return Palette.SUBTLE, Palette.SURFACE
        if self.kind == "primary":
            return (Palette.ON_DARK,
                    Palette.ACCENT_DEEP if hover else Palette.ACCENT)
        if self.kind == "ghost":
            return (Palette.ACCENT,
                    Palette.ACCENT_SOFT if hover else Palette.CARD)
        if self.kind == "rail":
            return (Palette.ON_DARK,
                    Palette.INK_ACTIVE if hover else Palette.INK_HOVER)
        return (Palette.TEXT,
                Palette.BORDER if hover else Palette.SURFACE)

    def _paint(self, hover: bool = False) -> None:
        foreground, background = self._colours(hover)
        self.configure(fg=foreground, bg=background,
                       cursor="hand2" if self.enabled else "arrow")

    def _click(self, _event) -> None:
        if self.enabled and self.command is not None:
            self.command()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self._paint()


class NavItem(tk.Frame):
    """One entry in the navigation rail."""

    def __init__(self, parent, theme: Theme, text: str, command) -> None:
        super().__init__(parent, bg=Palette.INK)
        self.theme = theme
        self.command = command
        self.active = False

        self.marker = tk.Frame(self, bg=Palette.INK, width=theme.px(3))
        self.marker.pack(side="left", fill="y")
        self.label = tk.Label(
            self, text=text, font=theme.body, bg=Palette.INK,
            fg=Palette.INK_TEXT, anchor="w",
            padx=theme.px(14), pady=theme.px(9))
        self.label.pack(side="left", fill="both", expand=True)

        for widget in (self, self.label):
            widget.bind("<Button-1>", lambda _e: self.command())
            widget.bind("<Enter>", lambda _e: self._paint(hover=True))
            widget.bind("<Leave>", lambda _e: self._paint())
        self.label.configure(cursor="hand2")

    def set_active(self, active: bool) -> None:
        self.active = active
        self._paint()

    def _paint(self, hover: bool = False) -> None:
        if self.active:
            background, foreground = Palette.INK_ACTIVE, Palette.ON_DARK
            marker = Palette.ACCENT
        elif hover:
            background, foreground = Palette.INK_HOVER, Palette.ON_DARK
            marker = Palette.INK_HOVER
        else:
            background, foreground = Palette.INK, Palette.INK_TEXT
            marker = Palette.INK
        self.configure(bg=background)
        self.label.configure(bg=background, fg=foreground)
        self.marker.configure(bg=marker)


def field_row(parent, theme: Theme, label: str, value: str,
              value_colour: str = Palette.TEXT, wrap: int = 0) -> tk.Frame:
    """A label-and-value line, used throughout the detail panels."""
    row = tk.Frame(parent, bg=Palette.CARD)
    row.pack(fill="x", pady=theme.px(3))
    tk.Label(row, text=label, font=theme.small, bg=Palette.CARD,
             fg=Palette.MUTED, anchor="w",
             width=18).pack(side="left", anchor="n")
    tk.Label(row, text=value or "-", font=theme.small_bold, bg=Palette.CARD,
             fg=value_colour, anchor="w", justify="left",
             wraplength=wrap or theme.px(320)).pack(side="left", fill="x",
                                                    expand=True)
    return row


def divider(parent, theme: Theme, pad: int = 8) -> tk.Frame:
    line = tk.Frame(parent, bg=Palette.BORDER, height=1)
    line.pack(fill="x", pady=theme.px(pad))
    return line


def section_label(parent, theme: Theme, text: str) -> tk.Label:
    label = tk.Label(parent, text=text.upper(), font=theme.tiny,
                     bg=Palette.CARD, fg=Palette.SUBTLE, anchor="w")
    label.pack(fill="x", pady=(theme.px(10), theme.px(4)))
    return label


def empty_note(parent, theme: Theme, text: str) -> tk.Label:
    label = tk.Label(parent, text=text, font=theme.small, bg=Palette.CARD,
                     fg=Palette.SUBTLE, anchor="w", justify="left",
                     wraplength=theme.px(420))
    label.pack(fill="x", pady=theme.px(6))
    return label
