"""The canonical work order model and its vocabularies."""

import unittest
from datetime import date

from servicelens.domain.models import (
    AssetCategory,
    AssignmentType,
    Priority,
    Severity,
    Status,
    WorkType,
)

from .support import TODAY, days_ago, days_ahead, work_order


class VocabularyTests(unittest.TestCase):

    def test_exact_label_matches(self):
        self.assertIs(Status.parse("In Progress"), Status.IN_PROGRESS)
        self.assertIs(Priority.parse("Emergency"), Priority.EMERGENCY)

    def test_matching_ignores_case_and_spacing(self):
        self.assertIs(Status.parse("  in   progress "), Status.IN_PROGRESS)
        self.assertIs(WorkType.parse("PREVENTIVE"), WorkType.PREVENTIVE)

    def test_aliases(self):
        self.assertIs(Status.parse("closed"), Status.COMPLETED)
        self.assertIs(Priority.parse("P1"), Priority.EMERGENCY)
        self.assertIs(WorkType.parse("pm"), WorkType.PREVENTIVE)
        self.assertIs(AssignmentType.parse("contractor"),
                      AssignmentType.EXTERNAL)
        self.assertIs(AssetCategory.parse("forklift"),
                      AssetCategory.MATERIAL_HANDLING)

    def test_member_name_matches(self):
        self.assertIs(Status.parse("in_progress"), Status.IN_PROGRESS)

    def test_unknown_returns_the_default(self):
        self.assertIsNone(Status.parse("Quote Stage"))
        self.assertIs(Status.parse("", Status.OPEN), Status.OPEN)
        self.assertIsNone(Status.parse(None))

    def test_priority_ranking_is_most_urgent_first(self):
        ranks = [p.rank for p in (Priority.EMERGENCY, Priority.HIGH,
                                  Priority.NORMAL, Priority.LOW)]
        self.assertEqual(ranks, sorted(ranks))

    def test_severity_ranking(self):
        self.assertLess(Severity.CRITICAL.rank, Severity.WARNING.rank)
        self.assertLess(Severity.WARNING.rank, Severity.INFORMATION.rank)


class StatusTests(unittest.TestCase):

    def test_terminal_statuses(self):
        self.assertTrue(Status.COMPLETED.is_terminal)
        self.assertTrue(Status.CANCELLED.is_terminal)
        self.assertFalse(Status.ON_HOLD.is_terminal)

    def test_open_is_the_inverse_of_terminal(self):
        for status in Status:
            self.assertNotEqual(status.is_open, status.is_terminal)


class OpennessTests(unittest.TestCase):

    def test_a_missing_status_is_treated_as_open(self):
        self.assertTrue(work_order(status=None).is_open)

    def test_completed_is_not_open(self):
        self.assertFalse(work_order(status=Status.COMPLETED).is_open)


class AgeTests(unittest.TestCase):

    def test_open_work_is_measured_to_the_reporting_date(self):
        record = work_order(opened_date=days_ago(10))
        self.assertEqual(record.age_days(TODAY), 10)

    def test_closed_work_is_measured_to_its_completion(self):
        record = work_order(status=Status.COMPLETED,
                            opened_date=days_ago(30),
                            completed_date=days_ago(24))
        self.assertEqual(record.age_days(TODAY), 6)

    def test_closed_work_without_a_date_falls_back_to_the_reporting_date(self):
        record = work_order(status=Status.COMPLETED,
                            opened_date=days_ago(30), completed_date=None)
        self.assertEqual(record.age_days(TODAY), 30)

    def test_no_opened_date_gives_no_age(self):
        self.assertIsNone(work_order(opened_date=None).age_days(TODAY))

    def test_a_future_opened_date_gives_a_negative_age_not_a_guess(self):
        record = work_order(opened_date=days_ahead(5))
        self.assertEqual(record.age_days(TODAY), -5)


class UpdateAgeTests(unittest.TestCase):

    def test_uses_the_most_recent_activity(self):
        record = work_order(opened_date=days_ago(40),
                            last_update_date=days_ago(5))
        self.assertEqual(record.days_since_update(TODAY), 5)

    def test_falls_back_to_the_opened_date(self):
        record = work_order(opened_date=days_ago(40), last_update_date=None)
        self.assertEqual(record.days_since_update(TODAY), 40)

    def test_an_undated_record_has_no_quiet_period(self):
        record = work_order(opened_date=None, last_update_date=None)
        self.assertIsNone(record.days_since_update(TODAY))


class AssigneeTests(unittest.TestCase):

    def test_internal_work_needs_a_technician(self):
        self.assertTrue(work_order().has_assignee)
        self.assertFalse(work_order(assigned_technician="").has_assignee)

    def test_external_work_needs_a_vendor_not_a_technician(self):
        external = work_order(assignment_type=AssignmentType.EXTERNAL,
                              assigned_technician="Someone", vendor="")
        self.assertFalse(external.has_assignee)
        self.assertTrue(work_order(
            assignment_type=AssignmentType.EXTERNAL,
            assigned_technician="", vendor="Apex Mechanical Contractors",
        ).has_assignee)

    def test_with_no_assignment_type_either_will_do(self):
        self.assertTrue(work_order(
            assignment_type=None, assigned_technician="",
            vendor="Ironwood Electrical").has_assignee)
        self.assertFalse(work_order(
            assignment_type=None, assigned_technician="",
            vendor="").has_assignee)


class NoteTests(unittest.TestCase):

    def test_a_real_note_is_usable(self):
        self.assertTrue(work_order().has_usable_note(12))

    def test_placeholders_are_not_usable(self):
        for note in ("", "  ", "TBD", "n/a", "pending", "-", "See notes."):
            self.assertFalse(
                work_order(last_note=note).has_usable_note(12), repr(note))

    def test_a_note_shorter_than_the_minimum_is_not_usable(self):
        self.assertFalse(work_order(last_note="too short").has_usable_note(12))
        self.assertTrue(work_order(
            last_note="long enough to say something").has_usable_note(12))


class CostTests(unittest.TestCase):

    def test_actual_cost_wins(self):
        record = work_order(estimated_cost=100.0, actual_cost=250.0)
        self.assertEqual(record.effective_cost, 250.0)

    def test_estimate_is_used_when_there_is_no_actual(self):
        self.assertEqual(work_order(estimated_cost=100.0,
                                    actual_cost=None).effective_cost, 100.0)

    def test_nothing_recorded_costs_nothing(self):
        self.assertEqual(work_order(estimated_cost=None,
                                    actual_cost=None).effective_cost, 0.0)


class IdentityTests(unittest.TestCase):

    def test_identity_falls_back_to_the_row(self):
        self.assertEqual(work_order(work_order_id="").identity, "(row 2)")
        self.assertEqual(work_order().identity, "WO-2026-000001")


class ImmutabilityTests(unittest.TestCase):

    def test_a_work_order_cannot_be_edited_in_place(self):
        record = work_order()
        with self.assertRaises(Exception):
            record.status = Status.COMPLETED


if __name__ == "__main__":
    unittest.main()
