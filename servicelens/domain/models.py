"""The canonical work order model.

Everything downstream of ingestion speaks this vocabulary. Source workbooks
vary; this module does not. A `WorkOrder` is a plain immutable record with
derived properties and no knowledge of where it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class _Vocabulary(Enum):
    """An enum whose members can be recovered from untidy source text."""

    @property
    def label(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str | None, default=None):
        """Best-effort lookup. Returns `default` when nothing matches."""
        if text is None:
            return default
        key = " ".join(str(text).split()).casefold()
        if not key:
            return default
        for member in cls:
            if member.value.casefold() == key:
                return member
        for member in cls:
            if member.name.casefold() == key.replace(" ", "_"):
                return member
        for member, aliases in cls._aliases().items():
            for alias in aliases:
                if alias.casefold() == key:
                    return member
        return default

    @classmethod
    def _aliases(cls) -> dict:
        return {}


class Priority(_Vocabulary):
    EMERGENCY = "Emergency"
    HIGH = "High"
    NORMAL = "Normal"
    LOW = "Low"

    @classmethod
    def _aliases(cls):
        return {
            cls.EMERGENCY: ("urgent", "p1", "1"),
            cls.HIGH: ("p2", "2"),
            cls.NORMAL: ("medium", "standard", "routine", "p3", "3"),
            cls.LOW: ("deferred", "p4", "4"),
        }

    @property
    def rank(self) -> int:
        return _PRIORITY_RANK[self]


class Status(_Vocabulary):
    OPEN = "Open"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "In Progress"
    AWAITING_PARTS = "Awaiting Parts"
    AWAITING_VENDOR = "Awaiting Vendor"
    ON_HOLD = "On Hold"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

    @classmethod
    def _aliases(cls):
        return {
            cls.OPEN: ("new", "logged", "requested"),
            cls.ASSIGNED: ("scheduled", "dispatched"),
            cls.IN_PROGRESS: ("in process", "working", "started"),
            cls.AWAITING_PARTS: ("parts hold", "awaiting parts delivery"),
            cls.AWAITING_VENDOR: ("with vendor", "vendor hold"),
            cls.ON_HOLD: ("hold", "suspended", "paused"),
            cls.COMPLETED: ("complete", "closed", "done", "finished"),
            cls.CANCELLED: ("canceled", "void", "withdrawn"),
        }

    @property
    def is_terminal(self) -> bool:
        """True when the status says no further work is expected."""
        return self in (Status.COMPLETED, Status.CANCELLED)

    @property
    def is_open(self) -> bool:
        return not self.is_terminal


class WorkType(_Vocabulary):
    CORRECTIVE = "Corrective"
    PREVENTIVE = "Preventive"
    INSPECTION = "Inspection"
    SAFETY = "Safety"
    INSTALLATION = "Installation"

    @classmethod
    def _aliases(cls):
        return {
            cls.CORRECTIVE: ("repair", "breakdown", "reactive"),
            cls.PREVENTIVE: ("pm", "preventative", "planned"),
            cls.INSPECTION: ("survey", "check"),
            cls.SAFETY: ("safety critical", "compliance"),
            cls.INSTALLATION: ("install", "project", "modification"),
        }


class AssignmentType(_Vocabulary):
    INTERNAL = "Internal"
    EXTERNAL = "External"

    @classmethod
    def _aliases(cls):
        return {
            cls.INTERNAL: ("in house", "in-house", "own staff"),
            cls.EXTERNAL: ("contractor", "contracted", "outsourced", "vendor"),
        }


class AssetCategory(_Vocabulary):
    HVAC = "HVAC"
    VEHICLE = "Vehicle"
    MATERIAL_HANDLING = "Material Handling"
    ELECTRICAL = "Electrical"
    PLUMBING = "Plumbing"
    PRODUCTION = "Production Equipment"
    GROUNDS = "Grounds"

    @classmethod
    def _aliases(cls):
        return {
            cls.HVAC: ("air handling", "heating", "cooling", "climate"),
            cls.VEHICLE: ("fleet", "truck", "van", "car"),
            cls.MATERIAL_HANDLING: ("forklift", "conveyor", "lift truck"),
            cls.ELECTRICAL: ("power", "controls", "lighting"),
            cls.PLUMBING: ("water", "drainage", "sanitary"),
            cls.PRODUCTION: ("process equipment", "machinery", "line"),
            cls.GROUNDS: ("landscape", "exterior", "grounds keeping"),
        }


# Priority ordering, most urgent first. Declared after the class so the
# members exist; kept as a module constant so sorting never re-derives it.
_PRIORITY_RANK = {
    member: index
    for index, member in enumerate(
        (Priority.EMERGENCY, Priority.HIGH, Priority.NORMAL, Priority.LOW))
}


class Severity(Enum):
    """How urgently a finding needs a human."""

    CRITICAL = "Critical"
    WARNING = "Warning"
    INFORMATION = "Information"

    @property
    def label(self) -> str:
        return self.value

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {
    Severity.CRITICAL: 0,
    Severity.WARNING: 1,
    Severity.INFORMATION: 2,
}

SEVERITY_ORDER = (Severity.CRITICAL, Severity.WARNING, Severity.INFORMATION)


class Domain(Enum):
    """What kind of problem a finding describes.

    The routing engine reads this, so a new rule joins an existing queue
    simply by declaring its domain.
    """

    DATA_QUALITY = "Data Quality"
    PRIORITY = "Priority"
    AGING = "Aging"
    STATUS = "Status"
    VENDOR = "Vendor"
    COST = "Cost"
    PREVENTIVE = "Preventive"

    @property
    def label(self) -> str:
        return self.value


# --- teams -----------------------------------------------------------
TEAM_FACILITIES = "Facilities Maintenance"
TEAM_FLEET = "Fleet Maintenance"
TEAM_ELECTRICAL = "Electrical & Controls"
TEAM_MECHANICAL = "Mechanical Services"
TEAM_CONTRACTED = "Contracted Services"
TEAM_OPERATIONS_REVIEW = "Operations Review"

TEAMS = (
    TEAM_FACILITIES,
    TEAM_FLEET,
    TEAM_ELECTRICAL,
    TEAM_MECHANICAL,
    TEAM_CONTRACTED,
    TEAM_OPERATIONS_REVIEW,
)


# --- queues ----------------------------------------------------------
QUEUE_IMMEDIATE = "Immediate Review"
QUEUE_DATA_QUALITY = "Data Quality"
QUEUE_VENDOR = "Vendor Follow-up"
QUEUE_COST = "Cost Review"
QUEUE_PREVENTIVE = "Preventive Maintenance"
QUEUE_PLANNING = "Maintenance Planning"
QUEUE_ROUTINE = "Routine Operations"

QUEUES = (
    QUEUE_IMMEDIATE,
    QUEUE_DATA_QUALITY,
    QUEUE_VENDOR,
    QUEUE_COST,
    QUEUE_PREVENTIVE,
    QUEUE_PLANNING,
    QUEUE_ROUTINE,
)


UNINFORMATIVE_NOTES = frozenset({
    # Filler that occupies the notes field without saying anything. A note
    # matching one of these is treated exactly as a blank note would be.
    "",
    "awaiting update", "chasing", "follow up", "followup", "in hand",
    "monitoring", "no change", "no update", "none", "n/a", "na", "nil",
    "not started", "ongoing", "open", "outstanding", "pending", "review",
    "see above", "see notes", "tba", "tbc", "tbd", "unknown", "update",
    "wait", "waiting", "wip", "x", "?", "??", "-",
})


@dataclass(frozen=True, slots=True)
class WorkOrder:
    """One work order, normalized.

    Every field is optional except the identifier, because real exports are
    incomplete and the rule engine's job is to say so rather than to crash.
    `row_number` is the 1-based worksheet row, so a finding can always be
    traced back to the line that produced it.
    """

    work_order_id: str = ""
    row_number: int = 0

    asset_id: str = ""
    asset_name: str = ""
    asset_category: AssetCategory | None = None

    site: str = ""
    department: str = ""

    description: str = ""
    work_type: WorkType | None = None
    priority: Priority | None = None
    status: Status | None = None
    raw_status: str = ""

    requested_date: date | None = None
    opened_date: date | None = None
    scheduled_date: date | None = None
    due_date: date | None = None
    completed_date: date | None = None
    last_update_date: date | None = None

    assignment_type: AssignmentType | None = None
    assigned_team: str = ""
    assigned_technician: str = ""
    vendor: str = ""

    estimated_cost: float | None = None
    actual_cost: float | None = None
    meter_reading: float | None = None

    last_note: str = ""
    unmapped: dict = field(default_factory=dict, compare=False)

    # -- derived -------------------------------------------------------

    @property
    def is_open(self) -> bool:
        """Open unless the status positively says the work is finished."""
        return self.status is None or self.status.is_open

    @property
    def has_assignee(self) -> bool:
        """True when the record says who is doing the work."""
        if self.assignment_type is AssignmentType.EXTERNAL:
            return bool(self.vendor.strip())
        if self.assigned_technician.strip():
            return True
        if self.assignment_type is AssignmentType.INTERNAL:
            return False
        return bool(self.vendor.strip())

    @property
    def effective_cost(self) -> float:
        """Actual spend where known, otherwise the estimate, otherwise zero."""
        if self.actual_cost is not None:
            return self.actual_cost
        if self.estimated_cost is not None:
            return self.estimated_cost
        return 0.0

    def age_days(self, as_of: date) -> int | None:
        """How long this work order has been running, or None if undatable.

        Closed work is measured to its completion date, open work to `as_of`.
        A future opened date yields a negative number rather than a guess -
        the integrity rules report it instead of silently clamping it.
        """
        if self.opened_date is None:
            return None
        end = as_of
        if not self.is_open and self.completed_date is not None:
            end = self.completed_date
        return (end - self.opened_date).days

    def days_since_update(self, as_of: date) -> int | None:
        """Days since the last recorded activity of any kind."""
        moments = [d for d in (self.last_update_date, self.opened_date)
                   if d is not None]
        if not moments:
            return None
        return (as_of - max(moments)).days

    def has_usable_note(self, minimum_characters: int) -> bool:
        """True when the note says more than a placeholder does."""
        note = " ".join(self.last_note.split())
        if not note:
            return False
        if note.strip(".:-").casefold() in UNINFORMATIVE_NOTES:
            return False
        return len(note) >= minimum_characters

    @property
    def identity(self) -> str:
        """A stable label for messages, even when the id is missing."""
        return self.work_order_id or f"(row {self.row_number})"
