"""Team ownership and queue routing."""

import unittest

from servicelens.domain import routing
from servicelens.domain.models import (
    AssetCategory,
    AssignmentType,
    Domain,
    Severity,
    TEAM_CONTRACTED,
    TEAM_ELECTRICAL,
    TEAM_FACILITIES,
    TEAM_FLEET,
    TEAM_MECHANICAL,
    TEAM_OPERATIONS_REVIEW,
    QUEUE_COST,
    QUEUE_DATA_QUALITY,
    QUEUE_IMMEDIATE,
    QUEUE_PLANNING,
    QUEUE_PREVENTIVE,
    QUEUE_ROUTINE,
    QUEUE_VENDOR,
)
from servicelens.domain.rules import Finding

from .support import work_order


def finding(severity, domain, key="k") -> Finding:
    return Finding(key=key, title=key.title(), severity=severity,
                   domain=domain, message="m", basis="b")


class TeamAssignmentTests(unittest.TestCase):

    def test_external_work_goes_to_contracted_services(self):
        record = work_order(assignment_type=AssignmentType.EXTERNAL,
                            assigned_team="Fleet Maintenance",
                            asset_category=AssetCategory.VEHICLE,
                            vendor="Northstar Service Group")
        result = routing.assign_team(record)
        self.assertEqual(result.team, TEAM_CONTRACTED)
        self.assertEqual(result.rule, "external_assignment")

    def test_external_outranks_a_reported_team(self):
        # Ownership of contracted work sits with whoever chases the vendor,
        # whatever the export says.
        record = work_order(assignment_type=AssignmentType.EXTERNAL,
                            assigned_team="Electrical & Controls", vendor="")
        self.assertEqual(routing.assign_team(record).team, TEAM_CONTRACTED)

    def test_a_recognized_reported_team_is_honoured(self):
        record = work_order(assigned_team="Mechanical Services",
                            asset_category=AssetCategory.HVAC)
        result = routing.assign_team(record)
        self.assertEqual(result.team, TEAM_MECHANICAL)
        self.assertEqual(result.rule, "reported_team")

    def test_reported_team_matching_ignores_case(self):
        record = work_order(assigned_team="  fleet maintenance ")
        self.assertEqual(routing.assign_team(record).team, TEAM_FLEET)

    def test_category_is_used_when_no_team_is_reported(self):
        cases = {
            AssetCategory.VEHICLE: TEAM_FLEET,
            AssetCategory.ELECTRICAL: TEAM_ELECTRICAL,
            AssetCategory.HVAC: TEAM_FACILITIES,
            AssetCategory.PLUMBING: TEAM_FACILITIES,
            AssetCategory.GROUNDS: TEAM_FACILITIES,
            AssetCategory.MATERIAL_HANDLING: TEAM_MECHANICAL,
            AssetCategory.PRODUCTION: TEAM_MECHANICAL,
        }
        for category, team in cases.items():
            record = work_order(assigned_team="", asset_category=category)
            result = routing.assign_team(record)
            self.assertEqual(result.team, team, category)
            self.assertEqual(result.rule, "asset_category")

    def test_every_category_has_an_owning_team(self):
        for category in AssetCategory:
            self.assertIn(category, routing.CATEGORY_TEAM, category)

    def test_nothing_to_go_on_becomes_operations_review(self):
        record = work_order(assigned_team="", asset_category=None)
        result = routing.assign_team(record)
        self.assertEqual(result.team, TEAM_OPERATIONS_REVIEW)
        self.assertTrue(result.needs_review)

    def test_an_unrecognized_team_is_held_for_review(self):
        record = work_order(assigned_team="Night Shift Crew",
                            asset_category=None)
        result = routing.assign_team(record)
        self.assertEqual(result.team, TEAM_OPERATIONS_REVIEW)
        self.assertEqual(result.rule, "unrecognized_team")
        self.assertIn("Night Shift Crew", result.reason)

    def test_an_unrecognized_team_still_falls_back_to_the_category(self):
        record = work_order(assigned_team="Night Shift Crew",
                            asset_category=AssetCategory.VEHICLE)
        self.assertEqual(routing.assign_team(record).team, TEAM_FLEET)

    def test_every_decision_carries_a_reason(self):
        for record in (
                work_order(),
                work_order(assigned_team="", asset_category=None),
                work_order(assignment_type=AssignmentType.EXTERNAL)):
            self.assertTrue(routing.assign_team(record).reason.strip())


class QueueRoutingTests(unittest.TestCase):

    def test_no_findings_is_routine(self):
        result = routing.assign_queue([])
        self.assertEqual(result.queue, QUEUE_ROUTINE)

    def test_anything_critical_is_an_immediate_review(self):
        for domain in Domain:
            result = routing.assign_queue(
                [finding(Severity.CRITICAL, domain)])
            self.assertEqual(result.queue, QUEUE_IMMEDIATE, domain)

    def test_severity_outranks_domain(self):
        findings = [finding(Severity.WARNING, Domain.COST),
                    finding(Severity.CRITICAL, Domain.AGING)]
        self.assertEqual(routing.assign_queue(findings).queue, QUEUE_IMMEDIATE)

    def test_domain_queues(self):
        cases = {
            Domain.DATA_QUALITY: QUEUE_DATA_QUALITY,
            Domain.VENDOR: QUEUE_VENDOR,
            Domain.COST: QUEUE_COST,
            Domain.PREVENTIVE: QUEUE_PREVENTIVE,
        }
        for domain, queue in cases.items():
            result = routing.assign_queue([finding(Severity.WARNING, domain)])
            self.assertEqual(result.queue, queue, domain)

    def test_domain_precedence_is_data_quality_first(self):
        findings = [finding(Severity.WARNING, Domain.COST, "cost"),
                    finding(Severity.WARNING, Domain.DATA_QUALITY, "dq")]
        self.assertEqual(routing.assign_queue(findings).queue,
                         QUEUE_DATA_QUALITY)

    def test_remaining_domains_go_to_planning(self):
        for domain in (Domain.AGING, Domain.STATUS, Domain.PRIORITY):
            result = routing.assign_queue([finding(Severity.WARNING, domain)])
            self.assertEqual(result.queue, QUEUE_PLANNING, domain)

    def test_information_only_findings_still_get_a_queue(self):
        result = routing.assign_queue(
            [finding(Severity.INFORMATION, Domain.PREVENTIVE)])
        self.assertEqual(result.queue, QUEUE_PREVENTIVE)

    def test_every_decision_carries_a_reason(self):
        for findings in ([], [finding(Severity.CRITICAL, Domain.AGING)],
                         [finding(Severity.WARNING, Domain.VENDOR)],
                         [finding(Severity.INFORMATION, Domain.STATUS)]):
            self.assertTrue(routing.assign_queue(findings).reason.strip())

    def test_every_domain_reaches_a_queue(self):
        # A new domain must not silently fall out of the routing table.
        for domain in Domain:
            queue = routing.assign_queue(
                [finding(Severity.WARNING, domain)]).queue
            self.assertTrue(queue)
            self.assertNotEqual(queue, QUEUE_ROUTINE, domain)


if __name__ == "__main__":
    unittest.main()
