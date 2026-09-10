"""The synthetic corpus generator.

The important test here is coverage: the demonstration workbook only
demonstrates anything if every rule has something in it to find.
"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from servicelens import analysis
from servicelens.demo import corpus, generator
from servicelens.domain.models import Severity
from servicelens.ingestion import schema as S
from servicelens.ingestion.normalization import load_workbook

REFERENCE = date(2026, 6, 15)


class DeterminismTests(unittest.TestCase):

    def test_the_same_seed_produces_the_same_corpus(self):
        first = generator.Generator(reference=REFERENCE).generate()
        second = generator.Generator(reference=REFERENCE).generate()
        self.assertEqual([r.values for r in first], [r.values for r in second])

    def test_a_different_seed_produces_a_different_corpus(self):
        first = generator.Generator(reference=REFERENCE).generate()
        other = generator.Generator(seed=1, reference=REFERENCE).generate()
        self.assertNotEqual([r.values for r in first],
                            [r.values for r in other])

    def test_the_corpus_is_within_the_intended_size_range(self):
        records = generator.Generator(reference=REFERENCE).generate()
        self.assertGreaterEqual(len(records), 1000)
        self.assertLessEqual(len(records), 3000)

    def test_the_plan_predicts_the_number_of_records_built(self):
        records = generator.Generator(reference=REFERENCE).generate()
        self.assertEqual(len(records), generator.planned_total())

    def test_every_planned_scenario_produced_records(self):
        instance = generator.Generator(reference=REFERENCE)
        instance.generate()
        for scenario, _ in generator.SCENARIO_PLAN:
            self.assertGreater(instance.scenario_counts.get(scenario, 0), 0,
                               scenario)


class HeaderTests(unittest.TestCase):

    def test_every_canonical_column_is_written(self):
        written = {canonical for _, canonical in generator.HEADERS
                   if canonical}
        self.assertEqual(written, {column.name for column in S.COLUMNS})

    def test_headers_exercise_the_alias_layer(self):
        aliased = [header for header, canonical in generator.HEADERS
                   if canonical and header != canonical]
        self.assertGreater(len(aliased), 5)

    def test_an_unmapped_column_is_included_on_purpose(self):
        unmapped = [h for h, canonical in generator.HEADERS
                    if canonical is None]
        self.assertEqual(unmapped, ["Reporting Region"])


class WorkbookTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.path = Path(cls.directory.name) / "demo.xlsx"
        instance = generator.Generator(reference=REFERENCE)
        cls.records = instance.generate()
        generator.write(cls.path, cls.records, REFERENCE)
        cls.imported = load_workbook(str(cls.path))
        cls.analysis = analysis.analyze_workbook(str(cls.path),
                                                 as_of=REFERENCE)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_the_workbook_reads_back_completely(self):
        self.assertEqual(self.imported.count, len(self.records))
        self.assertEqual(self.imported.sheet_name, generator.SHEET_NAME)

    def test_the_header_row_is_found_below_the_preamble(self):
        self.assertGreater(self.imported.header_row, 1)

    def test_every_canonical_column_is_recognized(self):
        self.assertEqual(self.imported.schema.missing_required, [])
        self.assertEqual(self.imported.schema.missing_optional, [])

    def test_the_extra_column_is_reported_not_interpreted(self):
        self.assertEqual(self.imported.schema.unmapped_headers,
                         ["Reporting Region"])

    def test_dates_survive_the_round_trip(self):
        dated = [w for w in self.imported.work_orders
                 if w.opened_date is not None]
        self.assertGreater(len(dated), 1000)
        self.assertTrue(all(isinstance(w.opened_date, date) for w in dated))

    def test_exclusions_reconcile(self):
        self.assertTrue(self.analysis.exclusions.reconciles())
        self.assertGreater(self.analysis.exclusions.total_excluded, 0)

    def test_every_rule_fires_at_least_once(self):
        unfired = self.analysis.unfired_rules()
        self.assertEqual(unfired, [], f"rules never triggered: {unfired}")

    def test_every_severity_is_represented(self):
        for label, count in self.analysis.metrics.severity_counts.items():
            self.assertGreater(count, 0, label)

    def test_every_queue_has_work_in_it(self):
        for queue, count in self.analysis.metrics.by_queue:
            self.assertGreater(count, 0, queue)

    def test_every_team_has_work_in_it(self):
        for team, count in self.analysis.metrics.by_team:
            self.assertGreater(count, 0, team)

    def test_every_aging_band_is_populated(self):
        for band, count in self.analysis.metrics.by_aging_band:
            self.assertGreater(count, 0, band)

    def test_the_exception_rate_sits_inside_the_intended_band(self):
        # A band, not a number: the point is that the demo looks like a
        # working operation, and a small change to one scenario should not
        # break the build.
        low, high = generator.EXCEPTION_RATE_BAND
        rate = self.analysis.metrics.exception_rate
        self.assertGreaterEqual(rate, low, f"exception rate {rate:.1%} too low")
        self.assertLessEqual(rate, high, f"exception rate {rate:.1%} too high")

    def test_the_band_brackets_the_stated_target(self):
        low, high = generator.EXCEPTION_RATE_BAND
        self.assertLess(low, generator.TARGET_EXCEPTION_RATE)
        self.assertGreater(high, generator.TARGET_EXCEPTION_RATE)

    def test_ordinary_work_is_the_clear_majority(self):
        metrics = self.analysis.metrics
        self.assertGreater(metrics.clean, metrics.with_findings)
        self.assertGreater(metrics.clean / metrics.total, 0.55)

    def test_critical_work_is_present_but_does_not_dominate(self):
        critical = [a for a in self.analysis.assessments
                    if a.severity is Severity.CRITICAL]
        share = len(critical) / self.analysis.metrics.total
        self.assertGreater(len(critical), 50, "no visible critical work")
        self.assertLess(share, 0.12, f"critical work is {share:.1%} of the board")

    def test_warnings_and_information_both_stay_meaningful(self):
        counts = self.analysis.metrics.severity_counts
        self.assertGreater(counts[Severity.WARNING.label], 100)
        self.assertGreater(counts[Severity.INFORMATION.label], 50)

    def test_clean_records_exist_so_the_corpus_is_not_all_exceptions(self):
        self.assertGreater(self.analysis.metrics.clean, 100)

    def test_both_open_and_completed_work_exist(self):
        self.assertGreater(self.analysis.metrics.open_count, 100)
        self.assertGreater(self.analysis.metrics.completed_count, 100)

    def test_the_reference_date_is_recovered_from_the_workbook(self):
        recovered = analysis.analyze_workbook(str(self.path))
        self.assertEqual(recovered.as_of, REFERENCE)


class CorpusTests(unittest.TestCase):

    def test_the_vocabulary_is_not_empty(self):
        for name in ("SITES", "DEPARTMENTS", "VENDORS", "TECHNICIANS"):
            self.assertGreater(len(getattr(corpus, name)), 3, name)

    def test_every_asset_category_has_names_and_faults(self):
        for category, (prefix, names) in corpus.ASSET_TYPES.items():
            self.assertTrue(prefix, category)
            self.assertGreater(len(names), 2, category)
            self.assertGreater(len(corpus.FAULTS[category]), 2, category)

    def test_asset_prefixes_are_unique(self):
        prefixes = [prefix for prefix, _ in corpus.ASSET_TYPES.values()]
        self.assertEqual(len(prefixes), len(set(prefixes)))


class CommandLineTests(unittest.TestCase):

    def test_the_module_writes_a_workbook(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.xlsx"
            code = generator.main(
                ["-o", str(path), "--reference", "2026-06-15", "--quiet"])
            self.assertEqual(code, 0)
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 10000)

    def test_a_pinned_reference_date_gives_a_byte_identical_file(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.xlsx"
            second = Path(directory) / "b.xlsx"
            for path in (first, second):
                generator.main(["-o", str(path), "--reference", "2026-06-15",
                                "--quiet"])
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
