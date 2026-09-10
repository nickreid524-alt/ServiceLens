"""The canonical column schema and the alias layer that reaches it.

Maintenance systems all export the same handful of ideas under different
column names. ServiceLens declares one canonical name per idea, plus the
spellings it will accept for it, and everything downstream reads only the
canonical name.

Adding support for a new export format is therefore a data change here, not
a code change anywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Column:
    """One canonical field and the header spellings that map onto it."""

    name: str
    required: bool = False
    aliases: tuple[str, ...] = ()
    purpose: str = ""

    def keys(self) -> tuple[str, ...]:
        """Every spelling this column answers to, canonical name first."""
        return (self.name,) + self.aliases


# Canonical column names, used as constants everywhere else.
WORK_ORDER_ID = "Work Order ID"
ASSET_ID = "Asset ID"
ASSET_NAME = "Asset Name"
ASSET_CATEGORY = "Asset Category"
SITE = "Site"
DEPARTMENT = "Department"
DESCRIPTION = "Description"
WORK_TYPE = "Work Type"
PRIORITY = "Priority"
STATUS = "Status"
REQUESTED_DATE = "Requested Date"
OPENED_DATE = "Opened Date"
SCHEDULED_DATE = "Scheduled Date"
DUE_DATE = "Due Date"
COMPLETED_DATE = "Completed Date"
LAST_UPDATE_DATE = "Last Update Date"
ASSIGNMENT_TYPE = "Assignment Type"
ASSIGNED_TEAM = "Assigned Team"
ASSIGNED_TECHNICIAN = "Assigned Technician"
VENDOR = "Vendor"
ESTIMATED_COST = "Estimated Cost"
ACTUAL_COST = "Actual Cost"
METER_READING = "Meter Reading"
LAST_NOTE = "Last Note"


COLUMNS: tuple[Column, ...] = (
    Column(
        WORK_ORDER_ID, required=True,
        aliases=("Work Order", "Work Order Number", "WO", "WO ID",
                 "WO Number", "Order ID", "Ticket", "Ticket ID",
                 "Job Number"),
        purpose="Identity on every screen, report and export.",
    ),
    Column(
        ASSET_ID, required=True,
        aliases=("Asset", "Asset Number", "Asset Tag", "Equipment",
                 "Equipment ID", "Equipment Number", "Unit", "Unit Number"),
        purpose="Links work to the thing it was performed on. Kept as text "
                "so an identifier beginning with a zero keeps it.",
    ),
    Column(
        STATUS, required=True,
        aliases=("Work Order Status", "WO Status", "State"),
        purpose="Whether the work is open, held or finished.",
    ),
    Column(
        OPENED_DATE, required=True,
        aliases=("Opened", "Date Opened", "Created Date", "Created",
                 "Open Date", "Reported Date", "Date Raised"),
        purpose="The start of every age calculation.",
    ),
    Column(
        PRIORITY,
        aliases=("Priority Level", "Urgency", "Severity Level"),
        purpose="Priority rules and the emergency response thresholds.",
    ),
    Column(
        WORK_TYPE,
        aliases=("Type", "Work Order Type", "Maintenance Type", "Job Type",
                 "Task Type"),
        purpose="Separates preventive, safety and corrective work.",
    ),
    Column(
        ASSET_NAME,
        aliases=("Asset Description", "Equipment Description",
                 "Equipment Name", "Asset Title"),
        purpose="Human-readable asset label for display.",
    ),
    Column(
        ASSET_CATEGORY,
        aliases=("Category", "Asset Type", "Equipment Category",
                 "Equipment Type", "Asset Class"),
        purpose="Ownership routing to the responsible maintenance team.",
    ),
    Column(
        SITE,
        aliases=("Location", "Facility", "Building", "Site Name", "Branch"),
        purpose="Grouping and filtering by place.",
    ),
    Column(
        DEPARTMENT,
        aliases=("Dept", "Cost Center", "Cost Centre", "Business Unit",
                 "Division"),
        purpose="Grouping and filtering by owning department.",
    ),
    Column(
        DESCRIPTION,
        aliases=("Work Description", "Work Order Description", "Summary",
                 "Problem", "Problem Description", "Task"),
        purpose="Shown on every row, card and report.",
    ),
    Column(
        REQUESTED_DATE,
        aliases=("Requested", "Date Requested", "Request Date"),
        purpose="When the work was first asked for.",
    ),
    Column(
        SCHEDULED_DATE,
        aliases=("Scheduled", "Date Scheduled", "Planned Date",
                 "Planned Start"),
        purpose="Vendor scheduling checks and planning views.",
    ),
    Column(
        DUE_DATE,
        aliases=("Due", "Target Date", "Required By", "Target Completion",
                 "Next Due"),
        purpose="Preventive maintenance overdue and due-soon rules.",
    ),
    Column(
        COMPLETED_DATE,
        aliases=("Completed", "Date Completed", "Closed Date", "Closed",
                 "Completion Date", "Finish Date"),
        purpose="Closes the age calculation and drives status integrity.",
    ),
    Column(
        LAST_UPDATE_DATE,
        aliases=("Last Updated", "Updated", "Last Activity", "Modified",
                 "Last Modified", "Last Note Date"),
        purpose="Detects work that has gone quiet.",
    ),
    Column(
        ASSIGNMENT_TYPE,
        aliases=("Assigned Type", "Assignment", "Labor Type",
                 "Internal/External", "Resource Type"),
        purpose="Separates in-house work from contracted work.",
    ),
    Column(
        ASSIGNED_TEAM,
        aliases=("Team", "Crew", "Shop", "Group", "Assigned Group",
                 "Maintenance Team"),
        purpose="Reported ownership, before routing recomputes it.",
    ),
    Column(
        ASSIGNED_TECHNICIAN,
        aliases=("Technician", "Assigned To", "Assignee", "Mechanic",
                 "Craftsperson", "Owner"),
        purpose="Whether the work has a named person on it.",
    ),
    Column(
        VENDOR,
        aliases=("Supplier", "Contractor", "Service Provider",
                 "Vendor Name", "Service Company"),
        purpose="Vendor follow-up rules and external ownership.",
    ),
    Column(
        ESTIMATED_COST,
        aliases=("Estimate", "Estimated Amount", "Quoted Cost", "Budget",
                 "Estimated Total"),
        purpose="Spend-approval and overrun rules.",
    ),
    Column(
        ACTUAL_COST,
        aliases=("Actual", "Total Cost", "Cost", "Actual Amount",
                 "Final Cost", "Invoiced Amount"),
        purpose="Cost totals and overrun detection.",
    ),
    Column(
        METER_READING,
        aliases=("Meter", "Hours", "Hour Meter", "Odometer", "Mileage",
                 "Runtime Hours"),
        purpose="Usage context on the work order detail.",
    ),
    Column(
        LAST_NOTE,
        aliases=("Note", "Notes", "Comment", "Comments", "Latest Note",
                 "Last Comment", "Remarks"),
        purpose="Whether a held work order explains itself.",
    ),
)

COLUMNS_BY_NAME = {column.name: column for column in COLUMNS}
REQUIRED_COLUMNS = tuple(c.name for c in COLUMNS if c.required)
OPTIONAL_COLUMNS = tuple(c.name for c in COLUMNS if not c.required)

DATE_COLUMNS = (
    REQUESTED_DATE, OPENED_DATE, SCHEDULED_DATE, DUE_DATE,
    COMPLETED_DATE, LAST_UPDATE_DATE,
)
NUMERIC_COLUMNS = (ESTIMATED_COST, ACTUAL_COST, METER_READING)
TEXT_COLUMNS = tuple(
    c.name for c in COLUMNS
    if c.name not in DATE_COLUMNS and c.name not in NUMERIC_COLUMNS
)


def _normalize_header(text: str) -> str:
    """Fold a header to a comparison key.

    Case, surrounding and repeated whitespace, and the punctuation that
    exports sprinkle around headers are all ignored, so `WO_Number`,
    `wo number` and `WO Number ` all reach the same column.
    """
    cleaned = []
    for character in str(text):
        if character.isalnum():
            cleaned.append(character.casefold())
        elif character in "_-/.#" or character.isspace():
            cleaned.append(" ")
    return " ".join("".join(cleaned).split())


# Comparison key -> canonical column name. Built once at import.
_ALIAS_INDEX: dict[str, str] = {}
for _column in COLUMNS:
    for _key in _column.keys():
        _ALIAS_INDEX.setdefault(_normalize_header(_key), _column.name)


def canonical_name(header: str) -> str | None:
    """The canonical column a header maps to, or None when unrecognized."""
    return _ALIAS_INDEX.get(_normalize_header(header))


@dataclass
class SchemaReport:
    """What the schema layer made of a workbook's header row.

    Surfaced at import time. A rule that depends on a column the workbook
    does not carry should announce that it cannot run, rather than simply
    finding nothing and looking as though everything is fine.
    """

    mapping: dict[int, str] = field(default_factory=dict)
    """Worksheet column index -> canonical column name."""

    matched: dict[str, str] = field(default_factory=dict)
    """Canonical column name -> the header spelling that supplied it."""

    duplicates: dict[str, list[str]] = field(default_factory=dict)
    """Canonical name -> the later headers that were ignored as repeats."""

    unmapped_headers: list[str] = field(default_factory=list)
    """Headers ServiceLens does not recognize. Kept, never interpreted."""

    @property
    def missing_required(self) -> list[str]:
        return [name for name in REQUIRED_COLUMNS if name not in self.matched]

    @property
    def missing_optional(self) -> list[str]:
        return [name for name in OPTIONAL_COLUMNS if name not in self.matched]

    @property
    def is_usable(self) -> bool:
        return not self.missing_required

    def summary(self) -> str:
        """One line stating what was understood, for logs and the UI."""
        parts = [f"{len(self.matched)} of {len(COLUMNS)} columns recognized"]
        if self.missing_required:
            parts.append("missing required: "
                         + ", ".join(self.missing_required))
        if self.missing_optional:
            parts.append(f"{len(self.missing_optional)} optional not present")
        if self.unmapped_headers:
            parts.append(f"{len(self.unmapped_headers)} unrecognized")
        return "; ".join(parts)


def resolve_headers(headers: list[str]) -> SchemaReport:
    """Map a worksheet header row onto the canonical schema.

    The first header that claims a canonical column wins; later repeats are
    recorded as duplicates rather than silently overwriting the first.
    """
    report = SchemaReport()
    for index, header in enumerate(headers):
        text = str(header).strip()
        if not text:
            continue
        name = canonical_name(text)
        if name is None:
            report.unmapped_headers.append(text)
            continue
        if name in report.matched:
            report.duplicates.setdefault(name, []).append(text)
            continue
        report.mapping[index] = name
        report.matched[name] = text
    return report


def header_score(headers: list[str]) -> int:
    """How many required columns a candidate header row supplies.

    Used to find the real header row in exports that carry title or filter
    rows above it.
    """
    report = resolve_headers(headers)
    return sum(1 for name in REQUIRED_COLUMNS if name in report.matched)
