"""Report and export generation.

Three outputs, all written with the standard library:

* `review_pack` - a narrative PDF for a management review.
* `exception_register` - a PDF listing each flagged record under its queue.
* `csv_export` - a flat CSV pairing the canonical fields with the derived
  intelligence, for a spreadsheet.

Nothing here reads or writes the source workbook.
"""

from .csv_export import write as write_csv
from .exception_register import write as write_exception_register
from .review_pack import write as write_review_pack
from .summary import ReportContext, ReportResult

__all__ = [
    "ReportContext",
    "ReportResult",
    "write_csv",
    "write_exception_register",
    "write_review_pack",
]
