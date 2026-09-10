"""The application service that ties ingestion and the domain together.

This is the only module that knows the whole pipeline:

    workbook -> normalize -> exclude -> assess -> route -> measure

The user interface calls into here and nothing else. Everything below is
importable and testable without a display.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .config import DEFAULT_POLICY, Policy
from .domain import directives, filters, integrity, metrics as metrics_module
from .domain import routing
from .domain.rules import Assessment, Context, combine, duplicate_ids
from .ingestion.normalization import ImportResult, load_workbook

ALL_RULES = combine(
    integrity.INTEGRITY_RULES,
    directives.DIRECTIVE_RULES,
    name="ServiceLens rules",
)


OUTLIER_GAP_DAYS = 5
"""How far a date must stand clear of the rest before it is an outlier."""

OUTLIER_SHARE = 0.01
"""The largest share of dates that may be discarded as outliers.

Because this is a share and not a count, a small set has no discardable tail
at all: fewer than a hundred dates and the plain maximum is used. A handful
of dates carries no evidence about which of them is anomalous.
"""


def derive_as_of(work_orders, today: date | None = None,
                 outlier_gap_days: int = OUTLIER_GAP_DAYS) -> date:
    """The date the analysis should treat as "now".

    A workbook is a snapshot, so ages are measured against the moment it was
    exported rather than the moment it happens to be opened. That moment is
    not recorded anywhere in the file, so it has to be inferred from the
    dates the workbook contains.

    Taking the plain maximum is wrong, because one mis-keyed year would drag
    the reference date forward and make every other work order look
    artificially young. So two things are ignored:

    * dates that have not happened yet, and
    * a thin tail of dates standing clear of everything else - at most one
      percent of the values, and only while each is more than
      `outlier_gap_days` beyond the next date down.

    A real snapshot's dates cluster tightly at the top, so nothing is
    discarded from healthy data. The discarded dates are not lost: the
    integrity rules report each of them in their own right.
    """
    reference = today or date.today()
    moments = sorted(
        moment
        for work_order in work_orders
        for moment in (work_order.opened_date, work_order.completed_date,
                       work_order.last_update_date)
        if moment is not None and moment <= reference
    )
    if not moments:
        return reference

    discardable = int(len(moments) * OUTLIER_SHARE)
    index = len(moments) - 1
    discarded = 0
    while (index > 0 and discarded < discardable
           and (moments[index] - moments[index - 1]).days > outlier_gap_days):
        index -= 1
        discarded += 1
    return moments[index]


def assess_one(work_order, policy: Policy = DEFAULT_POLICY,
               as_of: date | None = None,
               duplicates: frozenset = frozenset()) -> Assessment:
    """Evaluate, route and summarize a single work order."""
    context = Context(
        work_order=work_order,
        policy=policy,
        as_of=as_of or date.today(),
        duplicate_ids=duplicates,
    )
    findings = ALL_RULES.evaluate(context)
    team = routing.assign_team(work_order)
    queue = routing.assign_queue(findings)
    return Assessment(
        work_order=work_order,
        findings=findings,
        team=team.team,
        queue=queue.queue,
        routing_reason=team.reason,
        age=context.age,
    )


def assess_all(work_orders, policy: Policy = DEFAULT_POLICY,
               as_of: date | None = None) -> list:
    """Evaluate every work order against the full rule set.

    Duplicate identifiers are computed once over the whole set and handed to
    each evaluation, so the rules themselves stay pure.
    """
    reference = as_of or derive_as_of(work_orders)
    duplicates = duplicate_ids(work_orders)
    return [assess_one(w, policy, reference, duplicates) for w in work_orders]


@dataclass
class Analysis:
    """One complete pass over a workbook."""

    imported: ImportResult = field(default_factory=ImportResult)
    exclusions: filters.ExclusionReport = field(
        default_factory=filters.ExclusionReport)
    assessments: list = field(default_factory=list)
    metrics: metrics_module.Metrics = field(
        default_factory=metrics_module.Metrics)
    policy: Policy = DEFAULT_POLICY
    as_of: date = field(default_factory=date.today)

    @property
    def source_path(self) -> str:
        return self.imported.source_path

    def attention(self, limit: int | None = None) -> list:
        """Work orders in the order they should be looked at."""
        ranked = filters.rank_for_attention(
            [a for a in self.assessments if a.findings])
        return ranked[:limit] if limit else ranked

    def in_queue(self, queue: str) -> list:
        return [a for a in self.assessments if a.queue == queue]

    def rule_coverage(self) -> dict:
        """Every rule key mapped to how many times it fired."""
        counts = {rule.key: 0 for rule in ALL_RULES}
        counts.update(self.metrics.rule_counts)
        return counts

    def unfired_rules(self) -> list:
        """Rules that no work order triggered."""
        return sorted(key for key, count in self.rule_coverage().items()
                      if count == 0)


def analyze(work_orders, policy: Policy = DEFAULT_POLICY,
            as_of: date | None = None) -> Analysis:
    """Exclude, assess and measure a set of work orders."""
    exclusions = filters.apply_exclusions(work_orders, policy.exclusions)
    reference = as_of or derive_as_of(exclusions.retained)
    assessments = assess_all(exclusions.retained, policy, reference)
    return Analysis(
        exclusions=exclusions,
        assessments=assessments,
        metrics=metrics_module.compute(assessments),
        policy=policy,
        as_of=reference,
    )


def analyze_workbook(path: str, policy: Policy = DEFAULT_POLICY,
                     sheet_name: str | None = None,
                     as_of: date | None = None) -> Analysis:
    """Read a workbook and run the complete analysis over it."""
    imported = load_workbook(path, sheet_name)
    analysis = analyze(imported.work_orders, policy, as_of)
    analysis.imported = imported
    return analysis
