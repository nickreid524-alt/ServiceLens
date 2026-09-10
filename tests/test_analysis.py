"""The end-to-end analysis service."""

import unittest
from datetime import date

from servicelens import analysis
from servicelens.config import DEFAULT_POLICY
from servicelens.domain.models import (
    Priority,
    Status,
    QUEUE_IMMEDIATE,
    QUEUE_ROUTINE,
)
from servicelens.domain.rules import duplicate_ids

from .support import TODAY, days_ago, days_ahead, work_order


class DuplicateIdTests(unittest.TestCase):

    def test_finds_repeats(self):
        records = [work_order(work_order_id="WO-1"),
                   work_order(work_order_id="WO-1"),
                   work_order(work_order_id="WO-2")]
        self.assertEqual(duplicate_ids(records), frozenset({"wo-1"}))

    def test_spacing_and_case_do_not_hide_a_duplicate(self):
        records = [work_order(work_order_id="WO-1"),
                   work_order(work_order_id=" wo-1 ")]
        self.assertEqual(duplicate_ids(records), frozenset({"wo-1"}))

    def test_blanks_are_not_duplicates(self):
        records = [work_order(work_order_id=""), work_order(work_order_id="")]
        self.assertEqual(duplicate_ids(records), frozenset())


class ReferenceDateTests(unittest.TestCase):

    def dated(self, opened, **overrides):
        """A record whose only date is the one under test."""
        return work_order(opened_date=opened, last_update_date=None,
                          completed_date=None, **overrides)

    def cluster(self, newest, size=200):
        """A dense run of dates, as a real snapshot produces."""
        return [self.dated(days_ago(newest + n)) for n in range(size)]

    def test_uses_the_latest_date_in_the_data(self):
        records = self.cluster(4) + [self.dated(days_ago(30))]
        self.assertEqual(analysis.derive_as_of(records, TODAY), days_ago(4))

    def test_activity_dates_count_as_well_as_opened_dates(self):
        records = [work_order(opened_date=days_ago(30),
                              last_update_date=days_ago(2),
                              completed_date=None)]
        self.assertEqual(analysis.derive_as_of(records, TODAY), days_ago(2))

    def test_a_small_set_is_never_trimmed(self):
        # With only a few dates there is no evidence about which is odd.
        records = [self.dated(days_ago(90)), self.dated(days_ago(1))]
        self.assertEqual(analysis.derive_as_of(records, TODAY), days_ago(1))

    def test_dates_that_have_not_happened_yet_are_ignored(self):
        records = self.cluster(4) + [self.dated(days_ahead(400))]
        self.assertEqual(analysis.derive_as_of(records, TODAY), days_ago(4))

    def test_an_isolated_outlier_does_not_drag_the_date_forward(self):
        # One mis-keyed date, far clear of a dense cluster, is discarded.
        records = self.cluster(30) + [self.dated(days_ago(1))]
        self.assertEqual(analysis.derive_as_of(records, TODAY), days_ago(30))

    def test_a_dense_run_is_never_treated_as_outliers(self):
        records = self.cluster(0, size=60)
        self.assertEqual(analysis.derive_as_of(records, TODAY), TODAY)

    def test_no_more_than_a_thin_tail_is_ever_discarded(self):
        # Widely spaced dates are the data, not outliers. With 300 values
        # at most three may be trimmed, so the fourth is the furthest the
        # reference date can ever be pulled back.
        records = [self.dated(days_ago(n * 40)) for n in range(300)]
        self.assertEqual(analysis.derive_as_of(records, TODAY),
                         days_ago(3 * 40))

    def test_falls_back_to_today_when_nothing_is_dated(self):
        records = [self.dated(None)]
        self.assertEqual(analysis.derive_as_of(records, TODAY), TODAY)

    def test_an_empty_set_falls_back_to_today(self):
        self.assertEqual(analysis.derive_as_of([], TODAY), TODAY)


class AssessmentTests(unittest.TestCase):

    def test_a_healthy_record_is_clean_and_routine(self):
        result = analysis.assess_one(work_order(), as_of=TODAY)
        self.assertTrue(result.is_clean)
        self.assertEqual(result.queue, QUEUE_ROUTINE)
        self.assertIsNone(result.severity)

    def test_a_critical_record_reaches_immediate_review(self):
        record = work_order(priority=Priority.EMERGENCY,
                            opened_date=days_ago(30))
        result = analysis.assess_one(record, as_of=TODAY)
        self.assertEqual(result.queue, QUEUE_IMMEDIATE)
        self.assertTrue(result.has("emergency_unresolved"))

    def test_integrity_and_directive_rules_are_evaluated_together(self):
        record = work_order(work_order_id="", opened_date=days_ago(200))
        result = analysis.assess_one(record, as_of=TODAY)
        self.assertTrue(result.has("missing_work_order_id"))
        self.assertTrue(result.has("stale_work_order"))

    def test_findings_are_ordered_most_severe_first(self):
        record = work_order(work_order_id="", opened_date=days_ago(200),
                            assigned_technician="")
        result = analysis.assess_one(record, as_of=TODAY)
        ranks = [f.severity.rank for f in result.findings]
        self.assertEqual(ranks, sorted(ranks))

    def test_top_returns_the_most_severe_only(self):
        record = work_order(work_order_id="", opened_date=days_ago(200),
                            assigned_technician="")
        result = analysis.assess_one(record, as_of=TODAY)
        self.assertEqual(len(result.top(2)), 2)
        self.assertEqual(result.top(2), result.findings[:2])

    def test_duplicates_are_detected_across_the_whole_set(self):
        records = [work_order(work_order_id="WO-1"),
                   work_order(work_order_id="WO-1")]
        results = analysis.assess_all(records, as_of=TODAY)
        self.assertTrue(all(r.has("duplicate_work_order") for r in results))


class AnalyzeTests(unittest.TestCase):

    def setUp(self):
        self.records = [
            work_order(work_order_id="WO-1"),
            work_order(work_order_id="WO-2", priority=Priority.EMERGENCY,
                       opened_date=days_ago(40)),
            work_order(work_order_id="WO-3", status=Status.CANCELLED),
        ]
        self.result = analysis.analyze(self.records, as_of=TODAY)

    def test_exclusions_run_before_assessment(self):
        self.assertEqual(self.result.exclusions.retained_count, 2)
        self.assertEqual(len(self.result.assessments), 2)
        self.assertTrue(self.result.exclusions.reconciles())

    def test_excluded_work_reaches_no_metric(self):
        self.assertEqual(self.result.metrics.total, 2)

    def test_attention_lists_only_records_with_findings(self):
        attention = self.result.attention()
        self.assertEqual(len(attention), 1)
        self.assertEqual(attention[0].work_order.work_order_id, "WO-2")

    def test_in_queue(self):
        self.assertEqual(len(self.result.in_queue(QUEUE_IMMEDIATE)), 1)
        self.assertEqual(len(self.result.in_queue(QUEUE_ROUTINE)), 1)

    def test_rule_coverage_lists_every_rule(self):
        coverage = self.result.rule_coverage()
        self.assertEqual(set(coverage), set(analysis.ALL_RULES.keys))

    def test_unfired_rules_are_reported(self):
        self.assertIn("missing_asset", self.result.unfired_rules())


class RuleSetTests(unittest.TestCase):

    def test_all_rules_combines_both_sets_without_collision(self):
        keys = list(analysis.ALL_RULES.keys)
        self.assertEqual(len(keys), len(set(keys)))

    def test_a_rule_can_be_found_by_key(self):
        rule = analysis.ALL_RULES.by_key("stale_work_order")
        self.assertIsNotNone(rule)
        self.assertIsNone(analysis.ALL_RULES.by_key("no_such_rule"))

    def test_policy_changes_reach_the_whole_analysis(self):
        record = work_order(opened_date=days_ago(20))
        lenient = analysis.analyze([record], as_of=TODAY)
        strict = analysis.analyze(
            [record], policy=DEFAULT_POLICY.with_thresholds(stale_days=20),
            as_of=TODAY)
        self.assertEqual(lenient.metrics.critical, 0)
        self.assertEqual(strict.metrics.critical, 1)


if __name__ == "__main__":
    unittest.main()
