"""The rule framework.

A rule is data, not a branch in a function. Each one declares what it is
called, how serious it is, which domain it belongs to, the condition that
fires it, the action it asks for, and the evidence behind that action.

Keeping rules declarative buys three things:

* the rule catalogue can be rendered to the user without duplicating it,
* every finding can explain itself in terms of the record and the threshold,
* a new rule is one entry in a tuple, testable on its own.

The rules themselves live in `integrity.py` (is this record self-consistent?)
and `directives.py` (does this work need someone to act?).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from ..config import DEFAULT_POLICY, Policy, Thresholds
from .models import Domain, Severity, WorkOrder


@dataclass(frozen=True, slots=True)
class Context:
    """One work order plus everything a rule needs to judge it.

    `duplicate_ids` is the only corpus-level fact a rule can see. It is
    passed in rather than discovered, so every rule stays a pure function of
    its inputs and can be tested with a single record.
    """

    work_order: WorkOrder
    policy: Policy = DEFAULT_POLICY
    as_of: date = date.today()
    duplicate_ids: frozenset = frozenset()

    @property
    def wo(self) -> WorkOrder:
        return self.work_order

    @property
    def limits(self) -> Thresholds:
        return self.policy.thresholds

    @property
    def age(self) -> int | None:
        """Days open, or None when the record carries no opened date."""
        return self.work_order.age_days(self.as_of)

    @property
    def quiet_days(self) -> int | None:
        """Days since the last recorded activity."""
        return self.work_order.days_since_update(self.as_of)

    def aged_at_least(self, days: int) -> bool:
        """True when the work order is open and has reached `days` of age."""
        age = self.age
        return age is not None and age >= days

    def days_until_due(self) -> int | None:
        due = self.work_order.due_date
        if due is None:
            return None
        return (due - self.as_of).days


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing a rule noticed, with the reason it noticed it."""

    key: str
    title: str
    severity: Severity
    domain: Domain
    message: str
    basis: str
    work_order_id: str = ""

    @property
    def sort_key(self) -> tuple:
        return (self.severity.rank, self.domain.value, self.key)

    def __str__(self) -> str:
        return f"[{self.severity.label}] {self.title}: {self.message}"


@dataclass(frozen=True, slots=True)
class Rule:
    """A declarative check over one work order."""

    key: str
    title: str
    severity: Severity
    domain: Domain
    applies: Callable[[Context], bool]
    message: Callable[[Context], str]
    basis: Callable[[Context], str]
    explanation: str = ""
    reads: tuple = ()

    def evaluate(self, context: Context) -> Finding | None:
        """The finding this rule produces for `context`, or None."""
        if not self.applies(context):
            return None
        return Finding(
            key=self.key,
            title=self.title,
            severity=self.severity,
            domain=self.domain,
            message=self.message(context),
            basis=self.basis(context),
            work_order_id=context.work_order.work_order_id,
        )


@dataclass(frozen=True)
class RuleSet:
    """An ordered, named collection of rules."""

    name: str
    rules: tuple = ()

    def __iter__(self):
        return iter(self.rules)

    def __len__(self) -> int:
        return len(self.rules)

    @property
    def keys(self) -> tuple:
        return tuple(rule.key for rule in self.rules)

    def by_key(self, key: str) -> Rule | None:
        for rule in self.rules:
            if rule.key == key:
                return rule
        return None

    def evaluate(self, context: Context) -> list[Finding]:
        """Every finding this rule set produces, most severe first."""
        findings = [f for f in (rule.evaluate(context) for rule in self.rules)
                    if f is not None]
        findings.sort(key=lambda finding: finding.sort_key)
        return findings

    def catalogue(self) -> list[dict]:
        """The rule set as plain data, for display and documentation."""
        return [
            {
                "key": rule.key,
                "title": rule.title,
                "severity": rule.severity.label,
                "domain": rule.domain.label,
                "explanation": rule.explanation,
                "reads": list(rule.reads),
            }
            for rule in self.rules
        ]


def combine(*rule_sets: RuleSet, name: str = "All rules") -> RuleSet:
    """One rule set containing every rule from the given sets, in order."""
    rules: list[Rule] = []
    for rule_set in rule_sets:
        rules.extend(rule_set.rules)
    return RuleSet(name=name, rules=tuple(rules))


def duplicate_ids(work_orders) -> frozenset:
    """Identifiers that appear on more than one record.

    Comparison ignores case and surrounding space, because a duplicate that
    differs only in spacing is still a duplicate. Blank identifiers are not
    duplicates of each other - that is a separate, and different, problem.
    """
    seen: dict[str, int] = {}
    for work_order in work_orders:
        key = work_order.work_order_id.strip().casefold()
        if not key:
            continue
        seen[key] = seen.get(key, 0) + 1
    return frozenset(key for key, count in seen.items() if count > 1)


@dataclass
class Assessment:
    """The complete verdict on one work order."""

    work_order: WorkOrder
    findings: list = field(default_factory=list)
    team: str = ""
    queue: str = ""
    routing_reason: str = ""
    age: int | None = None

    @property
    def severity(self) -> Severity | None:
        """The most serious severity present, or None when clean."""
        if not self.findings:
            return None
        return min((f.severity for f in self.findings),
                   key=lambda s: s.rank)

    @property
    def is_clean(self) -> bool:
        return not self.findings

    def count_of(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity is severity)

    def has(self, key: str) -> bool:
        return any(f.key == key for f in self.findings)

    def domains(self) -> set:
        return {f.domain for f in self.findings}

    def top(self, limit: int) -> list:
        """The most serious findings, for a compact row."""
        return self.findings[:limit]
