"""Facts every report shares.

Both PDFs and the CSV need the same provenance and the same headline
figures. Computing them once here keeps a report from quietly disagreeing
with the screen, and keeps the source-path rule in one place: a report names
the file, never where it lives.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from ..domain.models import Severity
from . import pdf

SYNTHETIC_MARKERS = ("synthetic", "demonstration", "demo dataset")


@dataclass
class ReportResult:
    """What a completed export produced, for reporting back to the user."""

    path: str
    kind: str
    bytes_written: int = 0
    pages: int = 0
    rows: int = 0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    def describe(self) -> str:
        parts = [f"{self.bytes_written:,} bytes"]
        if self.pages:
            parts.insert(0, f"{self.pages} page"
                            f"{'s' if self.pages != 1 else ''}")
        if self.rows:
            parts.insert(0, f"{self.rows:,} row"
                            f"{'s' if self.rows != 1 else ''}")
        return ", ".join(parts)


@dataclass
class ReportContext:
    """The provenance and headline figures a report is built from."""

    analysis: object
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def metrics(self):
        return self.analysis.metrics

    @property
    def source_name(self) -> str:
        """The workbook's file name, never its path.

        A report may be shared outside the machine that produced it, so the
        directory it came from - which usually contains someone's user name -
        is deliberately not carried into the output.
        """
        return os.path.basename(
            self.analysis.imported.source_path) or "(not recorded)"

    @property
    def dataset_notice(self) -> str:
        """The workbook's own description of itself, if it carried one."""
        return self.analysis.imported.notice

    @property
    def is_synthetic(self) -> bool:
        """True when the source workbook declares itself demonstration data.

        Read from the workbook rather than assumed from the file name, so
        the disclosure follows the data and not the filename someone chose.
        """
        text = " ".join(self.analysis.imported.preamble).casefold()
        return any(marker in text for marker in SYNTHETIC_MARKERS)

    @property
    def disclosure(self) -> str:
        if not self.is_synthetic:
            return ""
        return ("SYNTHETIC MAINTENANCE DATASET - every work order, asset, "
                "site, technician and vendor in this report is invented for "
                "demonstration. No figure here describes a real operation.")

    @property
    def timestamp(self) -> str:
        return self.generated_at.strftime("%d %B %Y at %H:%M")

    @property
    def as_of(self) -> str:
        return self.analysis.as_of.strftime("%d %B %Y")

    # -- shared blocks -------------------------------------------------

    def provenance(self) -> list:
        imported = self.analysis.imported
        return [
            ("Source workbook", self.source_name),
            ("Worksheet", imported.sheet_name or "-"),
            ("Reporting date", self.as_of),
            ("Rows read", f"{imported.rows_read:,}"),
            ("Excluded", self.analysis.exclusions.summary()),
            ("Columns recognized", imported.schema.summary()),
            ("Generated", self.timestamp),
        ]

    def headline(self) -> list:
        """Headline figures as (value, caption, colour) tiles."""
        metrics = self.metrics
        limits = self.analysis.policy.thresholds
        critical = sum(1 for a in self.analysis.assessments
                       if a.severity is Severity.CRITICAL)
        aged = sum(1 for a in self.analysis.assessments
                   if a.work_order.is_open and a.age is not None
                   and a.age >= limits.aging_days)
        return [
            (f"{metrics.open_count:,}", "Open work orders", pdf.INK),
            (f"{critical:,}", "Carrying a critical finding", pdf.CRITICAL),
            (f"{aged:,}", f"Open {limits.aging_days}+ days", pdf.WARNING),
            (f"{metrics.exception_rate:.0%}", "Carrying any finding",
             pdf.ACCENT),
            (f"{metrics.with_findings:,}", "Flagged work orders", pdf.INK),
            (f"{metrics.clean:,}", "Clean work orders", pdf.CLEAR),
            (money(metrics.open_cost), "Open cost", pdf.INK),
            (f"{metrics.median_open_age:.0f}", "Median days open", pdf.INK),
        ]

    def severity_rows(self) -> list:
        counts = self.metrics.severity_counts
        return [(label, counts.get(label, 0))
                for label in ("Critical", "Warning", "Information")]

    def queue_rows(self) -> list:
        return list(self.metrics.by_queue)

    def aging_rows(self) -> list:
        return list(self.metrics.by_aging_band)

    def team_rows(self) -> list:
        return list(self.metrics.by_team)


def money(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    if value >= 10_000:
        return f"${value / 1000:,.0f}k"
    return f"${value:,.0f}"


def money_exact(value) -> str:
    return f"{value:,.2f}" if value is not None else ""


def severity_label(assessment) -> str:
    severity = assessment.severity
    return severity.label if severity else "None"


def severity_colour(assessment):
    return pdf.SEVERITY_COLOUR.get(severity_label(assessment), pdf.SUBTLE)


def primary_finding(assessment):
    """The finding that should be acted on first, or None when clean."""
    return assessment.findings[0] if assessment.findings else None
