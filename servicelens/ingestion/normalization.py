"""Turning worksheet rows into `WorkOrder` records.

The reader hands back strings. This module decides what those strings mean:
which row is the header, which dates are dates, which numbers are money, and
which vocabulary a status word belongs to.

Nothing here rejects a row for being incomplete. A blank or unreadable field
becomes `None` and the integrity rules report it; ingestion never decides
that a record is not worth keeping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from ..domain.models import (
    AssetCategory,
    AssignmentType,
    Priority,
    Status,
    WorkOrder,
    WorkType,
)
from . import schema as S
from .xlsx import Sheet, WorkbookError, read_sheet, serial_to_date

# Header rows sometimes sit below a title or a filter block.
HEADER_SEARCH_DEPTH = 25

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%b %d, %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%d %B %Y",
    "%Y%m%d",
)

_CURRENCY_NOISE = re.compile(r"[^0-9.\-()]")
_ISO_DATETIME = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ]")


def parse_date(value: str | None) -> date | None:
    """Read a date out of whatever the export wrote.

    Accepts ISO dates and datetimes, the common regional orderings, written
    month names, and bare Excel serial numbers for workbooks whose date
    styling was lost. Returns None rather than guessing.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    iso = _ISO_DATETIME.match(text)
    if iso:
        text = iso.group(1)

    for pattern in _DATE_FORMATS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue

    # A bare serial number, from a workbook that lost its date styling.
    try:
        serial = float(text)
    except ValueError:
        return None
    if 1 <= serial <= 2958465:  # 1900-01-01 through 9999-12-31
        try:
            return serial_to_date(serial)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def parse_number(value: str | None) -> float | None:
    """Read a number, tolerating currency symbols, commas and accountancy
    parentheses for negatives. Returns None when there is nothing to read."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = _CURRENCY_NOISE.sub("", text).replace("(", "").replace(")", "")
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return -number if negative else number


def clean_text(value: str | None) -> str:
    """Collapse whitespace and trim. Never returns None."""
    if value is None:
        return ""
    return " ".join(str(value).split())


@dataclass
class ImportResult:
    """Everything one import produced, including what it could not read."""

    work_orders: list[WorkOrder] = field(default_factory=list)
    schema: S.SchemaReport = field(default_factory=S.SchemaReport)
    sheet_name: str = ""
    source_path: str = ""
    header_row: int = 0
    rows_read: int = 0
    blank_rows_skipped: int = 0
    preamble: list = field(default_factory=list)
    """Text found above the header row.

    Exports often carry a title or a filter description there. It is not
    data, but it is provenance worth carrying into a report - and it is how
    a demonstration dataset can announce itself as one.
    """

    @property
    def count(self) -> int:
        return len(self.work_orders)

    @property
    def notice(self) -> str:
        """The most descriptive line above the header row, if any."""
        return max(self.preamble, key=len) if self.preamble else ""


def find_header_row(sheet: Sheet) -> int:
    """Index of the row that best matches the canonical schema.

    Scores each candidate on how many *required* columns it supplies, with
    total recognized columns as the tie-break, so a title row that happens
    to contain the word "Status" cannot outrank the real header.
    """
    best_index = 0
    best_score = (-1, -1)
    for index, row in enumerate(sheet.rows[:HEADER_SEARCH_DEPTH]):
        report = S.resolve_headers(row)
        required = sum(1 for name in S.REQUIRED_COLUMNS
                       if name in report.matched)
        score = (required, len(report.matched))
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def build_work_order(values: dict[str, str], row_number: int) -> WorkOrder:
    """Assemble one `WorkOrder` from canonical column values."""
    raw_status = clean_text(values.get(S.STATUS))
    return WorkOrder(
        work_order_id=clean_text(values.get(S.WORK_ORDER_ID)),
        row_number=row_number,
        asset_id=clean_text(values.get(S.ASSET_ID)),
        asset_name=clean_text(values.get(S.ASSET_NAME)),
        asset_category=AssetCategory.parse(values.get(S.ASSET_CATEGORY)),
        site=clean_text(values.get(S.SITE)),
        department=clean_text(values.get(S.DEPARTMENT)),
        description=clean_text(values.get(S.DESCRIPTION)),
        work_type=WorkType.parse(values.get(S.WORK_TYPE)),
        priority=Priority.parse(values.get(S.PRIORITY)),
        status=Status.parse(raw_status),
        raw_status=raw_status,
        requested_date=parse_date(values.get(S.REQUESTED_DATE)),
        opened_date=parse_date(values.get(S.OPENED_DATE)),
        scheduled_date=parse_date(values.get(S.SCHEDULED_DATE)),
        due_date=parse_date(values.get(S.DUE_DATE)),
        completed_date=parse_date(values.get(S.COMPLETED_DATE)),
        last_update_date=parse_date(values.get(S.LAST_UPDATE_DATE)),
        assignment_type=AssignmentType.parse(values.get(S.ASSIGNMENT_TYPE)),
        assigned_team=clean_text(values.get(S.ASSIGNED_TEAM)),
        assigned_technician=clean_text(values.get(S.ASSIGNED_TECHNICIAN)),
        vendor=clean_text(values.get(S.VENDOR)),
        estimated_cost=parse_number(values.get(S.ESTIMATED_COST)),
        actual_cost=parse_number(values.get(S.ACTUAL_COST)),
        meter_reading=parse_number(values.get(S.METER_READING)),
        last_note=clean_text(values.get(S.LAST_NOTE)),
    )


def normalize_sheet(sheet: Sheet, source_path: str = "") -> ImportResult:
    """Turn a worksheet into work orders, or explain why it cannot be."""
    if not sheet.rows:
        raise WorkbookError("The worksheet is empty.")

    header_index = find_header_row(sheet)
    headers = sheet.rows[header_index]
    report = S.resolve_headers(headers)

    if report.missing_required:
        raise WorkbookError(
            "This workbook is missing required column(s): "
            + ", ".join(report.missing_required)
            + ". ServiceLens accepts several spellings for each column - see "
              "the schema reference for the full list."
        )

    result = ImportResult(
        schema=report,
        sheet_name=sheet.name,
        source_path=source_path,
        header_row=sheet.row_numbers[header_index],
        preamble=[" ".join(" ".join(row).split())
                  for row in sheet.rows[:header_index]
                  if any(cell.strip() for cell in row)],
    )

    for offset, row in enumerate(sheet.rows[header_index + 1:],
                                 start=header_index + 1):
        line = sheet.row_numbers[offset]
        result.rows_read += 1
        values: dict[str, str] = {}
        for index, name in report.mapping.items():
            if index < len(row):
                values[name] = row[index]
        if not any(v.strip() for v in values.values()):
            result.blank_rows_skipped += 1
            continue
        result.work_orders.append(build_work_order(values, line))

    return result


def load_workbook(path: str, sheet_name: str | None = None) -> ImportResult:
    """Read and normalize a workbook in one step."""
    sheet = read_sheet(path, sheet_name)
    return normalize_sheet(sheet, source_path=path)
