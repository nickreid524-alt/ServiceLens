"""Record integrity rules.

Each test drives one rule from a healthy baseline record, so a failure names
the rule and the field that broke it.
"""

import unittest

from servicelens.domain import integrity
from servicelens.domain.models import Severity, Status

from .support import context, days_ago, days_ahead, fired, work_order


class MissingIdentityTests(unittest.TestCase):

    def test_blank_identifier_fires(self):
        self.assertTrue(fired(integrity.MISSING_WORK_ORDER_ID,
                              work_order(work_order_id="")))

    def test_present_identifier_does_not(self):
        self.assertFalse(fired(integrity.MISSING_WORK_ORDER_ID))

    def test_the_message_points_at_the_worksheet_row(self):
        finding = integrity.MISSING_WORK_ORDER_ID.evaluate(
            context(work_order(work_order_id="", row_number=41)))
        self.assertIn("41", finding.basis)


class DuplicateTests(unittest.TestCase):

    def test_fires_when_the_identifier_repeats(self):
        self.assertTrue(fired(
            integrity.DUPLICATE_WORK_ORDER,
            work_order(work_order_id="WO-9"),
            duplicates=frozenset({"wo-9"})))

    def test_comparison_ignores_case_and_spacing(self):
        self.assertTrue(fired(
            integrity.DUPLICATE_WORK_ORDER,
            work_order(work_order_id="  WO-9  "),
            duplicates=frozenset({"wo-9"})))

    def test_blank_identifiers_are_not_duplicates_of_each_other(self):
        self.assertFalse(fired(
            integrity.DUPLICATE_WORK_ORDER, work_order(work_order_id=""),
            duplicates=frozenset({""})))


class MissingFieldTests(unittest.TestCase):

    def test_missing_asset(self):
        self.assertTrue(fired(integrity.MISSING_ASSET,
                              work_order(asset_id="")))
        self.assertFalse(fired(integrity.MISSING_ASSET))

    def test_missing_opened_date(self):
        self.assertTrue(fired(integrity.MISSING_OPENED_DATE,
                              work_order(opened_date=None)))
        self.assertFalse(fired(integrity.MISSING_OPENED_DATE))

    def test_missing_status(self):
        self.assertTrue(fired(integrity.MISSING_STATUS,
                              work_order(status=None, raw_status="")))
        self.assertFalse(fired(integrity.MISSING_STATUS))


class DateConsistencyTests(unittest.TestCase):

    def test_opened_in_future(self):
        self.assertTrue(fired(integrity.OPENED_IN_FUTURE,
                              work_order(opened_date=days_ahead(3))))

    def test_opened_today_is_not_in_the_future(self):
        self.assertFalse(fired(integrity.OPENED_IN_FUTURE,
                               work_order(opened_date=days_ago(0))))

    def test_completed_before_opened(self):
        record = work_order(status=Status.COMPLETED,
                            opened_date=days_ago(10),
                            completed_date=days_ago(14))
        self.assertTrue(fired(integrity.COMPLETED_BEFORE_OPENED, record))

    def test_completed_on_the_same_day_is_fine(self):
        record = work_order(status=Status.COMPLETED,
                            opened_date=days_ago(10),
                            completed_date=days_ago(10))
        self.assertFalse(fired(integrity.COMPLETED_BEFORE_OPENED, record))

    def test_scheduled_before_opened(self):
        record = work_order(opened_date=days_ago(10),
                            scheduled_date=days_ago(12))
        self.assertTrue(fired(integrity.SCHEDULED_BEFORE_OPENED, record))

    def test_no_dates_means_no_date_findings(self):
        record = work_order(opened_date=None, completed_date=None,
                            scheduled_date=None)
        for rule in (integrity.OPENED_IN_FUTURE,
                     integrity.COMPLETED_BEFORE_OPENED,
                     integrity.SCHEDULED_BEFORE_OPENED):
            self.assertFalse(fired(rule, record), rule.key)


class StatusConsistencyTests(unittest.TestCase):

    def test_completed_without_a_date(self):
        record = work_order(status=Status.COMPLETED, completed_date=None)
        self.assertTrue(fired(integrity.COMPLETED_WITHOUT_DATE, record))

    def test_completed_with_a_date_is_fine(self):
        record = work_order(status=Status.COMPLETED,
                            completed_date=days_ago(1))
        self.assertFalse(fired(integrity.COMPLETED_WITHOUT_DATE, record))

    def test_open_but_carrying_a_completion_date(self):
        record = work_order(status=Status.IN_PROGRESS,
                            completed_date=days_ago(1))
        self.assertTrue(fired(integrity.OPEN_WITH_COMPLETION_DATE, record))

    def test_cancelled_work_with_a_date_is_not_flagged_as_open(self):
        record = work_order(status=Status.CANCELLED,
                            completed_date=days_ago(1))
        self.assertFalse(fired(integrity.OPEN_WITH_COMPLETION_DATE, record))

    def test_unrecognized_status(self):
        record = work_order(status=None, raw_status="Quote Stage")
        self.assertTrue(fired(integrity.UNRECOGNIZED_STATUS, record))

    def test_blank_status_is_reported_as_missing_not_unrecognized(self):
        record = work_order(status=None, raw_status="")
        self.assertFalse(fired(integrity.UNRECOGNIZED_STATUS, record))
        self.assertTrue(fired(integrity.MISSING_STATUS, record))


class CostSanityTests(unittest.TestCase):

    def test_negative_actual_cost(self):
        self.assertTrue(fired(integrity.NEGATIVE_COST,
                              work_order(actual_cost=-40.0)))

    def test_negative_estimate(self):
        self.assertTrue(fired(integrity.NEGATIVE_COST,
                              work_order(estimated_cost=-40.0)))

    def test_zero_is_not_negative(self):
        self.assertFalse(fired(integrity.NEGATIVE_COST,
                               work_order(estimated_cost=0.0,
                                          actual_cost=0.0)))


class RuleSetTests(unittest.TestCase):

    def test_a_healthy_record_produces_nothing(self):
        self.assertEqual(integrity.evaluate(context()), [])

    def test_findings_are_ordered_most_severe_first(self):
        record = work_order(work_order_id="", asset_id="",
                            scheduled_date=days_ago(99))
        findings = integrity.evaluate(context(record))
        ranks = [f.severity.rank for f in findings]
        self.assertEqual(ranks, sorted(ranks))
        self.assertIs(findings[0].severity, Severity.CRITICAL)

    def test_every_rule_key_is_unique(self):
        keys = list(integrity.INTEGRITY_RULES.keys)
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_rule_explains_itself(self):
        for rule in integrity.INTEGRITY_RULES:
            self.assertTrue(rule.explanation, rule.key)
            self.assertTrue(rule.reads, rule.key)

    def test_catalogue_is_plain_data(self):
        entries = integrity.INTEGRITY_RULES.catalogue()
        self.assertEqual(len(entries), len(integrity.INTEGRITY_RULES))
        self.assertEqual(
            set(entries[0]),
            {"key", "title", "severity", "domain", "explanation", "reads",
             "limits"})


if __name__ == "__main__":
    unittest.main()
