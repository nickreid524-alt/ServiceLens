"""The synthetic vocabulary the demonstration data is built from.

Every name here is invented for this project. The sites, vendors, people,
assets and descriptions do not refer to any real organisation, place or
person, and are not derived from any real dataset.

The environment is deliberately unbranded: ServiceLens Demo Operations is a
label for the demonstration data, not a fictional company the application
belongs to.
"""

from __future__ import annotations

from ..domain.models import AssetCategory

ENVIRONMENT_NAME = "ServiceLens Demo Operations"
DATASET_LABEL = "Synthetic Maintenance Dataset"

SITES = (
    "Riverbend Distribution Center",
    "Cedar Hollow Campus",
    "Kestrel Point Terminal",
    "Foxglove Industrial Park",
    "Ashmore Civic Center",
    "Larkspur Logistics Hub",
    "Windmere Office Park",
    "Talon Ridge Depot",
)

DEPARTMENTS = (
    "Facilities",
    "Fleet",
    "Production Support",
    "Grounds",
    "Utilities",
)

VENDORS = (
    "Northstar Service Group",
    "Apex Mechanical Contractors",
    "Summit Equipment Services",
    "Blue Ridge Controls",
    "Horizon Field Services",
    "Ironwood Electrical",
    "Clearwater Plumbing Co",
)

TECHNICIANS = (
    "Priya Raghunathan", "Desmond Achebe", "Lena Kowalczyk", "Tomas Iriarte",
    "Yuki Tanabe", "Nadia Belkacem", "Marcus Ellery", "Sofia Brandt",
    "Ravi Chandrasekar", "Imani Okonjo", "Petra Lindqvist", "Andre Dubois",
    "Wei Lin Chen", "Hana Farouk", "Callum Beckett", "Rosa Villalobos",
    "Jonas Halvorsen", "Amara Nwosu", "Elias Vogt", "Mei Sato",
    "Dara Kavanagh", "Otto Reinholt", "Sanaa Idrissi", "Theo Marchetti",
)

# Asset category -> (identifier prefix, asset names).
ASSET_TYPES = {
    AssetCategory.HVAC: (
        "HVAC",
        ("Rooftop Air Handler", "Chiller Unit", "Boiler", "Exhaust Fan",
         "Cooling Tower", "Split System Condenser"),
    ),
    AssetCategory.VEHICLE: (
        "VEH",
        ("Service Van", "Box Truck", "Utility Pickup", "Yard Tractor",
         "Passenger Shuttle", "Flatbed Truck"),
    ),
    AssetCategory.MATERIAL_HANDLING: (
        "MHE",
        ("Counterbalance Forklift", "Reach Truck", "Belt Conveyor",
         "Pallet Jack", "Dock Leveler", "Scissor Lift"),
    ),
    AssetCategory.ELECTRICAL: (
        "ELC",
        ("Main Switchgear", "Standby Generator", "Lighting Panel",
         "Transfer Switch", "Motor Control Center", "UPS Cabinet"),
    ),
    AssetCategory.PLUMBING: (
        "PLM",
        ("Domestic Water Pump", "Sump Pump", "Water Heater",
         "Backflow Preventer", "Grease Interceptor", "Irrigation Manifold"),
    ),
    AssetCategory.PRODUCTION: (
        "PRD",
        ("Case Sealer", "Labeling Line", "Air Compressor",
         "Wrapping Machine", "Sorter Module", "Palletizer"),
    ),
    AssetCategory.GROUNDS: (
        "GRD",
        ("Ride-On Mower", "Snow Plow Attachment", "Leaf Blower Unit",
         "Parking Lot Sweeper", "Gate Operator", "Perimeter Fence Section"),
    ),
}

# Repair descriptions, grouped by category so the corpus reads plausibly.
FAULTS = {
    AssetCategory.HVAC: (
        "No cooling on the north zone",
        "Condensate line backing up",
        "Compressor short cycling",
        "Belt squeal on startup",
        "Thermostat not holding setpoint",
        "Filter change and coil clean",
    ),
    AssetCategory.VEHICLE: (
        "Brake warning light on dash",
        "Coolant leak at the water pump",
        "Scheduled oil and filter service",
        "Rear door latch will not hold",
        "Tire wear inspection",
        "Battery not holding charge",
    ),
    AssetCategory.MATERIAL_HANDLING: (
        "Mast chain out of adjustment",
        "Hydraulic leak at the lift cylinder",
        "Conveyor belt tracking off centre",
        "Horn and reverse alarm inoperative",
        "Annual load test and inspection",
        "Drive motor overheating",
    ),
    AssetCategory.ELECTRICAL: (
        "Breaker tripping under load",
        "Generator failed weekly exercise",
        "Emergency lighting test failure",
        "Loose connection found on thermal scan",
        "Panel schedule out of date",
        "UPS battery replacement due",
    ),
    AssetCategory.PLUMBING: (
        "Water hammer on the supply riser",
        "Sump pump running continuously",
        "No hot water at the west wing",
        "Backflow device annual test",
        "Slow drain in the wash bay",
        "Pressure loss overnight",
    ),
    AssetCategory.PRODUCTION: (
        "Line stopping intermittently",
        "Air pressure dropping mid shift",
        "Sensor misreads at the infeed",
        "Guard interlock fault",
        "Quarterly lubrication route",
        "Excess vibration at the drive end",
    ),
    AssetCategory.GROUNDS: (
        "Deck blade replacement",
        "Gate operator will not reverse",
        "Sweeper brush worn through",
        "Hydraulic hose chafing",
        "Seasonal service before winter",
        "Fence panel damaged by vehicle",
    ),
}

# Notes that carry real information.
USEFUL_NOTES = (
    "Parts ordered, supplier confirmed a two week lead time.",
    "Technician attended, fault not present on arrival, monitoring.",
    "Quote received and sent for approval.",
    "Awaiting site access outside production hours.",
    "Temporary repair in place, permanent fix scheduled.",
    "Vendor booked for next available service window.",
    "Root cause traced to a failed sensor, replacement on order.",
    "Isolated and tagged out pending the replacement part.",
)

# Notes that look like an update but say nothing. The rule engine treats
# these as no note at all.
PLACEHOLDER_NOTES = ("TBD", "pending", "update", "n/a", "-", "see notes")
