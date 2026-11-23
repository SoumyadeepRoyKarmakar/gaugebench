"""Gauge scales: how a physical value maps to a needle angle, and where ticks go.

Angle convention used everywhere in GaugeBench:
    0 deg  = needle pointing straight up (12 o'clock)
    +deg   = clockwise
So a classic 270-degree pressure gauge sweeps from -135 (bottom-left) to +135 (bottom-right).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


SCALE_TYPES = ("linear", "sqrt", "log")


@dataclass
class Tick:
    value: float       # scale value printed/implied at this tick (before multiplier)
    major: bool
    labeled: bool


@dataclass
class Scale:
    vmin: float
    vmax: float
    kind: str = "linear"            # linear | sqrt | log
    start_angle: float = -135.0
    sweep: float = 270.0
    major_step: float = 10.0        # ignored for log (majors are decades)
    minors_per_major: int = 5       # number of minor *intervals* per major interval
    label_every: int = 1            # label every Nth major tick (ends always labeled)
    tick_origin: float | None = None  # if set, majors sit on multiples of major_step from here
                                      # (e.g. a psi ring 0..145.04 with majors 0,20,...,140)
    ticks: list[Tick] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind not in SCALE_TYPES:
            raise ValueError(f"unknown scale kind {self.kind}")
        if self.kind == "log" and self.vmin <= 0:
            raise ValueError("log scale needs vmin > 0")
        if not self.ticks:
            self.ticks = self._build_ticks()

    # ---- value <-> fraction of sweep -------------------------------------------------
    def fraction(self, v: float) -> float:
        if self.kind == "linear":
            return (v - self.vmin) / (self.vmax - self.vmin)
        if self.kind == "sqrt":
            x = max(0.0, (v - self.vmin) / (self.vmax - self.vmin))
            return math.sqrt(x)
        return (math.log10(v) - math.log10(self.vmin)) / (math.log10(self.vmax) - math.log10(self.vmin))

    def value_at_fraction(self, f: float) -> float:
        if self.kind == "linear":
            return self.vmin + f * (self.vmax - self.vmin)
        if self.kind == "sqrt":
            return self.vmin + (f * f) * (self.vmax - self.vmin)
        lo, hi = math.log10(self.vmin), math.log10(self.vmax)
        return 10 ** (lo + f * (hi - lo))

    def angle(self, v: float) -> float:
        return self.start_angle + self.fraction(v) * self.sweep

    @property
    def end_angle(self) -> float:
        return self.start_angle + self.sweep

    # ---- ticks ------------------------------------------------------------------------
    def _build_ticks(self) -> list[Tick]:
        ticks: list[Tick] = []
        if self.kind == "log":
            decade = self.vmin
            majors = []
            while decade <= self.vmax * (1 + 1e-9):
                majors.append(decade)
                decade *= 10
            for i, d in enumerate(majors):
                ticks.append(Tick(_clean(d), True, True))
                if i + 1 < len(majors):
                    for m in range(2, 10):
                        ticks.append(Tick(_clean(d * m), False, False))
            return ticks

        step = self.major_step
        minor_step = step / self.minors_per_major
        if self.tick_origin is None:
            first = self.vmin
            n_major = round((self.vmax - self.vmin) / step)
        else:
            first = self.tick_origin + math.ceil((self.vmin - self.tick_origin) / step - 1e-9) * step
            n_major = int(math.floor((self.vmax - first) / step + 1e-9))
        for i in range(n_major + 1):
            v = first + i * step
            labeled = (i % self.label_every == 0) or i == n_major
            ticks.append(Tick(_clean(v), True, labeled))
            if i < n_major:
                for j in range(1, self.minors_per_major):
                    ticks.append(Tick(_clean(v + j * minor_step), False, False))
        if self.tick_origin is not None:   # minor ticks in the partial divisions at either end
            for j in range(1, self.minors_per_major):
                lo, hi = first - j * minor_step, first + n_major * step + j * minor_step
                if lo >= self.vmin - 1e-9:
                    ticks.append(Tick(_clean(lo), False, False))
                if hi <= self.vmax + 1e-9:
                    ticks.append(Tick(_clean(hi), False, False))
        ticks.sort(key=lambda t: t.value)
        return ticks

    def bracket(self, v: float) -> tuple[Tick, Tick]:
        """The two adjacent ticks (any kind) that bracket value v."""
        ts = self.ticks
        for a, b in zip(ts, ts[1:]):
            if a.value <= v <= b.value:
                return a, b
        return (ts[0], ts[1]) if v < ts[0].value else (ts[-2], ts[-1])

    def local_division(self, v: float) -> float:
        """Width (in scale units) of the smallest tick division around v."""
        a, b = self.bracket(v)
        return b.value - a.value

    def reading_tolerance(self, v: float) -> float:
        """Accepted reading error: half of the local smallest division (standard
        human-reading practice for analogue instruments)."""
        return 0.5 * self.local_division(v)


def _clean(v: float) -> float:
    r = round(v, 6)
    return 0.0 if r == 0 else r


def fmt_value(v: float) -> str:
    """Pretty-print a tick label (no trailing .0, compact for big numbers)."""
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s
