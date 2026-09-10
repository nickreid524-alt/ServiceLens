"""Record integrity rules.

These describe the *record*, not the work. They ask whether what the export
says about a work order is internally consistent enough to be acted on: does
it have an identity, do its dates agree with each other, does its status
agree with its dates.

Integrity findings are never suppressed by age. A record that contradicts
itself is wrong the moment it is created.
"""

from __future__ import annotations

from .models import Domain, Severity, Status
from .rules import Context, Rule, RuleSet


def _fmt(value) -> str:
    return value.isoformat() if value is not None else "blank"


MISSING_WORK_ORDER_ID = Rule(
    key="missing_work_order_id",
    title="No work order identifier",
    severity=Severity.CRITICAL,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: not c.wo.work_order_id.strip(),
    message=lambda c: (
        "This row has no work order number, so it cannot be tracked, "
        "referenced or closed. Restore the identifier at source."
    ),
    basis=lambda c: f"Work Order ID is blank on worksheet row "
                    f"{c.wo.row_number}.",
    explanation="The work order identifier is blank.",
    reads=("Work Order ID",),
)

DUPLICATE_WORK_ORDER = Rule(
    key="duplicate_work_order",
    title="Duplicate work order number",
    severity=Severity.WARNING,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: (
        bool(c.wo.work_order_id.strip())
        and c.wo.work_order_id.strip().casefold() in c.duplicate_ids
    ),
    message=lambda c: (
        "More than one row carries this work order number. Confirm which "
        "record is authoritative and retire the rest."
    ),
    basis=lambda c: f"{c.wo.work_order_id} appears on more than one row of "
                    "this export.",
    explanation="The same identifier appears on more than one row.",
    reads=("Work Order ID",),
)

MISSING_ASSET = Rule(
    key="missing_asset",
    title="No asset recorded",
    severity=Severity.WARNING,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: not c.wo.asset_id.strip(),
    message=lambda c: (
        "No asset is recorded, so this work cannot be costed against "
        "equipment or counted in its maintenance history."
    ),
    basis=lambda c: f"Asset ID is blank on {c.wo.identity}.",
    explanation="The asset identifier is blank.",
    reads=("Asset ID",),
)

MISSING_OPENED_DATE = Rule(
    key="missing_opened_date",
    title="No opened date",
    severity=Severity.WARNING,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: c.wo.opened_date is None,
    message=lambda c: (
        "Without an opened date the work order has no age, so no aging or "
        "response rule can be applied to it."
    ),
    basis=lambda c: "Opened Date is blank, or holds something that is "
                    "not a date.",
    explanation="The opened date is missing or unreadable.",
    reads=("Opened Date",),
)

OPENED_IN_FUTURE = Rule(
    key="opened_in_future",
    title="Opened date in the future",
    severity=Severity.WARNING,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: (
        c.wo.opened_date is not None and c.wo.opened_date > c.as_of),
    message=lambda c: (
        "The opened date is later than the reporting date, so the age of "
        "this work order is meaningless until the date is corrected."
    ),
    basis=lambda c: (
        f"Opened {_fmt(c.wo.opened_date)} against a reporting date of "
        f"{c.as_of.isoformat()}."
    ),
    explanation="The opened date is later than the reporting date.",
    reads=("Opened Date",),
)

COMPLETED_BEFORE_OPENED = Rule(
    key="completed_before_opened",
    title="Completed before it was opened",
    severity=Severity.CRITICAL,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: (
        c.wo.completed_date is not None
        and c.wo.opened_date is not None
        and c.wo.completed_date < c.wo.opened_date
    ),
    message=lambda c: (
        "The completion date precedes the opened date. One of the two is "
        "wrong, and neither can be trusted until that is settled."
    ),
    basis=lambda c: (
        f"Completed {_fmt(c.wo.completed_date)}, opened "
        f"{_fmt(c.wo.opened_date)}."
    ),
    explanation="The completion date is earlier than the opened date.",
    reads=("Opened Date", "Completed Date"),
)

COMPLETED_WITHOUT_DATE = Rule(
    key="completed_without_date",
    title="Completed with no completion date",
    severity=Severity.WARNING,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: (
        c.wo.status is Status.COMPLETED and c.wo.completed_date is None),
    message=lambda c: (
        "The status says the work is finished but no completion date was "
        "recorded, so this work order cannot be counted in any turnaround "
        "measure."
    ),
    basis=lambda c: "Status is Completed and Completed Date is blank.",
    explanation="Status is Completed but the completion date is blank.",
    reads=("Status", "Completed Date"),
)

OPEN_WITH_COMPLETION_DATE = Rule(
    key="open_with_completion_date",
    title="Open but dated complete",
    severity=Severity.WARNING,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: (
        c.wo.completed_date is not None
        and c.wo.status is not None
        and c.wo.status.is_open
    ),
    message=lambda c: (
        "A completion date is recorded while the status is still open. "
        "Close the work order or clear the date."
    ),
    basis=lambda c: (
        f"Status is {c.wo.status.label} with a completion date of "
        f"{_fmt(c.wo.completed_date)}."
    ),
    explanation="A completion date exists while the status is still open.",
    reads=("Status", "Completed Date"),
)

SCHEDULED_BEFORE_OPENED = Rule(
    key="scheduled_before_opened",
    title="Scheduled before it was opened",
    severity=Severity.INFORMATION,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: (
        c.wo.scheduled_date is not None
        and c.wo.opened_date is not None
        and c.wo.scheduled_date < c.wo.opened_date
    ),
    message=lambda c: (
        "The scheduled date precedes the opened date. Confirm the schedule "
        "was not carried over from an earlier record."
    ),
    basis=lambda c: (
        f"Scheduled {_fmt(c.wo.scheduled_date)}, opened "
        f"{_fmt(c.wo.opened_date)}."
    ),
    explanation="The scheduled date is earlier than the opened date.",
    reads=("Opened Date", "Scheduled Date"),
)

UNRECOGNIZED_STATUS = Rule(
    key="unrecognized_status",
    title="Status not recognized",
    severity=Severity.INFORMATION,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: bool(c.wo.raw_status.strip()) and c.wo.status is None,
    message=lambda c: (
        "This status is outside the known vocabulary, so the work order is "
        "treated as open. Map the value or correct it at source."
    ),
    basis=lambda c: f"Status reads '{c.wo.raw_status}'.",
    explanation="The status value is not one ServiceLens recognizes.",
    reads=("Status",),
)

MISSING_STATUS = Rule(
    key="missing_status",
    title="No status recorded",
    severity=Severity.WARNING,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: not c.wo.raw_status.strip(),
    message=lambda c: (
        "No status is recorded, so the work order is treated as open and "
        "will keep aging until someone says otherwise."
    ),
    basis=lambda c: "Status is blank.",
    explanation="The status column is blank.",
    reads=("Status",),
)

NEGATIVE_COST = Rule(
    key="negative_cost",
    title="Negative cost recorded",
    severity=Severity.INFORMATION,
    domain=Domain.DATA_QUALITY,
    applies=lambda c: (
        (c.wo.actual_cost is not None and c.wo.actual_cost < 0)
        or (c.wo.estimated_cost is not None and c.wo.estimated_cost < 0)
    ),
    message=lambda c: (
        "A negative cost is recorded. Confirm whether this is a credit or a "
        "keying error before it reaches a spend total."
    ),
    basis=lambda c: (
        f"Estimated {c.wo.estimated_cost}, actual {c.wo.actual_cost}."),
    explanation="An estimated or actual cost is below zero.",
    reads=("Estimated Cost", "Actual Cost"),
)


INTEGRITY_RULES = RuleSet(
    name="Record integrity",
    rules=(
        MISSING_WORK_ORDER_ID,
        COMPLETED_BEFORE_OPENED,
        DUPLICATE_WORK_ORDER,
        MISSING_ASSET,
        MISSING_OPENED_DATE,
        MISSING_STATUS,
        OPENED_IN_FUTURE,
        COMPLETED_WITHOUT_DATE,
        OPEN_WITH_COMPLETION_DATE,
        SCHEDULED_BEFORE_OPENED,
        UNRECOGNIZED_STATUS,
        NEGATIVE_COST,
    ),
)


def evaluate(context: Context) -> list:
    """Every integrity finding for one work order."""
    return INTEGRITY_RULES.evaluate(context)
