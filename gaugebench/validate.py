"""Independent validation of every generated task.

The generator *knows* the answer because it chose the needle value. That alone
does not prove the picture actually shows it (a label could be cropped, glare
could hide the needle, ticks could blur together). So each task is checked by
code paths that do not reuse the generator's value->angle formula:

1. Pixel re-reading (``cv_read``): a deterministic computer-vision reader that
   works the way a technician does — find the needle direction from needle pixels,
   find tick marks from tick pixels, find the two printed labels either side, count
   the divisions between them, and interpolate. It never calls ``Scale.angle``.
   Its reading must agree with the answer key within tolerance.
2. Visibility checks on the *final photographed image*: needle not washed out by
   glare, enough contrast, tick divisions and labels large enough to resolve.
3. Ambiguity checks (family specific, in tasks.py): e.g. the needle is not sitting
   on a zone boundary, the "highest gauge" wins by a clear margin.

A task is only published if every check passes. Rejections are logged as
evidence that the guard rails work.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import cv2
import numpy as np

from .render import GaugeRender
from .scene import Scene

MIN_TICK_GAP_PX = 3.0       # neighbouring tick marks must be >= this far apart in the final image
MIN_LABEL_PX = 9.0          # printed numbers must be at least this tall in the final image
MAX_GLARE_ON_NEEDLE = 0.15  # fraction of needle pixels that may sit under strong glare
MIN_NEEDLE_CONTRAST = 30.0  # luminance difference needle vs surroundings (0..255)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ReadError(Exception):
    pass


# ---------------------------------------------------------------------------------------
# 1. Independent pixel reader
# ---------------------------------------------------------------------------------------
def _pixel_angles(mask: np.ndarray, cx: float, cy: float, r_lo: float, r_hi: float):
    ys, xs = np.nonzero(mask > 128)
    dx, dy = xs - cx, cy - ys
    r = np.hypot(dx, dy)
    keep = (r >= r_lo) & (r <= r_hi)
    return np.degrees(np.arctan2(dx[keep], dy[keep])), r[keep]


def _needle_angle(mask: np.ndarray, cx: float, cy: float, R: float) -> float:
    ang, _ = _pixel_angles(mask, cx, cy, 0.30 * R, 0.86 * R)
    if len(ang) < 20:
        raise ReadError("needle pixels not found")
    rad = np.radians(ang)
    return float(np.degrees(math.atan2(np.sin(rad).mean(), np.cos(rad).mean())))


def _tick_angles(mask: np.ndarray, cx: float, cy: float, r_lo: float, r_hi: float) -> list[float]:
    """Angles of individual tick marks = centroids of connected components inside a ring."""
    h, w = mask.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - cx, yy - cy)
    ring = ((mask > 100) & (r >= r_lo) & (r <= r_hi)).astype(np.uint8)
    n, _, _, cent = cv2.connectedComponentsWithStats(ring, connectivity=8)
    angles = [math.degrees(math.atan2(x - cx, cy - y)) for x, y in cent[1:]]
    return sorted(angles)


def _interpolate(ticks: list[float], labelled: list[tuple[int, float]], pos: float) -> float:
    """Technician-style reading along one axis (angle for dials, height for level glasses).
    `ticks` are tick coordinates in increasing order, `labelled` maps tick index -> printed value."""
    labelled = sorted(set(labelled))
    if len(labelled) < 2:
        raise ReadError("fewer than two labels")
    pair = None
    for (i0, v0), (i1, v1) in zip(labelled, labelled[1:]):
        if ticks[i0] <= pos <= ticks[i1]:
            pair = (i0, v0, i1, v1)
            break
    if pair is None:   # outside the labelled span: extrapolate from the nearest pair
        pair = (*labelled[0], *labelled[1]) if pos < ticks[labelled[0][0]] else (*labelled[-2], *labelled[-1])
    i0, v0, i1, v1 = pair
    if i1 == i0:
        raise ReadError("degenerate label pair")
    step = (v1 - v0) / (i1 - i0)            # value per tick division (counted, not computed)
    m = max(0, min(len(ticks) - 2, int(np.searchsorted(ticks, pos) - 1)))
    span = ticks[m + 1] - ticks[m]
    frac = (pos - ticks[m]) / span if span else 0.0
    return v0 + (m - i0) * step + frac * step


# tick-ring radii (fractions of R) where only the wanted ticks are present
RINGS = {
    "primary": {"all": (0.89, 0.94), "major": (0.80, 0.85)},
    "secondary": {"all": (0.525, 0.555), "major": (0.48, 0.51)},
}


def cv_read(render: GaugeRender, which: str = "needle", ring: str = "primary") -> float:
    """Read the instrument from pixels only. Returns the scale value (before multiplier)."""
    if render.kind == "level":
        return cv_read_level(render)
    cx, cy = render.center
    R = render.radius
    if which == "needle":
        mask = render.needle_mask
    else:
        if render.setpoint_mask is None:
            raise ReadError("no set-point needle")
        mask = np.clip(render.setpoint_mask.astype(int) - render.needle_mask.astype(int), 0, 255)
    theta = _needle_angle(mask, cx, cy, R)

    if ring == "primary":
        tmask, mmask, labels = render.tick_mask, render.major_tick_mask, render.labels
    else:
        if render.sec_tick_mask is None:
            raise ReadError("no secondary scale")
        tmask, mmask, labels = render.sec_tick_mask, render.sec_major_tick_mask, render.sec_labels
    (a0, a1), (b0, b1) = RINGS[ring]["all"], RINGS[ring]["major"]
    all_ticks = _tick_angles(tmask, cx, cy, a0 * R, a1 * R)
    majors = _tick_angles(mmask, cx, cy, b0 * R, b1 * R)
    if len(all_ticks) < 3 or len(majors) < 2:
        raise ReadError("too few tick marks resolved")

    # attach each printed label to the nearest major tick, then to its index in all_ticks
    labelled: list[tuple[int, float]] = []
    for lb in labels:
        la = math.degrees(math.atan2(lb.x - cx, cy - lb.y))
        m = min(majors, key=lambda a: abs(a - la))
        if abs(m - la) > 4.0:
            raise ReadError(f"label {lb.text} has no tick")
        idx = min(range(len(all_ticks)), key=lambda i: abs(all_ticks[i] - m))
        labelled.append((idx, lb.value))
    return _interpolate(all_ticks, labelled, theta)


def _row_centroids(mask: np.ndarray, x0: int, x1: int) -> list[float]:
    band = (mask[:, x0:x1] > 100).astype(np.uint8)
    n, _, _, cent = cv2.connectedComponentsWithStats(band, connectivity=8)
    return sorted(float(y) for _, y in cent[1:])


def cv_read_level(render: GaugeRender) -> float:
    """Level sight-glass: liquid surface = highest row where the liquid fills the tube."""
    from .level import TUBE_X0, TUBE_X1, TICK_X0, MAJOR_X1, MINOR_X1
    liq = render.liquid_mask[:, TUBE_X0 + 3:TUBE_X1 - 3] > 128
    rows = np.nonzero(liq.mean(axis=1) > 0.5)[0]
    if len(rows) == 0:
        raise ReadError("no liquid found")
    surface = float(rows.min())
    all_y = _row_centroids(render.tick_mask, TICK_X0 + 2, MINOR_X1 - 4)
    major_y = _row_centroids(render.major_tick_mask, MINOR_X1 + 4, MAJOR_X1 - 2)
    if len(all_y) < 3 or len(major_y) < 2:
        raise ReadError("too few tick marks resolved")
    # work in "height" (= -y) so values increase along the axis
    heights = sorted(-y for y in all_y)
    labelled = []
    for lb in render.labels:
        m = min(major_y, key=lambda y: abs(y - lb.y))
        if abs(m - lb.y) > 6:
            raise ReadError(f"label {lb.text} has no tick")
        idx = min(range(len(heights)), key=lambda i: abs(heights[i] + m))
        labelled.append((idx, lb.value))
    return _interpolate(heights, labelled, -surface)


def check_reading(render: GaugeRender, truth_scale_value: float, tol_scale: float, which: str = "needle",
                  ring: str = "primary") -> Check:
    name = f"pixel_reread_{which}" + ("" if ring == "primary" else f"_{ring}")
    try:
        v = cv_read(render, which, ring)
    except ReadError as e:
        return Check(name, False, f"reader failed: {e}")
    err = abs(v - truth_scale_value)
    return Check(name, err <= tol_scale, f"cv={v:.4g} key={truth_scale_value:.4g} err={err:.3g} tol={tol_scale:.3g}")


# ---------------------------------------------------------------------------------------
# 2. Visibility checks on the final image
# ---------------------------------------------------------------------------------------
def _luma(img: np.ndarray) -> np.ndarray:
    return img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114


def check_needle_visible(scene: Scene, i: int, which: str = "needle") -> list[Check]:
    m = scene.needle_masks[i] if which == "needle" else scene.setpoint_masks[i]
    if which != "needle":
        m = np.clip(m - scene.needle_masks[i], 0, 1)
    core = m > 0.6
    n = int(core.sum())
    if n < 15:
        return [Check(f"{which}_present", False, f"only {n} needle px")]
    glare_frac = float((scene.glare_alpha[core] > 0.35).mean())
    ring = cv2.dilate(core.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~(m > 0.05)
    L = _luma(scene.image.astype(np.float32))
    contrast = abs(float(L[core].mean()) - float(L[ring].mean())) if ring.any() else 0.0
    return [
        Check(f"{which}_not_glared", glare_frac <= MAX_GLARE_ON_NEEDLE, f"{glare_frac:.2f} of needle under glare"),
        Check(f"{which}_contrast", contrast >= MIN_NEEDLE_CONTRAST, f"contrast={contrast:.1f}"),
    ]


def check_legibility(scene: Scene, i: int) -> list[Check]:
    r = scene.renders[i]
    s = scene.local_scale(i)
    if r.kind == "level":
        from .level import TICK_X0, MINOR_X1
        ys = _row_centroids(r.tick_mask, TICK_X0 + 2, MINOR_X1 - 4)
        gap_px = float(np.diff(ys).min()) * s if len(ys) > 1 else 0.0
    else:
        cx, cy = r.center
        gaps = []
        rings = [("primary", r.tick_mask)] + ([("secondary", r.sec_tick_mask)] if r.sec_tick_mask is not None else [])
        for ring, m in rings:
            a0, a1 = RINGS[ring]["all"]
            t = _tick_angles(m, cx, cy, a0 * r.radius, a1 * r.radius)
            if len(t) > 1:
                gaps.append(float(np.diff(t).min()) * math.pi / 180 * r.radius * (a0 + a1) / 2 * s)
        gap_px = min(gaps) if gaps else 0.0
    all_labels = r.labels + r.sec_labels
    lbl_px = min(lb.height_px for lb in all_labels) * s if all_labels else 0.0
    return [
        Check("tick_divisions_resolvable", gap_px >= MIN_TICK_GAP_PX, f"min tick gap {gap_px:.1f}px"),
        Check("labels_legible", lbl_px >= MIN_LABEL_PX, f"label height {lbl_px:.1f}px"),
    ]


def margin_check(name: str, margin: float, needed: float, unit: str = "") -> Check:
    return Check(name, margin >= needed, f"margin {margin:.3g}{unit} (need {needed:.3g})")
