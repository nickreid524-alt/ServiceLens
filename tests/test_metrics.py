"""Dashboard aggregation."""

import unittest

from servicelens.domain import metrics as M
from servicelens.domain.models import (
    Domain,
    Priority,
    Severity,
    Status,
    TEAMS,
    QUEUES,
)
from servicelens.domain.rules import Assessment, Finding

from .support import days_ago, work_order


def finding(severity=Severity.WARNING, domain=Domain.AGING, key="k"):
    return Finding(key=key, title="T", severity=severity, domain=domain,
                   message="m", basis="b")


def assessment(work=None, findings=(), team="Facilities Maintenance",
               queue="Routine Operations", age=5):
    return Assessment(work_order=work if work is not None else work_order(),
                      findings=list(findings), team=team, queue=queue, age=age)


class BandTests(unittest.TestCase):

    def test_bands_cover_every_non_negative_age(self):
        for days in range(0, 400):
            self.assertNotEqual(M.band_for(days), "Undated", days)

    def test_band_boundaries(self):
        self.assertEqual(M.band_for(0), "0-7 days")
        self.assertEqual(M.band_for(7), "0-7 days")
        self.assertEqual(M.band_for(8), "8-14 days")
        self.assertEqual(M.band_for(45), "31-45 days")
        self.assertEqual(M.band_for(46), "46+ days")

    def test_undated_and_negative_ages(self):
        self.assertEqual(M.band_for(None), "Undated")
        self.assertEqual(M.band_for(-3), "Undated")


class EmptyInputTests(unittest.TestCase):

    def test_no_assessments_produces_zeroes_not_errors(self):
        metrics = M.compute([])
        self.assertEqual(metrics.total, 0)
        self.assertEqual(metrics.exception_rate, 0.0)
        self.assertEqual(metrics.completion_rate, 0.0)
        self.assertEqual(metrics.average_open_age, 0.0)
        self.assertEqual(metrics.oldest_open_age, 0)


class CountTests(unittest.TestCase):

    def setUp(self):
        self.items = [
            assessment(age=3),
            assessment(work_order(status=Status.COMPLETED,
                                  opened_date=days_ago(20),
                                  completed_date=days_ago(10)), age=10),
            assessment(findings=[finding(Severity.CRITICAL)], age=60),
            assessment(findings=[finding(Severity.WARNING),
                                 finding(Severity.INFORMATION)], age=20),
        ]
        self.metrics = M.compute(self.items)

    def test_totals(self):
        self.assertEqual(self.metrics.total, 4)
        self.assertEqual(self.metrics.open_count, 3)
        self.assertEqual(self.metrics.completed_count, 1)

    def test_finding_counts(self):
        self.assertEqual(self.metrics.with_findings, 2)
        self.assertEqual(self.metrics.clean, 2)
        self.assertEqual(self.metrics.findings_total, 3)

    def test_severity_counts(self):
        self.assertEqual(self.metrics.critical, 1)
        self.assertEqual(self.metrics.warning, 1)
        self.assertEqual(self.metrics.information, 1)

    def test_rates(self):
        self.assertAlmostEqual(self.metrics.exception_rate, 0.5)
        self.assertAlmostEqual(self.metrics.completion_rate, 0.25)

    def test_open_ages_exclude_completed_work(self):
        self.assertEqual(self.metrics.oldest_open_age, 60)
        self.assertAlmostEqual(
            self.metrics.average_open_age, (3 + 60 + 20) / 3)

    def test_median_open_age(self):
        self.assertEqual(self.metrics.median_open_age, 20)

    def test_every_severity_key_is_present_even_at_zero(self):
        metrics = M.compute([assessment()])
        for severity in Severity:
            self.assertIn(severity.label, metrics.severity_counts)


class GroupingTests(unittest.TestCase):

    def test_known_teams_appear_in_a_fixed_order_even_when_empty(self):
        metrics = M.compute([assessment(team="Fleet Maintenance")])
        self.assertEqual([name for name, _ in metrics.by_team], list(TEAMS))
        self.assertEqual(dict(metrics.by_team)["Fleet Maintenance"], 1)
        self.assertEqual(dict(metrics.by_team)["Mechanical Services"], 0)

    def test_known_queues_appear_in_a_fixed_order(self):
        metrics = M.compute([assessment(queue="Cost Review")])
        self.assertEqual([name for name, _ in metrics.by_queue], list(QUEUES))

    def test_unexpected_group_values_are_kept_after_the_known_ones(self):
        metrics = M.compute([assessment(team="Night Shift Crew")])
        names = [name for name, _ in metrics.by_team]
        self.assertEqual(names[:len(TEAMS)], list(TEAMS))
        self.assertIn("Night Shift Crew", names)

    def test_blank_values_are_labelled_not_dropped(self):
        metrics = M.compute([assessment(work_order(priority=None, site=""))])
        self.assertEqual(dict(metrics.by_priority)["(blank)"], 1)
        self.assertEqual(dict(metrics.by_site)["(blank)"], 1)

    def test_grouped_counts_sum_to_the_total(self):
        items = [assessment(work_order(priority=Priority.HIGH)),
                 assessment(), assessment(work_order(priority=None))]
        metrics = M.compute(items)
        for group in (metrics.by_team, metrics.by_queue, metrics.by_priority,
                      metrics.by_status, metrics.by_site):
            self.assertEqual(sum(count for _, count in group), metrics.total)

    def test_aging_bands_cover_only_open_work(self):
        items = [assessment(age=3),
                 assessment(work_order(status=Status.COMPLETED), age=99)]
        metrics = M.compute(items)
        self.assertEqual(sum(c for _, c in metrics.by_aging_band), 1)


class CostTests(unittest.TestCase):

    def test_open_cost_excludes_completed_work(self):
        items = [
            assessment(work_order(estimated_cost=100.0)),
            assessment(work_order(status=Status.COMPLETED,
                                  estimated_cost=500.0, actual_cost=520.0)),
        ]
        metrics = M.compute(items)
        self.assertEqual(metrics.open_cost, 100.0)
        self.assertEqual(metrics.estimated_cost, 600.0)
        self.assertEqual(metrics.actual_cost, 520.0)


class TeamSummaryTests(unittest.TestCase):

    def test_summary_per_team(self):
        items = [
            assessment(team="Fleet Maintenance",
                       findings=[finding(Severity.CRITICAL)], age=40),
            assessment(team="Fleet Maintenance", age=10),
            assessment(team="Mechanical Services", age=2),
        ]
        metrics = M.compute(items)
        fleet = metrics.team_summaries["Fleet Maintenance"]
        self.assertEqual(fleet.total, 2)
        self.assertEqual(fleet.critical, 1)
        self.assertEqual(fleet.needs_action, 1)
        self.assertEqual(fleet.oldest_age, 40)
        self.assertAlmostEqual(fleet.average_age, 25.0)


class RuleCountTests(unittest.TestCase):

    def test_rules_fired_is_ordered_most_frequent_first(self):
        items = [assessment(findings=[finding(key="a")]),
                 assessment(findings=[finding(key="a")]),
                 assessment(findings=[finding(key="b")])]
        metrics = M.compute(items)
        self.assertEqual(metrics.rules_fired()[0], ("a", 2))

    def test_domain_counts(self):
        items = [assessment(findings=[finding(domain=Domain.COST)])]
        metrics = M.compute(items)
        self.assertEqual(metrics.domain_counts[Domain.COST.label], 1)


if __name__ == "__main__":
    unittest.main()
