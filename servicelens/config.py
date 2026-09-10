"""Operating policy for ServiceLens.

Every threshold the rule engine uses lives here as data, so the policy can be
read, reviewed and changed in one place without touching rule code.

The values below are a worked example of a maintenance policy, not a
recommendation. They exist so the demonstration corpus exercises every rule.
A real deployment would replace them with its own service levels.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Thresholds:
    """Day counts and money limits that decide when a rule fires."""

    # -- responsiveness ------------------------------------------------
    emergency_response_days: int = 3
    """An Emergency work order should be resolved within this many days."""

    safety_response_days: int = 5
    """Safety work should not sit open longer than this."""

    high_priority_days: int = 7
    """High priority work needs a decision by this age."""

    # -- ageing --------------------------------------------------------
    aging_days: int = 14
    """Open work becomes a planning concern at this age."""

    stale_days: int = 45
    """Open work becomes a management escalation at this age."""

    no_update_days: int = 21
    """Work with no recorded update for this long has gone quiet."""

    # -- holds ---------------------------------------------------------
    parts_hold_days: int = 21
    """Awaiting Parts stops being normal at this age."""

    # -- external work -------------------------------------------------
    vendor_overdue_days: int = 30
    """Vendor work open longer than this needs chasing."""

    # -- preventive maintenance ---------------------------------------
    pm_due_soon_days: int = 7
    """A preventive task due within this window is worth surfacing."""

    # -- cost ----------------------------------------------------------
    cost_review_amount: float = 5000.0
    """Estimated cost at or above this needs a spend decision."""

    cost_overrun_ratio: float = 1.25
    """Actual cost above estimate x this ratio counts as an overrun."""

    cost_overrun_minimum: float = 250.0
    """Overruns smaller than this are noise and are not reported."""

    # -- record quality ------------------------------------------------
    note_minimum_characters: int = 12
    """A note shorter than this carries no usable information."""


@dataclass(frozen=True)
class ExclusionPolicy:
    """What is removed from analysis before anything is counted.

    Exclusions are deliberately configuration rather than code. Nothing is
    excluded by default except cancelled work, and every exclusion is counted
    and reconciled so a record can never vanish silently.
    """

    exclude_cancelled: bool = True
    """Cancelled work orders describe work that will not happen."""

    excluded_statuses: frozenset[str] = frozenset()
    """Extra status values to drop, compared case-insensitively."""

    excluded_asset_ids: frozenset[str] = frozenset()
    """Placeholder or test asset identifiers used by the source system."""

    excluded_sites: frozenset[str] = frozenset()
    """Sites outside the scope of this analysis."""


@dataclass(frozen=True)
class Policy:
    """The complete operating policy: thresholds plus exclusions."""

    thresholds: Thresholds = field(default_factory=Thresholds)
    exclusions: ExclusionPolicy = field(default_factory=ExclusionPolicy)

    def with_thresholds(self, **changes) -> "Policy":
        """A copy of this policy with individual thresholds overridden."""
        return replace(self, thresholds=replace(self.thresholds, **changes))

    def with_exclusions(self, **changes) -> "Policy":
        """A copy of this policy with individual exclusions overridden."""
        return replace(self, exclusions=replace(self.exclusions, **changes))


DEFAULT_POLICY = Policy()

MAX_FINDINGS_DISPLAYED = 3
"""How many findings a compact row shows. All findings are always retained."""
