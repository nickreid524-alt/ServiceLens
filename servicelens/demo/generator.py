"""Generate the synthetic demonstration workbook.

    python -m servicelens.demo.generator

The corpus is built from designed scenarios rather than from noise. Each
scenario exists to make one rule visibly true on real-looking records, so
every dashboard figure and every queue has something in it and nothing in
the application has to be imagined.

**Reproducibility.** The random seed is fixed, so the same run always
produces the same shape: the same scenario mix, the same site and vendor
choices, the same identifiers.

**Dates are relative.** Every date is generated as an offset from a
reference date, which defaults to the day the workbook is generated. Two
workbooks generated on different days therefore hold the same work orders
with the dates shifted. Pass `--reference` to pin the reference date and get
a byte-comparable file. ServiceLens infers a workbook's own reporting date
when it reads it, so a stored workbook keeps reporting the ages it was built
with rather than aging on the shelf.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from ..domain.models import AssetCategory
from ..ingestion import schema as S
from . import corpus
from .xlsx_writer import write_workbook

SEED = 20260910
DEFAULT_OUTPUT = Path("demo") / "servicelens_demo_workbook.xlsx"
SHEET_NAME = "Work Orders"

# Header spellings written into the workbook. Several are deliberately not
# the canonical names, so the demo exercises the alias layer rather than
# quietly matching itself.
HEADERS = (
    ("WO Number", S.WORK_ORDER_ID),
    ("Equipment ID", S.ASSET_ID),
    ("Equipment Description", S.ASSET_NAME),
    ("Asset Type", S.ASSET_CATEGORY),
    ("Location", S.SITE),
    ("Department", S.DEPARTMENT),
    ("Work Description", S.DESCRIPTION),
    ("Job Type", S.WORK_TYPE),
    ("Priority", S.PRIORITY),
    ("Status", S.STATUS),
    ("Requested Date", S.REQUESTED_DATE),
    ("Created Date", S.OPENED_DATE),
    ("Scheduled Date", S.SCHEDULED_DATE),
    ("Target Date", S.DUE_DATE),
    ("Completed Date", S.COMPLETED_DATE),
    ("Last Updated", S.LAST_UPDATE_DATE),
    ("Assigned Type", S.ASSIGNMENT_TYPE),
    ("Team", S.ASSIGNED_TEAM),
    ("Assigned To", S.ASSIGNED_TECHNICIAN),
    ("Supplier", S.VENDOR),
    ("Estimated Cost", S.ESTIMATED_COST),
    ("Actual Cost", S.ACTUAL_COST),
    ("Meter Reading", S.METER_READING),
    ("Last Note", S.LAST_NOTE),
    # Not part of the canonical schema. Kept, never interpreted - the import
    # report names it so the reader knows it was seen and ignored.
    ("Reporting Region", None),
)

CATEGORY_TEAM_LABEL = {
    AssetCategory.VEHICLE: "Fleet Maintenance",
    AssetCategory.ELECTRICAL: "Electrical & Controls",
    AssetCategory.HVAC: "Facilities Maintenance",
    AssetCategory.PLUMBING: "Facilities Maintenance",
    AssetCategory.GROUNDS: "Facilities Maintenance",
    AssetCategory.MATERIAL_HANDLING: "Mechanical Services",
    AssetCategory.PRODUCTION: "Mechanical Services",
}

REGIONS = ("North", "South", "East", "West", "Central")

# The share of retained work orders the corpus aims to give at least one
# finding. A demonstration dataset has to show the rules working, but a
# maintenance operation where most work is exceptional is not a plausible
# operation - it is a broken one. Roughly a third leaves the majority of the
# board ordinary while keeping every queue worth opening.
TARGET_EXCEPTION_RATE = 0.35
EXCEPTION_RATE_BAND = (0.30, 0.40)

# scenario name -> how many records to build. Ordered so the reader can see
# the intent: ordinary work first, then the exceptions it is contrasted with.
#
# The counts are set so that clean work is the clear majority and each rule
# still has enough records behind it to be worth looking at. Scenario counts
# are not finding counts: several scenarios raise more than one finding on a
# record, and a few overlap - vendor work left open long enough also reads as
# stale - so the realised rate runs a little above the sum of these rows.
SCENARIO_PLAN = (
    # -- ordinary work, the majority of any real board ------------------
    ("routine_open", 620),
    ("completed", 694),
    ("cancelled", 60),
    # -- aging ----------------------------------------------------------
    ("aging", 95),
    ("stale", 57),
    ("no_update", 50),
    # -- priority and response ------------------------------------------
    ("emergency_overdue", 28),
    ("emergency_unassigned", 11),
    ("safety_open", 22),
    ("high_priority_aging", 44),
    # -- ownership and holds --------------------------------------------
    ("unassigned", 54),
    ("parts_hold", 35),
    ("hold_without_note", 25),
    # -- contracted work ------------------------------------------------
    ("vendor_overdue", 38),
    ("vendor_not_named", 16),
    ("vendor_no_schedule", 28),
    # -- cost -----------------------------------------------------------
    ("high_cost", 35),
    ("cost_overrun", 31),
    # -- preventive maintenance -----------------------------------------
    ("pm_overdue", 38),
    ("pm_due_soon", 25),
    # -- record integrity: deliberately rare, as in real data -----------
    ("missing_work_order_id", 4),
    ("duplicate_pair", 8),
    ("missing_asset", 9),
    ("missing_opened_date", 6),
    ("opened_in_future", 4),
    ("completed_before_opened", 5),
    ("completed_without_date", 8),
    ("open_with_completion_date", 6),
    ("scheduled_before_opened", 5),
    ("unrecognized_status", 6),
    ("missing_status", 5),
    ("negative_cost", 4),
)

# duplicate_pair builds two records per instance; every other scenario one.
MULTI_RECORD_SCENARIOS = {"duplicate_pair": 2}


def planned_total() -> int:
    """How many rows the plan produces, before any are excluded."""
    return sum(instances * MULTI_RECORD_SCENARIOS.get(name, 1)
               for name, instances in SCENARIO_PLAN)


@dataclass
class Record:
    """A row under construction, keyed by canonical column name."""

    values: dict

    def set(self, column: str, value) -> None:
        self.values[column] = value


class Generator:
    """Builds the synthetic corpus."""

    def __init__(self, seed: int = SEED,
                 reference: date | None = None) -> None:
        self.random = random.Random(seed)
        self.reference = reference or date.today()
        self._sequence = 0
        self.scenario_counts: dict = {}

    # -- helpers -------------------------------------------------------

    def _next_id(self) -> str:
        self._sequence += 1
        return f"WO-{self.reference.year}-{self._sequence:06d}"

    def _days_ago(self, days: int) -> date:
        return self.reference - timedelta(days=days)

    def _pick(self, sequence):
        return self.random.choice(list(sequence))

    def _asset(self, category: AssetCategory) -> tuple[str, str]:
        prefix, names = corpus.ASSET_TYPES[category]
        number = self.random.randint(1000, 9899)
        return f"{prefix}-{number}", self._pick(names)

    def _cost(self, low: int, high: int) -> float:
        return round(self.random.uniform(low, high), 2)

    # -- the baseline record -------------------------------------------

    def _base(self, age_days: int) -> Record:
        """An ordinary, complete, internally assigned open work order.

        Every scenario starts here and changes only what it needs to, so a
        record that fires one rule differs from a clean record in exactly
        one respect.
        """
        category = self._pick(list(corpus.ASSET_TYPES))
        asset_id, asset_name = self._asset(category)
        opened = self._days_ago(age_days)
        requested = opened - timedelta(days=self.random.randint(0, 3))
        updated = opened + timedelta(
            days=self.random.randint(0, min(age_days, 6)))

        team = CATEGORY_TEAM_LABEL[category]
        # A quarter of records leave the team blank, so ownership has to be
        # inferred from the asset category.
        if self.random.random() < 0.25:
            team = ""

        values = {
            S.WORK_ORDER_ID: self._next_id(),
            S.ASSET_ID: asset_id,
            S.ASSET_NAME: asset_name,
            S.ASSET_CATEGORY: category.label,
            S.SITE: self._pick(corpus.SITES),
            S.DEPARTMENT: self._pick(corpus.DEPARTMENTS),
            S.DESCRIPTION: self._pick(corpus.FAULTS[category]),
            S.WORK_TYPE: self._pick(
                ("Corrective", "Corrective", "Inspection", "Installation")),
            S.PRIORITY: self._pick(("Normal", "Normal", "Normal", "Low")),
            S.STATUS: self._pick(("Open", "Assigned", "In Progress")),
            S.REQUESTED_DATE: requested,
            S.OPENED_DATE: opened,
            S.SCHEDULED_DATE: "",
            S.DUE_DATE: "",
            S.COMPLETED_DATE: "",
            S.LAST_UPDATE_DATE: updated,
            S.ASSIGNMENT_TYPE: "Internal",
            S.ASSIGNED_TEAM: team,
            S.ASSIGNED_TECHNICIAN: self._pick(corpus.TECHNICIANS),
            S.VENDOR: "",
            S.ESTIMATED_COST: self._cost(80, 2400),
            S.ACTUAL_COST: "",
            S.METER_READING: (
                self.random.randint(400, 48000)
                if category in (AssetCategory.VEHICLE,
                                AssetCategory.MATERIAL_HANDLING)
                else ""),
            S.LAST_NOTE: self._pick(corpus.USEFUL_NOTES),
            "Reporting Region": self._pick(REGIONS),
        }
        return Record(values)

    def _external(self, record: Record, named: bool = True) -> None:
        record.set(S.ASSIGNMENT_TYPE, "External")
        record.set(S.ASSIGNED_TECHNICIAN, "")
        record.set(S.ASSIGNED_TEAM, "")
        record.set(S.VENDOR, self._pick(corpus.VENDORS) if named else "")

    def _complete(self, record: Record, age_days: int,
                  duration: int | None = None) -> None:
        opened = record.values[S.OPENED_DATE]
        span = duration if duration is not None else self.random.randint(
            1, max(1, age_days - 1))
        completed = opened + timedelta(days=span)
        if completed > self.reference:
            completed = self.reference
        record.set(S.STATUS, "Completed")
        record.set(S.COMPLETED_DATE, completed)
        record.set(S.LAST_UPDATE_DATE, completed)
        record.set(S.ACTUAL_COST,
                   round(record.values[S.ESTIMATED_COST]
                         * self.random.uniform(0.85, 1.15), 2))

    # -- scenarios -----------------------------------------------------

    def build(self, scenario: str) -> list:
        """Build the record or records for one scenario instance."""
        method = getattr(self, f"_scenario_{scenario}")
        result = method()
        return result if isinstance(result, list) else [result]

    def _scenario_routine_open(self) -> Record:
        # Young, assigned, documented and cheap: nothing should fire.
        return self._base(self.random.randint(0, 12))

    def _scenario_completed(self) -> Record:
        age = self.random.randint(3, 120)
        record = self._base(age)
        self._complete(record, age)
        return record

    def _scenario_cancelled(self) -> Record:
        record = self._base(self.random.randint(5, 90))
        record.set(S.STATUS, "Cancelled")
        record.set(S.LAST_NOTE, "Cancelled at the requester's instruction.")
        return record

    def _scenario_aging(self) -> Record:
        age = self.random.randint(14, 44)
        record = self._base(age)
        record.set(S.LAST_UPDATE_DATE,
                   self._days_ago(self.random.randint(0, 18)))
        return record

    def _scenario_stale(self) -> Record:
        age = self.random.randint(46, 240)
        record = self._base(age)
        record.set(S.LAST_UPDATE_DATE,
                   self._days_ago(self.random.randint(0, 19)))
        return record

    def _scenario_no_update(self) -> Record:
        age = self.random.randint(24, 40)
        record = self._base(age)
        record.set(S.LAST_UPDATE_DATE,
                   self._days_ago(self.random.randint(21, age)))
        return record

    def _scenario_emergency_overdue(self) -> Record:
        record = self._base(self.random.randint(3, 25))
        record.set(S.PRIORITY, "Emergency")
        return record

    def _scenario_emergency_unassigned(self) -> Record:
        record = self._base(self.random.randint(0, 2))
        record.set(S.PRIORITY, "Emergency")
        record.set(S.ASSIGNED_TECHNICIAN, "")
        record.set(S.STATUS, "Open")
        return record

    def _scenario_safety_open(self) -> Record:
        record = self._base(self.random.randint(5, 30))
        record.set(S.WORK_TYPE, "Safety")
        return record

    def _scenario_high_priority_aging(self) -> Record:
        record = self._base(self.random.randint(7, 13))
        record.set(S.PRIORITY, "High")
        return record

    def _scenario_unassigned(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        record.set(S.ASSIGNED_TECHNICIAN, "")
        record.set(S.STATUS, "Open")
        return record

    def _scenario_parts_hold(self) -> Record:
        age = self.random.randint(21, 40)
        record = self._base(age)
        record.set(S.STATUS, "Awaiting Parts")
        record.set(S.LAST_UPDATE_DATE,
                   self._days_ago(self.random.randint(0, 18)))
        record.set(S.LAST_NOTE,
                   "Part on back order, supplier confirmed the delay.")
        return record

    def _scenario_hold_without_note(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        record.set(S.STATUS, self._pick(("On Hold", "Awaiting Vendor")))
        record.set(S.LAST_NOTE, self._pick(corpus.PLACEHOLDER_NOTES))
        return record

    def _scenario_vendor_overdue(self) -> Record:
        age = self.random.randint(30, 90)
        record = self._base(age)
        self._external(record)
        record.set(S.SCHEDULED_DATE,
                   record.values[S.OPENED_DATE] + timedelta(days=5))
        record.set(S.LAST_UPDATE_DATE,
                   self._days_ago(self.random.randint(0, 19)))
        return record

    def _scenario_vendor_not_named(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        self._external(record, named=False)
        return record

    def _scenario_vendor_no_schedule(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        self._external(record)
        record.set(S.SCHEDULED_DATE, "")
        return record

    def _scenario_high_cost(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        record.set(S.ESTIMATED_COST, self._cost(5000, 42000))
        return record

    def _scenario_cost_overrun(self) -> Record:
        age = self.random.randint(6, 90)
        record = self._base(age)
        estimate = self._cost(600, 9000)
        record.set(S.ESTIMATED_COST, estimate)
        self._complete(record, age)
        record.set(S.ACTUAL_COST,
                   round(estimate * self.random.uniform(1.35, 2.4), 2))
        return record

    def _scenario_pm_overdue(self) -> Record:
        record = self._base(self.random.randint(8, 13))
        record.set(S.WORK_TYPE, "Preventive")
        record.set(S.DUE_DATE, self._days_ago(self.random.randint(1, 40)))
        return record

    def _scenario_pm_due_soon(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        record.set(S.WORK_TYPE, "Preventive")
        record.set(S.DUE_DATE,
                   self.reference + timedelta(days=self.random.randint(0, 7)))
        return record

    # -- record integrity scenarios ------------------------------------

    def _scenario_missing_work_order_id(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        record.set(S.WORK_ORDER_ID, "")
        return record

    def _scenario_duplicate_pair(self) -> list:
        first = self._base(self.random.randint(0, 12))
        second = self._base(self.random.randint(0, 12))
        # The repeat differs only in spacing, which is still a duplicate.
        second.set(S.WORK_ORDER_ID, f" {first.values[S.WORK_ORDER_ID]} ")
        return [first, second]

    def _scenario_missing_asset(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        record.set(S.ASSET_ID, "")
        return record

    def _scenario_missing_opened_date(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        record.set(S.OPENED_DATE, "")
        record.set(S.LAST_UPDATE_DATE, self._days_ago(2))
        return record

    def _scenario_opened_in_future(self) -> Record:
        record = self._base(0)
        # A mis-keyed year, which is how future dates actually arise.
        record.set(S.OPENED_DATE,
                   self.reference + timedelta(
                       days=self.random.randint(180, 400)))
        record.set(S.LAST_UPDATE_DATE, "")
        return record

    def _scenario_completed_before_opened(self) -> Record:
        age = self.random.randint(10, 60)
        record = self._base(age)
        record.set(S.STATUS, "Completed")
        record.set(S.COMPLETED_DATE,
                   record.values[S.OPENED_DATE] - timedelta(
                       days=self.random.randint(1, 9)))
        record.set(S.ACTUAL_COST, record.values[S.ESTIMATED_COST])
        return record

    def _scenario_completed_without_date(self) -> Record:
        record = self._base(self.random.randint(5, 60))
        record.set(S.STATUS, "Completed")
        record.set(S.COMPLETED_DATE, "")
        record.set(S.ACTUAL_COST, record.values[S.ESTIMATED_COST])
        return record

    def _scenario_open_with_completion_date(self) -> Record:
        age = self.random.randint(6, 13)
        record = self._base(age)
        record.set(S.COMPLETED_DATE,
                   record.values[S.OPENED_DATE] + timedelta(days=2))
        return record

    def _scenario_scheduled_before_opened(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        record.set(S.SCHEDULED_DATE,
                   record.values[S.OPENED_DATE] - timedelta(
                       days=self.random.randint(1, 6)))
        return record

    def _scenario_unrecognized_status(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        record.set(S.STATUS, self._pick(
            ("Referred To Planning", "Quote Stage", "Site Survey Booked")))
        return record

    def _scenario_missing_status(self) -> Record:
        record = self._base(self.random.randint(0, 12))
        record.set(S.STATUS, "")
        return record

    def _scenario_negative_cost(self) -> Record:
        age = self.random.randint(5, 40)
        record = self._base(age)
        self._complete(record, age)
        record.set(S.ACTUAL_COST, -abs(self._cost(50, 900)))
        return record

    # -- assembly ------------------------------------------------------

    def generate(self) -> list:
        """The full corpus, shuffled so scenarios are not written in blocks."""
        records: list = []
        for scenario, instances in SCENARIO_PLAN:
            produced = 0
            for _ in range(instances):
                built = self.build(scenario)
                records.extend(built)
                produced += len(built)
            self.scenario_counts[scenario] = produced

        # A handful of records lose their team entirely, so ownership has to
        # fall through to Operations Review.
        for record in self.random.sample(records, k=min(24, len(records))):
            record.set(S.ASSIGNED_TEAM, "")
            record.set(S.ASSET_CATEGORY, "")
        for record in self.random.sample(records, k=min(10, len(records))):
            record.set(S.ASSIGNED_TEAM, "Night Shift Crew")
            record.set(S.ASSET_CATEGORY, "")

        self.random.shuffle(records)
        return records


def to_rows(records) -> list:
    """Records as worksheet rows, in header order."""
    rows = []
    for record in records:
        rows.append([record.values.get(canonical or header, "")
                     for header, canonical in HEADERS])
    return rows


def write(path: Path, records, reference: date) -> None:
    """Write the corpus to an .xlsx workbook."""
    path.parent.mkdir(parents=True, exist_ok=True)
    preamble = [
        [f"{corpus.ENVIRONMENT_NAME} - {corpus.DATASET_LABEL}"],
        [f"Generated {reference.isoformat()}. "
         "Every value in this workbook is synthetic."],
        [],
    ]
    write_workbook(
        str(path),
        headers=[header for header, _ in HEADERS],
        rows=to_rows(records),
        sheet_name=SHEET_NAME,
        preamble=preamble,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m servicelens.demo.generator",
        description="Generate the ServiceLens synthetic demonstration "
                    "workbook.",
    )
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"output path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--seed", type=int, default=SEED,
                        help=f"random seed (default: {SEED})")
    parser.add_argument("--reference", type=date.fromisoformat, default=None,
                        help="reporting date the corpus is built around, as "
                             "YYYY-MM-DD (default: today)")
    parser.add_argument("--quiet", action="store_true",
                        help="write the workbook without printing a summary")
    arguments = parser.parse_args(argv)

    generator = Generator(seed=arguments.seed, reference=arguments.reference)
    records = generator.generate()
    write(arguments.output, records, generator.reference)

    if not arguments.quiet:
        size = arguments.output.stat().st_size
        print(f"{corpus.DATASET_LABEL}")
        print(f"  file        {arguments.output}")
        print(f"  work orders {len(records):,}")
        print(f"  size        {size:,} bytes")
        print(f"  seed        {arguments.seed}")
        print(f"  reference   {generator.reference.isoformat()}")
        print(f"  scenarios   {len(generator.scenario_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
