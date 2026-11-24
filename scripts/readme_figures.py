"""Builds the figures used in README.md (docs/images/readme-*.png).

    python scripts/readme_figures.py

Re-run after a new evaluation so the results chart matches the data.
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "images"

INK = (24, 28, 36)
MUTED = (96, 104, 118)
LINE = (222, 226, 232)
BG = (252, 252, 251)
CARD = (255, 255, 255)
BLUE = (0x3F, 0x72, 0xB8)        # validated palette (dataviz validator, light surface)
ORANGE = (0xD9, 0x65, 0x0F)
NAVY = (11, 46, 92)


def font(px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold
             else ["arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, px)
        except OSError:
            pass
    return ImageFont.load_default(size=px)


def fit(im: Image.Image, w: int, h: int, bg=(238, 240, 243)) -> Image.Image:
    """Letterbox an image into w x h."""
    im = im.convert("RGB")
    im.thumbnail((w, h), Image.LANCZOS)
    out = Image.new("RGB", (w, h), bg)
    out.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return out


def wrap(draw: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=f) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fmt_key(t: dict) -> str:
    a = t["answer"]
    if t["answer_type"] == "number":
        a = f"{a:g}"
    unit = f" {t['unit']}" if t.get("unit") and t["answer_type"] == "number" else ""
    return f"{a}{unit}"


# ------------------------------------------------------------------------------- gallery
GALLERY = [
    ("sample", "read_value-L2-0001", "Read the value", "Exact reading, incl. log/√ scales and ×10 multipliers"),
    ("sample", "zone_status-L3-0002", "Zone status", "Is the needle tip in the green, yellow or red band?"),
    ("sample", "setpoint_deviation-L2-0001", "Set-point deviation", "Read two needles and subtract"),
    ("sample", "dual_scale-L2-0001", "Dual scale", "Pick the right ring; the other is a distractor"),
    ("sample", "panel_alarm-L2-0001", "Panel alarm", "Which gauge on the panel is in its red zone?"),
    ("sample", "panel_max-L2-0001", "Panel max", "Highest value when every dial has a different range"),
    ("sample", "panel_count-L2-0001", "Panel count", "How many dials are outside their green band?"),
    ("sample", "temporal_change-L2-0001", "Change over time", "Same dial, two photos: how much did it change?"),
    ("sample", "level_reading-L2-0001", "Tank level", "Read a vertical sight-glass"),
    ("instruments", "dial_meter-L2-0001", "Clock-dial meter", "4–5 dials turning in alternating directions"),
    ("instruments", "vernier-L2-0001", "Vernier caliper", "Find the one vernier line that aligns"),
    ("instruments", "digital_display-L2-0001", "Digital display", "7-segment LCD/LED with a ×10 indicator (the control)"),
]


def gallery() -> Path:
    cols, tw, th, cap = 4, 380, 300, 92
    pad = 18
    rows = (len(GALLERY) + cols - 1) // cols
    W = cols * tw + (cols + 1) * pad
    H = rows * (th + cap) + (rows + 1) * pad
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ft, fs, fk = font(21, True), font(15), font(15, True)
    for i, (suite, tid, title, desc) in enumerate(GALLERY):
        p = ROOT / "runs" / suite / "tasks" / tid
        t = json.loads((p / "task.json").read_text(encoding="utf-8"))
        x = pad + (i % cols) * (tw + pad)
        y = pad + (i // cols) * (th + cap + pad)
        d.rounded_rectangle([x - 1, y - 1, x + tw, y + th + cap], 12, fill=CARD, outline=LINE)
        tile = fit(Image.open(p / "image.png"), tw - 16, th - 16)
        img.paste(tile, (x + 8, y + 8))
        d.text((x + 14, y + th + 6), title, font=ft, fill=NAVY)
        d.text((x + 14, y + th + 34), wrap(d, desc, fs, tw - 28)[0], font=fs, fill=MUTED)
        key = f"Answer key: {fmt_key(t)}"
        d.text((x + 14, y + th + 60), key, font=fk, fill=ORANGE)
    out = OUT / "readme-gallery.png"
    img.save(out, optimize=True)
    return out


# ------------------------------------------------------------------------------- conditions
CONDITIONS = [
    ("sweep-glare-0-000", "Clean"), ("sweep-glare-2-000", "Strong glare"), ("sweep-tilt-40-000", "Camera tilt 40°"),
    ("sweep-blur-2.0-000", "Blur 2 px"), ("sweep-lighting-0.45-000", "Under-exposed"),
    ("sweep-scale_kind-log-000", "Log scale"), ("sweep-multiplier-x100-000", "×100 multiplier"),
    ("sweep-face-dark-000", "Dark face"),
]


def conditions() -> Path:
    n, tw, th, cap, pad = len(CONDITIONS), 230, 230, 40, 12
    W = n * tw + (n + 1) * pad
    H = th + cap + 2 * pad
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f = font(17, True)
    for i, (tid, label) in enumerate(CONDITIONS):
        x = pad + i * (tw + pad)
        tile = fit(Image.open(ROOT / "runs" / "sample" / "tasks" / tid / "image.png"), tw, th)
        img.paste(tile, (x, pad))
        w = d.textlength(label, font=f)
        d.text((x + (tw - w) / 2, pad + th + 10), label, font=f, fill=INK)
    out = OUT / "readme-conditions.png"
    img.save(out, optimize=True)
    return out


# ------------------------------------------------------------------------------- validator
def _decode(data_url: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1])))


def validator() -> Path:
    from gaugebench.app import make_live_task
    from gaugebench.spec import BASE_FACTORS
    rec = None
    for seed in range(200, 400):               # find a task whose factory floor shows a rejected photo
        r = make_live_task("read_value", {**BASE_FACTORS, "glare": 2, "tilt": 15}, seed)
        if any(x.get("thumb") for x in r["rejected"]):
            rec = r
            break
    rej = next(x for x in rec["rejected"] if x.get("thumb"))
    plain = {"needle_not_glared": "glare hides the needle", "labels_do_not_overlap": "printed numbers overlap",
             "tick_divisions_resolvable": "tick marks too close together", "labels_legible": "numbers too small",
             "needle_clear_of_zone_boundary": "needle sits on a zone edge"}
    name = rej["reasons"][0]["name"]
    reason = plain.get(name, name.replace("_", " "))
    panels = [(_decode(rec["image"]), "1. The photo the model sees", "Glare, tilt and a scale to read"),
              (_decode(rec["vision"]), "2. What the validator measured", "Needle pixels in orange, glare in cyan"),
              (_decode(rej["thumb"]), "3. A candidate it threw away", f"Rejected: {reason}")]
    tw, th, cap, pad = 420, 420, 70, 18
    W = 3 * tw + 4 * pad
    H = th + cap + 2 * pad
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for i, (im, title, sub) in enumerate(panels):
        x = pad + i * (tw + pad)
        img.paste(fit(im, tw, th, bg=(30, 32, 36)), (x, pad))
        d.text((x + 4, pad + th + 10), title, font=font(19, True), fill=NAVY)
        d.text((x + 4, pad + th + 38), sub, font=font(16), fill=ORANGE if i == 2 else MUTED)
    out = OUT / "readme-validator.png"
    img.save(out, optimize=True)
    return out


# ------------------------------------------------------------------------------- results
LABELS = {
    "zone_status": "Zone status", "panel_max": "Panel max (mixed ranges)", "panel_alarm": "Panel alarm",
    "setpoint_deviation": "Set-point deviation", "panel_count": "Panel count", "dual_scale": "Dual scale",
    "level_reading": "Tank level", "temporal_change": "Change over time", "read_value": "Read the exact value",
    "dial_meter": "Clock-dial meter", "vernier": "Vernier caliper", "digital_display": "Digital display",
}


def results(suite: str = "v2", model: str = "gemini-3.5-flash-lite") -> Path:
    tasks = {}
    for line in (ROOT / "runs" / suite / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        t = json.loads(line)
        tasks[t["id"]] = t
    rows = [json.loads(l) for l in (ROOT / "runs" / suite / "results" / f"{model}.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if not r.get("error") and r["id"] in tasks]
    fam: dict[str, list[bool]] = {}
    for r in rows:
        fam.setdefault(tasks[r["id"]]["family"], []).append(bool(r["correct"]))
    data = sorted(((LABELS.get(f, f), sum(v) / len(v), len(v), f) for f, v in fam.items()), key=lambda x: -x[1])
    overall = sum(r["correct"] for r in rows) / len(rows)

    S = 2                                       # draw at 2x for crisp text on retina screens
    lab_w, bar_w, row_h, top, gap = 300 * S, 640 * S, 38 * S, 96 * S, 10 * S
    W = lab_w + bar_w + 120 * S
    H = top + (len(data) + 1) * row_h + gap + 70 * S
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((24 * S, 20 * S), f"Gemini 3.5 Flash-Lite: accuracy by skill", font=font(26 * S, True), fill=INK)
    d.text((24 * S, 56 * S), f"{len(rows)} of {len(tasks)} tasks answered · answer counts as right only within "
           f"half a scale division", font=font(15 * S), fill=MUTED)
    x0 = lab_w
    for pct in (0, 0.25, 0.5, 0.75, 1.0):       # recessive gridlines
        gx = x0 + pct * bar_w
        d.line([gx, top - 8 * S, gx, top + len(data) * row_h], fill=LINE, width=S)
        tl = f"{int(pct * 100)}%"
        d.text((gx - d.textlength(tl, font=font(12 * S)) / 2, top + len(data) * row_h + 4 * S), tl,
               font=font(12 * S), fill=MUTED)

    def bar(i, label, value, n, color, bold=False, y_extra=0):
        y = top + i * row_h + y_extra
        f = font(15 * S, bold)
        lw = d.textlength(label, font=f)
        d.text((x0 - 14 * S - lw, y + 8 * S), label, font=f, fill=INK)
        h = row_h - 12 * S
        w = max(4 * S, value * bar_w)
        d.rounded_rectangle([x0, y + 4 * S, x0 + w, y + 4 * S + h], 4 * S, fill=color)
        d.rectangle([x0, y + 4 * S, x0 + 4 * S, y + 4 * S + h], fill=color)     # square at the baseline
        v = f"{value * 100:.0f}%"
        d.text((x0 + w + 8 * S, y + 8 * S), v, font=font(15 * S, True), fill=INK)
        d.text((x0 + w + 8 * S + d.textlength(v, font=font(15 * S, True)) + 6 * S, y + 10 * S), f"n={n}",
               font=font(12 * S), fill=MUTED)

    for i, (label, value, n, f) in enumerate(data):
        bar(i, label, value, n, ORANGE if f == "read_value" else BLUE, bold=f == "read_value")
    sep = top + len(data) * row_h + 22 * S
    bar(len(data), "Overall", overall, len(rows), NAVY, bold=True, y_extra=gap + 22 * S)
    out = OUT / "readme-results.png"
    img.save(out, optimize=True)
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (gallery, conditions, validator, results):
        print(fn())
