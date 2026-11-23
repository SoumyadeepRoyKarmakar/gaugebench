"""Tank level sight-glass: a vertical glass tube showing the liquid, with a
printed linear scale beside it. A second instrument geometry (linear, vertical)
next to the round dials, with its own evidence layers for validation.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from .render import CANON, SS, GaugeRender, LabelInfo, font
from .scales import fmt_value
from .spec import GaugeSpec

TUBE_X0, TUBE_X1 = 225, 295      # canonical px
Y_TOP, Y_BOT = 70, 530           # y of vmax and vmin on the scale
TICK_X0 = 305
MAJOR_X1, MINOR_X1 = 350, 330
LABEL_X = 362
LIQUIDS = {"water": (40, 110, 205), "oil": (205, 135, 30), "coolant": (40, 165, 95)}


def level_y(spec: GaugeSpec, v: float) -> float:
    return Y_BOT - spec.scale.fraction(v) * (Y_BOT - Y_TOP)


def render_level(spec: GaugeSpec, liquid: str = "water") -> GaugeRender:
    W = CANON * SS
    s = SS
    dark = spec.face == "dark"
    plate = (36, 38, 42) if dark else (238, 237, 230)
    ink = (240, 240, 240) if dark else (20, 20, 22)
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ticks_m, major_m = Image.new("L", (W, W), 0), Image.new("L", (W, W), 0)
    dt, dm = ImageDraw.Draw(ticks_m), ImageDraw.Draw(major_m)
    liquid_m, meniscus_m = Image.new("L", (W, W), 0), Image.new("L", (W, W), 0)

    # back plate, frame and glass
    d.rounded_rectangle([150 * s, 20 * s, 470 * s, 580 * s], 18 * s, fill=(110, 113, 118, 255))
    d.rounded_rectangle([160 * s, 30 * s, 460 * s, 570 * s], 14 * s, fill=plate + (255,))
    d.rectangle([(TUBE_X0 - 12) * s, (Y_TOP - 30) * s, (TUBE_X1 + 12) * s, (Y_BOT + 30) * s], fill=(90, 92, 96, 255))
    d.rectangle([TUBE_X0 * s, (Y_TOP - 20) * s, TUBE_X1 * s, (Y_BOT + 20) * s], fill=(214, 222, 228, 255))

    # liquid column up to the level
    y_lv = level_y(spec, spec.value)
    col = LIQUIDS[liquid]
    box = [TUBE_X0 * s, y_lv * s, TUBE_X1 * s, (Y_BOT + 20) * s]
    d.rectangle(box, fill=col + (255,))
    ImageDraw.Draw(liquid_m).rectangle(box, fill=255)
    men = [TUBE_X0 * s, (y_lv - 1.5) * s, TUBE_X1 * s, (y_lv + 2.5) * s]
    d.rectangle(men, fill=tuple(int(c * 0.55) for c in col) + (255,))      # darker meniscus line
    ImageDraw.Draw(meniscus_m).rectangle(men, fill=255)
    # glass highlight (cosmetic, drawn over everything in the tube)
    hl = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rectangle([(TUBE_X0 + 8) * s, (Y_TOP - 20) * s, (TUBE_X0 + 16) * s, (Y_BOT + 20) * s],
                                 fill=(255, 255, 255, 70))
    img.alpha_composite(hl)

    # scale
    labels = []
    lpx = 34
    f_lbl = font(lpx * s)
    for t in spec.scale.ticks:
        y = level_y(spec, t.value) * s
        x1 = (MAJOR_X1 if t.major else MINOR_X1) * s
        w = (5 if t.major else 3) * s
        d.line([(TICK_X0 * s, y), (x1, y)], fill=ink + (255,), width=w)
        dt.line([(TICK_X0 * s, y), (x1, y)], fill=255, width=w)
        if t.major:
            dm.line([(TICK_X0 * s, y), (x1, y)], fill=255, width=w)
        if t.labeled:
            txt = fmt_value(t.value)
            d.text((LABEL_X * s, y), txt, font=f_lbl, fill=ink + (255,), anchor="lm")
            labels.append(LabelInfo(t.value, txt, LABEL_X + 15, y / s, lpx))
    d.text((195 * s, 300 * s), spec.unit, font=font(36 * s), fill=ink + (255,), anchor="mm")

    def down(im):
        return im.resize((CANON, CANON), Image.LANCZOS)

    return GaugeRender(
        rgba=down(img), needle_mask=np.asarray(down(meniscus_m)), setpoint_mask=None,
        tick_mask=np.asarray(down(ticks_m)), major_tick_mask=np.asarray(down(major_m)),
        center=(CANON / 2, CANON / 2), radius=CANON * 0.4, labels=labels,
        needle_angle=0.0, kind="level", liquid_mask=np.asarray(down(liquid_m)),
    )
