"""A minimal .xlsx writer, standard library only.

Used solely to produce the demonstration workbook. ServiceLens itself never
writes to a workbook - source files are always opened read-only.

The output is a real Office Open XML package rather than a CSV with a
misleading extension, so the demo workbook exercises the reader properly:
shared strings, date-styled numeric cells and sparse rows all appear in it.
"""

from __future__ import annotations

import zipfile
from datetime import date, datetime
from xml.sax.saxutils import escape

# The epoch Excel's 1900 date system effectively counts from, for every date
# after the spurious 29 February 1900. See `xlsx.serial_to_date`.
_EPOCH = date(1899, 12, 30)

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""

# Style 0 is General. Style 1 carries built-in number format 14 (a short
# date), which is what tells a reader that the number is a date. Style 2 is
# the bold header.
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

STYLE_GENERAL = 0
STYLE_DATE = 1
STYLE_HEADER = 2


def date_to_serial(value: date) -> int:
    """The Excel 1900-system serial number for a date."""
    return (value - _EPOCH).days


def column_letter(index: int) -> str:
    """Spreadsheet column letters for a zero-based index: 0 -> A, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


class _StringTable:
    """The shared string table, which is how .xlsx stores most text."""

    def __init__(self) -> None:
        self._index: dict[str, int] = {}
        self.order: list[str] = []
        self.total = 0

    def add(self, text: str) -> int:
        self.total += 1
        found = self._index.get(text)
        if found is not None:
            return found
        position = len(self.order)
        self._index[text] = position
        self.order.append(text)
        return position

    def to_xml(self) -> str:
        items = "".join(
            f"<si><t xml:space=\"preserve\">{escape(text)}</t></si>"
            for text in self.order
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml'
            f'/2006/main" count="{self.total}" '
            f'uniqueCount="{len(self.order)}">{items}</sst>'
        )


def _cell_xml(reference: str, value, strings: _StringTable,
              style: int) -> str:
    """One `<c>` element. Empty values are omitted entirely, so the sheet
    stays sparse the way a real export is."""
    if value is None or value == "":
        return ""

    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return (f'<c r="{reference}" s="{STYLE_DATE}">'
                f"<v>{date_to_serial(value)}</v></c>")
    if isinstance(value, bool):
        return f'<c r="{reference}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        style_attribute = f' s="{style}"' if style else ""
        return f'<c r="{reference}"{style_attribute}><v>{value}</v></c>'

    index = strings.add(str(value))
    style_attribute = f' s="{style}"' if style else ""
    return f'<c r="{reference}"{style_attribute} t="s"><v>{index}</v></c>'


def write_workbook(path: str, headers, rows, sheet_name: str = "Sheet1",
                   preamble=()) -> None:
    """Write one worksheet to `path`.

    `preamble` rows are written above the header row. Real exports often
    carry a title or a filter summary there, and ServiceLens finds the header
    row rather than assuming it is first - the demo workbook exercises that.
    """
    strings = _StringTable()
    body: list[str] = []
    line = 0

    for preamble_row in preamble:
        line += 1
        cells = "".join(
            _cell_xml(f"{column_letter(i)}{line}", value, strings,
                      STYLE_GENERAL)
            for i, value in enumerate(preamble_row)
        )
        body.append(f'<row r="{line}">{cells}</row>')

    line += 1
    header_cells = "".join(
        _cell_xml(f"{column_letter(i)}{line}", name, strings, STYLE_HEADER)
        for i, name in enumerate(headers)
    )
    body.append(f'<row r="{line}">{header_cells}</row>')

    for row in rows:
        line += 1
        cells = "".join(
            _cell_xml(f"{column_letter(i)}{line}", value, strings,
                      STYLE_GENERAL)
            for i, value in enumerate(row)
        )
        body.append(f'<row r="{line}">{cells}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml'
        '/2006/main"><sheetData>' + "".join(body) + "</sheetData></worksheet>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml'
        '/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships"><sheets>'
        f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
        "</sheets></workbook>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        archive.writestr("xl/styles.xml", _STYLES)
        archive.writestr("xl/sharedStrings.xml", strings.to_xml())
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
