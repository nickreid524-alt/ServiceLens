"""Value parsing and row-to-record normalization."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from servicelens.demo.xlsx_writer import write_workbook
from servicelens.domain.models import (
    AssignmentType,
    Priority,
    Status,
    WorkType,
)
from servicelens.ingestion.normalization import (
    build_work_order,
    clean_text,
    find_header_row,
    load_workbook,
    normalize_sheet,
    parse_date,
    parse_number,
)
from servicelens.ingestion.xlsx import Sheet, WorkbookError, read_sheet


class ParseDateTests(unittest.TestCase):

    def test_iso(self):
        self.assertEqual(parse_date("2026-03-04"), date(2026, 3, 4))

    def test_iso_datetime_is_truncated(self):
        self.assertEqual(parse_date("2026-03-04T09:15:00"), date(2026, 3, 4))
        self.assertEqual(parse_date("2026-03-04 09:15"), date(2026, 3, 4))

    def test_regional_orderings(self):
        self.assertEqual(parse_date("03/04/2026"), date(2026, 3, 4))
        self.assertEqual(parse_date("2026/03/04"), date(2026, 3, 4))

    def test_written_months(self):
        self.assertEqual(parse_date("Mar 4, 2026"), date(2026, 3, 4))
        self.assertEqual(parse_date("4 March 2026"), date(2026, 3, 4))

    def test_bare_serial_number(self):
        self.assertEqual(parse_date("46085"), date(2026, 3, 4))

    def test_unreadable_values_return_none(self):
        for value in (None, "", "   ", "not a date", "13/45/2026", "0"):
            self.assertIsNone(parse_date(value), repr(value))

    def test_passthrough_for_real_dates(self):
        self.assertEqual(parse_date(date(2026, 3, 4)), date(2026, 3, 4))


class ParseNumberTests(unittest.TestCase):

    def test_plain_numbers(self):
        self.assertEqual(parse_number("1234.5"), 1234.5)
        self.assertEqual(parse_number(42), 42.0)

    def test_currency_and_separators(self):
        self.assertEqual(parse_number("$1,234.50"), 1234.5)
        self.assertEqual(parse_number("USD 900"), 900.0)

    def test_accountancy_parentheses_are_negative(self):
        self.assertEqual(parse_number("(250.00)"), -250.0)

    def test_explicit_negative(self):
        self.assertEqual(parse_number("-250"), -250.0)

    def test_zero_is_kept_not_treated_as_missing(self):
        self.assertEqual(parse_number("0"), 0.0)

    def test_unreadable_values_return_none(self):
        for value in (None, "", "  ", "n/a", "-", "."):
            self.assertIsNone(parse_number(value), repr(value))


class CleanTextTests(unittest.TestCase):

    def test_collapses_whitespace(self):
        self.assertEqual(clean_text("  two   words \n"), "two words")

    def test_none_becomes_empty_string(self):
        self.assertEqual(clean_text(None), "")


class BuildWorkOrderTests(unittest.TestCase):

    def test_vocabularies_are_parsed(self):
        record = build_work_order({
            "Work Order ID": " WO-1 ",
            "Status": "in process",
            "Priority": "urgent",
            "Work Type": "PM",
            "Assignment Type": "contractor",
        }, row_number=7)
        self.assertEqual(record.work_order_id, "WO-1")
        self.assertIs(record.status, Status.IN_PROGRESS)
        self.assertIs(record.priority, Priority.EMERGENCY)
        self.assertIs(record.work_type, WorkType.PREVENTIVE)
        self.assertIs(record.assignment_type, AssignmentType.EXTERNAL)
        self.assertEqual(record.row_number, 7)

    def test_unknown_status_is_kept_as_raw_text(self):
        record = build_work_order({"Status": "Quote Stage"}, 2)
        self.assertIsNone(record.status)
        self.assertEqual(record.raw_status, "Quote Stage")

    def test_leading_zeros_on_asset_ids_survive(self):
        record = build_work_order({"Asset ID": "004120"}, 2)
        self.assertEqual(record.asset_id, "004120")

    def test_absent_fields_become_none_not_errors(self):
        record = build_work_order({}, 2)
        self.assertIsNone(record.opened_date)
        self.assertIsNone(record.estimated_cost)
        self.assertEqual(record.work_order_id, "")


class HeaderRowTests(unittest.TestCase):

    def test_header_found_below_a_title_block(self):
        sheet = Sheet("S", [
            ["Maintenance Status Report"],
            ["Filtered to open work"],
            ["WO Number", "Equipment", "Status", "Opened"],
            ["WO-1", "A-1", "Open", "2026-01-01"],
        ], [1, 2, 3, 4])
        self.assertEqual(find_header_row(sheet), 2)

    def test_first_row_is_used_when_it_is_the_header(self):
        sheet = Sheet("S", [
            ["Work Order ID", "Asset ID", "Status", "Opened Date"],
            ["WO-1", "A-1", "Open", "2026-01-01"],
        ], [1, 2])
        self.assertEqual(find_header_row(sheet), 0)


class NormalizeSheetTests(unittest.TestCase):

    HEADERS = ["WO Number", "Equipment", "Status", "Opened", "Supplier"]

    def sheet(self, rows, preamble=()):
        grid = [list(r) for r in preamble] + [self.HEADERS] + [
            list(r) for r in rows]
        return Sheet("Work Orders", grid, list(range(1, len(grid) + 1)))

    def test_rows_become_work_orders(self):
        result = normalize_sheet(self.sheet([
            ["WO-1", "A-1", "Open", "2026-01-02", "Northstar Service Group"],
        ]))
        self.assertEqual(result.count, 1)
        self.assertEqual(result.work_orders[0].vendor,
                         "Northstar Service Group")
        self.assertEqual(result.work_orders[0].opened_date, date(2026, 1, 2))

    def test_row_number_points_at_the_worksheet_line(self):
        result = normalize_sheet(self.sheet(
            [["WO-1", "A-1", "Open", "2026-01-02", ""]],
            preamble=[["Title"], []]))
        self.assertEqual(result.work_orders[0].row_number, 4)
        self.assertEqual(result.header_row, 3)

    def test_blank_rows_are_counted_not_kept(self):
        result = normalize_sheet(self.sheet([
            ["WO-1", "A-1", "Open", "2026-01-02", ""],
            ["", "", "", "", ""],
        ]))
        self.assertEqual(result.count, 1)
        self.assertEqual(result.blank_rows_skipped, 1)
        self.assertEqual(result.rows_read, 2)

    def test_short_rows_do_not_raise(self):
        result = normalize_sheet(self.sheet([["WO-1", "A-1", "Open"]]))
        self.assertEqual(result.count, 1)
        self.assertIsNone(result.work_orders[0].opened_date)

    def test_missing_required_column_is_refused_with_a_named_reason(self):
        sheet = Sheet("S", [["WO Number", "Equipment"], ["WO-1", "A-1"]],
                      [1, 2])
        with self.assertRaises(WorkbookError) as caught:
            normalize_sheet(sheet)
        message = str(caught.exception)
        self.assertIn("Status", message)
        self.assertIn("Opened Date", message)

    def test_empty_sheet_is_refused(self):
        with self.assertRaises(WorkbookError):
            normalize_sheet(Sheet("S", [], []))

    def test_unmapped_columns_are_reported(self):
        sheet = Sheet("S", [self.HEADERS + ["Reporting Region"],
                            ["WO-1", "A-1", "Open", "2026-01-02", "", "North"]],
                      [1, 2])
        result = normalize_sheet(sheet)
        self.assertEqual(result.schema.unmapped_headers, ["Reporting Region"])


class LoadWorkbookTests(unittest.TestCase):

    def test_round_trip_through_a_real_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.xlsx"
            write_workbook(
                str(path),
                headers=["WO Number", "Equipment", "Status", "Created Date",
                         "Actual Cost"],
                rows=[["WO-1", "VEH-2207", "Open", date(2026, 2, 1), 1250.75]],
                sheet_name="Work Orders",
                preamble=[["Synthetic Maintenance Dataset"], []],
            )
            result = load_workbook(str(path))

        self.assertEqual(result.sheet_name, "Work Orders")
        self.assertEqual(result.count, 1)
        record = result.work_orders[0]
        self.assertEqual(record.work_order_id, "WO-1")
        self.assertEqual(record.opened_date, date(2026, 2, 1))
        self.assertEqual(record.actual_cost, 1250.75)

    def test_reading_does_not_alter_the_workbook(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.xlsx"
            write_workbook(str(path), ["WO Number", "Equipment", "Status",
                                       "Opened"],
                           [["WO-1", "A-1", "Open", date(2026, 2, 1)]])
            before = path.read_bytes()
            load_workbook(str(path))
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
