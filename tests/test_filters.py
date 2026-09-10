"""Exclusions, search and interactive filtering."""

import unittest

from servicelens.config import ExclusionPolicy
from servicelens.domain import filters
from servicelens.domain.models import Severity, Status
from servicelens.domain.rules import Assessment, Finding

from .support import work_order


def assessment(work=None, findings=(), team="Facilities Maintenance",
               queue="Routine Operations", age=5) -> Assessment:
    return Assessment(
        work_order=work if work is not None else work_order(),
        findings=list(findings), team=team, queue=queue, age=age)


def finding(severity=Severity.WARNING, key="k") -> Finding:
    from servicelens.domain.models import Domain
    return Finding(key=key, title="T", severity=severity,
                   domain=Domain.AGING, message="m", basis="b")


class ExclusionTests(unittest.TestCase):

    def test_cancelled_work_is_excluded_by_default(self):
        records = [work_order(), work_order(status=Status.CANCELLED)]
        report = filters.apply_exclusions(records)
        self.assertEqual(report.retained_count, 1)
        self.assertEqual(report.counts[filters.REASON_CANCELLED], 1)

    def test_cancelled_work_can_be_kept(self):
        records = [work_order(status=Status.CANCELLED)]
        report = filters.apply_exclusions(
            records, ExclusionPolicy(exclude_cancelled=False))
        self.assertEqual(report.retained_count, 1)

    def test_everything_reconciles(self):
        records = [work_order(), work_order(status=Status.CANCELLED),
                   work_order(asset_id="PLACEHOLDER"),
                   work_order(site="Decommissioned Yard")]
        report = filters.apply_exclusions(records, ExclusionPolicy(
            excluded_asset_ids=frozenset({"placeholder"}),
            excluded_sites=frozenset({"Decommissioned Yard"})))
        self.assertTrue(report.reconciles())
        self.assertEqual(report.rows_in, 4)
        self.assertEqual(report.retained_count, 1)
        self.assertEqual(report.total_excluded, 3)

    def test_a_record_is_counted_once_under_the_first_reason(self):
        record = work_order(status=Status.CANCELLED, asset_id="PLACEHOLDER")
        report = filters.apply_exclusions([record], ExclusionPolicy(
            excluded_asset_ids=frozenset({"placeholder"})))
        self.assertEqual(report.counts[filters.REASON_CANCELLED], 1)
        self.assertNotIn(filters.REASON_ASSET, report.counts)
        self.assertTrue(report.reconciles())

    def test_status_exclusions_compare_the_raw_value(self):
        record = work_order(status=None, raw_status="Quote Stage")
        report = filters.apply_exclusions([record], ExclusionPolicy(
            excluded_statuses=frozenset({"quote stage"})))
        self.assertEqual(report.retained_count, 0)

    def test_excluded_identities_are_recorded(self):
        report = filters.apply_exclusions(
            [work_order(work_order_id="WO-7", status=Status.CANCELLED)])
        self.assertEqual(report.excluded_ids[filters.REASON_CANCELLED],
                         ["WO-7"])

    def test_nothing_excluded_still_reconciles(self):
        report = filters.apply_exclusions([work_order(), work_order()])
        self.assertTrue(report.reconciles())
        self.assertEqual(report.total_excluded, 0)

    def test_an_empty_set_reconciles(self):
        report = filters.apply_exclusions([])
        self.assertTrue(report.reconciles())
        self.assertEqual(report.summary(), "0 read, 0 retained")


class SearchTests(unittest.TestCase):

    def test_matches_across_fields(self):
        record = work_order(site="Riverbend Distribution Center",
                            description="Domestic water pump failure")
        self.assertTrue(filters.matches_search(record, "pump riverbend"))

    def test_all_words_must_match(self):
        record = work_order(description="Belt squeal on startup")
        self.assertFalse(filters.matches_search(record, "belt gearbox"))

    def test_search_is_case_insensitive(self):
        self.assertTrue(filters.matches_search(work_order(), "PRIYA"))

    def test_an_empty_search_matches_everything(self):
        self.assertTrue(filters.matches_search(work_order(), "   "))


class FilterTests(unittest.TestCase):

    def test_no_criteria_matches_everything(self):
        self.assertTrue(filters.Filter().matches(assessment()))

    def test_team_filter(self):
        criteria = filters.Filter(teams=frozenset({"Fleet Maintenance"}))
        self.assertFalse(criteria.matches(assessment()))
        self.assertTrue(criteria.matches(
            assessment(team="Fleet Maintenance")))

    def test_queue_filter(self):
        criteria = filters.Filter(queues=frozenset({"Immediate Review"}))
        self.assertTrue(criteria.matches(
            assessment(queue="Immediate Review")))
        self.assertFalse(criteria.matches(assessment()))

    def test_open_only(self):
        criteria = filters.Filter(open_only=True)
        closed = assessment(work_order(status=Status.COMPLETED))
        self.assertFalse(criteria.matches(closed))
        self.assertTrue(criteria.matches(assessment()))

    def test_with_findings_only(self):
        criteria = filters.Filter(with_findings_only=True)
        self.assertFalse(criteria.matches(assessment()))
        self.assertTrue(criteria.matches(assessment(findings=[finding()])))

    def test_severity_filter_uses_the_worst_finding(self):
        criteria = filters.Filter(severities=frozenset({"Critical"}))
        critical = assessment(findings=[finding(Severity.CRITICAL),
                                        finding(Severity.INFORMATION)])
        self.assertTrue(criteria.matches(critical))
        self.assertFalse(criteria.matches(
            assessment(findings=[finding(Severity.WARNING)])))

    def test_criteria_combine(self):
        criteria = filters.Filter(open_only=True, search="riverbend")
        record = work_order(site="Riverbend Distribution Center")
        self.assertTrue(criteria.matches(assessment(record)))
        closed = work_order(site="Riverbend Distribution Center",
                            status=Status.COMPLETED)
        self.assertFalse(criteria.matches(assessment(closed)))

    def test_apply_filter_preserves_order(self):
        items = [assessment(team="Fleet Maintenance"), assessment(),
                 assessment(team="Fleet Maintenance")]
        result = filters.apply_filter(
            items, filters.Filter(teams=frozenset({"Fleet Maintenance"})))
        self.assertEqual(len(result), 2)


class RankingTests(unittest.TestCase):

    def test_critical_comes_first(self):
        clean = assessment()
        warning = assessment(findings=[finding(Severity.WARNING)])
        critical = assessment(findings=[finding(Severity.CRITICAL)])
        ranked = filters.rank_for_attention([clean, warning, critical])
        self.assertIs(ranked[0], critical)
        self.assertIs(ranked[-1], clean)

    def test_more_findings_outrank_fewer_at_the_same_severity(self):
        one = assessment(findings=[finding(Severity.WARNING, "a")])
        two = assessment(findings=[finding(Severity.WARNING, "a"),
                                   finding(Severity.WARNING, "b")])
        self.assertIs(filters.rank_for_attention([one, two])[0], two)

    def test_older_work_outranks_newer(self):
        young = assessment(findings=[finding()], age=5)
        old = assessment(findings=[finding()], age=90)
        self.assertIs(filters.rank_for_attention([young, old])[0], old)

    def test_ranking_is_stable_for_identical_records(self):
        items = [assessment(work_order(work_order_id=f"WO-{n}"),
                            findings=[finding()]) for n in (3, 1, 2)]
        ranked = filters.rank_for_attention(items)
        self.assertEqual([a.work_order.work_order_id for a in ranked],
                         ["WO-1", "WO-2", "WO-3"])

    def test_undated_records_do_not_break_ranking(self):
        undated = assessment(findings=[finding()], age=None)
        dated = assessment(findings=[finding()], age=10)
        self.assertEqual(len(filters.rank_for_attention([undated, dated])), 2)


if __name__ == "__main__":
    unittest.main()
