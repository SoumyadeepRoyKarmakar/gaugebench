"""Three more instrument geometries, each testing a different visual skill.

| family          | instrument                         | skill                                              |
|-----------------|------------------------------------|----------------------------------------------------|
| dial_meter      | utility "clock" meter, 4-5 dials   | apply a reading *convention* across alternating    |
|                 |                                    | clockwise / anticlockwise dials                    |
| vernier         | vernier caliper (0.1 mm)           | sub-division precision: find the aligned line      |
| digital_display | 7-segment LCD / LED / VFD          | the digital *control*: is the difficulty analogue? |

Like the dials, every instrument returns evidence layers, and every task is
re-read from pixels by a reader that does not reuse the drawing formulas
(for the vernier and the meter it works from tick/pointer masks; for the
digital display from luminance at segment positions).
"""
from __future__ import annotations

import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

from . import validate as V
from .render import CANON, SS, GaugeRender, LabelInfo, font
from .scene import build_scene
from .spec import MULTIPLIERS, photo_from_factors
from .tasks import ANSWER_FORMAT_NUM, Reject, Task, _round_for

S = SS


def _down(im: Image.Image) -> Image.Image:
    return im.resize((CANON, CANON), Image.LANCZOS)


def _label_check(scene, i: int, label_px: float) -> V.Check:
    px = label_px * scene.local_scale(i)
    return V.Check("labels_legible", px >= V.MIN_LABEL_PX, f"label height {px:.1f}px")


# =======================================================================================
# 1. Utility clock-dial meter
# =======================================================================================
def _meter_angle(p: float, ccw: bool) -> float:
    return (-p if ccw else p) * 36.0          # 0 at top; one digit = 36 degrees


def render_dial_meter(positions: list[float], dark: bool = False) -> GaugeRender:
    """positions: pointer position (0..10) of each dial, most significant first."""
    n = len(positions)
    W = CANON * S
    spacing = 138 if n == 4 else 110
    R = 0.445 * spacing
    cy = 300
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    plate = (30, 32, 36) if dark else (236, 233, 222)
    ink = (236, 236, 236) if dark else (24, 24, 26)
    d.rounded_rectangle([14 * S, 128 * S, 586 * S, 472 * S], 22 * S, fill=(96, 99, 104, 255))
    d.rounded_rectangle([24 * S, 138 * S, 576 * S, 462 * S], 16 * S, fill=plate + (255,))
    d.text((300 * S, 170 * S), "kWh", font=font(30 * S), fill=ink + (255,), anchor="mm")
    d.text((548 * S, 170 * S), "1/1", font=font(16 * S), fill=ink + (160,), anchor="mm")

    union = Image.new("L", (W, W), 0)
    dials, labels = [], []
    lbl_px = 0.30 * R
    for i, p in enumerate(positions):
        cx = 300 + (i - (n - 1) / 2) * spacing
        ccw = (n - 1 - i) % 2 == 1                 # units dial (rightmost) turns clockwise
        d.ellipse([(cx - R) * S, (cy - R) * S, (cx + R) * S, (cy + R) * S], outline=ink + (255,), width=int(2 * S))
        for k in range(10):
            a = math.radians(_meter_angle(k, ccw))
            x0, y0 = cx + 0.86 * R * math.sin(a), cy - 0.86 * R * math.cos(a)
            x1, y1 = cx + 0.98 * R * math.sin(a), cy - 0.98 * R * math.cos(a)
            d.line([(x0 * S, y0 * S), (x1 * S, y1 * S)], fill=ink + (255,), width=int(2.4 * S))
            tx, ty = cx + 0.68 * R * math.sin(a), cy - 0.68 * R * math.cos(a)
            d.text((tx * S, ty * S), str(k), font=font(int(lbl_px * S)), fill=ink + (255,), anchor="mm")
            labels.append(LabelInfo(k, str(k), tx, ty, lbl_px))
        # direction arrow above the dial
        sweep = (-50, -10) if ccw else (10, 50)
        box = [(cx - R - 9) * S, (cy - R - 9) * S, (cx + R + 9) * S, (cy + R + 9) * S]
        d.arc(box, sweep[0] - 90, sweep[1] - 90, fill=(200, 60, 40, 255), width=int(2 * S))
        end = math.radians(sweep[0] if ccw else sweep[1])
        ex, ey = cx + (R + 9) * math.sin(end), cy - (R + 9) * math.cos(end)
        tang = end + (-math.pi / 2 if ccw else math.pi / 2)
        tip = (ex + 7 * math.sin(tang), ey - 7 * math.cos(tang))
        side = [(ex + 4.5 * math.sin(end), ey - 4.5 * math.cos(end)), (ex - 4.5 * math.sin(end), ey + 4.5 * math.cos(end))]
        d.polygon([(tip[0] * S, tip[1] * S)] + [(x * S, y * S) for x, y in side], fill=(200, 60, 40, 255))
        mult = 10 ** (n - 1 - i)
        d.text((cx * S, (cy + R + 26) * S), f"×{mult:,}".replace(",", " "), font=font(int(17 * S)),
               fill=ink + (255,), anchor="mm")
        # pointer
        a = math.radians(_meter_angle(p, ccw))
        ux, uy = math.sin(a), -math.cos(a)
        px_, py_ = -uy, ux
        tip = (cx + 0.74 * R * ux, cy + 0.74 * R * uy)
        tail = (cx - 0.22 * R * ux, cy - 0.22 * R * uy)
        bw = 0.075 * R
        poly = [(tip[0], tip[1]), (cx + bw * px_, cy + bw * py_), (tail[0] + 0.6 * bw * px_, tail[1] + 0.6 * bw * py_),
                (tail[0] - 0.6 * bw * px_, tail[1] - 0.6 * bw * py_), (cx - bw * px_, cy - bw * py_)]
        layer = Image.new("L", (W, W), 0)
        ImageDraw.Draw(layer).polygon([(x * S, y * S) for x, y in poly], fill=255)
        img.paste(Image.new("RGBA", (W, W), (12, 12, 12, 255) if not dark else (245, 245, 245, 255)), (0, 0), layer)
        union.paste(255, (0, 0), layer)
        d.ellipse([(cx - 0.12 * R) * S, (cy - 0.12 * R) * S, (cx + 0.12 * R) * S, (cy + 0.12 * R) * S],
                  fill=(150, 40, 30, 255))
        dials.append({"cx": cx, "cy": cy, "R": R, "ccw": ccw, "mask": np.asarray(_down(layer))})

    r = GaugeRender(rgba=_down(img), needle_mask=np.asarray(_down(union)), setpoint_mask=None,
                    tick_mask=np.zeros((CANON, CANON), np.uint8), major_tick_mask=np.zeros((CANON, CANON), np.uint8),
                    center=(300, 300), radius=R, labels=labels, kind="dial_meter")
    r.dials = dials
    return r


def cv_read_dial_meter(render: GaugeRender) -> list[float]:
    out = []
    for dl in render.dials:
        ang = V._needle_angle(dl["mask"], dl["cx"], dl["cy"], dl["R"])
        out.append(((-ang if dl["ccw"] else ang) % 360.0) / 36.0)
    return out


def build_dial_meter(rng, factors):
    n = int(rng.choice([4, 5]))
    value = int(rng.integers(10 ** (n - 1) // 10, 10 ** n))
    frac = float(rng.uniform(0.2, 0.8))                       # units pointer between two numbers
    full = value + frac
    positions = [(full / 10 ** k) % 10 for k in range(n - 1, -1, -1)]
    for k in ("scale_kind", "sweep", "minors_per_major", "label_every", "multiplier"):
        factors[k] = {"scale_kind": "linear", "sweep": "270", "minors_per_major": 5, "label_every": 1,
                      "multiplier": "x1"}[k]
    r = render_dial_meter(positions, dark=factors["face"] == "dark")
    scene = build_scene(rng, [r], [""], "single", photo_from_factors(factors))
    q = ("This is an electricity meter with clock-style dials. Adjacent dials turn in opposite directions "
         "(see the arrows). Read the dials from left to right; when a pointer is between two numbers, take "
         "the lower number it has just passed (after 9 comes 0). What is the meter reading in kWh? "
         + ANSWER_FORMAT_NUM)
    t = Task("", "dial_meter", q, value, "number", 0.0, unit="kWh",
             meta={"n_dials": n, "positions": [round(p, 3) for p in positions], "range": [0, 10 ** n - 1]})

    try:
        read = cv_read_dial_meter(r)
        errs = [min(abs(a - b), 10 - abs(a - b)) for a, b in zip(read, positions)]
        digits = "".join(str(int(math.floor(p + 1e-9)) % 10) for p in read)
        ok = max(errs) < 0.2 and int(digits) == value
        reread = V.Check("pixel_reread_dials", ok, f"cv digits={digits} key={value} max_err={max(errs):.2f} digit")
    except V.ReadError as e:
        reread = V.Check("pixel_reread_dials", False, f"reader failed: {e}")
    # every non-units pointer must sit visibly between two numbers, never on one
    margin = min(min(p % 1, 1 - p % 1) for p in positions[:-1])
    checks = [reread] + V.check_needle_visible(scene, 0) + [_label_check(scene, 0, 0.30 * r.radius),
              V.margin_check("pointers_clear_of_numbers", margin, 0.07, " digit")]
    return t, scene, checks


# =======================================================================================
# 2. Vernier caliper (least count 0.1 mm)
# =======================================================================================
PPM = 28.0                 # canonical px per mm
X0 = 170.0                 # x of the vernier zero line
BEAM_Y0, BEAM_Y1 = 160, 300
PLATE_Y1 = 432
VERN_DIV = 0.9             # 10 vernier divisions span 9 mm


def render_vernier(value_mm: float) -> GaugeRender:
    W = CANON * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (22, 22, 24)
    # beam with a brushed-steel vertical gradient
    beam = np.zeros((BEAM_Y1 - BEAM_Y0, 600, 4), np.uint8)
    g = np.linspace(205, 172, BEAM_Y1 - BEAM_Y0)[:, None]
    beam[..., 0] = g; beam[..., 1] = g + 3; beam[..., 2] = g + 8; beam[..., 3] = 255
    beam_im = Image.fromarray(beam).resize((600 * S, (BEAM_Y1 - BEAM_Y0) * S))
    img.alpha_composite(beam_im, (0, BEAM_Y0 * S))
    d.line([(0, BEAM_Y0 * S), (W, BEAM_Y0 * S)], fill=(120, 124, 130, 255), width=int(2 * S))
    # sliding vernier plate
    plate = [118 * S, (BEAM_Y1 - 4) * S, 478 * S, PLATE_Y1 * S]
    d.rounded_rectangle(plate, 10 * S, fill=(222, 224, 228, 255), outline=(140, 144, 150, 255), width=int(2 * S))
    d.ellipse([440 * S, 395 * S, 462 * S, 417 * S], fill=(160, 164, 170, 255), outline=(110, 112, 118, 255), width=S)
    d.line([444 * S, 406 * S, 458 * S, 406 * S], fill=(100, 100, 104, 255), width=int(2 * S))

    main_m, vern_m = Image.new("L", (W, W), 0), Image.new("L", (W, W), 0)
    dm, dv = ImageDraw.Draw(main_m), ImageDraw.Draw(vern_m)
    labels = []
    lpx = 30
    lo = math.ceil(value_mm - (X0 - 24) / PPM)
    hi = math.floor(value_mm + (576 - X0) / PPM)
    for m in range(max(0, lo), hi + 1):
        x = X0 + (m - value_mm) * PPM
        L = 36 if m % 10 == 0 else 25 if m % 5 == 0 else 16
        seg = [(x * S, (BEAM_Y1 - L) * S), (x * S, (BEAM_Y1 - 1) * S)]
        d.line(seg, fill=ink + (255,), width=int(2.4 * S))
        dm.line(seg, fill=255, width=int(2.4 * S))
        if m % 10 == 0:
            txt = str(m // 10)
            d.text((x * S, (BEAM_Y1 - 58) * S), txt, font=font(lpx * S), fill=ink + (255,), anchor="mm")
            labels.append(LabelInfo(m, txt, x, BEAM_Y1 - 58, lpx))
    d.text((40 * S, (BEAM_Y0 + 24) * S), "mm", font=font(18 * S), fill=ink + (255,), anchor="mm")
    for k in range(11):
        x = X0 + k * VERN_DIV * PPM
        L = 30 if k in (0, 5, 10) else 20
        seg = [(x * S, (BEAM_Y1 + 1) * S), (x * S, (BEAM_Y1 + L) * S)]
        d.line(seg, fill=ink + (255,), width=int(2.2 * S))
        dv.line(seg, fill=255, width=int(2.2 * S))
        if k % 2 == 0:
            d.text((x * S, (BEAM_Y1 + 48) * S), str(k), font=font(22 * S), fill=ink + (255,), anchor="mm")
    d.text((360 * S, 406 * S), "0.1 mm", font=font(20 * S), fill=ink + (255,), anchor="mm")

    r = GaugeRender(rgba=_down(img), needle_mask=np.asarray(_down(vern_m)), setpoint_mask=None,
                    tick_mask=np.asarray(_down(main_m)), major_tick_mask=np.asarray(_down(main_m)),
                    center=(300, 300), radius=240, labels=labels, kind="vernier")
    return r


def _cols(mask: np.ndarray, y0: int, y1: int) -> list[float]:
    band = (mask[y0:y1, :] > 100).astype(np.uint8)
    n, _, _, cent = cv2.connectedComponentsWithStats(band, connectivity=8)
    return sorted(float(x) for x, _ in cent[1:])


def cv_read_vernier(render: GaugeRender) -> tuple[float, float]:
    """Returns (reading in mm, alignment margin in canonical px)."""
    main = _cols(render.tick_mask, BEAM_Y1 - 14, BEAM_Y1 - 2)
    vern = _cols(render.needle_mask, BEAM_Y1 + 3, BEAM_Y1 + 16)
    if len(main) < 5 or len(vern) != 11:
        raise V.ReadError(f"found {len(main)} main and {len(vern)} vernier lines")
    lab = []
    for lb in render.labels:
        j = min(range(len(main)), key=lambda i: abs(main[i] - lb.x))
        if abs(main[j] - lb.x) > 4:
            raise V.ReadError(f"label {lb.text} has no line")
        lab.append((j, lb.value))
    if not lab:
        raise V.ReadError("no main-scale label visible")
    j0, v0 = lab[0]
    zero = vern[0]
    left = [i for i in range(len(main)) if main[i] <= zero + 0.5]
    if not left:
        raise V.ReadError("vernier zero left of the main scale")
    whole = v0 + (left[-1] - j0)
    mis = [min(abs(vx - mx) for mx in main) for vx in vern]
    order = sorted(range(1, 10), key=lambda k: mis[k])          # lines 1..9 (0 and 10 frame the scale)
    best, second = order[0], order[1]
    return whole + best / 10.0, mis[second] - mis[best]


def build_vernier(rng, factors):
    value = int(rng.integers(0, 141)) + int(rng.integers(1, 10)) / 10.0
    for k in ("scale_kind", "sweep", "minors_per_major", "label_every", "multiplier", "face"):
        factors[k] = {"scale_kind": "linear", "sweep": "270", "minors_per_major": 10, "label_every": 1,
                      "multiplier": "x1", "face": "light"}[k]
    r = render_vernier(value)
    scene = build_scene(rng, [r], [""], "single", photo_from_factors(factors))
    q = ("This is a close-up of a vernier caliper. The main scale is in millimetres, and its numbers mark whole "
         "centimetres. The sliding vernier scale has a least count of 0.1 mm. What measurement does the caliper "
         "show, in mm? " + ANSWER_FORMAT_NUM)
    tol = 0.05
    t = Task("", "vernier", q, round(value, 1), "number", tol, unit="mm", meta={"range": [0, 150]})
    try:
        read, margin = cv_read_vernier(r)
        reread = V.Check("pixel_reread_vernier", abs(read - value) < 1e-6,
                         f"cv={read:.1f} key={value:.1f} alignment margin={margin:.1f}px")
    except V.ReadError as e:
        reread, margin = V.Check("pixel_reread_vernier", False, f"reader failed: {e}"), 0.0
    s = scene.local_scale(0)
    need = 1.5 + float(factors["blur"])                          # blur smears the 2.8 px alignment step
    checks = [reread] + V.check_needle_visible(scene, 0) + [
        _label_check(scene, 0, 30),
        V.margin_check("vernier_alignment_resolvable", margin * s, need, " px"),
    ]
    return t, scene, checks


# =======================================================================================
# 3. Digital 7-segment panel meter
# =======================================================================================
SEGS = {  # which of a b c d e f g are lit
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
    "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", " ": "",
}
DECODE = {"".join(sorted(v)): k for k, v in SEGS.items() if k != " "}
STYLES = {
    "lcd": {"bg": (156, 170, 146), "lit": (26, 32, 26), "ghost": (138, 152, 128), "case": (60, 62, 66)},
    "led": {"bg": (24, 8, 8), "lit": (255, 52, 36), "ghost": (52, 18, 16), "case": (34, 34, 38)},
    "vfd": {"bg": (8, 20, 20), "lit": (70, 245, 215), "ghost": (16, 46, 44), "case": (34, 34, 38)},
}


def _seg_polys(x: float, y: float, w: float, h: float, t: float) -> dict[str, list[tuple[float, float]]]:
    """Hexagonal segments for a cell with top-left (x, y), slanted slightly like real displays."""
    def hseg(cx, cy, L):
        return [(cx - L / 2, cy), (cx - L / 2 + t / 2, cy - t / 2), (cx + L / 2 - t / 2, cy - t / 2),
                (cx + L / 2, cy), (cx + L / 2 - t / 2, cy + t / 2), (cx - L / 2 + t / 2, cy + t / 2)]

    def vseg(cx, cy, L):
        return [(cx, cy - L / 2), (cx + t / 2, cy - L / 2 + t / 2), (cx + t / 2, cy + L / 2 - t / 2),
                (cx, cy + L / 2), (cx - t / 2, cy + L / 2 - t / 2), (cx - t / 2, cy - L / 2 + t / 2)]
    g = 1.5
    L_h, L_v = w - t - 2 * g, h / 2 - t / 2 - 2 * g
    polys = {
        "a": hseg(x + w / 2, y + t / 2, L_h), "g": hseg(x + w / 2, y + h / 2, L_h), "d": hseg(x + w / 2, y + h - t / 2, L_h),
        "f": vseg(x + t / 2, y + h / 4 + t / 4, L_v), "b": vseg(x + w - t / 2, y + h / 4 + t / 4, L_v),
        "e": vseg(x + t / 2, y + 3 * h / 4 - t / 4, L_v), "c": vseg(x + w - t / 2, y + 3 * h / 4 - t / 4, L_v),
    }
    slant = 0.09
    cy = y + h / 2
    return {k: [(px + (cy - py) * slant, py) for px, py in v] for k, v in polys.items()}


def render_digital(text: str, unit: str, style: str, annunciator: str = "") -> GaugeRender:
    """text: e.g. '-12.48'; the '.' attaches to the preceding cell."""
    st = STYLES[style]
    cells, dots = [], []
    for ch in text:
        if ch == ".":
            dots.append(len(cells) - 1)
        else:
            cells.append(ch)
    n = max(4, len(cells))
    cells = [" "] * (n - len(cells)) + cells                      # right-aligned like real meters
    dots = [i + (n - len([c for c in text if c != "."])) for i in dots]
    W = CANON * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lit_m = Image.new("L", (W, W), 0)
    dl = ImageDraw.Draw(lit_m)
    d.rounded_rectangle([30 * S, 150 * S, 570 * S, 450 * S], 18 * S, fill=st["case"] + (255,))
    d.rounded_rectangle([58 * S, 176 * S, 542 * S, 392 * S], 8 * S, fill=st["bg"] + (255,))
    cw = min(92.0, 440.0 / n)
    ch = 140.0
    t = cw * 0.17
    x0 = 300 - (n * cw) / 2 + 6
    y0 = 226
    seg_info = []
    for i, c in enumerate(cells):
        x = x0 + i * cw
        polys = _seg_polys(x + 6, y0, cw - 18, ch, t)
        on = set(SEGS.get(c, ""))
        cell = {}
        for name, poly in polys.items():
            col = st["lit"] if name in on else st["ghost"]
            d.polygon([(px * S, py * S) for px, py in poly], fill=col + (255,))
            if name in on:
                dl.polygon([(px * S, py * S) for px, py in poly], fill=255)
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            cell[name] = (cx, cy)
        dot = (x + cw - 9, y0 + ch - t / 2)
        on_dot = i in dots
        d.ellipse([(dot[0] - t * 0.55) * S, (dot[1] - t * 0.55) * S, (dot[0] + t * 0.55) * S, (dot[1] + t * 0.55) * S],
                  fill=(st["lit"] if on_dot else st["ghost"]) + (255,))
        if on_dot:
            dl.ellipse([(dot[0] - t * 0.55) * S, (dot[1] - t * 0.55) * S, (dot[0] + t * 0.55) * S, (dot[1] + t * 0.55) * S], fill=255)
        cell["dp"] = dot
        seg_info.append(cell)
    # annunciators (multiplier) top-right inside the window, unlit ones as ghosts
    ann_px = 18
    ann_pos = {"×10": (418, 200), "×100": (478, 200)}
    for a, (ax, ay) in ann_pos.items():
        col = st["lit"] if a == annunciator else st["ghost"]
        d.text((ax * S, ay * S), a, font=font(ann_px * S), fill=col + (255,), anchor="mm")
    text_col = (230, 230, 230)
    d.text((520 * S, 421 * S), unit, font=font(30 * S), fill=text_col + (255,), anchor="rm")
    d.text((80 * S, 421 * S), "PV", font=font(22 * S), fill=(170, 170, 170, 255), anchor="lm")
    r = GaugeRender(rgba=_down(img), needle_mask=np.asarray(_down(lit_m)), setpoint_mask=None,
                    tick_mask=np.zeros((CANON, CANON), np.uint8), major_tick_mask=np.zeros((CANON, CANON), np.uint8),
                    center=(300, 300), radius=240, labels=[LabelInfo(0, "unit", 520, 421, 30)], kind="digital")
    r.cells = seg_info
    r.bg_point = (70, 382)
    return r


def cv_read_digital(render: GaugeRender) -> str:
    """Decode the display from luminance at segment centres (works for dark-on-light and light-on-dark)."""
    rgb = np.asarray(render.rgba.convert("RGB")).astype(np.float32)
    L = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114

    def lum(p):
        x, y = int(round(p[0])), int(round(p[1]))
        return float(L[y - 1:y + 2, x - 1:x + 2].mean())
    samples = [lum(p) for c in render.cells for p in c.values()]
    bg = lum(render.bg_point)
    far = max(samples, key=lambda v: abs(v - bg))                # lit segments differ most from background
    thr = (far + bg) / 2
    lit = (lambda v: v < thr) if far < bg else (lambda v: v > thr)
    out = ""
    for c in render.cells:
        on = "".join(sorted(k for k, p in c.items() if k != "dp" and lit(lum(p))))
        if on == "":
            ch = " "
        elif on in DECODE:
            ch = DECODE[on]
        else:
            raise V.ReadError(f"unknown segment pattern {on}")
        out += ch
        if lit(lum(c["dp"])):
            out += "."
    return out.strip()


def ann_h(ann: str) -> float:
    """Smallest text the reader must resolve: the multiplier annunciator if lit, else the unit."""
    return 18.0 if ann else 30.0


def build_digital_display(rng, factors):
    decimals = int(rng.choice([0, 1, 1, 2, 2, 3]))
    mag = float(rng.choice([10, 100, 1000, 10000]))
    v = float(rng.uniform(0, mag))
    if rng.random() < 0.18:
        v = -v
    text = f"{v:.{decimals}f}"
    if len(text.replace(".", "").replace("-", "")) > 5:
        raise Reject("too many digits for the display")
    style = "lcd" if factors["face"] == "light" else str(rng.choice(["led", "vfd"]))
    mult_key = factors["multiplier"] if factors["multiplier"] in ("x1", "x10", "x100") else "x1"
    ann = {"x1": "", "x10": "×10", "x100": "×100"}[mult_key]
    factors["multiplier"] = mult_key
    for k in ("scale_kind", "sweep", "minors_per_major", "label_every"):
        factors[k] = {"scale_kind": "linear", "sweep": "270", "minors_per_major": 5, "label_every": 1}[k]
    unit = str(rng.choice(["bar", "kPa", "°C", "m³/h", "rpm", "A", "V"]))
    r = render_digital(text, unit, style, ann)
    scene = build_scene(rng, [r], [""], "single", photo_from_factors(factors))
    m = MULTIPLIERS[mult_key]
    tol = 0.5 * 10 ** (-decimals) * m
    answer = _round_for(tol, float(text) * m)
    q = (f"This is a digital panel meter. What value does it show, in {unit}? Take into account everything shown "
         f"on the display. " + ANSWER_FORMAT_NUM)
    t = Task("", "digital_display", q, answer, "number", tol, unit=unit,
             meta={"display": text, "style": style, "annunciator": ann, "range": [-mag * m, mag * m]})
    try:
        read = cv_read_digital(r)
        reread = V.Check("pixel_reread_digits", read == text, f"cv='{read}' key='{text}'")
    except V.ReadError as e:
        reread = V.Check("pixel_reread_digits", False, f"reader failed: {e}")
    checks = [reread] + V.check_needle_visible(scene, 0) + [_label_check(scene, 0, ann_h(ann))]
    return t, scene, checks


NEW_FAMILIES = {
    "dial_meter": build_dial_meter,
    "vernier": build_vernier,
    "digital_display": build_digital_display,
}
