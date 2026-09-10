"""A read-only .xlsx reader built on the standard library.

An .xlsx file is a zip archive of XML parts. Reading one needs `zipfile` and
`ElementTree` and nothing else, so ServiceLens carries no spreadsheet
dependency at all.

The workbook is opened in read mode. Nothing is ever written back to it.

Three details make the difference between a toy reader and a usable one:

* **Sparse cells.** A row stores only the cells that have content, so cell
  references have to be decoded to find each value's real column.
* **Dates.** A date is stored as a number whose *style* says it is a date.
  Without reading `styles.xml`, every date reads back as a five-digit
  integer. This reader resolves the style and returns an ISO date string.
* **Shared strings.** Most text lives in a single shared table, and rich
  text is split across several runs that must be concatenated.
"""

from __future__ import annotations

import re
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = ("http://schemas.openxmlformats.org/officeDocument/2006"
              "/relationships")
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_MAIN = f"{{{MAIN_NS}}}"

# Number format ids Excel reserves for dates and times.
BUILTIN_DATE_FORMATS = frozenset(
    list(range(14, 23)) + list(range(45, 48)) + [27, 30, 36, 50, 57]
)

# Strips literal text, colour codes and escapes out of a custom format code
# before looking for date placeholders, so a currency format containing the
# word "May" in quotes is not mistaken for a date.
_FORMAT_LITERALS = re.compile(r'"[^"]*"|\[[^\]]*\]|\\.')
_DATE_PLACEHOLDER = re.compile(r"[ymdhs]")


class WorkbookError(Exception):
    """Raised when a file cannot be interpreted as a usable workbook."""


class Sheet:
    """One worksheet, read into memory as a rectangular grid of strings."""

    __slots__ = ("name", "rows", "row_numbers")

    def __init__(self, name: str, rows: list[list[str]],
                 row_numbers: list[int]) -> None:
        self.name = name
        self.rows = rows
        self.row_numbers = row_numbers

    def __len__(self) -> int:
        return len(self.rows)


def column_index(cell_reference: str) -> int:
    """Zero-based column number for a cell reference such as ``BC12``."""
    match = re.match(r"[A-Za-z]+", cell_reference or "")
    if not match:
        return 0
    number = 0
    for character in match.group(0).upper():
        number = number * 26 + (ord(character) - 64)
    return number - 1


def row_index(cell_reference: str) -> int:
    """The 1-based row number in a cell reference, or 0 when absent."""
    match = re.search(r"\d+", cell_reference or "")
    return int(match.group(0)) if match else 0


def serial_to_date(serial: float, date_system_1904: bool = False) -> date:
    """Convert an Excel date serial to a real date.

    Excel's 1900 system contains a deliberate bug: it treats 1900 as a leap
    year for compatibility with a much older spreadsheet. Serial 60 is that
    non-existent 29 February. Serials above it are therefore offset from
    1899-12-30, and serials below it from 1899-12-31.
    """
    whole = int(serial)
    if date_system_1904:
        return date(1904, 1, 1) + timedelta(days=whole)
    if whole < 60:
        return date(1899, 12, 31) + timedelta(days=whole)
    return date(1899, 12, 30) + timedelta(days=whole)


def _is_date_format(format_code: str) -> bool:
    """True when a custom number format code describes a date or time."""
    stripped = _FORMAT_LITERALS.sub("", format_code or "")
    return bool(_DATE_PLACEHOLDER.search(stripped.casefold()))


class _Styles:
    """Which cell style indexes mean "this number is a date"."""

    __slots__ = ("date_styles",)

    def __init__(self, date_styles: frozenset[int]) -> None:
        self.date_styles = date_styles

    def is_date(self, style_index: str | None) -> bool:
        if not style_index:
            return False
        try:
            return int(style_index) in self.date_styles
        except ValueError:
            return False

    @classmethod
    def load(cls, archive: zipfile.ZipFile) -> "_Styles":
        path = "xl/styles.xml"
        if path not in archive.namelist():
            return cls(frozenset())
        try:
            root = ET.fromstring(archive.read(path))
        except ET.ParseError:
            return cls(frozenset())

        custom_date_ids = set()
        for entry in root.iter(f"{_MAIN}numFmt"):
            try:
                format_id = int(entry.attrib.get("numFmtId", "-1"))
            except ValueError:
                continue
            if _is_date_format(entry.attrib.get("formatCode", "")):
                custom_date_ids.add(format_id)

        date_styles = set()
        cell_formats = root.find(f"{_MAIN}cellXfs")
        if cell_formats is not None:
            for position, entry in enumerate(
                    cell_formats.findall(f"{_MAIN}xf")):
                try:
                    format_id = int(entry.attrib.get("numFmtId", "0"))
                except ValueError:
                    continue
                if (format_id in BUILTIN_DATE_FORMATS
                        or format_id in custom_date_ids):
                    date_styles.add(position)
        return cls(frozenset(date_styles))


class WorkbookReader:
    """Reads the first meaningful worksheet out of an .xlsx file."""

    @staticmethod
    def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
        path = "xl/sharedStrings.xml"
        if path not in archive.namelist():
            return []
        try:
            root = ET.fromstring(archive.read(path))
        except ET.ParseError as error:
            raise WorkbookError(
                "The workbook's shared string table is damaged.") from error
        strings = []
        for item in root.findall(f"{_MAIN}si"):
            # Rich text splits one value across several <t> runs.
            strings.append("".join(
                node.text or "" for node in item.iter(f"{_MAIN}t")))
        return strings

    @staticmethod
    def _date_system_1904(archive: zipfile.ZipFile) -> bool:
        path = "xl/workbook.xml"
        if path not in archive.namelist():
            return False
        try:
            root = ET.fromstring(archive.read(path))
        except ET.ParseError:
            return False
        properties = root.find(f"{_MAIN}workbookPr")
        if properties is None:
            return False
        flag = properties.attrib.get("date1904", "0").strip().casefold()
        return flag in ("1", "true")

    @staticmethod
    def _sheet_targets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
        """Every worksheet as (display name, archive path), in book order."""
        names = archive.namelist()
        if "xl/workbook.xml" not in names:
            raise WorkbookError(
                "This file is not an Excel workbook. Save the report as "
                "Excel Workbook (.xlsx) and try again.")
        try:
            book = ET.fromstring(archive.read("xl/workbook.xml"))
        except ET.ParseError as error:
            raise WorkbookError("The workbook index is damaged.") from error

        relationships: dict[str, str] = {}
        rels_path = "xl/_rels/workbook.xml.rels"
        if rels_path in names:
            try:
                rels_root = ET.fromstring(archive.read(rels_path))
            except ET.ParseError as error:
                raise WorkbookError(
                    "The workbook index is damaged.") from error
            for entry in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship"):
                relationships[entry.attrib.get("Id", "")] = (
                    entry.attrib.get("Target", ""))

        sheets_node = book.find(f"{_MAIN}sheets")
        if sheets_node is None or len(sheets_node) == 0:
            raise WorkbookError("The workbook contains no worksheets.")

        targets: list[tuple[str, str]] = []
        for position, sheet in enumerate(sheets_node, start=1):
            name = sheet.attrib.get("name", f"Sheet{position}")
            target = relationships.get(
                sheet.attrib.get(f"{{{DOC_REL_NS}}}id", ""), "")
            if not target:
                target = f"worksheets/sheet{position}.xml"
            target = target.lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            if target in names:
                targets.append((name, target))
        if not targets:
            raise WorkbookError("The workbook's worksheet data is missing.")
        return targets

    @classmethod
    def _cell_text(cls, cell: ET.Element, strings: list[str],
                   styles: _Styles, date_1904: bool) -> str:
        cell_type = cell.attrib.get("t", "")

        if cell_type == "inlineStr":
            return "".join(
                node.text or "" for node in cell.iter(f"{_MAIN}t")).strip()

        value_node = cell.find(f"{_MAIN}v")
        if value_node is None or value_node.text is None:
            return ""
        value = value_node.text.strip()

        if cell_type == "s":
            try:
                return strings[int(value)].strip()
            except (ValueError, IndexError):
                return value
        if cell_type == "b":
            return "Yes" if value == "1" else "No"
        if cell_type in ("str", "e"):
            return value

        # A bare number. Its style decides whether it is really a date.
        if styles.is_date(cell.attrib.get("s")):
            try:
                return serial_to_date(float(value), date_1904).isoformat()
            except (ValueError, OverflowError, OSError):
                return value
        return value

    @classmethod
    def read_sheet(cls, path: str, sheet_name: str | None = None) -> Sheet:
        """Read one worksheet into a grid of trimmed strings.

        Without `sheet_name`, the first worksheet holding data is used.
        Blank rows are dropped but their original row numbers are kept, so
        a record can always be traced back to its line in the file.
        """
        try:
            with zipfile.ZipFile(path, "r") as archive:
                strings = cls._shared_strings(archive)
                styles = _Styles.load(archive)
                date_1904 = cls._date_system_1904(archive)
                targets = cls._sheet_targets(archive)

                if sheet_name is not None:
                    wanted = sheet_name.strip().casefold()
                    targets = [t for t in targets
                               if t[0].strip().casefold() == wanted]
                    if not targets:
                        raise WorkbookError(
                            f"The workbook has no worksheet named "
                            f"'{sheet_name}'.")

                for name, target in targets:
                    rows, numbers = cls._read_grid(
                        archive, target, strings, styles, date_1904)
                    if rows:
                        return Sheet(name, rows, numbers)
                return Sheet(targets[0][0], [], [])

        except zipfile.BadZipFile as error:
            raise WorkbookError(
                "This is not a readable .xlsx file. If it is an older .xls "
                "workbook, re-save it as Excel Workbook (.xlsx)."
            ) from error
        except (OSError, ET.ParseError) as error:
            raise WorkbookError(f"The workbook could not be read: {error}"
                                ) from error

    @classmethod
    def _read_grid(cls, archive: zipfile.ZipFile, target: str,
                   strings: list[str], styles: _Styles,
                   date_1904: bool) -> tuple[list[list[str]], list[int]]:
        root = ET.fromstring(archive.read(target))
        sheet_data = root.find(f"{_MAIN}sheetData")
        if sheet_data is None:
            return [], []

        rows: list[list[str]] = []
        numbers: list[int] = []
        for position, row in enumerate(
                sheet_data.findall(f"{_MAIN}row"), start=1):
            try:
                line = int(row.attrib.get("r", position))
            except ValueError:
                line = position

            values: list[str] = []
            for cell in row.findall(f"{_MAIN}c"):
                index = column_index(cell.attrib.get("r", ""))
                while len(values) <= index:
                    values.append("")
                values[index] = cls._cell_text(
                    cell, strings, styles, date_1904).strip()

            if any(values):
                rows.append(values)
                numbers.append(line)
        return rows, numbers


def read_sheet(path: str, sheet_name: str | None = None) -> Sheet:
    """Read one worksheet from an .xlsx file."""
    return WorkbookReader.read_sheet(path, sheet_name)
