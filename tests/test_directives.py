"""Operational rules, tested at their threshold boundaries."""

import unittest

from servicelens.config import DEFAULT_POLICY
from servicelens.domain import directives
from servicelens.domain.models import (
    AssignmentType,
    Priority,
    Status,
    WorkType,
)

from .support import context, days_ago, days_ahead, fired, work_order

LIMITS = DEFAULT_POLICY.thresholds


class PriorityRuleTests(unittest.TestCase):

    def emergency(self, age):
        return work_order(priority=Priority.EMERGENCY,
                          opened_date=days_ago(age))

    def test_emergency_fires_on_the_threshold_not_before(self):
        threshold = LIMITS.emergency_response_days
        self.assertFalse(fired(directives.EMERGENCY_UNRESOLVED,
                               self.emergency(threshold - 1)))
        self.assertTrue(fired(directives.EMERGENCY_UNRESOLVED,
                              self.emergency(threshold)))

    def test_closed_emergency_work_does_not_fire(self):
        record = work_order(priority=Priority.EMERGENCY,
                            status=Status.COMPLETED,
                            opened_date=days_ago(90),
                            completed_date=days_ago(1))
        self.assertFalse(fired(directives.EMERGENCY_UNRESOLVED, record))

    def test_unassigned_emergency_fires_at_any_age(self):
        record = work_order(priority=Priority.EMERGENCY,
                            opened_date=days_ago(0), assigned_technician="")
        self.assertTrue(fired(directives.EMERGENCY_UNASSIGNED, record))

    def test_an_assigned_emergency_does_not_fire_the_ownership_rule(self):
        self.assertFalse(fired(directives.EMERGENCY_UNASSIGNED,
                               self.emergency(1)))

    def test_safety_work_threshold(self):
        threshold = LIMITS.safety_response_days
        below = work_order(work_type=WorkType.SAFETY,
                           opened_date=days_ago(threshold - 1))
        at = work_order(work_type=WorkType.SAFETY,
                        opened_date=days_ago(threshold))
        self.assertFalse(fired(directives.SAFETY_WORK_OPEN, below))
        self.assertTrue(fired(directives.SAFETY_WORK_OPEN, at))

    def test_high_priority_threshold(self):
        threshold = LIMITS.high_priority_days
        self.assertFalse(fired(
            directives.HIGH_PRIORITY_AGING,
            work_order(priority=Priority.HIGH,
                       opened_date=days_ago(threshold - 1))))
        self.assertTrue(fired(
            directives.HIGH_PRIORITY_AGING,
            work_order(priority=Priority.HIGH,
                       opened_date=days_ago(threshold))))

    def test_normal_priority_never_fires_the_priority_rules(self):
        record = work_order(opened_date=days_ago(200))
        for rule in (directives.EMERGENCY_UNRESOLVED,
                     directives.HIGH_PRIORITY_AGING):
            self.assertFalse(fired(rule, record), rule.key)


class AgingRuleTests(unittest.TestCase):

    def test_aging_and_stale_do_not_overlap(self):
        aging, stale = LIMITS.aging_days, LIMITS.stale_days
        for age, expect_aging, expect_stale in (
                (aging - 1, False, False),
                (aging, True, False),
                (stale - 1, True, False),
                (stale, False, True),
                (stale + 100, False, True)):
            record = work_order(opened_date=days_ago(age))
            self.assertEqual(fired(directives.AGING_WORK_ORDER, record),
                             expect_aging, f"aging at {age} days")
            self.assertEqual(fired(directives.STALE_WORK_ORDER, record),
                             expect_stale, f"stale at {age} days")

    def test_undated_work_cannot_age(self):
        record = work_order(opened_date=None)
        for rule in (directives.AGING_WORK_ORDER, directives.STALE_WORK_ORDER):
            self.assertFalse(fired(rule, record), rule.key)

    def test_no_recent_update_threshold(self):
        threshold = LIMITS.no_update_days
        base = dict(opened_date=days_ago(120))
        self.assertFalse(fired(
            directives.NO_RECENT_UPDATE,
            work_order(last_update_date=days_ago(threshold - 1), **base)))
        self.assertTrue(fired(
            directives.NO_RECENT_UPDATE,
            work_order(last_update_date=days_ago(threshold), **base)))

    def test_closed_work_is_not_chased_for_updates(self):
        record = work_order(status=Status.COMPLETED,
                            opened_date=days_ago(300),
                            completed_date=days_ago(200),
                            last_update_date=days_ago(200))
        self.assertFalse(fired(directives.NO_RECENT_UPDATE, record))


class StatusRuleTests(unittest.TestCase):

    def test_unassigned_work(self):
        self.assertTrue(fired(directives.UNASSIGNED_WORK,
                              work_order(assigned_technician="")))
        self.assertFalse(fired(directives.UNASSIGNED_WORK))

    def test_unassigned_emergency_is_reported_by_its_own_rule_only(self):
        record = work_order(priority=Priority.EMERGENCY,
                            assigned_technician="")
        self.assertFalse(fired(directives.UNASSIGNED_WORK, record))
        self.assertTrue(fired(directives.EMERGENCY_UNASSIGNED, record))

    def test_parts_hold_threshold(self):
        threshold = LIMITS.parts_hold_days
        self.assertFalse(fired(directives.PARTS_HOLD_EXTENDED, work_order(
            status=Status.AWAITING_PARTS,
            opened_date=days_ago(threshold - 1))))
        self.assertTrue(fired(directives.PARTS_HOLD_EXTENDED, work_order(
            status=Status.AWAITING_PARTS, opened_date=days_ago(threshold))))

    def test_hold_without_explanation(self):
        for status in (Status.ON_HOLD, Status.AWAITING_PARTS,
                       Status.AWAITING_VENDOR):
            self.assertTrue(fired(
                directives.HOLD_WITHOUT_EXPLANATION,
                work_order(status=status, last_note="TBD")), status)

    def test_a_hold_with_a_real_note_is_left_alone(self):
        record = work_order(status=Status.ON_HOLD,
                            last_note="Awaiting site access next Tuesday.")
        self.assertFalse(fired(directives.HOLD_WITHOUT_EXPLANATION, record))

    def test_an_in_progress_record_is_not_a_hold(self):
        self.assertFalse(fired(directives.HOLD_WITHOUT_EXPLANATION,
                               work_order(last_note="")))


class VendorRuleTests(unittest.TestCase):

    def external(self, **overrides):
        base = dict(assignment_type=AssignmentType.EXTERNAL,
                    assigned_technician="",
                    vendor="Summit Equipment Services")
        base.update(overrides)
        return work_order(**base)

    def test_vendor_not_named(self):
        self.assertTrue(fired(directives.VENDOR_NOT_NAMED,
                              self.external(vendor="")))
        self.assertFalse(fired(directives.VENDOR_NOT_NAMED, self.external()))

    def test_internal_work_is_never_a_vendor_problem(self):
        for rule in (directives.VENDOR_NOT_NAMED,
                     directives.VENDOR_WORK_OVERDUE,
                     directives.VENDOR_WITHOUT_SCHEDULE):
            self.assertFalse(fired(rule, work_order(opened_date=days_ago(200))),
                             rule.key)

    def test_vendor_overdue_threshold(self):
        threshold = LIMITS.vendor_overdue_days
        self.assertFalse(fired(
            directives.VENDOR_WORK_OVERDUE,
            self.external(opened_date=days_ago(threshold - 1))))
        self.assertTrue(fired(
            directives.VENDOR_WORK_OVERDUE,
            self.external(opened_date=days_ago(threshold))))

    def test_vendor_without_a_booked_date(self):
        self.assertTrue(fired(directives.VENDOR_WITHOUT_SCHEDULE,
                              self.external(scheduled_date=None)))
        self.assertFalse(fired(
            directives.VENDOR_WITHOUT_SCHEDULE,
            self.external(scheduled_date=days_ahead(4))))

    def test_an_unnamed_vendor_is_not_chased_for_a_date(self):
        record = self.external(vendor="", scheduled_date=None)
        self.assertFalse(fired(directives.VENDOR_WITHOUT_SCHEDULE, record))


class CostRuleTests(unittest.TestCase):

    def test_high_estimate_threshold(self):
        limit = LIMITS.cost_review_amount
        self.assertFalse(fired(directives.HIGH_ESTIMATED_COST,
                               work_order(estimated_cost=limit - 0.01)))
        self.assertTrue(fired(directives.HIGH_ESTIMATED_COST,
                              work_order(estimated_cost=limit)))

    def test_closed_work_needs_no_spend_approval(self):
        record = work_order(status=Status.COMPLETED,
                            completed_date=days_ago(1),
                            estimated_cost=90000.0)
        self.assertFalse(fired(directives.HIGH_ESTIMATED_COST, record))

    def test_overrun_needs_both_the_ratio_and_the_minimum(self):
        # Over the ratio but only by $50 - below the minimum variance.
        small = work_order(estimated_cost=100.0, actual_cost=150.0)
        self.assertFalse(fired(directives.COST_OVERRUN, small))
        # Over both.
        large = work_order(estimated_cost=1000.0, actual_cost=1600.0)
        self.assertTrue(fired(directives.COST_OVERRUN, large))

    def test_within_the_ratio_is_not_an_overrun(self):
        record = work_order(estimated_cost=10000.0, actual_cost=11000.0)
        self.assertFalse(fired(directives.COST_OVERRUN, record))

    def test_a_missing_estimate_cannot_be_overrun(self):
        self.assertFalse(fired(directives.COST_OVERRUN,
                               work_order(estimated_cost=None,
                                          actual_cost=9000.0)))

    def test_a_zero_estimate_cannot_be_overrun(self):
        self.assertFalse(fired(directives.COST_OVERRUN,
                               work_order(estimated_cost=0.0,
                                          actual_cost=9000.0)))


class PreventiveRuleTests(unittest.TestCase):

    def preventive(self, **overrides):
        base = dict(work_type=WorkType.PREVENTIVE)
        base.update(overrides)
        return work_order(**base)

    def test_overdue(self):
        self.assertTrue(fired(directives.PM_OVERDUE,
                              self.preventive(due_date=days_ago(1))))

    def test_due_today_is_due_soon_not_overdue(self):
        record = self.preventive(due_date=days_ago(0))
        self.assertFalse(fired(directives.PM_OVERDUE, record))
        self.assertTrue(fired(directives.PM_DUE_SOON, record))

    def test_due_soon_window(self):
        window = LIMITS.pm_due_soon_days
        self.assertTrue(fired(directives.PM_DUE_SOON,
                              self.preventive(due_date=days_ahead(window))))
        self.assertFalse(fired(directives.PM_DUE_SOON,
                               self.preventive(due_date=days_ahead(window + 1))))

    def test_corrective_work_is_never_a_pm_finding(self):
        record = work_order(work_type=WorkType.CORRECTIVE,
                            due_date=days_ago(30))
        for rule in (directives.PM_OVERDUE, directives.PM_DUE_SOON):
            self.assertFalse(fired(rule, record), rule.key)

    def test_no_due_date_means_no_pm_finding(self):
        record = self.preventive(due_date=None)
        for rule in (directives.PM_OVERDUE, directives.PM_DUE_SOON):
            self.assertFalse(fired(rule, record), rule.key)


class PolicyTests(unittest.TestCase):

    def test_thresholds_come_from_the_policy_not_from_the_rule(self):
        record = work_order(opened_date=days_ago(20))
        strict = DEFAULT_POLICY.with_thresholds(stale_days=20)
        self.assertFalse(fired(directives.STALE_WORK_ORDER, record))
        self.assertTrue(fired(directives.STALE_WORK_ORDER, record,
                              policy=strict))

    def test_the_basis_quotes_the_active_threshold(self):
        strict = DEFAULT_POLICY.with_thresholds(stale_days=20)
        finding = directives.STALE_WORK_ORDER.evaluate(
            context(work_order(opened_date=days_ago(25)), policy=strict))
        self.assertIn("20", finding.basis)


class RuleSetTests(unittest.TestCase):

    def test_a_healthy_record_produces_nothing(self):
        self.assertEqual(directives.evaluate(context()), [])

    def test_every_rule_key_is_unique(self):
        keys = list(directives.DIRECTIVE_RULES.keys)
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_rule_explains_itself(self):
        for rule in directives.DIRECTIVE_RULES:
            self.assertTrue(rule.explanation, rule.key)
            self.assertTrue(rule.reads, rule.key)

    def test_every_message_names_an_action(self):
        # A directive is only useful if it asks for something.
        record = work_order(opened_date=days_ago(200), assigned_technician="",
                            last_note="")
        for finding in directives.evaluate(context(record)):
            self.assertTrue(finding.message.strip(), finding.key)
            self.assertTrue(finding.basis.strip(), finding.key)


if __name__ == "__main__":
    unittest.main()
