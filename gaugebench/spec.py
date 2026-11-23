"""Gauge + photo specifications and the random sampler that creates them.

Every visual property that can make a gauge harder to read is an explicit,
recorded *factor*. That lets us (a) mix factors for a realistic suite and
(b) sweep one factor while holding the rest fixed to get clean capability curves.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np

from .scales import Scale

# (unit, vmin, vmax, major_step, kind) — realistic industrial ranges
RANGE_PRESETS: dict[str, list[tuple[str, float, float, float]]] = {
    "linear": [
        ("bar", 0, 10, 1), ("bar", 0, 16, 2), ("bar", 0, 25, 5), ("bar", 0, 6, 1),
        ("kPa", 0, 600, 100), ("kPa", 0, 250, 50), ("psi", 0, 160, 20), ("psi", 0, 300, 50),
        ("°C", 0, 120, 20), ("°C", 0, 200, 50),
    ],
    "offset": [  # ranges that do not start at zero (negative / compound / vacuum)
        ("°C", -40, 60, 20), ("°C", -30, 50, 10), ("bar", -1, 0, 0.2), ("bar", -1, 3, 1),
        ("°C", -20, 120, 20),
    ],
    "sqrt": [("m³/h", 0, 100, 10), ("m³/h", 0, 50, 10), ("L/min", 0, 400, 100)],
    "log": [("mbar", 1, 1000, 0), ("mbar", 0.1, 100, 0), ("Pa", 1, 10000, 0)],
    # dials whose printed numbers must be scaled by a printed multiplier ("×10")
    "multiplied": [("kPa", 0, 10, 1), ("rpm", 0, 40, 5), ("kPa", 0, 6, 1), ("psi", 0, 16, 2),
                   ("rpm", 0, 30, 5)],
}

MIN_TICK_DEG = 1.6   # design rule: neighbouring divisions at least this many degrees apart

SWEEPS = {"270": (-135.0, 270.0), "180": (-90.0, 180.0), "90": (-45.0, 90.0)}
MULTIPLIERS = {"x1": 1.0, "x10": 10.0, "x100": 100.0, "x0.1": 0.1}

# Factor domains (values a sweep may take). Order = increasing expected difficulty.
FACTOR_DOMAINS: dict[str, list[Any]] = {
    "scale_kind": ["linear", "offset", "sqrt", "log"],
    "sweep": ["270", "180", "90"],
    "minors_per_major": [2, 5, 10],
    "label_every": [1, 2],
    "multiplier": ["x1", "x10", "x100", "x0.1"],
    "face": ["light", "dark"],
    "glare": [0, 1, 2],
    "tilt": [0, 15, 30, 40],
    "blur": [0.0, 1.0, 2.0],
    "noise": [0.0, 8.0, 16.0],
    "lighting": [1.0, 0.7, 0.45],
}

# A clean, easy baseline used as the "held fixed" point for sweeps.
BASE_FACTORS: dict[str, Any] = {
    "scale_kind": "linear", "sweep": "270", "minors_per_major": 5, "label_every": 1,
    "multiplier": "x1", "face": "light", "glare": 0, "tilt": 0, "blur": 0.0,
    "noise": 0.0, "lighting": 1.0,
}


@dataclass
class Zone:
    lo: float
    hi: float
    name: str   # normal | warning | danger


@dataclass
class GaugeSpec:
    scale: Scale
    value: float                       # true reading in *scale* units (before multiplier)
    unit: str
    multiplier: float = 1.0
    face: str = "light"
    zones: list[Zone] = field(default_factory=list)
    setpoint: float | None = None      # optional red set-point needle (scale units)
    tag: str = ""
    secondary: Scale | None = None     # optional inner second scale (e.g. psi under bar)
    secondary_unit: str = ""

    @property
    def true_reading(self) -> float:
        return self.value * self.multiplier

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scale"].pop("ticks", None)
        if d.get("secondary"):
            d["secondary"].pop("ticks", None)
        return d


@dataclass
class PhotoSpec:
    glare: int = 0            # 0 none, 1 mild, 2 strong
    tilt: float = 0.0         # simulated camera tilt in degrees
    blur: float = 0.0         # gaussian sigma (output pixels)
    noise: float = 0.0        # gaussian noise sigma (0-255)
    lighting: float = 1.0     # exposure gain


def sample_factors(rng: np.random.Generator, level: int | None, overrides: dict | None = None) -> dict:
    """Sample a factor set. level 1..5 controls how far up each domain we may go;
    None means "use the clean base". overrides pin specific factors."""
    f = dict(BASE_FACTORS)
    if level is not None:
        frac = (level - 1) / 4.0          # 0 .. 1
        for name, dom in FACTOR_DOMAINS.items():
            hi = max(1, math.ceil(len(dom) * (0.35 + 0.65 * frac)))
            f[name] = dom[int(rng.integers(0, hi))]
    if overrides:
        f.update(overrides)
    if f["scale_kind"] in ("sqrt", "log"):
        f["multiplier"] = "x1"        # multipliers only appear on linear industrial dials
    if f["scale_kind"] == "log":
        f["minors_per_major"] = 9     # log dials always have the 2..9 sub-ticks
        f["label_every"] = 1
    return f


def build_scale(rng: np.random.Generator, factors: dict) -> tuple[Scale, str]:
    kind_key = factors["scale_kind"]
    presets = RANGE_PRESETS[kind_key]
    if factors["multiplier"] != "x1" and kind_key in ("linear", "offset"):
        presets = RANGE_PRESETS["multiplied"]
    start, sweep = SWEEPS[factors["sweep"]]
    kind = "linear" if kind_key == "offset" else kind_key
    if kind == "log":   # manufacturers don't squeeze 4 decades into a 90-degree dial
        presets = [p for p in presets if sweep * 0.0458 / math.log10(p[2] / p[1]) >= 1.2] or presets
    unit, vmin, vmax, step = presets[int(rng.integers(0, len(presets)))]
    minors = factors["minors_per_major"]
    if kind == "log":
        minors = 9
    else:
        # Real dials keep divisions >= ~1.6 deg apart; fewer minor ticks if the dial is too dense.
        n_major = round((vmax - vmin) / step)
        smallest = sweep / (n_major * minors)
        if kind == "sqrt":   # sqrt dials crowd at the top end: last division is the narrowest
            n = n_major * minors
            smallest = sweep * (1 - math.sqrt(1 - 1 / n))
        while minors > 1 and smallest < MIN_TICK_DEG:
            minors = {10: 5, 5: 2, 2: 1}.get(minors, 1)
            n = n_major * minors
            smallest = sweep / n if kind == "linear" else sweep * (1 - math.sqrt(1 - 1 / n))
        factors["minors_per_major"] = minors   # record what was actually drawn
    scale = Scale(vmin=vmin, vmax=vmax, kind=kind, start_angle=start, sweep=sweep,
                  major_step=step or 1.0, minors_per_major=minors,
                  label_every=factors["label_every"])
    return scale, unit


def sample_value(rng: np.random.Generator, scale: Scale, lo_frac: float = 0.04, hi_frac: float = 0.96) -> float:
    f = float(rng.uniform(lo_frac, hi_frac))
    return float(scale.value_at_fraction(f))


def sample_gauge(rng: np.random.Generator, factors: dict, tag: str = "") -> GaugeSpec:
    scale, unit = build_scale(rng, factors)
    return GaugeSpec(scale=scale, value=sample_value(rng, scale), unit=unit,
                     multiplier=MULTIPLIERS[factors["multiplier"]], face=factors["face"], tag=tag)


def photo_from_factors(factors: dict) -> PhotoSpec:
    return PhotoSpec(glare=factors["glare"], tilt=factors["tilt"], blur=factors["blur"],
                     noise=factors["noise"], lighting=factors["lighting"])


def make_zones(rng: np.random.Generator, scale: Scale, high_alarm: bool = True) -> list[Zone]:
    """Green / yellow / red bands snapped to major tick values."""
    majors = [t.value for t in scale.ticks if t.major]
    n = len(majors)
    if n < 4:
        return []
    if high_alarm:
        r = int(rng.integers(max(2, n - 3), n - 1))        # red starts here
        y = int(rng.integers(max(1, r - 2), r))
        return [Zone(majors[0], majors[y], "normal"), Zone(majors[y], majors[r], "warning"),
                Zone(majors[r], majors[-1], "danger")]
    r = int(rng.integers(1, min(3, n - 2)))
    y = int(rng.integers(r + 1, min(r + 3, n - 1)))
    return [Zone(majors[0], majors[r], "danger"), Zone(majors[r], majors[y], "warning"),
            Zone(majors[y], majors[-1], "normal")]


def zone_of(value: float, zones: list[Zone]) -> str | None:
    for z in zones:
        if z.lo <= value <= z.hi:
            return z.name
    return None
