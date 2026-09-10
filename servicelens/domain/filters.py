"""Exclusions, search and filtering.

Two separate ideas live here.

**Exclusion** happens once, before anything is counted, and is reconciled:
every row read is either excluded for a stated reason or retained, and the
two always add back up to the total. A record can never disappear quietly.

**Filtering** happens repeatedly, while someone is looking at the data. It
changes what is on screen and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import DEFAULT_POLICY, ExclusionPolicy
from .models import Status, WorkOrder

REASON_CANCELLED = "Cancelled work"
REASON_STATUS = "Excluded status"
REASON_ASSET = "Excluded asset"
REASON_SITE = "Excluded site"


@dataclass
class ExclusionReport:
    """What was removed before analysis, and why.

    `reconciles()` is the guarantee: rows in equals rows excluded plus rows
    retained. Every screen that shows a total can state that it balances.
    """

    rows_in: int = 0
    retained: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    excluded_ids: dict = field(default_factory=dict)

    @property
    def total_excluded(self) -> int:
        return sum(self.counts.values())

    @property
    def retained_count(self) -> int:
        return len(self.retained)

    def reconciles(self) -> bool:
        return self.rows_in == self.total_excluded + self.retained_count

    def stages(self) -> list:
        """Every exclusion reason with its count, in a stable order."""
        order = (REASON_CANCELLED, REASON_STATUS, REASON_ASSET, REASON_SITE)
        return [(reason, self.counts.get(reason, 0)) for reason in order]

    def summary(self) -> str:
        parts = [f"{self.rows_in} read", f"{self.retained_count} retained"]
        for reason, count in self.stages():
            if count:
                parts.append(f"{count} {reason.casefold()}")
        return ", ".join(parts)


def _fold(values) -> frozenset:
    return frozenset(v.strip().casefold() for v in values if v.strip())


def apply_exclusions(work_orders,
                     policy: ExclusionPolicy | None = None) -> ExclusionReport:
    """Split work orders into retained and excluded, counting each reason.

    Reasons are checked in a fixed order and a record is counted once, under
    the first reason that matched, so the counts never double-count.
    """
    rules = policy if policy is not None else DEFAULT_POLICY.exclusions
    statuses = _fold(rules.excluded_statuses)
    assets = _fold(rules.excluded_asset_ids)
    sites = _fold(rules.excluded_sites)

    report = ExclusionReport(rows_in=len(work_orders))

    def drop(work_order: WorkOrder, reason: str) -> None:
        report.counts[reason] = report.counts.get(reason, 0) + 1
        report.excluded_ids.setdefault(reason, []).append(work_order.identity)

    for work_order in work_orders:
        if rules.exclude_cancelled and work_order.status is Status.CANCELLED:
            drop(work_order, REASON_CANCELLED)
            continue
        if statuses and work_order.raw_status.strip().casefold() in statuses:
            drop(work_order, REASON_STATUS)
            continue
        if assets and work_order.asset_id.strip().casefold() in assets:
            drop(work_order, REASON_ASSET)
            continue
        if sites and work_order.site.strip().casefold() in sites:
            drop(work_order, REASON_SITE)
            continue
        report.retained.append(work_order)

    return report


# --- interactive filtering -------------------------------------------

SEARCH_FIELDS = (
    "work_order_id", "asset_id", "asset_name", "description", "site",
    "department", "assigned_technician", "vendor", "last_note",
)


def matches_search(work_order: WorkOrder, term: str) -> bool:
    """True when every word of `term` appears somewhere in the record.

    All words must match, but they may match different fields, so
    "pump riverbend" finds pump work at Riverbend without needing to know
    which column holds which.
    """
    words = term.casefold().split()
    if not words:
        return True
    haystack = " ".join(
        str(getattr(work_order, name, "")) for name in SEARCH_FIELDS
    ).casefold()
    return all(word in haystack for word in words)


@dataclass(frozen=True)
class Filter:
    """A set of interactive filters. Empty fields mean "no restriction"."""

    search: str = ""
    teams: frozenset = frozenset()
    queues: frozenset = frozenset()
    statuses: frozenset = frozenset()
    priorities: frozenset = frozenset()
    sites: frozenset = frozenset()
    severities: frozenset = frozenset()
    open_only: bool = False
    with_findings_only: bool = False

    def matches(self, assessment) -> bool:
        work_order = assessment.work_order
        if self.open_only and not work_order.is_open:
            return False
        if self.with_findings_only and assessment.is_clean:
            return False
        if self.teams and assessment.team not in self.teams:
            return False
        if self.queues and assessment.queue not in self.queues:
            return False
        if self.statuses:
            label = work_order.status.label if work_order.status else ""
            if label not in self.statuses:
                return False
        if self.priorities:
            label = work_order.priority.label if work_order.priority else ""
            if label not in self.priorities:
                return False
        if self.sites and work_order.site not in self.sites:
            return False
        if self.severities:
            severity = assessment.severity
            label = severity.label if severity else ""
            if label not in self.severities:
                return False
        if self.search and not matches_search(work_order, self.search):
            return False
        return True


def apply_filter(assessments, criteria: Filter) -> list:
    """Every assessment matching the criteria, in the order given."""
    return [a for a in assessments if criteria.matches(a)]


def rank_for_attention(assessments) -> list:
    """Assessments ordered by how much they need a human.

    Severity first, then how many things are wrong, then age, then priority.
    The identifier breaks remaining ties so the order is never arbitrary.
    """
    def key(assessment):
        severity = assessment.severity
        return (
            severity.rank if severity else 99,
            -len(assessment.findings),
            -(assessment.age if assessment.age is not None else 0),
            assessment.work_order.priority.rank
            if assessment.work_order.priority else 99,
            assessment.work_order.work_order_id,
        )

    return sorted(assessments, key=key)
