"""Routing: who owns the work, and what should happen to it next.

Two independent decisions, deliberately kept apart:

**Team** is ownership. It answers "whose work is this?" and is derived from
the record itself - who it is contracted to, who the export says owns it, and
what kind of asset it is.

**Queue** is action. It answers "what should happen to this next?" and is
derived from the *findings*, not the record. A queue is therefore a work
list: everything in Vendor Follow-up needs a vendor chased, everything in
Data Quality needs a record fixed.

Because queue routing reads a finding's `Domain` rather than its rule key, a
new rule joins the right queue simply by declaring which domain it belongs
to. Nothing in this module has to change.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    AssetCategory,
    AssignmentType,
    Domain,
    Severity,
    WorkOrder,
    QUEUE_COST,
    QUEUE_DATA_QUALITY,
    QUEUE_IMMEDIATE,
    QUEUE_PLANNING,
    QUEUE_PREVENTIVE,
    QUEUE_ROUTINE,
    QUEUE_VENDOR,
    TEAM_CONTRACTED,
    TEAM_ELECTRICAL,
    TEAM_FACILITIES,
    TEAM_FLEET,
    TEAM_MECHANICAL,
    TEAM_OPERATIONS_REVIEW,
    TEAMS,
)

# Which team maintains which class of asset. This is the fallback used when
# the export does not say who owns the work.
CATEGORY_TEAM = {
    AssetCategory.VEHICLE: TEAM_FLEET,
    AssetCategory.ELECTRICAL: TEAM_ELECTRICAL,
    AssetCategory.HVAC: TEAM_FACILITIES,
    AssetCategory.PLUMBING: TEAM_FACILITIES,
    AssetCategory.GROUNDS: TEAM_FACILITIES,
    AssetCategory.MATERIAL_HANDLING: TEAM_MECHANICAL,
    AssetCategory.PRODUCTION: TEAM_MECHANICAL,
}

_TEAM_LOOKUP = {team.casefold(): team for team in TEAMS}

# Domain -> queue, consulted in this order once severity has been checked.
DOMAIN_QUEUE = (
    (Domain.DATA_QUALITY, QUEUE_DATA_QUALITY),
    (Domain.VENDOR, QUEUE_VENDOR),
    (Domain.COST, QUEUE_COST),
    (Domain.PREVENTIVE, QUEUE_PREVENTIVE),
)


@dataclass(frozen=True, slots=True)
class TeamAssignment:
    """The ownership decision, with the reason it was reached."""

    team: str
    rule: str
    reason: str
    needs_review: bool = False


@dataclass(frozen=True, slots=True)
class QueueAssignment:
    """The action decision, with the reason it was reached."""

    queue: str
    rule: str
    reason: str


def recognized_team(value: str) -> str:
    """The canonical team name for a reported value, or '' if unknown."""
    return _TEAM_LOOKUP.get(" ".join(str(value).split()).casefold(), "")


def assign_team(work_order: WorkOrder) -> TeamAssignment:
    """Decide which team owns a work order. First match wins."""

    # 1. Contracted work belongs to the team that manages contracts,
    #    whatever the asset is, because that is who chases the vendor.
    if work_order.assignment_type is AssignmentType.EXTERNAL:
        vendor = work_order.vendor.strip()
        return TeamAssignment(
            TEAM_CONTRACTED,
            "external_assignment",
            f"Assignment Type is External, so Contracted Services owns it"
            + (f"; the work is with {vendor}." if vendor
               else ", though no vendor is named yet."),
        )

    # 2. The export's own team, when it is one ServiceLens knows.
    reported = recognized_team(work_order.assigned_team)
    if reported:
        return TeamAssignment(
            reported,
            "reported_team",
            f"The export assigns this work order to {reported}.",
        )

    # 3. Otherwise infer ownership from the class of asset.
    if work_order.asset_category is not None:
        team = CATEGORY_TEAM.get(work_order.asset_category)
        if team:
            return TeamAssignment(
                team,
                "asset_category",
                f"No team is recorded, so ownership follows the asset "
                f"category {work_order.asset_category.label}, which "
                f"{team} maintains.",
            )

    # 4. Nothing to go on.
    unknown = work_order.assigned_team.strip()
    if unknown:
        return TeamAssignment(
            TEAM_OPERATIONS_REVIEW,
            "unrecognized_team",
            f"Team '{unknown}' is not a recognized team and the asset "
            "category does not identify an owner, so ownership is unresolved.",
            needs_review=True,
        )
    return TeamAssignment(
        TEAM_OPERATIONS_REVIEW,
        "no_owner",
        "Neither a team nor an asset category is recorded, so ownership "
        "cannot be determined from this record.",
        needs_review=True,
    )


def assign_queue(findings) -> QueueAssignment:
    """Decide what should happen next, from the findings alone.

    Severity outranks domain: anything critical is an immediate review
    regardless of what kind of problem it is.
    """
    if not findings:
        return QueueAssignment(
            QUEUE_ROUTINE,
            "no_findings",
            "No rule raised anything against this work order.",
        )

    critical = [f for f in findings if f.severity is Severity.CRITICAL]
    if critical:
        titles = ", ".join(sorted({f.title for f in critical}))
        return QueueAssignment(
            QUEUE_IMMEDIATE,
            "critical_finding",
            f"Carries a critical finding ({titles}), which outranks every "
            "other queue.",
        )

    present = {f.domain for f in findings}
    for domain, queue in DOMAIN_QUEUE:
        if domain in present:
            matched = ", ".join(
                sorted({f.title for f in findings if f.domain is domain}))
            return QueueAssignment(
                queue,
                f"domain_{domain.name.casefold()}",
                f"The most specific finding is a {domain.label} one "
                f"({matched}).",
            )

    titles = ", ".join(sorted({f.title for f in findings}))
    return QueueAssignment(
        QUEUE_PLANNING,
        "planning_finding",
        f"Needs planning attention ({titles}) but nothing more urgent.",
    )
