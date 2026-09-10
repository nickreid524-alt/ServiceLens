"""Operational rules: work that needs someone to do something.

Where integrity rules describe the record, these describe the *work*. Each
one names an action, so a queue is a list of decisions rather than a list of
complaints.

Every threshold comes from `config.Policy`, never from a literal here, so
the operating policy can be changed in one place and every message and
justification follows it.
"""

from __future__ import annotations

from .models import (
    AssignmentType,
    Domain,
    Priority,
    Severity,
    Status,
    WorkType,
)
from .rules import Context, Rule, RuleSet


def _money(value) -> str:
    if value is None:
        return "not recorded"
    return f"{value:,.2f}"


def _age(context: Context) -> str:
    age = context.age
    if age is None:
        return "an unknown number of days"
    return f"{age} day" if age == 1 else f"{age} days"


# --- priority and response ------------------------------------------

EMERGENCY_UNASSIGNED = Rule(
    key="emergency_unassigned",
    title="Emergency work with no owner",
    severity=Severity.CRITICAL,
    domain=Domain.PRIORITY,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.priority is Priority.EMERGENCY
        and not c.wo.has_assignee
    ),
    message=lambda c: (
        "Assign this emergency work order now. Nobody is recorded as "
        "working on it."
    ),
    basis=lambda c: (
        "Priority is Emergency, the work order is open, and no technician "
        "or vendor is recorded."
    ),
    explanation="Priority is Emergency, the work is open, and no technician "
                "or vendor is named. No age threshold applies.",
    reads=("Priority", "Status", "Assigned Technician", "Vendor"),
)

EMERGENCY_UNRESOLVED = Rule(
    key="emergency_unresolved",
    title="Emergency past response time",
    severity=Severity.CRITICAL,
    domain=Domain.PRIORITY,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.priority is Priority.EMERGENCY
        and c.aged_at_least(c.limits.emergency_response_days)
    ),
    message=lambda c: (
        f"Emergency work order open {_age(c)}. Confirm the repair plan and "
        "an expected completion date today."
    ),
    basis=lambda c: (
        f"Open {_age(c)} at Emergency priority. The emergency response "
        f"threshold is {c.limits.emergency_response_days} days."
    ),
    explanation="Emergency priority, still open, and past the emergency "
                "response threshold.",
    reads=("Priority", "Status", "Opened Date"),
)

SAFETY_WORK_OPEN = Rule(
    key="safety_work_open",
    title="Safety work still open",
    severity=Severity.CRITICAL,
    domain=Domain.PRIORITY,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.work_type is WorkType.SAFETY
        and c.aged_at_least(c.limits.safety_response_days)
    ),
    message=lambda c: (
        f"Open {_age(c)}. Confirm whether the asset should stay in "
        "service until this is closed."
    ),
    basis=lambda c: (
        f"Safety work, open {_age(c)}. The safety response threshold is "
        f"{c.limits.safety_response_days} days."
    ),
    explanation="Safety work, still open, and past the safety response "
                "threshold.",
    reads=("Work Type", "Status", "Opened Date"),
)

HIGH_PRIORITY_AGING = Rule(
    key="high_priority_aging",
    title="High priority work aging",
    severity=Severity.WARNING,
    domain=Domain.PRIORITY,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.priority is Priority.HIGH
        and c.aged_at_least(c.limits.high_priority_days)
    ),
    message=lambda c: (
        f"Open {_age(c)} at High priority. Either it still is, and needs "
        "a date, or it is not, and should be downgraded."
    ),
    basis=lambda c: (
        f"High priority, open {_age(c)}. The high priority threshold is "
        f"{c.limits.high_priority_days} days."
    ),
    explanation="High priority, still open, and past the high priority "
                "threshold.",
    reads=("Priority", "Status", "Opened Date"),
)


# --- aging ------------------------------------------------------------

STALE_WORK_ORDER = Rule(
    key="stale_work_order",
    title="Stale work order",
    severity=Severity.CRITICAL,
    domain=Domain.AGING,
    applies=lambda c: c.wo.is_open and c.aged_at_least(c.limits.stale_days),
    message=lambda c: (
        f"Open for {_age(c)}. Decide between completion, reassignment and "
        "closure - this work order is no longer moving."
    ),
    basis=lambda c: (
        f"Open {_age(c)}. The stale threshold is {c.limits.stale_days} "
        "days."
    ),
    explanation="Open beyond the stale threshold.",
    reads=("Status", "Opened Date"),
)

AGING_WORK_ORDER = Rule(
    key="aging_work_order",
    title="Work order aging",
    severity=Severity.WARNING,
    domain=Domain.AGING,
    applies=lambda c: (
        c.wo.is_open
        and c.aged_at_least(c.limits.aging_days)
        and not c.aged_at_least(c.limits.stale_days)
    ),
    message=lambda c: (
        "Post a current status, the next action, and an expected "
        "completion date."
    ),
    basis=lambda c: (
        f"Open {_age(c)}: past the {c.limits.aging_days}-day planning "
        f"threshold, short of the {c.limits.stale_days}-day stale one."
    ),
    explanation="The work order is open between the aging and stale "
                "thresholds.",
    reads=("Status", "Opened Date"),
)

NO_RECENT_UPDATE = Rule(
    key="no_recent_update",
    title="No recent update",
    severity=Severity.WARNING,
    domain=Domain.AGING,
    applies=lambda c: (
        c.wo.is_open
        and c.quiet_days is not None
        and c.quiet_days >= c.limits.no_update_days
    ),
    message=lambda c: (
        f"No activity recorded for {c.quiet_days} days. Confirm the work "
        "order is still live and record where it stands."
    ),
    basis=lambda c: (
        f"The most recent recorded activity was {c.quiet_days} days ago, "
        f"against a threshold of {c.limits.no_update_days} days."
    ),
    explanation="Nothing has been recorded against the work order for at "
                "least the quiet threshold.",
    reads=("Status", "Last Update Date", "Opened Date"),
)


# --- status integrity -------------------------------------------------

UNASSIGNED_WORK = Rule(
    key="unassigned_work",
    title="Work with no owner",
    severity=Severity.WARNING,
    domain=Domain.STATUS,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.priority is not Priority.EMERGENCY
        and not c.wo.has_assignee
    ),
    message=lambda c: (
        "Assign a technician or a vendor. Nobody is recorded as "
        "responsible for this work."
    ),
    basis=lambda c: (
        "The work order is open and no technician or vendor is recorded"
        + (f"; assignment type is {c.wo.assignment_type.label}."
           if c.wo.assignment_type else " and no assignment type is set.")
    ),
    explanation="The work order is open and names neither a technician nor "
                "a vendor. Emergency work is reported under its own rule.",
    reads=("Status", "Assignment Type", "Assigned Technician", "Vendor"),
)

PARTS_HOLD_EXTENDED = Rule(
    key="parts_hold_extended",
    title="Extended parts hold",
    severity=Severity.WARNING,
    domain=Domain.STATUS,
    applies=lambda c: (
        c.wo.status is Status.AWAITING_PARTS
        and c.aged_at_least(c.limits.parts_hold_days)
    ),
    message=lambda c: (
        f"On a parts hold for {_age(c)}. Confirm the order reference, the "
        "expected arrival, and whether a substitute part would release it."
    ),
    basis=lambda c: (
        f"Awaiting Parts, open {_age(c)}. The parts hold threshold is "
        f"{c.limits.parts_hold_days} days."
    ),
    explanation="Status is Awaiting Parts beyond the parts hold threshold.",
    reads=("Status", "Opened Date"),
)

HOLD_WITHOUT_EXPLANATION = Rule(
    key="hold_without_explanation",
    title="Hold with no explanation",
    severity=Severity.INFORMATION,
    domain=Domain.STATUS,
    applies=lambda c: (
        c.wo.status in (Status.ON_HOLD, Status.AWAITING_PARTS,
                        Status.AWAITING_VENDOR)
        and not c.wo.has_usable_note(c.limits.note_minimum_characters)
    ),
    message=lambda c: (
        "Record what this work order is waiting for and who is chasing it."
    ),
    basis=lambda c: (
        f"Status is {c.wo.status.label} and the note is "
        + ("blank." if not c.wo.last_note.strip()
           else f"'{c.wo.last_note}', which is shorter than the "
                f"{c.limits.note_minimum_characters}-character minimum or a "
                "known placeholder.")
    ),
    explanation="The work order is on a hold status and carries no note "
                "beyond a placeholder.",
    reads=("Status", "Last Note"),
)


# --- vendor -----------------------------------------------------------

VENDOR_NOT_NAMED = Rule(
    key="vendor_not_named",
    title="External work with no vendor",
    severity=Severity.WARNING,
    domain=Domain.VENDOR,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.assignment_type is AssignmentType.EXTERNAL
        and not c.wo.vendor.strip()
    ),
    message=lambda c: (
        "This work is marked external but names no vendor. Record who is "
        "carrying it out."
    ),
    basis=lambda c: "Assignment Type is External and Vendor is blank.",
    explanation="Assignment Type is External while the vendor is blank.",
    reads=("Assignment Type", "Vendor", "Status"),
)

VENDOR_WORK_OVERDUE = Rule(
    key="vendor_work_overdue",
    title="Vendor work overdue",
    severity=Severity.WARNING,
    domain=Domain.VENDOR,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.assignment_type is AssignmentType.EXTERNAL
        and c.aged_at_least(c.limits.vendor_overdue_days)
    ),
    message=lambda c: (
        f"With the vendor for {_age(c)}. Chase a completion date or bring "
        "the work back in house."
    ),
    basis=lambda c: (
        f"Contracted out and open {_age(c)}. The vendor threshold is "
        f"{c.limits.vendor_overdue_days} days"
        + (f"; vendor is {c.wo.vendor}." if c.wo.vendor.strip() else ".")
    ),
    explanation="Contracted work open beyond the vendor threshold.",
    reads=("Assignment Type", "Status", "Opened Date", "Vendor"),
)

VENDOR_WITHOUT_SCHEDULE = Rule(
    key="vendor_without_schedule",
    title="Vendor work with no date booked",
    severity=Severity.INFORMATION,
    domain=Domain.VENDOR,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.assignment_type is AssignmentType.EXTERNAL
        and c.wo.vendor.strip() != ""
        and c.wo.scheduled_date is None
    ),
    message=lambda c: (
        f"Book a date with {c.wo.vendor}, or record the one already agreed."
    ),
    basis=lambda c: (
        f"Assignment Type is External, vendor is {c.wo.vendor}, and "
        "Scheduled Date is blank."
    ),
    explanation="External work names a vendor but has no scheduled date.",
    reads=("Assignment Type", "Vendor", "Scheduled Date", "Status"),
)


# --- cost -------------------------------------------------------------

HIGH_ESTIMATED_COST = Rule(
    key="high_estimated_cost",
    title="Spend needs approval",
    severity=Severity.WARNING,
    domain=Domain.COST,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.estimated_cost is not None
        and c.wo.estimated_cost >= c.limits.cost_review_amount
    ),
    message=lambda c: (
        f"Estimated at {_money(c.wo.estimated_cost)}. Confirm the spend is "
        "approved before the work proceeds."
    ),
    basis=lambda c: (
        f"Estimated cost {_money(c.wo.estimated_cost)} is at or above the "
        f"review threshold of {_money(c.limits.cost_review_amount)}."
    ),
    explanation="The estimated cost is at or above the review threshold.",
    reads=("Estimated Cost", "Status"),
)

COST_OVERRUN = Rule(
    key="cost_overrun",
    title="Cost exceeds estimate",
    severity=Severity.WARNING,
    domain=Domain.COST,
    applies=lambda c: (
        c.wo.actual_cost is not None
        and c.wo.estimated_cost is not None
        and c.wo.estimated_cost > 0
        and c.wo.actual_cost > c.wo.estimated_cost * c.limits.cost_overrun_ratio
        and (c.wo.actual_cost - c.wo.estimated_cost)
        >= c.limits.cost_overrun_minimum
    ),
    message=lambda c: (
        f"Actual cost {_money(c.wo.actual_cost)} against an estimate of "
        f"{_money(c.wo.estimated_cost)}. Confirm the variance is understood."
    ),
    basis=lambda c: (
        f"Actual exceeds estimate by "
        f"{_money(c.wo.actual_cost - c.wo.estimated_cost)}, more than the "
        f"{c.limits.cost_overrun_ratio:.2f}x ratio and the "
        f"{_money(c.limits.cost_overrun_minimum)} minimum variance."
    ),
    explanation="The actual cost exceeds the estimate by more than both the "
                "overrun ratio and the minimum variance.",
    reads=("Estimated Cost", "Actual Cost"),
)


# --- preventive maintenance -------------------------------------------

PM_OVERDUE = Rule(
    key="pm_overdue",
    title="Preventive maintenance overdue",
    severity=Severity.WARNING,
    domain=Domain.PREVENTIVE,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.work_type is WorkType.PREVENTIVE
        and c.days_until_due() is not None
        and c.days_until_due() < 0
    ),
    message=lambda c: (
        f"Preventive maintenance is {abs(c.days_until_due())} days past its "
        "due date. Reschedule it or record why it slipped."
    ),
    basis=lambda c: (
        f"Work Type is Preventive and the due date "
        f"{c.wo.due_date.isoformat()} has passed."
    ),
    explanation="Preventive work is open past its due date.",
    reads=("Work Type", "Due Date", "Status"),
)

PM_DUE_SOON = Rule(
    key="pm_due_soon",
    title="Preventive maintenance due soon",
    severity=Severity.INFORMATION,
    domain=Domain.PREVENTIVE,
    applies=lambda c: (
        c.wo.is_open
        and c.wo.work_type is WorkType.PREVENTIVE
        and c.days_until_due() is not None
        and 0 <= c.days_until_due() <= c.limits.pm_due_soon_days
    ),
    message=lambda c: (
        f"Due in {c.days_until_due()} days. Confirm parts and labour are "
        "booked."
    ),
    basis=lambda c: (
        f"Work Type is Preventive and the due date "
        f"{c.wo.due_date.isoformat()} falls within the "
        f"{c.limits.pm_due_soon_days}-day window."
    ),
    explanation="Preventive work is due within the due-soon window.",
    reads=("Work Type", "Due Date", "Status"),
)


DIRECTIVE_RULES = RuleSet(
    name="Operational directives",
    rules=(
        EMERGENCY_UNASSIGNED,
        EMERGENCY_UNRESOLVED,
        SAFETY_WORK_OPEN,
        STALE_WORK_ORDER,
        HIGH_PRIORITY_AGING,
        AGING_WORK_ORDER,
        NO_RECENT_UPDATE,
        UNASSIGNED_WORK,
        PARTS_HOLD_EXTENDED,
        VENDOR_NOT_NAMED,
        VENDOR_WORK_OVERDUE,
        HIGH_ESTIMATED_COST,
        COST_OVERRUN,
        PM_OVERDUE,
        HOLD_WITHOUT_EXPLANATION,
        VENDOR_WITHOUT_SCHEDULE,
        PM_DUE_SOON,
    ),
)


def evaluate(context: Context) -> list:
    """Every directive finding for one work order."""
    return DIRECTIVE_RULES.evaluate(context)
