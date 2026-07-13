"""Generic unit conversion for the small set of physical-quantity
categories this app's input fields actually use.

This is deliberately NOT a general dimensional-analysis engine -- each
category is just a base unit plus a set of named scale factors (mostly
SI prefixes, plus the non-decimal time units researchers actually type).
Every calculation elsewhere in `core/` continues to work in one fixed
base unit per quantity (volts, seconds, amps, F/g) exactly as before;
this module only converts a user-entered (value, unit) pair into that
base unit at the UI boundary, so no formula module needs to change.
"""

# Each category: {unit_name: multiplier_to_base}. The base unit is the
# one with multiplier 1.0 -- that's what every core/ formula expects.
CATEGORIES: dict[str, dict[str, float]] = {
    "voltage": {  # base: V
        "µV": 1e-6, "uV": 1e-6, "mV": 1e-3, "V": 1.0, "kV": 1e3,
    },
    "current": {  # base: A
        "nA": 1e-9, "µA": 1e-6, "uA": 1e-6, "mA": 1e-3, "A": 1.0,
    },
    "time": {  # base: s
        "ms": 1e-3, "s": 1.0, "min": 60.0, "h": 3600.0,
    },
    "mass": {  # base: g
        "µg": 1e-6, "ug": 1e-6, "mg": 1e-3, "g": 1.0, "kg": 1e3,
    },
    "specific_capacitance": {  # base: F/g -- gravimetric capacitance
        "µF/g": 1e-6, "uF/g": 1e-6, "mF/g": 1e-3, "F/g": 1.0,
    },
    "areal_capacitance": {  # base: F/cm2 -- areal capacitance
        "µF/cm²": 1e-6, "uF/cm2": 1e-6, "mF/cm²": 1e-3, "F/cm²": 1.0,
    },
    "volumetric_capacitance": {  # base: F/cm3 -- volumetric capacitance
        "mF/cm³": 1e-3, "F/cm³": 1.0,
    },
    "scan_rate": {  # base: V/s -- for single-column tables where the
                     # compound voltage/time widget would be overkill
                     # (a whole column is overwhelmingly likely to share
                     # one consistent unit already)
        "mV/s": 1e-3, "V/s": 1.0, "mV/min": 1e-3 / 60.0, "V/min": 1.0 / 60.0,
    },
    "resistance": {  # base: Ohm
        "mOhm": 1e-3, "Ohm": 1.0, "kOhm": 1e3, "MOhm": 1e6,
    },
}

BASE_UNIT = {category: next(u for u, m in units.items() if m == 1.0)
             for category, units in CATEGORIES.items()}


def units_for(category: str) -> list[str]:
    """Ordered unit names for a category, smallest scale first -- the
    order a unit dropdown should list them in."""
    units = CATEGORIES[category]
    return sorted(units, key=lambda u: units[u])


def to_base(value: float, unit: str, category: str) -> float:
    """Convert `value` (in `unit`) to this category's base unit."""
    try:
        factor = CATEGORIES[category][unit]
    except KeyError:
        raise ValueError(f"Unknown unit '{unit}' for category '{category}'. "
                          f"Choose from {units_for(category)}.")
    return value * factor


def from_base(value_base: float, unit: str, category: str) -> float:
    """Convert a base-unit value into `unit` for display."""
    try:
        factor = CATEGORIES[category][unit]
    except KeyError:
        raise ValueError(f"Unknown unit '{unit}' for category '{category}'. "
                          f"Choose from {units_for(category)}.")
    return value_base / factor
