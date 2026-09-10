"""The management review pack.

A narrative PDF: what the board looks like, where the work is queued, how it
is aging, and then the records that need a decision first - each with the
finding, the evidence behind it, and the action being asked for.

It is written to be read by someone who was not at the keyboard, so every
number carries its provenance and the reporting date is stated on the first
page rather than assumed.
"""

from __future__ import annotations

from ..domain.models import Severity
from . import pdf
from .summary import (
    ReportContext,
    ReportResult,
    money_exact,
    severity_colour,
)

DEFAULT_DETAIL_RECORDS = 25
DEFAULT_FILENAME = "servicelens_review_pack.pdf"


def _queue_colour(name: str):
    return {
        "Immediate Review": pdf.CRITICAL,
        "Data Quality": pdf.INFORMATION,
        "Vendor Follow-up": pdf.ACCENT,
        "Cost Review": pdf.WARNING,
        "Preventive Maintenance": pdf.CLEAR,
        "Maintenance Planning": pdf.ACCENT,
        "Routine Operations": pdf.SUBTLE,
    }.get(name, pdf.ACCENT)


def build(analysis, detail_records: int = DEFAULT_DETAIL_RECORDS,
          context: ReportContext | None = None) -> pdf.Document:
    """Compose the review pack. Returns the document, unwritten."""
    facts = context or ReportContext(analysis)
    document = pdf.Document(
        title="ServiceLens Review Pack",
        subject=f"Work order intelligence for {facts.source_name}")
    layout = pdf.Layout(
        document,
        title="ServiceLens - Work Order Intelligence",
        subtitle="Review pack",
        footer=("Synthetic Maintenance Dataset" if facts.is_synthetic
                else facts.source_name),
    )
    layout.new_page()

    _cover(layout, facts)
    _condition(layout, facts)
    _distributions(layout, facts)
    _priorities(layout, facts, analysis)
    _details(layout, facts, analysis, detail_records)
    _method(layout, facts)
    return document


def write(analysis, path, detail_records: int = DEFAULT_DETAIL_RECORDS
          ) -> ReportResult:
    """Build and write the review pack."""
    document = build(analysis, detail_records)
    written = document.save(path)
    return ReportResult(str(path), "PDF review pack", written,
                        pages=len(document.pages))


# --- sections --------------------------------------------------------

def _cover(layout: pdf.Layout, facts: ReportContext) -> None:
    page = layout.page
    layout.y += 26
    page.text(layout.margin, layout._at(), "ServiceLens", 24, True, pdf.INK)
    layout.y += 15
    page.text(layout.margin, layout._at(), "WORK ORDER INTELLIGENCE", 9,
              True, pdf.ACCENT)
    layout.y += 26
    page.text(layout.margin, layout._at(), "Management review pack", 15,
              True, pdf.INK)
    layout.y += 6
    layout.rule(6, 10)

    if facts.disclosure:
        _banner(layout, facts.disclosure)

    layout.label("Report basis")
    layout.key_values(facts.provenance(), label_width=132)
    if facts.dataset_notice:
        layout.paragraph("The workbook describes itself as: "
                         f"'{facts.dataset_notice}'", 8, pdf.SUBTLE)


def _banner(layout: pdf.Layout, text: str) -> None:
    """A boxed notice that cannot be mistaken for body text."""
    lines = pdf.wrap(text, 8.5, layout.width - 22, True)
    height = len(lines) * 11 + 12
    layout.ensure(height + 10)
    layout.y += 4
    top = layout._at()
    layout.page.rect(layout.margin, top - height + 8, layout.width, height,
                     fill=(0.99, 0.95, 0.94), stroke=pdf.CRITICAL,
                     line_width=0.8)
    layout.y += 10
    for line in lines:
        layout.page.text(layout.margin + 11, layout._at(), line, 8.5, True,
                         pdf.CRITICAL)
        layout.y += 11
    layout.y += 6


def _condition(layout: pdf.Layout, facts: ReportContext) -> None:
    layout.rule(8, 6)
    layout.heading("Board condition", 13)
    metrics = facts.metrics
    layout.paragraph(
        f"{metrics.total:,} work orders were retained for analysis after "
        f"exclusions. {metrics.with_findings:,} of them "
        f"({metrics.exception_rate:.0%}) carry at least one finding, raising "
        f"{metrics.findings_total:,} findings in total. The remaining "
        f"{metrics.clean:,} need no action beyond completing the work.")
    layout.figures(facts.headline(), per_row=4)

    layout.label("Findings by severity")
    layout.bars(facts.severity_rows(),
                colour=lambda label: pdf.SEVERITY_COLOUR.get(label,
                                                             pdf.ACCENT))


def _distributions(layout: pdf.Layout, facts: ReportContext) -> None:
    layout.rule(10, 6)
    layout.heading("Where the work sits", 13)
    layout.paragraph(
        "Ownership follows the record - who it is contracted to, who the "
        "export says owns it, and what kind of asset it is. The action queue "
        "follows the findings instead, so a queue is a list of decisions "
        "rather than a list of departments.")

    layout.label("Routing queues")
    layout.bars(facts.queue_rows(), colour=_queue_colour)

    layout.label("Aging of open work")
    layout.bars(facts.aging_rows(), colour=pdf.ACCENT)

    layout.label("Work by owning team")
    layout.bars(facts.team_rows(), colour=pdf.ACCENT)


def _priorities(layout: pdf.Layout, facts: ReportContext, analysis) -> None:
    layout.rule(10, 6)
    layout.heading("Highest priority work orders", 13)
    layout.paragraph(
        "Ranked by severity, then by how many findings a record carries, "
        "then by age. This is the order the queue should be worked in.")

    # Widths sum to less than the usable page width; `test_reporting`
    # asserts it, because an over-wide table silently prints off the edge.
    columns = (
        pdf.Column("Work order", 92, bold=True),
        pdf.Column("Asset", 58),
        pdf.Column("Site", 106),
        pdf.Column("Priority", 46),
        pdf.Column("Severity", 50),
        pdf.Column("Queue", 92),
        pdf.Column("Age", 28, align="right"),
        pdf.Column("Flags", 28, align="right"),
    )
    layout.table_header(columns)
    for index, assessment in enumerate(analysis.attention(limit=30)):
        work_order = assessment.work_order
        severity = assessment.severity
        layout.table_row(
            columns,
            (work_order.identity,
             work_order.asset_id or "-",
             work_order.site or "-",
             work_order.priority.label if work_order.priority else "-",
             severity.label if severity else "-",
             assessment.queue,
             f"{assessment.age}" if assessment.age is not None else "-",
             f"{len(assessment.findings)}"),
            colours=(pdf.INK, pdf.INK, pdf.INK, pdf.INK,
                     severity_colour(assessment), pdf.MUTED, pdf.INK,
                     pdf.INK),
            banded=bool(index % 2))
    layout.gap(6)


def _details(layout: pdf.Layout, facts: ReportContext, analysis,
             limit: int) -> None:
    if limit <= 0:
        return
    records = analysis.attention(limit=limit)
    if not records:
        return

    layout.rule(10, 6)
    layout.heading("What needs deciding, and why", 13)
    layout.paragraph(
        f"The {len(records)} most urgent records in full. Each finding is "
        "shown with the evidence on the record that triggered it and the "
        "action being requested, so a decision can be taken without opening "
        "the source workbook.")

    for assessment in records:
        _detail_block(layout, assessment)


def _detail_block(layout: pdf.Layout, assessment) -> None:
    work_order = assessment.work_order
    severity = assessment.severity
    accent = severity_colour(assessment)

    layout.ensure(74)
    layout.gap(10)
    top = layout._at()
    layout.page.rect(layout.margin - 4, top - 4, 2.5, 16, fill=accent)
    layout.page.text(layout.margin + 4, top, work_order.identity, 10.5, True,
                     pdf.INK)
    layout.page.text_right(
        layout.size[0] - layout.margin, top,
        f"{severity.label if severity else 'No findings'}  ·  "
        f"{assessment.queue}", 8.5, True, accent)
    layout.y += 12
    layout.page.text(layout.margin + 4, layout._at(),
                     pdf.truncate(work_order.description or
                                  "No description recorded", 8.5,
                                  layout.width - 8),
                     8.5, False, pdf.MUTED)
    layout.y += 6

    facts_line = "   ".join(part for part in (
        work_order.asset_id and f"Asset {work_order.asset_id}",
        work_order.site,
        work_order.status.label if work_order.status else work_order.raw_status,
        work_order.priority.label if work_order.priority else "",
        f"{assessment.age} days open" if assessment.age is not None else "",
        f"Team {assessment.team}",
        work_order.vendor and f"Vendor {work_order.vendor}",
        (work_order.estimated_cost is not None
         and f"Estimate {money_exact(work_order.estimated_cost)}") or "",
    ) if part)
    for line in pdf.wrap(facts_line, 7.5, layout.width - 8):
        layout.y += 10
        layout.page.text(layout.margin + 4, layout._at(), line, 7.5, False,
                         pdf.SUBTLE)
    layout.y += 4

    for finding in assessment.findings:
        colour = pdf.SEVERITY_COLOUR.get(finding.severity.label, pdf.SUBTLE)
        layout.ensure(34)
        layout.y += 11
        layout.page.text(layout.margin + 10, layout._at(),
                         f"{finding.severity.label.upper()}  {finding.title}",
                         8, True, colour)
        for line in pdf.wrap(finding.message, 8, layout.width - 20):
            layout.ensure(12)
            layout.y += 10
            layout.page.text(layout.margin + 10, layout._at(), line, 8,
                             False, pdf.INK)
        for line in pdf.wrap(f"Evidence: {finding.basis}", 7.5,
                             layout.width - 20):
            layout.ensure(12)
            layout.y += 9.5
            layout.page.text(layout.margin + 10, layout._at(), line, 7.5,
                             False, pdf.MUTED)
    layout.y += 4
    layout.page.line(layout.margin, layout._at(),
                     layout.size[0] - layout.margin, layout._at(),
                     pdf.LINE, 0.4)


def _method(layout: pdf.Layout, facts: ReportContext) -> None:
    layout.rule(12, 6)
    layout.heading("How these figures were produced", 12)
    analysis = facts.analysis
    layout.paragraph(
        "The source workbook was opened for reading only and was not "
        "modified. Columns were matched to a canonical schema through an "
        "alias layer; anything unrecognised is reported rather than "
        "discarded. Exclusions are counted so that rows read always equal "
        "rows excluded plus rows retained.")
    layout.key_values([
        ("Rules evaluated", f"{len(analysis.rule_coverage())}"),
        ("Rules that fired", str(sum(
            1 for count in analysis.rule_coverage().values() if count))),
        ("Exclusions reconcile",
         "yes" if analysis.exclusions.reconciles() else "no"),
        ("Reporting date basis",
         "inferred from the latest date in the workbook"),
    ], label_width=150)
    if facts.disclosure:
        layout.gap(4)
        layout.paragraph(facts.disclosure, 8, pdf.CRITICAL)
