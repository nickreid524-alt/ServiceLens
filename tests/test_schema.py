"""Canonical schema and the alias layer."""

import unittest

from servicelens.ingestion import schema as S


class CanonicalNameTests(unittest.TestCase):

    def test_canonical_name_matches_itself(self):
        for column in S.COLUMNS:
            self.assertEqual(S.canonical_name(column.name), column.name)

    def test_every_alias_resolves(self):
        for column in S.COLUMNS:
            for alias in column.aliases:
                self.assertEqual(
                    S.canonical_name(alias), column.name,
                    f"alias {alias!r} did not reach {column.name!r}")

    def test_case_and_spacing_are_ignored(self):
        for spelling in ("work order id", "WORK ORDER ID", "  Work  Order ID ",
                         "work_order_id", "Work-Order-ID"):
            self.assertEqual(S.canonical_name(spelling), S.WORK_ORDER_ID)

    def test_unknown_header_returns_none(self):
        self.assertIsNone(S.canonical_name("Reporting Region"))
        self.assertIsNone(S.canonical_name(""))

    def test_no_alias_is_claimed_by_two_columns(self):
        seen = {}
        for column in S.COLUMNS:
            for key in column.keys():
                folded = S._normalize_header(key)
                self.assertNotIn(
                    folded, seen,
                    f"{key!r} is claimed by both {seen.get(folded)} and "
                    f"{column.name}")
                seen[folded] = column.name


class ResolveHeaderTests(unittest.TestCase):

    def test_maps_indexes_to_canonical_names(self):
        report = S.resolve_headers(
            ["WO Number", "Equipment ID", "Status", "Created Date"])
        self.assertEqual(report.mapping, {
            0: S.WORK_ORDER_ID,
            1: S.ASSET_ID,
            2: S.STATUS,
            3: S.OPENED_DATE,
        })
        self.assertTrue(report.is_usable)
        self.assertEqual(report.missing_required, [])

    def test_records_the_spelling_that_matched(self):
        report = S.resolve_headers(["WO Number"])
        self.assertEqual(report.matched[S.WORK_ORDER_ID], "WO Number")

    def test_missing_required_columns_are_named(self):
        report = S.resolve_headers(["Work Order ID", "Site"])
        self.assertFalse(report.is_usable)
        self.assertEqual(
            sorted(report.missing_required),
            sorted([S.ASSET_ID, S.OPENED_DATE, S.STATUS]))

    def test_missing_optional_columns_are_named_not_fatal(self):
        report = S.resolve_headers(
            ["Work Order ID", "Asset ID", "Status", "Opened Date"])
        self.assertTrue(report.is_usable)
        self.assertIn(S.VENDOR, report.missing_optional)

    def test_first_spelling_wins_and_repeats_are_recorded(self):
        report = S.resolve_headers(["Work Order ID", "WO Number"])
        self.assertEqual(report.mapping, {0: S.WORK_ORDER_ID})
        self.assertEqual(report.duplicates[S.WORK_ORDER_ID], ["WO Number"])

    def test_unrecognized_headers_are_kept_not_dropped(self):
        report = S.resolve_headers(["Work Order ID", "Reporting Region"])
        self.assertEqual(report.unmapped_headers, ["Reporting Region"])

    def test_blank_headers_are_skipped(self):
        report = S.resolve_headers(["Work Order ID", "", "   ", "Status"])
        self.assertEqual(report.mapping, {0: S.WORK_ORDER_ID, 3: S.STATUS})

    def test_summary_mentions_missing_required(self):
        report = S.resolve_headers(["Work Order ID"])
        self.assertIn("missing required", report.summary())


class HeaderScoreTests(unittest.TestCase):

    def test_real_header_outscores_a_title_row(self):
        title = ["Maintenance Status Report", "", ""]
        header = ["WO Number", "Equipment", "Status", "Opened"]
        self.assertGreater(S.header_score(header), S.header_score(title))


if __name__ == "__main__":
    unittest.main()
