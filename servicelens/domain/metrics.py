"""Aggregate measures over a set of assessed work orders.

Everything a dashboard needs, computed once from a list of assessments and
held as plain numbers and lists. No presentation decisions are made here -
no formatting, no colours, no truncation - so the same numbers can be
rendered on screen, written to a report, or asserted in a test.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import (
    SEVERITY_ORDER,
    Severity,
    Status,
    QUEUES,
    TEAMS,
)

# Aging bands, as (label, lower bound inclusive, upper bound inclusive).
AGING_BANDS = (
    ("0-7 days", 0, 7),
    ("8-14 days", 8, 14),
    ("15-30 days", 15, 30),
    ("31-45 days", 31, 45),
    ("46+ days", 46, None),
)


def band_for(days: int | None) -> str:
    """The aging band a day count falls into."""
    if days is None:
        return "Undated"
    for label, low, high in AGING_BANDS:
        if days >= low and (high is None or days <= high):
            return label
    return "Undated"


def _tally(values) -> dict:
    counts: dict = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _ordered(counts: dict, order) -> list:
    """Counts in a fixed order, then anything unexpected, largest first."""
    known = [(name, counts.get(name, 0)) for name in order]
    extra = sorted(
        ((name, count) for name, count in counts.items() if name not in order),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return known + extra


def _ranked(counts: dict, limit: int | None = None) -> list:
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return ranked[:limit] if limit else ranked


def _median(numbers) -> float:
    ordered = sorted(numbers)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


@dataclass
class TeamSummary:
    """One team's slice of the workload."""

    name: str
    total: int = 0
    open_count: int = 0
    critical: int = 0
    warning: int = 0
    needs_action: int = 0
    average_age: float = 0.0
    oldest_age: int = 0
    cost: float = 0.0


@dataclass
class Metrics:
    """Every headline number, computed once."""

    total: int = 0
    open_count: int = 0
    completed_count: int = 0

    with_findings: int = 0
    clean: int = 0
    findings_total: int = 0
    severity_counts: dict = field(default_factory=dict)
    rule_counts: dict = field(default_factory=dict)
    domain_counts: dict = field(default_factory=dict)

    by_team: list = field(default_factory=list)
    by_queue: list = field(default_factory=list)
    by_status: list = field(default_factory=list)
    by_priority: list = field(default_factory=list)
    by_site: list = field(default_factory=list)
    by_category: list = field(default_factory=list)
    by_work_type: list = field(default_factory=list)
    by_aging_band: list = field(default_factory=list)

    team_summaries: dict = field(default_factory=dict)

    average_open_age: float = 0.0
    median_open_age: float = 0.0
    oldest_open_age: int = 0
    undated: int = 0

    estimated_cost: float = 0.0
    actual_cost: float = 0.0
    open_cost: float = 0.0
    costed_records: int = 0

    @property
    def critical(self) -> int:
        return self.severity_counts.get(Severity.CRITICAL.label, 0)

    @property
    def warning(self) -> int:
        return self.severity_counts.get(Severity.WARNING.label, 0)

    @property
    def information(self) -> int:
        return self.severity_counts.get(Severity.INFORMATION.label, 0)

    @property
    def exception_rate(self) -> float:
        """Share of work orders carrying at least one finding, 0.0 to 1.0."""
        return self.with_findings / self.total if self.total else 0.0

    @property
    def completion_rate(self) -> float:
        return self.completed_count / self.total if self.total else 0.0

    def rules_fired(self) -> list:
        """Every rule that fired at least once, most frequent first."""
        return _ranked(self.rule_counts)


def compute(assessments) -> Metrics:
    """Build the full metric set from assessed work orders."""
    metrics = Metrics(total=len(assessments))

    severity_counts = {severity.label: 0 for severity in SEVERITY_ORDER}
    rule_counts: dict = {}
    domain_counts: dict = {}

    teams: dict = {}
    queues: dict = {}
    statuses: dict = {}
    priorities: dict = {}
    sites: dict = {}
    categories: dict = {}
    work_types: dict = {}
    bands: dict = {}

    open_ages: list = []
    team_records: dict = {}

    for assessment in assessments:
        work_order = assessment.work_order

        if work_order.is_open:
            metrics.open_count += 1
            if assessment.age is not None:
                open_ages.append(assessment.age)
            else:
                metrics.undated += 1
        elif work_order.status is Status.COMPLETED:
            metrics.completed_count += 1

        if assessment.findings:
            metrics.with_findings += 1
            metrics.findings_total += len(assessment.findings)
        else:
            metrics.clean += 1

        for finding in assessment.findings:
            severity_counts[finding.severity.label] = (
                severity_counts.get(finding.severity.label, 0) + 1)
            rule_counts[finding.key] = rule_counts.get(finding.key, 0) + 1
            domain_counts[finding.domain.label] = (
                domain_counts.get(finding.domain.label, 0) + 1)

        teams[assessment.team] = teams.get(assessment.team, 0) + 1
        queues[assessment.queue] = queues.get(assessment.queue, 0) + 1
        team_records.setdefault(assessment.team, []).append(assessment)

        status = work_order.status.label if work_order.status else "(blank)"
        statuses[status] = statuses.get(status, 0) + 1

        priority = (work_order.priority.label
                    if work_order.priority else "(blank)")
        priorities[priority] = priorities.get(priority, 0) + 1

        site = work_order.site or "(blank)"
        sites[site] = sites.get(site, 0) + 1

        category = (work_order.asset_category.label
                    if work_order.asset_category else "(blank)")
        categories[category] = categories.get(category, 0) + 1

        work_type = (work_order.work_type.label
                     if work_order.work_type else "(blank)")
        work_types[work_type] = work_types.get(work_type, 0) + 1

        if work_order.is_open:
            band = band_for(assessment.age)
            bands[band] = bands.get(band, 0) + 1

        if work_order.estimated_cost:
            metrics.estimated_cost += work_order.estimated_cost
        if work_order.actual_cost:
            metrics.actual_cost += work_order.actual_cost
        if work_order.effective_cost:
            metrics.costed_records += 1
            if work_order.is_open:
                metrics.open_cost += work_order.effective_cost

    metrics.severity_counts = severity_counts
    metrics.rule_counts = rule_counts
    metrics.domain_counts = domain_counts

    metrics.by_team = _ordered(teams, TEAMS)
    metrics.by_queue = _ordered(queues, QUEUES)
    metrics.by_status = _ranked(statuses)
    metrics.by_priority = _ranked(priorities)
    metrics.by_site = _ranked(sites)
    metrics.by_category = _ranked(categories)
    metrics.by_work_type = _ranked(work_types)
    metrics.by_aging_band = _ordered(
        bands, tuple(label for label, _, _ in AGING_BANDS) + ("Undated",))

    if open_ages:
        metrics.average_open_age = sum(open_ages) / len(open_ages)
        metrics.median_open_age = _median(open_ages)
        metrics.oldest_open_age = max(open_ages)

    for name, records in team_records.items():
        ages = [a.age for a in records
                if a.work_order.is_open and a.age is not None]
        metrics.team_summaries[name] = TeamSummary(
            name=name,
            total=len(records),
            open_count=sum(1 for a in records if a.work_order.is_open),
            critical=sum(a.count_of(Severity.CRITICAL) for a in records),
            warning=sum(a.count_of(Severity.WARNING) for a in records),
            needs_action=sum(1 for a in records if a.findings),
            average_age=(sum(ages) / len(ages)) if ages else 0.0,
            oldest_age=max(ages) if ages else 0,
            cost=sum(a.work_order.effective_cost for a in records),
        )

    return metrics
