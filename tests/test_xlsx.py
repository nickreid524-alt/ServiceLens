"""The standard-library .xlsx reader."""

import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from servicelens.demo.xlsx_writer import (
    column_letter,
    date_to_serial,
    write_workbook,
)
from servicelens.ingestion.xlsx import (
    WorkbookError,
    column_index,
    read_sheet,
    serial_to_date,
)


class ReferenceTests(unittest.TestCase):

    def test_column_index(self):
        for reference, expected in (("A1", 0), ("B2", 1), ("Z9", 25),
                                    ("AA1", 26), ("AB1", 27), ("BC12", 54)):
            self.assertEqual(column_index(reference), expected, reference)

    def test_column_letter_round_trips(self):
        for index in (0, 1, 25, 26, 27, 51, 52, 701, 702):
            self.assertEqual(
                column_index(f"{column_letter(index)}1"), index)

    def test_missing_reference_is_tolerated(self):
        self.assertEqual(column_index(""), 0)


class SerialDateTests(unittest.TestCase):

    def test_known_serials(self):
        # 1 is 1900-01-01; 61 is 1900-03-01, the first date after the
        # spurious leap day the 1900 system contains.
        self.assertEqual(serial_to_date(1), date(1900, 1, 1))
        self.assertEqual(serial_to_date(59), date(1900, 2, 28))
        self.assertEqual(serial_to_date(61), date(1900, 3, 1))
        self.assertEqual(serial_to_date(45000), date(2023, 3, 15))

    def test_round_trip_for_modern_dates(self):
        for value in (date(1990, 1, 1), date(2026, 9, 10), date(2099, 12, 31)):
            self.assertEqual(serial_to_date(date_to_serial(value)), value)

    def test_1904_system(self):
        self.assertEqual(serial_to_date(0, True), date(1904, 1, 1))
        self.assertEqual(serial_to_date(366, True), date(1905, 1, 1))


class ReadWorkbookTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "book.xlsx"

    def tearDown(self):
        self.directory.cleanup()

    def write(self, headers, rows, **kwargs):
        write_workbook(str(self.path), headers, rows, **kwargs)
        return read_sheet(str(self.path))

    def test_reads_headers_and_rows(self):
        sheet = self.write(["A", "B"], [["1", "2"], ["3", "4"]])
        self.assertEqual(sheet.rows[0], ["A", "B"])
        self.assertEqual(sheet.rows[1], ["1", "2"])
        self.assertEqual(len(sheet), 3)

    def test_sheet_name_is_preserved(self):
        sheet = self.write(["A"], [["1"]], sheet_name="Work Orders")
        self.assertEqual(sheet.name, "Work Orders")

    def test_named_sheet_lookup_is_case_insensitive(self):
        write_workbook(str(self.path), ["A"], [["1"]],
                       sheet_name="Work Orders")
        self.assertEqual(read_sheet(str(self.path), "work orders").name,
                         "Work Orders")

    def test_unknown_sheet_name_is_reported(self):
        write_workbook(str(self.path), ["A"], [["1"]])
        with self.assertRaises(WorkbookError):
            read_sheet(str(self.path), "No Such Sheet")

    def test_dates_come_back_as_iso_text(self):
        sheet = self.write(["Opened"], [[date(2026, 3, 4)]])
        self.assertEqual(sheet.rows[1], ["2026-03-04"])

    def test_numbers_are_not_mistaken_for_dates(self):
        sheet = self.write(["Cost"], [[45000.5]])
        self.assertEqual(sheet.rows[1], ["45000.5"])

    def test_sparse_cells_keep_their_column(self):
        # Blank values are omitted from the XML entirely, so the reader has
        # to place later cells by their reference rather than by position.
        sheet = self.write(["A", "B", "C"], [["", "", "third"]])
        self.assertEqual(sheet.rows[1], ["", "", "third"])

    def test_blank_rows_are_skipped_but_line_numbers_survive(self):
        sheet = self.write(["A"], [["one"], ["", ], ["two"]])
        self.assertEqual([r[0] for r in sheet.rows], ["A", "one", "two"])
        self.assertEqual(sheet.row_numbers, [1, 2, 4])

    def test_preamble_rows_are_returned(self):
        sheet = self.write(["A"], [["one"]],
                           preamble=[["Report title"], []])
        self.assertEqual(sheet.rows[0], ["Report title"])
        self.assertEqual(sheet.rows[1], ["A"])

    def test_repeated_text_shares_one_string_entry(self):
        write_workbook(str(self.path), ["A"], [["same"]] * 20)
        with zipfile.ZipFile(self.path) as archive:
            shared = archive.read("xl/sharedStrings.xml").decode()
        self.assertIn('uniqueCount="2"', shared)  # "A" and "same"
        self.assertEqual(len(read_sheet(str(self.path)).rows), 21)

    def test_booleans_read_as_yes_and_no(self):
        sheet = self.write(["Flag"], [[True], [False]])
        self.assertEqual([r[0] for r in sheet.rows[1:]], ["Yes", "No"])

    def test_a_non_zip_file_is_reported_clearly(self):
        self.path.write_bytes(b"this is not a zip archive")
        with self.assertRaises(WorkbookError) as caught:
            read_sheet(str(self.path))
        self.assertIn(".xlsx", str(caught.exception))

    def test_a_zip_that_is_not_a_workbook_is_reported(self):
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("hello.txt", "not a workbook")
        with self.assertRaises(WorkbookError):
            read_sheet(str(self.path))

    def test_a_missing_file_is_reported(self):
        with self.assertRaises(WorkbookError):
            read_sheet(str(self.path.with_name("absent.xlsx")))

    def test_the_source_file_is_never_modified(self):
        self.write(["A"], [["one"]])
        before = self.path.read_bytes()
        read_sheet(str(self.path))
        read_sheet(str(self.path))
        self.assertEqual(self.path.read_bytes(), before)


class InlineStringTests(unittest.TestCase):
    """Some exporters write text inline instead of into the shared table."""

    MINIMAL = {
        "[Content_Types].xml":
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats'
            '.org/package/2006/content-types"/>',
        "_rels/.rels":
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.'
            'openxmlformats.org/package/2006/relationships"><Relationship '
            'Id="rId1" Type="x" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml":
            '<?xml version="1.0"?><workbook xmlns="http://schemas.'
            'openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://'
            'schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>",
        "xl/_rels/workbook.xml.rels":
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.'
            'openxmlformats.org/package/2006/relationships"><Relationship '
            'Id="rId1" Type="x" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        "xl/worksheets/sheet1.xml":
            '<?xml version="1.0"?><worksheet xmlns="http://schemas.'
            'openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            '<row r="1"><c r="A1" t="inlineStr"><is><t>Rich</t>'
            "<t> Text</t></is></c></row></sheetData></worksheet>",
    }

    def test_inline_runs_are_joined(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inline.xlsx"
            with zipfile.ZipFile(path, "w") as archive:
                for name, content in self.MINIMAL.items():
                    archive.writestr(name, content)
            self.assertEqual(read_sheet(str(path)).rows[0], ["Rich Text"])


if __name__ == "__main__":
    unittest.main()
