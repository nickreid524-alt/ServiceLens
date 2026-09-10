"""Shared test helpers."""

from __future__ import annotations

from datetime import date, timedelta

from servicelens.config import DEFAULT_POLICY, Policy
from servicelens.domain.models import (
    AssignmentType,
    Priority,
    Status,
    WorkOrder,
    WorkType,
)
from servicelens.domain.rules import Context

TODAY = date(2026, 6, 15)


def work_order(**overrides) -> WorkOrder:
    """A complete, healthy work order. Override only what a test is about."""
    defaults = dict(
        work_order_id="WO-2026-000001",
        row_number=2,
        asset_id="HVAC-1001",
        asset_name="Rooftop Air Handler",
        site="Riverbend Distribution Center",
        department="Facilities",
        description="Filter change and coil clean",
        work_type=WorkType.CORRECTIVE,
        priority=Priority.NORMAL,
        status=Status.IN_PROGRESS,
        raw_status="In Progress",
        opened_date=TODAY - timedelta(days=3),
        last_update_date=TODAY - timedelta(days=1),
        assignment_type=AssignmentType.INTERNAL,
        assigned_technician="Priya Raghunathan",
        estimated_cost=450.0,
        last_note="Parts ordered, supplier confirmed a two week lead time.",
    )
    defaults.update(overrides)
    return WorkOrder(**defaults)


def context(work=None, policy: Policy = DEFAULT_POLICY, as_of: date = TODAY,
            duplicates=frozenset()) -> Context:
    return Context(
        work_order=work if work is not None else work_order(),
        policy=policy,
        as_of=as_of,
        duplicate_ids=duplicates,
    )


def fired(rule, work=None, **kwargs) -> bool:
    """True when `rule` produces a finding for the given work order."""
    return rule.evaluate(context(work, **kwargs)) is not None


def days_ago(count: int) -> date:
    return TODAY - timedelta(days=count)


def days_ahead(count: int) -> date:
    return TODAY + timedelta(days=count)
