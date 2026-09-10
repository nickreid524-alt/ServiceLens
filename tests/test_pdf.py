"""The standard-library PDF writer.

Structural tests only: the file parses, the cross-reference table points at
real objects, text survives escaping. Nothing here renders pixels.
"""

import re
import unittest
import zlib

from servicelens.reporting import pdf


def parse(data: bytes) -> dict:
    """Pull the pieces of a PDF apart far enough to check them."""
    objects = {int(m.group(1)): m.start()
               for m in re.finditer(rb"(\d+) 0 obj", data)}
    start = int(re.search(rb"startxref\s+(\d+)", data).group(1))
    xref_block = data[start:]
    entries = re.findall(rb"(\d{10}) (\d{5}) ([nf])", xref_block)
    return {
        "objects": objects,
        "startxref": start,
        "entries": entries,
        "count": int(re.search(rb"/Size (\d+)", data).group(1)),
        "pages": int(re.search(rb"/Count (\d+)", data).group(1)),
    }


def page_text(data: bytes, index: int = 0) -> str:
    """Decompressed content of one page's stream."""
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S)
    return zlib.decompress(streams[index]).decode("latin-1")


class MetricsTests(unittest.TestCase):

    def test_widths_scale_with_size(self):
        self.assertAlmostEqual(pdf.text_width("a", 10), 5.56)
        self.assertAlmostEqual(pdf.text_width("a", 20), 11.12)

    def test_bold_is_wider(self):
        self.assertGreater(pdf.text_width("Report", 10, bold=True),
                           pdf.text_width("Report", 10))

    def test_unknown_characters_get_a_fallback_width(self):
        self.assertGreater(pdf.text_width("☃", 10), 0)

    def test_truncate_fits_the_limit(self):
        text = "A fairly long description of a maintenance task"
        short = pdf.truncate(text, 9, 80)
        self.assertTrue(short.endswith("..."))
        self.assertLessEqual(pdf.text_width(short, 9), 80)

    def test_truncate_leaves_short_text_alone(self):
        self.assertEqual(pdf.truncate("Pump", 9, 200), "Pump")

    def test_wrap_respects_the_limit(self):
        text = " ".join(["word"] * 40)
        lines = pdf.wrap(text, 9, 120)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(pdf.text_width(line, 9), 120)

    def test_wrap_breaks_an_overlong_single_word(self):
        lines = pdf.wrap("x" * 200, 9, 100)
        self.assertGreater(len(lines), 1)
        self.assertEqual("".join(lines), "x" * 200)

    def test_wrap_of_nothing_is_nothing(self):
        self.assertEqual(pdf.wrap("   ", 9, 100), [])


class EscapingTests(unittest.TestCase):

    def test_parentheses_and_backslashes_are_escaped(self):
        self.assertEqual(pdf.escape("a(b)c\\d"), b"a\\(b\\)c\\\\d")

    def test_non_latin_text_does_not_raise(self):
        self.assertIsInstance(pdf.escape("☃ snow"), bytes)

    def test_win_ansi_characters_survive(self):
        self.assertEqual(pdf.escape("café"), "café".encode("cp1252"))


class DocumentTests(unittest.TestCase):

    def build(self, pages: int = 1, compress: bool = True) -> bytes:
        document = pdf.Document(title="Test (title)")
        for number in range(pages):
            page = document.add_page()
            page.text(50, 700, f"Page {number + 1} says (hello)", 12)
            page.rect(50, 600, 100, 20, fill=pdf.BAND)
            page.line(50, 590, 150, 590)
        return document.to_bytes(compress=compress)

    def test_header_and_trailer(self):
        data = self.build()
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))

    def test_object_count_matches_the_trailer(self):
        parsed = parse(self.build(pages=3))
        # catalogue, pages, two fonts, info, then two objects per page
        self.assertEqual(len(parsed["objects"]), 5 + 3 * 2)
        self.assertEqual(parsed["count"], len(parsed["objects"]) + 1)
        self.assertEqual(parsed["pages"], 3)

    def test_every_xref_offset_points_at_its_object(self):
        data = self.build(pages=4)
        parsed = parse(data)
        self.assertEqual(len(parsed["entries"]), parsed["count"])
        for number, (offset, _generation, kind) in enumerate(
                parsed["entries"]):
            if kind == b"f":
                self.assertEqual(number, 0)
                continue
            self.assertEqual(int(offset), parsed["objects"][number])
            self.assertTrue(
                data[int(offset):].startswith(f"{number} 0 obj".encode()))

    def test_startxref_points_at_the_xref_table(self):
        data = self.build()
        parsed = parse(data)
        self.assertTrue(data[parsed["startxref"]:].startswith(b"xref"))

    def test_streams_declare_their_length(self):
        data = self.build()
        for match in re.finditer(
                rb"/Length (\d+)[^>]*>>\s*stream\r?\n(.*?)\r?\nendstream",
                data, re.S):
            self.assertEqual(int(match.group(1)), len(match.group(2)))

    def test_text_is_present_and_escaped(self):
        content = page_text(self.build())
        self.assertIn(r"(Page 1 says \(hello\)) Tj", content)

    def test_uncompressed_output_is_readable_directly(self):
        data = self.build(compress=False)
        self.assertNotIn(b"FlateDecode", data)
        self.assertIn(b"(Page 1 says \\(hello\\)) Tj", data)

    def test_compressed_output_is_smaller(self):
        self.assertLess(len(self.build(pages=3)),
                        len(self.build(pages=3, compress=False)))

    def test_an_empty_document_still_has_one_page(self):
        parsed = parse(pdf.Document().to_bytes())
        self.assertEqual(parsed["pages"], 1)

    def test_document_info_is_written(self):
        data = self.build()
        self.assertIn(b"/Title (Test \\(title\\))", data)
        self.assertIn(b"/Producer (ServiceLens)", data)

    def test_empty_text_writes_nothing(self):
        document = pdf.Document()
        page = document.add_page()
        page.text(10, 10, "")
        page.text(10, 10, None)
        self.assertEqual(page.content(), b"")


class LayoutTests(unittest.TestCase):

    def test_pages_break_when_content_runs_out_of_room(self):
        document = pdf.Document()
        layout = pdf.Layout(document, title="T", footer="F")
        layout.new_page()
        for _ in range(200):
            layout.paragraph("A line of text that takes some room.")
        self.assertGreater(len(document.pages), 2)

    def test_running_header_and_footer_appear_after_page_one(self):
        document = pdf.Document()
        layout = pdf.Layout(document, title="Running title", footer="Foot")
        layout.new_page()
        layout.new_page()
        first = page_text(document.to_bytes(), 0)
        second = page_text(document.to_bytes(), 1)
        self.assertIn("(Page 1) Tj", first)
        self.assertIn("(Foot) Tj", first)
        self.assertNotIn("(Running title) Tj", first)
        self.assertIn("(Running title) Tj", second)
        self.assertIn("(Page 2) Tj", second)

    def test_table_columns_are_truncated_to_their_width(self):
        document = pdf.Document()
        layout = pdf.Layout(document)
        layout.new_page()
        columns = (pdf.Column("Narrow", 40),)
        layout.table_header(columns)
        layout.table_row(columns, ("An extremely long cell value",))
        content = page_text(document.to_bytes())
        self.assertIn("...", content)
        self.assertNotIn("An extremely long cell value", content)

    def test_bars_handle_all_zero_rows(self):
        document = pdf.Document()
        layout = pdf.Layout(document)
        layout.new_page()
        layout.bars([("a", 0), ("b", 0)])
        self.assertIn("(a) Tj", page_text(document.to_bytes()))

    def test_bars_with_nothing_say_so(self):
        document = pdf.Document()
        layout = pdf.Layout(document)
        layout.new_page()
        layout.bars([])
        self.assertIn("Nothing to show", page_text(document.to_bytes()))


if __name__ == "__main__":
    unittest.main()
