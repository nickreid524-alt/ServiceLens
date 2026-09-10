"""The three exports: review pack, exception register, CSV."""

import csv
import hashlib
import os
import re
import tempfile
import unittest
import zlib
from datetime import date
from pathlib import Path

from servicelens import analysis as analysis_module
from servicelens import reporting
from servicelens.demo import generator
from servicelens.domain.models import AssignmentType, Priority, Status
from servicelens.ingestion.normalization import ImportResult
from servicelens.reporting import (
    csv_export,
    exception_register,
    pdf,
    review_pack,
    summary,
)

from .support import TODAY, days_ago, work_order

REFERENCE = date(2026, 6, 15)
USABLE_WIDTH = pdf.A4[0] - 2 * pdf.MARGIN

# A realistic absolute path, assembled rather than written out, so the tests
# prove the reports strip it without the literal appearing in the source.
FIXTURE_PATH = os.path.join(os.path.abspath(os.sep), "Users", "someone",
                            "Documents", "export.xlsx")


def all_text(data: bytes) -> str:
    """Every string drawn anywhere in a PDF."""
    out = []
    for raw in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        content = zlib.decompress(raw).decode("latin-1")
        out.extend(re.findall(r"\((.*?)\) Tj", content))
    return "\n".join(out)


def small_analysis(with_findings: bool = True, notice: str = ""):
    """A tiny analysis with predictable content."""
    records = [work_order(work_order_id="WO-CLEAN-1")]
    if with_findings:
        records += [
            work_order(work_order_id="WO-EMERGENCY", priority=Priority.EMERGENCY,
                       opened_date=days_ago(30), site="Kestrel Point Terminal"),
            work_order(work_order_id="WO-NO-ASSET", asset_id=""),
            work_order(work_order_id="WO-DONE", status=Status.COMPLETED,
                       opened_date=days_ago(20), completed_date=days_ago(2),
                       estimated_cost=100.0, actual_cost=900.0),
        ]
    result = analysis_module.analyze(records, as_of=TODAY)
    result.imported = ImportResult(
        work_orders=records, sheet_name="Sheet A",
        source_path=FIXTURE_PATH,
        rows_read=len(records),
        preamble=[notice] if notice else [])
    return result


class ContextTests(unittest.TestCase):

    def test_source_name_is_the_file_name_only(self):
        facts = reporting.ReportContext(small_analysis())
        self.assertEqual(facts.source_name, "export.xlsx")
        self.assertNotIn("someone", facts.source_name)

    def test_synthetic_is_read_from_the_workbook_not_the_file_name(self):
        plain = reporting.ReportContext(small_analysis())
        declared = reporting.ReportContext(
            small_analysis(notice="Synthetic Maintenance Dataset"))
        self.assertFalse(plain.is_synthetic)
        self.assertEqual(plain.disclosure, "")
        self.assertTrue(declared.is_synthetic)
        self.assertIn("SYNTHETIC", declared.disclosure)

    def test_headline_tiles_carry_values_and_captions(self):
        tiles = reporting.ReportContext(small_analysis()).headline()
        self.assertGreaterEqual(len(tiles), 6)
        for value, caption, colour in tiles:
            self.assertTrue(str(value))
            self.assertTrue(caption)
            self.assertEqual(len(colour), 3)

    def test_result_description(self):
        result = reporting.ReportResult("x/y.pdf", "PDF", 1200, pages=3)
        self.assertEqual(result.name, "y.pdf")
        self.assertIn("3 pages", result.describe())
        self.assertIn("1,200 bytes", result.describe())


class ReviewPackTests(unittest.TestCase):

    def test_builds_a_multi_page_document(self):
        document = review_pack.build(small_analysis())
        self.assertGreaterEqual(len(document.pages), 1)
        data = document.to_bytes()
        self.assertTrue(data.startswith(b"%PDF"))

    def test_contains_the_headline_content(self):
        text = all_text(review_pack.build(small_analysis()).to_bytes())
        for expected in ("ServiceLens", "WORK ORDER INTELLIGENCE",
                         "Management review pack", "export.xlsx",
                         "Board condition", "ROUTING QUEUES",
                         "Highest priority work orders", "WO-EMERGENCY",
                         "Emergency past response time", "Evidence:",
                         "How these figures were produced"):
            self.assertIn(expected, text, expected)

    def test_never_contains_the_source_directory(self):
        text = all_text(review_pack.build(small_analysis()).to_bytes())
        self.assertNotIn("someone", text)
        self.assertNotIn("Documents", text)
        self.assertNotIn("C:", text)

    def test_disclosure_appears_only_for_synthetic_data(self):
        plain = all_text(review_pack.build(small_analysis()).to_bytes())
        declared = all_text(review_pack.build(
            small_analysis(notice="Synthetic Maintenance Dataset")
        ).to_bytes())
        self.assertNotIn("SYNTHETIC MAINTENANCE DATASET", plain)
        self.assertIn("SYNTHETIC MAINTENANCE DATASET", declared)
        self.assertIn("Synthetic Maintenance Dataset", declared)  # footer

    def test_an_analysis_with_no_findings_still_produces_a_report(self):
        text = all_text(review_pack.build(
            small_analysis(with_findings=False)).to_bytes())
        self.assertIn("Board condition", text)
        self.assertNotIn("What needs deciding", text)

    def test_detail_count_is_respected(self):
        text = all_text(review_pack.build(small_analysis(),
                                          detail_records=1).to_bytes())
        self.assertIn("The 1 most urgent", text)

    def test_table_columns_fit_the_page(self):
        # An over-wide table prints off the edge with no error, so the sum
        # of the widths is asserted here rather than discovered on paper.
        source = Path(review_pack.__file__).read_text(encoding="utf-8")
        widths = [int(w) for w in re.findall(
            r'pdf\.Column\("[^"]+", (\d+)', source)]
        self.assertLessEqual(sum(widths), USABLE_WIDTH)

    def test_write_reports_pages_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pack.pdf"
            result = review_pack.write(small_analysis(), path)
            self.assertTrue(path.exists())
            self.assertEqual(result.bytes_written, path.stat().st_size)
            self.assertGreaterEqual(result.pages, 1)
            self.assertEqual(result.kind, "PDF review pack")


class ExceptionRegisterTests(unittest.TestCase):

    def test_groups_flagged_records_by_queue(self):
        text = all_text(exception_register.build(small_analysis()).to_bytes())
        self.assertIn("EXCEPTION REGISTER", text)
        self.assertIn("Immediate Review", text)
        self.assertIn("Data Quality", text)
        self.assertIn("WO-EMERGENCY", text)
        self.assertIn("WO-NO-ASSET", text)

    def test_clean_records_are_not_listed(self):
        text = all_text(exception_register.build(small_analysis()).to_bytes())
        self.assertNotIn("WO-CLEAN-1", text)

    def test_row_count_matches_flagged_records(self):
        with tempfile.TemporaryDirectory() as directory:
            result = exception_register.write(
                small_analysis(), Path(directory) / "register.pdf")
        self.assertEqual(result.rows, 3)

    def test_nothing_flagged_still_produces_a_cover(self):
        text = all_text(exception_register.build(
            small_analysis(with_findings=False)).to_bytes())
        self.assertIn("EXCEPTION REGISTER", text)
        self.assertIn("0 of 1 retained", text)

    def test_table_columns_fit_the_page(self):
        self.assertLessEqual(
            sum(column.width for column in exception_register.COLUMNS),
            USABLE_WIDTH)

    def test_never_contains_the_source_directory(self):
        text = all_text(exception_register.build(small_analysis()).to_bytes())
        self.assertNotIn("someone", text)


class CsvTests(unittest.TestCase):

    def write(self, analysis, assessments=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "out.csv"
        result = csv_export.write(analysis, path, assessments)
        with open(path, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))
        return result, rows[0], rows[1:]

    def test_headers_are_the_declared_ones(self):
        _, header, _ = self.write(small_analysis())
        self.assertEqual(tuple(header), csv_export.HEADERS)

    def test_one_row_per_assessment(self):
        analysis = small_analysis()
        result, _, body = self.write(analysis)
        self.assertEqual(len(body), len(analysis.assessments))
        self.assertEqual(result.rows, len(body))

    def test_every_row_has_every_column(self):
        _, header, body = self.write(small_analysis())
        for row in body:
            self.assertEqual(len(row), len(header))

    def test_derived_fields(self):
        _, header, body = self.write(small_analysis())
        index = {name: position for position, name in enumerate(header)}
        by_id = {row[index["Work Order ID"]]: row for row in body}

        emergency = by_id["WO-EMERGENCY"]
        self.assertEqual(emergency[index["Severity"]], "Critical")
        self.assertEqual(emergency[index["Routing Queue"]], "Immediate Review")
        self.assertEqual(emergency[index["Age Days"]], "30")
        self.assertEqual(emergency[index["Age Band"]], "15-30 days")
        self.assertEqual(emergency[index["Primary Finding"]],
                         "Emergency past response time")
        self.assertIn("emergency_unresolved", emergency[index["Finding Keys"]])
        self.assertEqual(emergency[index["Vendor State"]], "Internal")

        done = by_id["WO-DONE"]
        self.assertEqual(done[index["Open"]], "No")
        self.assertEqual(done[index["Age Band"]], "")
        self.assertEqual(done[index["Cost Signal"]], "Over estimate")
        self.assertEqual(done[index["Cost Variance"]], "800.00")

        clean = by_id["WO-CLEAN-1"]
        self.assertEqual(clean[index["Severity"]], "None")
        self.assertEqual(clean[index["Finding Count"]], "0")
        self.assertEqual(clean[index["Has Integrity Finding"]], "No")

        no_asset = by_id["WO-NO-ASSET"]
        self.assertEqual(no_asset[index["Has Integrity Finding"]], "Yes")

    def test_a_subset_can_be_exported(self):
        analysis = small_analysis()
        flagged = [a for a in analysis.assessments if a.findings]
        result, _, body = self.write(analysis, flagged)
        self.assertEqual(len(body), 3)
        self.assertEqual(result.rows, 3)

    def test_an_empty_subset_writes_headers_only(self):
        result, header, body = self.write(small_analysis(), [])
        self.assertEqual(body, [])
        self.assertEqual(len(header), len(csv_export.HEADERS))
        self.assertEqual(result.rows, 0)

    def test_awkward_text_round_trips_through_quoting(self):
        record = work_order(
            work_order_id="WO-QUOTES",
            description='Belt "squeal", then a stop; check, re-check',
            last_note="Line one\nLine two")
        analysis = analysis_module.analyze([record], as_of=TODAY)
        analysis.imported = ImportResult(work_orders=[record])
        _, header, body = self.write(analysis)
        index = {name: position for position, name in enumerate(header)}
        self.assertEqual(body[0][index["Description"]],
                         'Belt "squeal", then a stop; check, re-check')
        self.assertEqual(body[0][index["Last Note"]], "Line one\nLine two")

    def test_vendor_states(self):
        cases = (
            (dict(), "Internal"),
            (dict(assignment_type=AssignmentType.EXTERNAL,
                  assigned_technician="", vendor=""),
             "External - vendor not named"),
            (dict(assignment_type=AssignmentType.EXTERNAL,
                  assigned_technician="", vendor="Apex Mechanical Contractors",
                  scheduled_date=None), "External - not scheduled"),
            (dict(assignment_type=AssignmentType.EXTERNAL,
                  assigned_technician="", vendor="Apex Mechanical Contractors",
                  scheduled_date=days_ago(1)), "External - scheduled"),
            (dict(assignment_type=AssignmentType.EXTERNAL,
                  assigned_technician="", vendor="Apex Mechanical Contractors",
                  scheduled_date=days_ago(40), opened_date=days_ago(60)),
             "External - overdue"),
        )
        for overrides, expected in cases:
            assessment = analysis_module.assess_one(
                work_order(**overrides), as_of=TODAY)
            self.assertEqual(csv_export.vendor_state(assessment), expected,
                             overrides)


class FullCorpusTests(unittest.TestCase):
    """Exports over the real demonstration corpus."""

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        cls.source = root / "demo.xlsx"
        records = generator.Generator(reference=REFERENCE).generate()
        generator.write(cls.source, records, REFERENCE)
        cls.before = hashlib.sha256(cls.source.read_bytes()).hexdigest()
        cls.analysis = analysis_module.analyze_workbook(str(cls.source),
                                                        as_of=REFERENCE)
        cls.pack = reporting.write_review_pack(cls.analysis, root / "a.pdf")
        cls.register = reporting.write_exception_register(
            cls.analysis, root / "b.pdf")
        cls.csv = reporting.write_csv(cls.analysis, root / "c.csv")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_the_source_workbook_is_byte_identical_after_every_export(self):
        after = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.assertEqual(after, self.before)

    def test_the_synthetic_disclosure_is_present(self):
        for result in (self.pack, self.register):
            text = all_text(Path(result.path).read_bytes())
            self.assertIn("SYNTHETIC MAINTENANCE DATASET", text, result.kind)

    def test_register_rows_equal_flagged_records(self):
        self.assertEqual(self.register.rows,
                         self.analysis.metrics.with_findings)

    def test_csv_rows_equal_retained_records(self):
        self.assertEqual(self.csv.rows, self.analysis.metrics.total)

    def test_no_text_runs_past_the_right_margin(self):
        for result in (self.pack, self.register):
            data = Path(result.path).read_bytes()
            pattern = re.compile(
                r"/(F\d) ([\d.]+) Tf 1 0 0 1 ([-\d.]+) [-\d.]+ Tm \((.*?)\) Tj")
            for raw in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data,
                                  re.S):
                content = zlib.decompress(raw).decode("latin-1")
                for font, size, x, text in pattern.findall(content):
                    right = float(x) + pdf.text_width(
                        text, float(size), font == "F2")
                    self.assertLessEqual(
                        right, pdf.A4[0] - pdf.MARGIN + 1.0,
                        f"{result.kind}: {text!r} overruns the margin")

    def test_every_page_has_a_number(self):
        for result in (self.pack, self.register):
            text = all_text(Path(result.path).read_bytes())
            for number in range(1, result.pages + 1):
                self.assertIn(f"Page {number}", text)


if __name__ == "__main__":
    unittest.main()
