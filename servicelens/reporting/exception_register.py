"""The exception register.

Every flagged work order, grouped by the queue it was routed to, with the
action being asked for on each. A PDF rather than a spreadsheet because this
is the artefact that goes into a review meeting: it is read in queue order,
one section at a time, and each section ends with its own count.

The flat, filterable view of the same data is the CSV export.
"""

from __future__ import annotations

from ..domain.models import QUEUES
from . import pdf
from .summary import ReportContext, ReportResult, severity_colour

DEFAULT_FILENAME = "servicelens_exception_register.pdf"

COLUMNS = (
    pdf.Column("Work order", 86, bold=True),
    pdf.Column("Asset", 54),
    pdf.Column("Site", 96),
    pdf.Column("Priority", 44),
    pdf.Column("Status", 56),
    pdf.Column("Sev", 30),
    pdf.Column("Flags", 24, align="right"),
    pdf.Column("Recommended action", 110),
)


def build(analysis, context: ReportContext | None = None) -> pdf.Document:
    """Compose the exception register. Returns the document, unwritten."""
    facts = context or ReportContext(analysis)
    document = pdf.Document(
        title="ServiceLens Exception Register",
        subject=f"Flagged work orders from {facts.source_name}")
    layout = pdf.Layout(
        document,
        title="ServiceLens - Exception Register",
        subtitle=facts.as_of,
        footer=("Synthetic Maintenance Dataset" if facts.is_synthetic
                else facts.source_name),
    )
    layout.new_page()

    _cover(layout, facts)
    _sections(layout, facts, analysis)
    return document


def write(analysis, path) -> ReportResult:
    """Build and write the exception register."""
    document = build(analysis)
    written = document.save(path)
    return ReportResult(str(path), "PDF exception register", written,
                        pages=len(document.pages),
                        rows=analysis.metrics.with_findings)


def _cover(layout: pdf.Layout, facts: ReportContext) -> None:
    page = layout.page
    layout.y += 22
    page.text(layout.margin, layout._at(), "ServiceLens", 20, True, pdf.INK)
    layout.y += 13
    page.text(layout.margin, layout._at(), "EXCEPTION REGISTER", 9, True,
              pdf.ACCENT)
    layout.y += 8
    layout.rule(6, 8)

    metrics = facts.metrics
    layout.paragraph(
        f"Every work order carrying at least one finding, grouped by the "
        f"queue it was routed to. {metrics.with_findings:,} of "
        f"{metrics.total:,} retained records appear here; the remaining "
        f"{metrics.clean:,} raised nothing.")

    if facts.disclosure:
        layout.gap(2)
        layout.paragraph(facts.disclosure, 8, pdf.CRITICAL)

    layout.key_values([
        ("Source workbook", facts.source_name),
        ("Reporting date", facts.as_of),
        ("Generated", facts.timestamp),
        ("Critical / Warning / Information",
         f"{metrics.critical:,} / {metrics.warning:,} / "
         f"{metrics.information:,}"),
    ], label_width=150)


def _sections(layout: pdf.Layout, facts: ReportContext, analysis) -> None:
    ordered = [queue for queue in QUEUES if queue != "Routine Operations"]
    for queue in ordered:
        records = [a for a in analysis.attention() if a.queue == queue]
        if not records:
            continue
        _section(layout, queue, records)


def _section(layout: pdf.Layout, queue: str, records) -> None:
    layout.rule(12, 6)
    layout.heading(queue, 12.5)
    layout.paragraph(
        f"{len(records):,} work order{'s' if len(records) != 1 else ''} "
        f"routed here.", 8.5, pdf.MUTED)
    layout.table_header(COLUMNS)

    for index, assessment in enumerate(records):
        work_order = assessment.work_order
        severity = assessment.severity
        finding = assessment.findings[0] if assessment.findings else None
        layout.table_row(
            COLUMNS,
            (work_order.identity,
             work_order.asset_id or "-",
             work_order.site or "-",
             work_order.priority.label if work_order.priority else "-",
             (work_order.status.label if work_order.status
              else work_order.raw_status or "-"),
             (severity.label[:4].upper() if severity else "-"),
             f"{len(assessment.findings)}",
             finding.title if finding else "-"),
            colours=(pdf.INK, pdf.INK, pdf.INK, pdf.INK, pdf.INK,
                     severity_colour(assessment), pdf.INK, pdf.MUTED),
            banded=bool(index % 2))
    layout.gap(4)
