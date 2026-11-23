"""Draw a single analogue gauge in a canonical (un-photographed) frame.

Besides the RGBA picture we return *evidence layers*: separate masks for the
needle(s) and the tick marks, plus the positions of every printed label. The
validator uses these pixel layers to re-read the gauge independently.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .scales import fmt_value
from .spec import GaugeSpec

CANON = 600          # canonical gauge image size (px)
SS = 2               # supersampling factor for anti-aliasing
R_FRAC = 0.40        # face radius as a fraction of CANON

# Radii as fractions of the face radius R
R_BAND_OUT, R_BAND_IN = 0.95, 0.87
R_TICK_OUT = 0.95
R_MAJOR_IN = 0.78
R_MINOR_IN = 0.87
R_LABEL = 0.64
R_NEEDLE_TIP = 0.90
R_NEEDLE_TAIL = 0.20
# inner secondary scale (dual-scale dials)
R_SEC_OUT = 0.565
R_SEC_MAJOR_IN = 0.47
R_SEC_MINOR_IN = 0.52
R_SEC_LABEL = 0.395

ZONE_COLORS = {"normal": (46, 160, 67), "warning": (235, 180, 30), "danger": (210, 40, 40)}

FONT_CANDIDATES = [
    "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


@lru_cache(maxsize=64)
def font(px: int) -> ImageFont.FreeTypeFont:
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default(size=px)


def polar(cx: float, cy: float, r: float, angle_deg: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return cx + r * math.sin(a), cy - r * math.cos(a)


@dataclass
class LabelInfo:
    value: float      # scale value printed (before multiplier)
    text: str
    x: float
    y: float
    height_px: float


@dataclass
class GaugeRender:
    rgba: Image.Image
    needle_mask: np.ndarray            # uint8, CANON x CANON
    setpoint_mask: np.ndarray | None
    tick_mask: np.ndarray              # uint8 — all tick marks
    major_tick_mask: np.ndarray        # uint8 — major ticks only (they reach further in)
    center: tuple[float, float]
    radius: float
    labels: list[LabelInfo] = field(default_factory=list)
    multiplier_text: str = ""
    needle_angle: float = 0.0
    setpoint_angle: float | None = None
    # inner secondary scale (dual-scale dials)
    sec_tick_mask: np.ndarray | None = None
    sec_major_tick_mask: np.ndarray | None = None
    sec_labels: list[LabelInfo] = field(default_factory=list)
    kind: str = "dial"                  # dial | level
    liquid_mask: np.ndarray | None = None  # level sight-glass only


def _needle_polygon(cx, cy, R, angle, tip_w, base_w, tail_w):
    tip = polar(cx, cy, R * R_NEEDLE_TIP, angle)
    tail = polar(cx, cy, -R * R_NEEDLE_TAIL, angle)
    left = polar(cx, cy, base_w * R, angle - 90)
    right = polar(cx, cy, base_w * R, angle + 90)
    tl = (tail[0] + (left[0] - cx) * tail_w / base_w, tail[1] + (left[1] - cy) * tail_w / base_w)
    tr = (tail[0] + (right[0] - cx) * tail_w / base_w, tail[1] + (right[1] - cy) * tail_w / base_w)
    tip_l = polar(tip[0], tip[1], tip_w * R, angle - 90)
    tip_r = polar(tip[0], tip[1], tip_w * R, angle + 90)
    return [tip_l, tip_r, right, tr, tl, left]


def render_gauge(spec: GaugeSpec) -> GaugeRender:
    W = CANON * SS
    R = CANON * R_FRAC * SS
    cx = cy = W / 2
    dark = spec.face == "dark"
    face_rgb = (28, 30, 34) if dark else (246, 245, 239)
    ink = (240, 240, 240) if dark else (20, 20, 22)
    needle_rgb = (250, 250, 250) if dark else (15, 15, 15)

    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ticks_m = Image.new("L", (W, W), 0)
    dt = ImageDraw.Draw(ticks_m)
    major_m = Image.new("L", (W, W), 0)
    dm = ImageDraw.Draw(major_m)

    # bezel + face
    for k, col in [(1.13, (70, 72, 76)), (1.10, (175, 178, 182)), (1.05, (120, 123, 128)), (1.02, (60, 62, 66))]:
        d.ellipse([cx - R * k, cy - R * k, cx + R * k, cy + R * k], fill=col + (255,))
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=face_rgb + (255,))

    sc = spec.scale

    # coloured zone bands
    for z in spec.zones:
        a0, a1 = sc.angle(z.lo), sc.angle(z.hi)
        bbox = [cx - R * R_BAND_OUT, cy - R * R_BAND_OUT, cx + R * R_BAND_OUT, cy + R * R_BAND_OUT]
        d.arc(bbox, a0 - 90, a1 - 90, fill=ZONE_COLORS[z.name] + (255,),
              width=int(R * (R_BAND_OUT - R_BAND_IN)))

    # ticks
    labels: list[LabelInfo] = []
    lbl_px = int(R * 0.115)
    f_lbl = font(lbl_px)
    for t in sc.ticks:
        a = sc.angle(t.value)
        r_in = R_MAJOR_IN if t.major else R_MINOR_IN
        w = max(2, int(R * (0.020 if t.major else 0.009)))
        p0 = polar(cx, cy, R * R_TICK_OUT, a)
        p1 = polar(cx, cy, R * r_in, a)
        d.line([p0, p1], fill=ink + (255,), width=w)
        dt.line([p0, p1], fill=255, width=w)
        if t.major:
            dm.line([p0, p1], fill=255, width=w)
        if t.labeled:
            txt = fmt_value(t.value)
            lx, ly = polar(cx, cy, R * R_LABEL, a)
            d.text((lx, ly), txt, font=f_lbl, fill=ink + (255,), anchor="mm")
            labels.append(LabelInfo(t.value, txt, lx / SS, ly / SS, lbl_px / SS))

    # optional inner secondary scale, printed in red (dual-scale dials, e.g. bar + psi)
    sec_ticks_m = sec_major_m = None
    sec_labels: list[LabelInfo] = []
    red = (255, 110, 90) if dark else (200, 35, 35)
    if spec.secondary is not None:
        sec_ticks_m = Image.new("L", (W, W), 0)
        sec_major_m = Image.new("L", (W, W), 0)
        st, sm = ImageDraw.Draw(sec_ticks_m), ImageDraw.Draw(sec_major_m)
        s2 = spec.secondary
        f2px = int(R * 0.085)
        for t in s2.ticks:
            a = s2.angle(t.value)
            r_in = R_SEC_MAJOR_IN if t.major else R_SEC_MINOR_IN
            w = max(2, int(R * (0.016 if t.major else 0.008)))
            p0, p1 = polar(cx, cy, R * R_SEC_OUT, a), polar(cx, cy, R * r_in, a)
            d.line([p0, p1], fill=red + (255,), width=w)
            st.line([p0, p1], fill=255, width=w)
            if t.major:
                sm.line([p0, p1], fill=255, width=w)
            if t.labeled:
                txt = fmt_value(t.value)
                lx, ly = polar(cx, cy, R * R_SEC_LABEL, a)
                d.text((lx, ly), txt, font=font(f2px), fill=red + (255,), anchor="mm")
                sec_labels.append(LabelInfo(t.value, txt, lx / SS, ly / SS, f2px / SS))

    # unit + multiplier text
    unit_px = int(R * 0.10)
    if spec.secondary is not None:
        d.text((cx, cy + R * 0.30), spec.unit, font=font(unit_px), fill=ink + (255,), anchor="mm")
        d.text((cx, cy + R * 0.45), spec.secondary_unit, font=font(unit_px), fill=red + (255,), anchor="mm")
    else:
        d.text((cx, cy + R * 0.40), spec.unit, font=font(unit_px), fill=ink + (255,), anchor="mm")
    mult_text = ""
    if spec.multiplier != 1.0:
        mult_text = "×" + fmt_value(spec.multiplier)
        d.text((cx, cy + R * 0.56), mult_text, font=font(int(unit_px * 0.95)),
               fill=(200, 40, 40, 255) if not dark else (255, 120, 90, 255), anchor="mm")

    # set-point needle (thin red), drawn below the main needle
    sp_mask = None
    sp_angle = None
    if spec.setpoint is not None:
        sp_angle = sc.angle(spec.setpoint)
        sp_layer = Image.new("L", (W, W), 0)
        poly = _needle_polygon(cx, cy, R, sp_angle, 0.004, 0.018, 0.012)
        ImageDraw.Draw(sp_layer).polygon(poly, fill=255)
        img.paste(Image.new("RGBA", (W, W), (215, 30, 30, 255)), (0, 0), sp_layer)
        sp_mask = sp_layer

    # main needle
    n_angle = sc.angle(spec.value)
    n_layer = Image.new("L", (W, W), 0)
    poly = _needle_polygon(cx, cy, R, n_angle, 0.006, 0.032, 0.022)
    ImageDraw.Draw(n_layer).polygon(poly, fill=255)
    img.paste(Image.new("RGBA", (W, W), needle_rgb + (255,)), (0, 0), n_layer)

    # hub (cosmetic, not part of the needle mask)
    hr = R * 0.075
    d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=(90, 92, 96, 255))
    d.ellipse([cx - hr * 0.5, cy - hr * 0.5, cx + hr * 0.5, cy + hr * 0.5], fill=(40, 40, 44, 255))

    def down(im: Image.Image) -> Image.Image:
        return im.resize((CANON, CANON), Image.LANCZOS)

    return GaugeRender(
        rgba=down(img),
        needle_mask=np.asarray(down(n_layer)),
        setpoint_mask=np.asarray(down(sp_mask)) if sp_mask is not None else None,
        tick_mask=np.asarray(down(ticks_m)),
        major_tick_mask=np.asarray(down(major_m)),
        center=(CANON / 2, CANON / 2),
        radius=CANON * R_FRAC,
        labels=labels,
        multiplier_text=mult_text,
        needle_angle=n_angle,
        setpoint_angle=sp_angle,
        sec_tick_mask=np.asarray(down(sec_ticks_m)) if sec_ticks_m is not None else None,
        sec_major_tick_mask=np.asarray(down(sec_major_m)) if sec_major_m is not None else None,
        sec_labels=sec_labels,
    )
