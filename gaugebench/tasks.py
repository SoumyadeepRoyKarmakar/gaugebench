"""Task families. Each family = a kind of visual reasoning an operator needs.

| family              | what the model must do                                          |
|---------------------|-----------------------------------------------------------------|
| read_value          | precise reading incl. non-linear scales and printed multipliers |
| zone_status         | relate needle position to coloured safety bands                 |
| setpoint_deviation  | read two needles and subtract                                   |
| panel_alarm         | scan a multi-gauge panel; find the one in its red zone          |
| panel_max           | compare values across dials with *different ranges*             |
| temporal_change     | read the same dial in two photos and compute the change         |
| dual_scale          | pick the right ring on a two-scale dial (bar/psi, °C/°F)        |
| level_reading       | read a vertical tank sight-glass (different instrument geometry)|
| panel_count         | count how many dials on a panel are outside their green band    |

Each builder returns (Task, list[Check]) or raises Reject to request a new sample.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

import numpy as np

from . import validate as V
from .level import render_level, LIQUIDS
from .render import render_gauge
from .scene import Scene, build_scene
from .scales import Scale
from .spec import (GaugeSpec, RANGE_PRESETS, SWEEPS, make_zones, photo_from_factors, sample_gauge,
                   sample_value, zone_of)


class Reject(Exception):
    pass


@dataclass
class Task:
    id: str
    family: str
    question: str
    answer: Any
    answer_type: str                 # "number" | "choice"
    tolerance: float | None = None   # for numbers: accepted absolute error
    choices: list[str] | None = None
    unit: str = ""
    factors: dict = field(default_factory=dict)
    gauges: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    seed: int = 0
    image: str = "image.png"

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["tolerance"] is not None:
            d["tolerance"] = float(f"{d['tolerance']:.6g}")
        return d


ANSWER_FORMAT_NUM = "Respond with your reasoning if you like, then finish with a final line exactly of the form 'ANSWER: <number>' (number only, no units)."
ANSWER_FORMAT_CHOICE = "Respond with your reasoning if you like, then finish with a final line exactly of the form 'ANSWER: <choice>' using one of the allowed options."


def _round_for(tol: float, v: float) -> float:
    dec = max(0, -math.floor(math.log10(max(tol, 1e-9) / 5)))
    return round(v, dec)


def _tags(rng: np.random.Generator, n: int, prefix: str = "PI") -> list[str]:
    base = int(rng.integers(1, 8)) * 100
    nums = sorted(rng.choice(np.arange(base + 1, base + 40), size=n, replace=False))
    return [f"{prefix}-{k}" for k in nums]


def _common_checks(scene: Scene, i: int, spec: GaugeSpec, which: str = "needle") -> list[V.Check]:
    val = spec.value if which == "needle" else spec.setpoint
    checks = [V.check_reading(scene.renders[i], val, spec.scale.reading_tolerance(val), which)]
    checks += V.check_needle_visible(scene, i, which)
    return checks


# ---------------------------------------------------------------------------------------
def build_read_value(rng, factors) -> tuple[Task, Scene, list[V.Check]]:
    g = sample_gauge(rng, factors)
    r = render_gauge(g)
    scene = build_scene(rng, [r], [""], "single", photo_from_factors(factors))
    tol = g.scale.reading_tolerance(g.value) * g.multiplier
    q = (f"This is a photo of an industrial gauge. What is the actual measured value it shows, "
         f"in {g.unit}? Take into account everything printed on the dial. {ANSWER_FORMAT_NUM}")
    t = Task("", "read_value", q, _round_for(tol, g.true_reading), "number", tol, unit=g.unit,
             gauges=[g.to_dict()])
    checks = _common_checks(scene, 0, g) + V.check_legibility(scene, 0)
    return t, scene, checks


def build_zone_status(rng, factors) -> tuple[Task, Scene, list[V.Check]]:
    g = sample_gauge(rng, factors)
    g.zones = make_zones(rng, g.scale, high_alarm=bool(rng.integers(0, 4)))
    if not g.zones:
        raise Reject("range too small for zones")
    # pick a zone uniformly, then a value inside it, so answers are balanced
    z = g.zones[int(rng.integers(0, len(g.zones)))]
    g.value = float(g.scale.value_at_fraction(rng.uniform(g.scale.fraction(z.lo), g.scale.fraction(z.hi))))
    r = render_gauge(g)
    scene = build_scene(rng, [r], [""], "single", photo_from_factors(factors))
    choices = ["normal", "warning", "danger"]
    q = ("This gauge has coloured bands: green = normal, yellow = warning, red = danger. "
         "Which band is the needle currently pointing into? Allowed options: normal, warning, danger. "
         + ANSWER_FORMAT_CHOICE)
    t = Task("", "zone_status", q, zone_of(g.value, g.zones), "choice", choices=choices, unit=g.unit,
             gauges=[g.to_dict()])
    bounds = [b for zz in g.zones for b in (zz.lo, zz.hi)]
    ang = g.scale.angle(g.value)
    margin = min(abs(ang - g.scale.angle(b)) for b in bounds)
    checks = _common_checks(scene, 0, g) + V.check_legibility(scene, 0)
    checks.append(V.margin_check("needle_clear_of_zone_boundary", margin, 2.5, "deg"))
    return t, scene, checks


def build_setpoint_deviation(rng, factors) -> tuple[Task, Scene, list[V.Check]]:
    g = sample_gauge(rng, factors)
    g.setpoint = sample_value(rng, g.scale, 0.1, 0.9)
    r = render_gauge(g)
    scene = build_scene(rng, [r], [""], "single", photo_from_factors(factors))
    tol = (g.scale.reading_tolerance(g.value) + g.scale.reading_tolerance(g.setpoint)) * g.multiplier
    dev = (g.value - g.setpoint) * g.multiplier
    q = (f"This gauge has two needles: the thin red needle marks the set point, the main needle shows "
         f"the actual value. What is the actual value minus the set point, in {g.unit}? "
         f"Take into account everything printed on the dial (a negative answer means below set point). "
         + ANSWER_FORMAT_NUM)
    t = Task("", "setpoint_deviation", q, _round_for(tol, dev), "number", tol, unit=g.unit,
             gauges=[g.to_dict()])
    sep = abs(g.scale.angle(g.value) - g.scale.angle(g.setpoint))
    checks = _common_checks(scene, 0, g) + _common_checks(scene, 0, g, "setpoint") + V.check_legibility(scene, 0)
    checks.append(V.margin_check("needles_separated", sep, 8.0, "deg"))
    return t, scene, checks


def build_panel_alarm(rng, factors) -> tuple[Task, Scene, list[V.Check]]:
    n = int(rng.integers(3, 7))
    tags = _tags(rng, n)
    hot = int(rng.integers(0, n))
    gauges, margins = [], []
    for i in range(n):
        g = sample_gauge(rng, factors, tags[i])
        g.zones = make_zones(rng, g.scale, high_alarm=bool(rng.integers(0, 4)))
        if not g.zones:
            raise Reject("range too small for zones")
        danger = [z for z in g.zones if z.name == "danger"][0]
        safe = [z for z in g.zones if z.name != "danger"]
        z = danger if i == hot else safe[int(rng.integers(0, len(safe)))]
        g.value = float(g.scale.value_at_fraction(rng.uniform(g.scale.fraction(z.lo), g.scale.fraction(z.hi))))
        ang = g.scale.angle(g.value)
        margins.append(min(abs(ang - g.scale.angle(b)) for b in (danger.lo, danger.hi)))
        gauges.append(g)
    renders = [render_gauge(g) for g in gauges]
    scene = build_scene(rng, renders, tags, "panel", photo_from_factors(factors))
    q = (f"This control panel has {n} gauges, each with its own coloured bands "
         f"(green = normal, yellow = warning, red = danger). Exactly one gauge has its needle in the red "
         f"danger band. Which one? Answer with its tag. Allowed options: {', '.join(tags)}. "
         + ANSWER_FORMAT_CHOICE)
    t = Task("", "panel_alarm", q, tags[hot], "choice", choices=tags,
             gauges=[g.to_dict() for g in gauges], meta={"n_gauges": n})
    checks = []
    for i, g in enumerate(gauges):
        checks += _common_checks(scene, i, g)
        checks += V.check_legibility(scene, i)
    checks.append(V.margin_check("all_needles_clear_of_danger_boundary", min(margins), 3.0, "deg"))
    return t, scene, checks


def build_panel_max(rng, factors) -> tuple[Task, Scene, list[V.Check]]:
    # same unit, *different ranges*: the needle furthest round is not always the highest value
    unit = "bar"
    options = [p for p in RANGE_PRESETS["linear"] if p[0] == unit]
    n = int(rng.integers(3, 5))
    tags = _tags(rng, n)
    gauges = []
    for i in range(n):
        u, vmin, vmax, step = options[int(rng.integers(0, len(options)))]
        start, sweep = SWEEPS[factors["sweep"]]
        sc = Scale(vmin=vmin, vmax=vmax, kind="linear", start_angle=start, sweep=sweep, major_step=step,
                   minors_per_major=factors["minors_per_major"], label_every=factors["label_every"])
        g = GaugeSpec(scale=sc, value=sample_value(rng, sc), unit=u, face=factors["face"], tag=tags[i])
        gauges.append(g)
    vals = [g.value for g in gauges]
    order = np.argsort(vals)[::-1]
    best, second = int(order[0]), int(order[1])
    tol_sum = gauges[best].scale.reading_tolerance(vals[best]) + gauges[second].scale.reading_tolerance(vals[second])
    fracs = [g.scale.fraction(g.value) for g in gauges]
    trap = int(np.argmax(fracs)) != best
    renders = [render_gauge(g) for g in gauges]
    scene = build_scene(rng, renders, tags, "panel", photo_from_factors(factors))
    q = (f"These {n} pressure gauges have different ranges. Which gauge shows the highest pressure in bar? "
         f"Answer with its tag. Allowed options: {', '.join(tags)}. " + ANSWER_FORMAT_CHOICE)
    t = Task("", "panel_max", q, tags[best], "choice", choices=tags, unit=unit,
             gauges=[g.to_dict() for g in gauges],
             meta={"n_gauges": n, "angle_trap": trap, "trap_tag": tags[int(np.argmax(fracs))]})
    checks = []
    for i, g in enumerate(gauges):
        checks += _common_checks(scene, i, g)
        checks += V.check_legibility(scene, i)
    checks.append(V.margin_check("winner_clear_margin", vals[best] - vals[second], 2 * tol_sum, " bar"))
    return t, scene, checks


def build_temporal_change(rng, factors) -> tuple[Task, Scene, list[V.Check]]:
    a = sample_gauge(rng, factors, "A  08:00")
    b = GaugeSpec(scale=a.scale, value=sample_value(rng, a.scale), unit=a.unit, multiplier=a.multiplier,
                  face=a.face, tag="B  10:00")
    renders = [render_gauge(a), render_gauge(b)]
    scene = build_scene(rng, renders, [a.tag, b.tag], "panel", photo_from_factors(factors))
    tol = (a.scale.reading_tolerance(a.value) + a.scale.reading_tolerance(b.value)) * a.multiplier
    delta = (b.value - a.value) * a.multiplier
    q = (f"The image shows the same gauge photographed at 08:00 (A) and at 10:00 (B). By how much did the "
         f"reading change from A to B (B minus A), in {a.unit}? Take into account everything printed on the "
         f"dial. " + ANSWER_FORMAT_NUM)
    t = Task("", "temporal_change", q, _round_for(tol, delta), "number", tol, unit=a.unit,
             gauges=[a.to_dict(), b.to_dict()])
    checks = _common_checks(scene, 0, a) + _common_checks(scene, 1, b)
    checks += V.check_legibility(scene, 0) + V.check_legibility(scene, 1)
    checks.append(V.margin_check("change_larger_than_reading_error", abs(delta), 2 * tol, f" {a.unit}"))
    return t, scene, checks


# (primary unit, vmin, vmax, step, minors) , (secondary unit, factor, offset, step, minors)
DUAL_PAIRS = [
    (("bar", 0, 10, 1, 5), ("psi", 14.5038, 0.0, 20, 4)),
    (("bar", 0, 16, 2, 4), ("psi", 14.5038, 0.0, 40, 4)),
    (("bar", 0, 6, 1, 5), ("psi", 14.5038, 0.0, 10, 2)),
    (("kPa", 0, 600, 100, 5), ("psi", 0.145038, 0.0, 10, 2)),
    (("°C", -20, 50, 10, 5), ("°F", 1.8, 32.0, 20, 4)),
    (("°C", 0, 120, 20, 4), ("°F", 1.8, 32.0, 40, 4)),
]


def build_dual_scale(rng, factors) -> tuple[Task, Scene, list[V.Check]]:
    (u1, vmin, vmax, step, minors), (u2, k, off, step2, minors2) = DUAL_PAIRS[int(rng.integers(0, len(DUAL_PAIRS)))]
    if factors["sweep"] == "90":          # two rings don't fit on a quadrant dial
        factors["sweep"] = "270"
    start, sweep = SWEEPS[factors["sweep"]]
    sc = Scale(vmin=vmin, vmax=vmax, start_angle=start, sweep=sweep, major_step=step, minors_per_major=minors)
    sc2 = Scale(vmin=vmin * k + off, vmax=vmax * k + off, start_angle=start, sweep=sweep, major_step=step2,
                minors_per_major=minors2, tick_origin=0.0)
    g = GaugeSpec(scale=sc, value=sample_value(rng, sc), unit=u1, face=factors["face"],
                  secondary=sc2, secondary_unit=u2)
    ask_secondary = bool(rng.integers(0, 2))
    r = render_gauge(g)
    scene = build_scene(rng, [r], [""], "single", photo_from_factors(factors))
    if ask_secondary:
        val2 = g.value * k + off
        tol = sc2.reading_tolerance(val2)
        ans, unit = val2, u2
        checks = [V.check_reading(r, val2, tol, ring="secondary")]
    else:
        tol = sc.reading_tolerance(g.value)
        ans, unit = g.value, u1
        checks = [V.check_reading(r, g.value, tol)]
    q = (f"This gauge has two printed scales ({u1} and {u2}). What is the reading in {unit}? " + ANSWER_FORMAT_NUM)
    t = Task("", "dual_scale", q, _round_for(tol, ans), "number", tol, unit=unit, gauges=[g.to_dict()],
             meta={"asked_scale": "secondary" if ask_secondary else "primary", "other_unit": u1 if ask_secondary else u2})
    checks += V.check_needle_visible(scene, 0) + V.check_legibility(scene, 0)
    return t, scene, checks


LEVEL_RANGES = [("%", 0, 100, 10), ("L", 0, 5000, 1000), ("L", 0, 2000, 500), ("m", 0, 8, 1), ("m³", 0, 40, 10)]


def build_level_reading(rng, factors) -> tuple[Task, Scene, list[V.Check]]:
    unit, vmin, vmax, step = LEVEL_RANGES[int(rng.integers(0, len(LEVEL_RANGES)))]
    n_major = round((vmax - vmin) / step)
    minors = factors["minors_per_major"] if factors["minors_per_major"] in (2, 5, 10) else 5
    factors["scale_kind"], factors["multiplier"] = "linear", "x1"   # not applicable to sight-glasses
    while minors > 1 and 460 / (n_major * minors) < 8:      # keep divisions >= 8 canonical px apart
        minors = {10: 5, 5: 2, 2: 1}[minors]
    factors["minors_per_major"] = minors
    sc = Scale(vmin=vmin, vmax=vmax, major_step=step, minors_per_major=minors, label_every=factors["label_every"])
    g = GaugeSpec(scale=sc, value=sample_value(rng, sc, 0.05, 0.95), unit=unit, face=factors["face"])
    liquid = list(LIQUIDS)[int(rng.integers(0, len(LIQUIDS)))]
    r = render_level(g, liquid)
    scene = build_scene(rng, [r], [""], "single", photo_from_factors(factors))
    tol = sc.reading_tolerance(g.value)
    q = (f"This is a tank level sight-glass with a printed scale. Reading at the top surface of the liquid, "
         f"what is the level in {unit}? " + ANSWER_FORMAT_NUM)
    t = Task("", "level_reading", q, _round_for(tol, g.value), "number", tol, unit=unit, gauges=[g.to_dict()],
             meta={"liquid": liquid})
    checks = [V.check_reading(r, g.value, tol)] + V.check_needle_visible(scene, 0) + V.check_legibility(scene, 0)
    return t, scene, checks


def build_panel_count(rng, factors) -> tuple[Task, Scene, list[V.Check]]:
    n = int(rng.integers(4, 7))
    tags = _tags(rng, n, "TI" if rng.integers(0, 2) else "PI")
    k = int(rng.integers(0, n + 1))            # how many are outside the green band
    out_idx = set(rng.choice(n, size=k, replace=False).tolist())
    gauges, margins = [], []
    for i in range(n):
        g = sample_gauge(rng, factors, tags[i])
        g.zones = make_zones(rng, g.scale, high_alarm=bool(rng.integers(0, 4)))
        if not g.zones:
            raise Reject("range too small for zones")
        pool = [z for z in g.zones if (z.name != "normal") == (i in out_idx)]
        z = pool[int(rng.integers(0, len(pool)))]
        g.value = float(g.scale.value_at_fraction(rng.uniform(g.scale.fraction(z.lo), g.scale.fraction(z.hi))))
        ang = g.scale.angle(g.value)
        margins.append(min(abs(ang - g.scale.angle(b)) for zz in g.zones for b in (zz.lo, zz.hi)))
        gauges.append(g)
    renders = [render_gauge(g) for g in gauges]
    scene = build_scene(rng, renders, tags, "panel", photo_from_factors(factors))
    q = (f"This panel has {n} gauges, each with coloured bands (green = normal, yellow = warning, red = danger). "
         f"How many gauges have their needle outside the green band (in yellow or red)? " + ANSWER_FORMAT_NUM)
    t = Task("", "panel_count", q, k, "number", 0.0, gauges=[g.to_dict() for g in gauges],
             meta={"n_gauges": n})
    checks = []
    for i, g in enumerate(gauges):
        checks += _common_checks(scene, i, g) + V.check_legibility(scene, i)
    checks.append(V.margin_check("all_needles_clear_of_zone_boundaries", min(margins), 3.0, "deg"))
    return t, scene, checks


FAMILIES: dict[str, Callable] = {
    "read_value": build_read_value,
    "zone_status": build_zone_status,
    "setpoint_deviation": build_setpoint_deviation,
    "panel_alarm": build_panel_alarm,
    "panel_max": build_panel_max,
    "temporal_change": build_temporal_change,
    "dual_scale": build_dual_scale,
    "level_reading": build_level_reading,
    "panel_count": build_panel_count,
}
