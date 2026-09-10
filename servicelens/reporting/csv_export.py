"""Flat CSV export.

One row per work order, carrying both the canonical fields read from the
workbook and the intelligence ServiceLens derived from them - severity,
queue, team, age band, finding count and the primary action. That pairing is
the point: the file can be pivoted in a spreadsheet without needing the
application to interpret it.

Written with the standard `csv` module, so quoting and embedded newlines are
handled correctly rather than by string concatenation.
"""

from __future__ import annotations

import csv

from ..domain.metrics import band_for
from ..domain.models import AssignmentType, Severity
from .summary import ReportResult, money_exact

DEFAULT_FILENAME = "servicelens_work_orders.csv"

HEADERS = (
    # -- as read from the workbook -------------------------------------
    "Work Order ID",
    "Asset ID",
    "Asset Name",
    "Asset Category",
    "Site",
    "Department",
    "Description",
    "Work Type",
    "Priority",
    "Status",
    "Requested Date",
    "Opened Date",
    "Scheduled Date",
    "Due Date",
    "Completed Date",
    "Last Update Date",
    "Assignment Type",
    "Reported Team",
    "Assigned Technician",
    "Vendor",
    "Estimated Cost",
    "Actual Cost",
    "Meter Reading",
    "Last Note",
    "Worksheet Row",
    # -- derived by ServiceLens ----------------------------------------
    "Open",
    "Age Days",
    "Age Band",
    "Days Since Update",
    "Owning Team",
    "Routing Queue",
    "Routing Reason",
    "Severity",
    "Finding Count",
    "Critical Count",
    "Warning Count",
    "Information Count",
    "Primary Finding",
    "Recommended Action",
    "Finding Keys",
    "Has Integrity Finding",
    "Vendor State",
    "Cost Signal",
    "Cost Variance",
)


def _iso(value) -> str:
    return value.isoformat() if value else ""


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def vendor_state(assessment) -> str:
    """A single word for where a work order stands with a vendor."""
    work_order = assessment.work_order
    if work_order.assignment_type is not AssignmentType.EXTERNAL:
        return "Internal"
    if not work_order.vendor.strip():
        return "External - vendor not named"
    if assessment.has("vendor_work_overdue"):
        return "External - overdue"
    if work_order.scheduled_date is None:
        return "External - not scheduled"
    return "External - scheduled"


def cost_signal(assessment) -> str:
    """Whether cost is worth a look, and why."""
    if assessment.has("cost_overrun"):
        return "Over estimate"
    if assessment.has("high_estimated_cost"):
        return "Needs approval"
    if assessment.has("negative_cost"):
        return "Negative value"
    work_order = assessment.work_order
    if work_order.estimated_cost is None and work_order.actual_cost is None:
        return "No cost recorded"
    return "Within expectation"


def cost_variance(work_order) -> str:
    """Actual minus estimate, when both are known."""
    if work_order.actual_cost is None or work_order.estimated_cost is None:
        return ""
    return money_exact(work_order.actual_cost - work_order.estimated_cost)


def row_for(assessment) -> list:
    """One CSV row: the record as read, then what was derived from it."""
    work_order = assessment.work_order
    findings = assessment.findings
    primary = findings[0] if findings else None
    integrity = any(f.domain.name == "DATA_QUALITY" for f in findings)

    return [
        work_order.work_order_id,
        work_order.asset_id,
        work_order.asset_name,
        work_order.asset_category.label if work_order.asset_category else "",
        work_order.site,
        work_order.department,
        work_order.description,
        work_order.work_type.label if work_order.work_type else "",
        work_order.priority.label if work_order.priority else "",
        work_order.status.label if work_order.status else work_order.raw_status,
        _iso(work_order.requested_date),
        _iso(work_order.opened_date),
        _iso(work_order.scheduled_date),
        _iso(work_order.due_date),
        _iso(work_order.completed_date),
        _iso(work_order.last_update_date),
        work_order.assignment_type.label if work_order.assignment_type else "",
        work_order.assigned_team,
        work_order.assigned_technician,
        work_order.vendor,
        money_exact(work_order.estimated_cost),
        money_exact(work_order.actual_cost),
        (f"{work_order.meter_reading:,.0f}"
         if work_order.meter_reading is not None else ""),
        work_order.last_note,
        work_order.row_number,

        _yes_no(work_order.is_open),
        "" if assessment.age is None else assessment.age,
        band_for(assessment.age) if work_order.is_open else "",
        "",  # filled below, needs the reporting date
        assessment.team,
        assessment.queue,
        assessment.routing_reason,
        assessment.severity.label if assessment.severity else "None",
        len(findings),
        assessment.count_of(Severity.CRITICAL),
        assessment.count_of(Severity.WARNING),
        assessment.count_of(Severity.INFORMATION),
        primary.title if primary else "",
        primary.message if primary else "",
        " ".join(f.key for f in findings),
        _yes_no(integrity),
        vendor_state(assessment),
        cost_signal(assessment),
        cost_variance(work_order),
    ]


def rows_for(analysis, assessments=None) -> list:
    """Every row, with the update age filled in from the reporting date."""
    records = (analysis.assessments if assessments is None else assessments)
    quiet_index = HEADERS.index("Days Since Update")
    out = []
    for assessment in records:
        row = row_for(assessment)
        quiet = assessment.work_order.days_since_update(analysis.as_of)
        row[quiet_index] = "" if quiet is None else quiet
        out.append(row)
    return out


def write(analysis, path, assessments=None) -> ReportResult:
    """Write the export. Returns what was produced.

    `newline=""` is required: the csv module writes its own line terminator,
    and without it Windows turns each one into a blank line.
    """
    rows = rows_for(analysis, assessments)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADERS)
        writer.writerows(rows)

    import os
    return ReportResult(str(path), "CSV export", os.path.getsize(path),
                        rows=len(rows))
