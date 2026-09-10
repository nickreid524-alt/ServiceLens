"""Writing PDF files with nothing but the standard library.

A PDF is a set of numbered objects, a cross-reference table giving the byte
offset of each, and a trailer pointing at the root. None of that needs a
library - it needs `zlib` for stream compression and careful bookkeeping of
offsets.

Two layers live here:

* `Document` and `Page` - the file format. Objects, streams, the xref table,
  text and rectangle operators.
* `Layout` - the part that makes a report readable. It works top-down in
  millimetre-ish points from the top of the page, breaks pages when a block
  will not fit, and repeats the running header and footer.

Text is measured with the Helvetica width tables below, so wrapping and
truncation are correct rather than guessed at.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field

# --- page geometry ---------------------------------------------------
# PDF units are points: 72 to the inch.
A4 = (595.28, 841.89)
LETTER = (612.0, 792.0)

MARGIN = 46.0

# --- colour ----------------------------------------------------------
# Print values, deliberately not the screen palette: the very light screen
# tints disappear on paper, and pure black text prints heavier than it looks.
INK = (0.09, 0.13, 0.18)
MUTED = (0.42, 0.48, 0.55)
SUBTLE = (0.60, 0.65, 0.71)
LINE = (0.82, 0.86, 0.90)
BAND = (0.95, 0.96, 0.97)
ACCENT = (0.17, 0.43, 0.61)
CRITICAL = (0.66, 0.19, 0.15)
WARNING = (0.64, 0.44, 0.08)
INFORMATION = (0.24, 0.45, 0.62)
CLEAR = (0.18, 0.47, 0.34)
WHITE = (1.0, 1.0, 1.0)

SEVERITY_COLOUR = {
    "Critical": CRITICAL,
    "Warning": WARNING,
    "Information": INFORMATION,
}

# --- font metrics ----------------------------------------------------
# Adobe's published widths for the base-14 Helvetica faces, in 1/1000 em.
# Needed so text can be measured without asking a font engine.
_HELVETICA = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333,
    278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278,
    584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
    500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
    667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556,
    278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
    278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)
_HELVETICA_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333,
    278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333,
    584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278,
    556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
    667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556,
    333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556,
    333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
)
_FALLBACK_WIDTH = 556


def text_width(text: str, size: float, bold: bool = False) -> float:
    """Width of `text` at `size` points."""
    widths = _HELVETICA_BOLD if bold else _HELVETICA
    total = 0
    for character in str(text):
        index = ord(character) - 32
        total += widths[index] if 0 <= index < len(widths) else _FALLBACK_WIDTH
    return total * size / 1000.0


def truncate(text: str, size: float, limit: float,
             bold: bool = False) -> str:
    """`text` shortened with an ellipsis until it fits `limit` points."""
    text = str(text)
    if text_width(text, size, bold) <= limit:
        return text
    while text and text_width(text + "...", size, bold) > limit:
        text = text[:-1]
    return text.rstrip() + "..." if text else ""


def wrap(text: str, size: float, limit: float, bold: bool = False) -> list:
    """`text` broken into lines that each fit `limit` points."""
    words = str(text).split()
    if not words:
        return []
    lines, current = [], words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_width(candidate, size, bold) <= limit:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    # A single word longer than the line still has to be broken somewhere.
    broken = []
    for line in lines:
        while text_width(line, size, bold) > limit and len(line) > 1:
            cut = len(line) - 1
            while cut > 1 and text_width(line[:cut], size, bold) > limit:
                cut -= 1
            broken.append(line[:cut])
            line = line[cut:]
        broken.append(line)
    return broken


def escape(text: str) -> bytes:
    """Encode a string for a PDF literal string object.

    PDF literal strings are delimited by parentheses, so those and the escape
    character itself must be escaped. Text is encoded as WinAnsi, which is
    what the font resource declares.
    """
    encoded = str(text).encode("cp1252", "replace")
    out = bytearray()
    for byte in encoded:
        if byte in (0x28, 0x29, 0x5C):        # ( ) \
            out.append(0x5C)
        out.append(byte)
    return bytes(out)


class Page:
    """One page and the drawing operators recorded on it.

    Coordinates here are PDF-native: the origin is the bottom-left corner and
    y increases upwards. `Layout` converts from top-down measurements.
    """

    def __init__(self, width: float = A4[0], height: float = A4[1]) -> None:
        self.width = width
        self.height = height
        self._operators: list = []

    def text(self, x: float, y: float, value: str, size: float = 9.0,
             bold: bool = False, colour=INK) -> None:
        if value is None or str(value) == "":
            return
        red, green, blue = colour
        font = "/F2" if bold else "/F1"
        self._operators.append(
            b"BT " + f"{red:.3f} {green:.3f} {blue:.3f} rg ".encode()
            + f"{font} {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ".encode()
            + b"(" + escape(value) + b") Tj ET")

    def text_right(self, right: float, y: float, value: str,
                   size: float = 9.0, bold: bool = False, colour=INK) -> None:
        self.text(right - text_width(value, size, bold), y, value, size,
                  bold, colour)

    def rect(self, x: float, y: float, width: float, height: float,
             fill=None, stroke=None, line_width: float = 0.6) -> None:
        parts = []
        if fill is not None:
            parts.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        if stroke is not None:
            parts.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG")
            parts.append(f"{line_width:.2f} w")
        parts.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re")
        if fill is not None and stroke is not None:
            parts.append("B")
        elif fill is not None:
            parts.append("f")
        else:
            parts.append("S")
        self._operators.append(" ".join(parts).encode())

    def line(self, x1: float, y1: float, x2: float, y2: float,
             colour=LINE, width: float = 0.6) -> None:
        self._operators.append(
            f"{colour[0]:.3f} {colour[1]:.3f} {colour[2]:.3f} RG "
            f"{width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"
            .encode())

    def content(self) -> bytes:
        return b"\n".join(self._operators)


class Document:
    """A collection of pages, serialised to a PDF file."""

    def __init__(self, title: str = "", author: str = "ServiceLens",
                 subject: str = "") -> None:
        self.title = title
        self.author = author
        self.subject = subject
        self.pages: list = []

    def add_page(self, width: float = A4[0], height: float = A4[1]) -> Page:
        page = Page(width, height)
        self.pages.append(page)
        return page

    def to_bytes(self, compress: bool = True) -> bytes:
        """Serialise the document.

        Object numbering: 1 is the catalogue, 2 the page tree, 3 and 4 the
        two fonts, 5 the document information, then a page object and a
        content stream for each page.
        """
        if not self.pages:
            self.add_page()

        objects: dict = {}
        first_page_object = 6
        page_ids = [first_page_object + index * 2
                    for index in range(len(self.pages))]

        objects[1] = (b"<< /Type /Catalog /Pages 2 0 R >>")
        kids = " ".join(f"{number} 0 R" for number in page_ids)
        objects[2] = (f"<< /Type /Pages /Count {len(self.pages)} "
                      f"/Kids [{kids}] >>").encode()
        objects[3] = (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                      b"/Encoding /WinAnsiEncoding >>")
        objects[4] = (b"<< /Type /Font /Subtype /Type1 "
                      b"/BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding "
                      b">>")
        objects[5] = (b"<< /Title (" + escape(self.title)
                      + b") /Author (" + escape(self.author)
                      + b") /Subject (" + escape(self.subject)
                      + b") /Producer (ServiceLens) >>")

        for index, page in enumerate(self.pages):
            page_id = page_ids[index]
            stream_id = page_id + 1
            objects[page_id] = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox "
                f"[0 0 {page.width:.2f} {page.height:.2f}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                f"/Contents {stream_id} 0 R >>").encode()

            raw = page.content()
            if compress:
                body = zlib.compress(raw, 6)
                header = (f"<< /Length {len(body)} /Filter /FlateDecode >>"
                          ).encode()
            else:
                body = raw
                header = f"<< /Length {len(body)} >>".encode()
            objects[stream_id] = (header + b"\nstream\n" + body
                                  + b"\nendstream")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: dict = {}
        for number in sorted(objects):
            offsets[number] = len(out)
            out += f"{number} 0 obj\n".encode()
            out += objects[number]
            out += b"\nendobj\n"

        xref_at = len(out)
        count = max(objects) + 1
        out += f"xref\n0 {count}\n".encode()
        # The mandatory free-list head: object 0, generation 65535.
        out += f"{0:010d} 65535 f \n".encode()
        for number in range(1, count):
            out += f"{offsets.get(number, 0):010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {count} /Root 1 0 R /Info 5 0 R >>\n"
                f"startxref\n{xref_at}\n%%EOF\n").encode()
        return bytes(out)

    def save(self, path) -> int:
        """Write the document. Returns the number of bytes written."""
        data = self.to_bytes()
        with open(path, "wb") as handle:
            handle.write(data)
        return len(data)


@dataclass
class Column:
    """One column of a table: how wide, how aligned, and its heading."""

    heading: str
    width: float
    align: str = "left"
    bold: bool = False


@dataclass
class Layout:
    """Top-down page composition with automatic page breaks.

    `y` is measured downward from the top of the page, which is how a report
    is actually written; the conversion to PDF coordinates happens once, in
    `_at`.
    """

    document: Document
    title: str = ""
    subtitle: str = ""
    footer: str = ""
    size: tuple = A4
    margin: float = MARGIN

    page: Page = field(init=False, default=None)
    y: float = field(init=False, default=0.0)
    number: int = field(init=False, default=0)

    @property
    def width(self) -> float:
        return self.size[0] - 2 * self.margin

    @property
    def bottom_limit(self) -> float:
        return self.size[1] - self.margin - 26

    def _at(self, offset: float = 0.0) -> float:
        """PDF y for the current cursor."""
        return self.size[1] - self.y - offset

    def new_page(self) -> Page:
        self.page = self.document.add_page(*self.size)
        self.number += 1
        self.y = self.margin
        self._running_header()
        self._page_footer()
        return self.page

    def _running_header(self) -> None:
        if self.number == 1:
            return
        self.page.text(self.margin, self._at(), self.title, 8, False, SUBTLE)
        if self.subtitle:
            self.page.text_right(self.size[0] - self.margin, self._at(),
                                 self.subtitle, 8, False, SUBTLE)
        self.y += 11
        self.page.line(self.margin, self._at(), self.size[0] - self.margin,
                       self._at(), LINE, 0.5)
        self.y += 14

    def _page_footer(self) -> None:
        base = self.margin - 6
        self.page.line(self.margin, base + 14, self.size[0] - self.margin,
                       base + 14, LINE, 0.5)
        if self.footer:
            self.page.text(self.margin, base, self.footer, 7.5, False, SUBTLE)
        self.page.text_right(self.size[0] - self.margin, base,
                             f"Page {self.number}", 7.5, False, SUBTLE)

    def ensure(self, space: float) -> None:
        """Start a new page when `space` points will not fit below."""
        if self.page is None or self.y + space > self.bottom_limit:
            self.new_page()

    # -- blocks --------------------------------------------------------

    def gap(self, space: float) -> None:
        self.y += space

    def rule(self, space_before: float = 6, space_after: float = 8) -> None:
        self.ensure(space_before + space_after + 2)
        self.y += space_before
        self.page.line(self.margin, self._at(), self.size[0] - self.margin,
                       self._at(), LINE, 0.5)
        self.y += space_after

    def heading(self, text: str, size: float = 13) -> None:
        self.ensure(size + 12)
        self.y += size
        self.page.text(self.margin, self._at(), text, size, True, INK)
        self.y += 8

    def label(self, text: str) -> None:
        self.ensure(16)
        self.y += 8
        self.page.text(self.margin, self._at(), text.upper(), 7.5, True,
                       SUBTLE)
        self.y += 6

    def paragraph(self, text: str, size: float = 8.5, colour=MUTED,
                  width: float = None) -> None:
        limit = width or self.width
        for line in wrap(text, size, limit):
            self.ensure(size + 3)
            self.y += size + 1.5
            self.page.text(self.margin, self._at(), line, size, False, colour)
        self.y += 3

    def key_values(self, pairs, label_width: float = 120,
                   size: float = 8.5) -> None:
        for key, value in pairs:
            self.ensure(size + 5)
            self.y += size + 3
            self.page.text(self.margin, self._at(), key, size, False, MUTED)
            self.page.text(self.margin + label_width, self._at(),
                           truncate(str(value), size, self.width
                                    - label_width, True),
                           size, True, INK)
        self.y += 3

    def figures(self, tiles, per_row: int = 4) -> None:
        """A row of headline numbers with captions beneath."""
        cell = self.width / per_row
        for start in range(0, len(tiles), per_row):
            chunk = tiles[start:start + per_row]
            self.ensure(34)
            self.y += 16
            for index, (value, caption, colour) in enumerate(chunk):
                x = self.margin + index * cell
                self.page.text(x, self._at(), str(value), 15, True, colour)
            self.y += 11
            for index, (_value, caption, _colour) in enumerate(chunk):
                x = self.margin + index * cell
                self.page.text(x, self._at(),
                               truncate(caption, 7.5, cell - 8), 7.5, False,
                               SUBTLE)
            self.y += 8

    def bars(self, rows, colour=ACCENT, label_width: float = 150) -> None:
        """A horizontal bar chart: label, proportional bar, value."""
        if not rows:
            self.paragraph("Nothing to show.", 8, SUBTLE)
            return
        largest = max((count for _, count in rows), default=0) or 1
        value_width = 46
        track_left = self.margin + label_width
        track = self.width - label_width - value_width
        for label, count in rows:
            self.ensure(15)
            self.y += 11
            baseline = self._at()
            self.page.text(self.margin, baseline,
                           truncate(str(label), 8.5, label_width - 8), 8.5,
                           False, INK)
            self.page.rect(track_left, baseline - 1.5, track, 7, fill=BAND)
            filled = track * (count / largest)
            if count:
                paint = colour(label) if callable(colour) else colour
                self.page.rect(track_left, baseline - 1.5, max(filled, 1.5),
                               7, fill=paint)
            self.page.text_right(self.size[0] - self.margin, baseline,
                                 f"{count:,}", 8.5, True, INK)
            self.y += 4

    def table_header(self, columns) -> None:
        self.ensure(20)
        self.y += 11
        x = self.margin
        for column in columns:
            self._cell(x, column, column.heading, 7.5, True, SUBTLE)
            x += column.width
        self.y += 4
        self.page.line(self.margin, self._at(), self.size[0] - self.margin,
                       self._at(), LINE, 0.5)
        self.y += 3

    def table_row(self, columns, values, colours=None, banded: bool = False,
                  size: float = 8) -> None:
        self.ensure(14)
        self.y += size + 3
        baseline = self._at()
        if banded:
            self.page.rect(self.margin - 3, baseline - 3, self.width + 6,
                           size + 5, fill=BAND)
        x = self.margin
        for index, column in enumerate(columns):
            value = values[index] if index < len(values) else ""
            colour = (colours[index] if colours and index < len(colours)
                      and colours[index] else INK)
            self._cell(x, column, value, size, column.bold, colour)
            x += column.width

    def _cell(self, x: float, column: Column, value, size: float,
              bold: bool, colour) -> None:
        text = truncate(str(value), size, column.width - 6, bold)
        baseline = self._at()
        if column.align == "right":
            self.page.text_right(x + column.width - 6, baseline, text, size,
                                 bold, colour)
        elif column.align == "center":
            offset = (column.width - text_width(text, size, bold)) / 2
            self.page.text(x + offset, baseline, text, size, bold, colour)
        else:
            self.page.text(x, baseline, text, size, bold, colour)
