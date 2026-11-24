"""Inspection round: a job, not a single question.

A technician's shift round, compressed into one task. The model sees photos from
4-6 plant cameras (each its own gauge, range, unit and camera conditions), must
log the reading of every gauge, and must flag every gauge whose needle is in its
red danger band. Some rounds have no alarms at all, so false alarms are measured
as well as missed ones.

Every camera photo goes through the same validation as a single-dial task
(independent pixel re-read, glare/contrast/legibility checks, and a margin
from the danger boundary), so the full answer sheet is known to be readable.

Answer format the model must end with:

    ANSWER: PI-301=4.2; PI-305=120; TI-312=-15 | ALARMS: PI-305

(`ALARMS: none` when nothing is in the red.) Scoring gives per-reading credit,
alarm recall and false alarms; the task counts as correct only for a perfect
round, because that is what a plant needs.
"""
from __future__ import annotations

import re

import numpy as np
from PIL import Image, ImageDraw

from . import validate as V
from .render import font, render_gauge
from .scene import Scene, build_scene
from .spec import PhotoSpec, make_zones, sample_gauge

FAMILY = "inspection_round"
COLS = 3
CAPTION_H = 46
GAP = 16
SHEET_BG = (34, 37, 42)
CAMERA_ATTEMPTS = 12

ROUND_FORMAT = ("Respond with your reasoning if you like, then finish with a final line exactly of the form "
                "'ANSWER: <tag>=<reading>; <tag>=<reading>; ... | ALARMS: <tag>, <tag>' giving every gauge's "
                "reading as a number in its own unit, and 'ALARMS: none' if no gauge is in the red.")


def _camera_photo(rng: np.random.Generator, factors: dict) -> PhotoSpec:
    """Each camera has its own conditions, up to the round's difficulty."""
    return PhotoSpec(glare=int(rng.integers(0, factors["glare"] + 1)),
                     tilt=float(rng.uniform(0, factors["tilt"])) if factors["tilt"] else 0.0,
                     blur=float(rng.uniform(0, factors["blur"])) if factors["blur"] else 0.0,
                     noise=float(rng.uniform(0, factors["noise"])) if factors["noise"] else 0.0,
                     lighting=float(rng.uniform(factors["lighting"], 1.0)))


DIAL_MIX = {        # a plant round passes many kinds of dial; each camera gets its own
    "scale_kind": (["linear", "offset", "sqrt", "log"], [0.55, 0.2, 0.15, 0.1]),
    "sweep": (["270", "180", "90"], [0.7, 0.2, 0.1]),
    "minors_per_major": ([2, 5, 10], [0.3, 0.5, 0.2]),
    "label_every": ([1, 2], [0.75, 0.25]),
    "face": (["light", "dark"], [0.75, 0.25]),
    "multiplier": (["x1", "x10", "x100", "x0.1"], [0.75, 0.1, 0.05, 0.1]),
}


def _camera_dial(rng: np.random.Generator, factors: dict) -> dict:
    f = dict(factors)
    for k, (vals, w) in DIAL_MIX.items():
        f[k] = vals[int(rng.choice(len(vals), p=w))]
    return f


def _contact_sheet(scenes: list[Scene], captions: list[str]) -> Scene:
    """Tile the camera photos into one monitoring-screen image (and carry the
    evidence masks along, so 'validator vision' still works)."""
    th, tw = scenes[0].image.shape[:2]
    n = len(scenes)
    rows = (n + COLS - 1) // COLS
    W = COLS * tw + (COLS + 1) * GAP
    H = rows * (th + CAPTION_H) + (rows + 1) * GAP
    sheet = Image.new("RGB", (W, H), SHEET_BG)
    d = ImageDraw.Draw(sheet)
    glare = np.zeros((H, W), np.float32)
    needles, setpoints, renders, places = [], [], [], []
    f = font(24)
    for i, (sc, cap) in enumerate(zip(scenes, captions)):
        x = GAP + (i % COLS) * (tw + GAP)
        y = GAP + (i // COLS) * (th + CAPTION_H + GAP)
        d.rectangle([x, y, x + tw - 1, y + CAPTION_H - 4], fill=(18, 20, 24))
        d.ellipse([x + 12, y + 15, x + 24, y + 27], fill=(220, 50, 50))          # recording dot
        d.text((x + 34, y + 8), cap, font=f, fill=(235, 235, 230))
        oy = y + CAPTION_H
        sheet.paste(Image.fromarray(sc.image), (x, oy))
        glare[oy:oy + th, x:x + tw] = sc.glare_alpha
        m = np.zeros((H, W), np.float32)
        m[oy:oy + th, x:x + tw] = sc.needle_masks[0]
        needles.append(m)
        setpoints.append(None)
        renders.append(sc.renders[0])
        places.append(sc.placements[0])
    return Scene(np.asarray(sheet), renders, places, needles, setpoints, glare, np.eye(3), captions)


def build_inspection_round(rng, factors):
    from .tasks import Reject, Task, _round_for, _tags          # late import: tasks registers this family

    n = int(rng.integers(4, 7))
    tags = _tags(rng, n)
    n_alarm = int(rng.choice([0, 1, 1, 2, 2, 3]))
    alarm_idx = set(rng.choice(n, size=min(n_alarm, n - 1), replace=False).tolist()) if n_alarm else set()

    gauges, scenes, checks, margins, retries = [], [], [], [], {}
    for i in range(n):
        # A camera whose photo fails any check is re-shot (new gauge, new conditions); every published
        # camera passes the full single-dial validation. Retries are recorded in the task's meta.
        for attempt in range(CAMERA_ATTEMPTS):
            g = sample_gauge(rng, _camera_dial(rng, factors), tags[i])
            g.zones = make_zones(rng, g.scale, high_alarm=bool(rng.integers(0, 4)))
            if not g.zones:
                continue
            danger = [z for z in g.zones if z.name == "danger"][0]
            safe = [z for z in g.zones if z.name != "danger"]
            z = danger if i in alarm_idx else safe[int(rng.integers(0, len(safe)))]
            g.value = float(g.scale.value_at_fraction(rng.uniform(g.scale.fraction(z.lo), g.scale.fraction(z.hi))))
            ang = g.scale.angle(g.value)
            margin = min(abs(ang - g.scale.angle(b)) for b in (danger.lo, danger.hi))
            sc = build_scene(rng, [render_gauge(g)], [""], "single", _camera_photo(rng, factors))
            cam = [V.check_reading(sc.renders[0], g.value, g.scale.reading_tolerance(g.value))]
            cam += V.check_needle_visible(sc, 0) + V.check_legibility(sc, 0)
            cam.append(V.margin_check("needle_clear_of_danger_boundary", margin, 3.0, "deg"))
            failed = [c.name for c in cam if not c.passed]
            if not failed:
                break
            for name in failed:
                retries[name] = retries.get(name, 0) + 1
        else:
            raise Reject(f"camera {i + 1} unreadable after {CAMERA_ATTEMPTS} shots")
        for c in cam:                                      # keep the camera in the evidence; names stay
            c.detail = f"CAM {i + 1}: {c.detail}"          # standard so redaction/report logic still applies
        checks += cam
        margins.append(margin)
        gauges.append(g)
        scenes.append(sc)
    checks.append(V.margin_check("all_needles_clear_of_danger_boundary", min(margins), 3.0, "deg"))

    captions = [f"CAM {i + 1}  ·  {t}" for i, t in enumerate(tags)]
    sheet = _contact_sheet(scenes, captions)
    readings, tols = {}, {}
    for g in gauges:
        tol = g.scale.reading_tolerance(g.value) * g.multiplier
        readings[g.tag] = _round_for(tol, g.true_reading)
        tols[g.tag] = float(f"{tol:.6g}")
    alarms = [tags[i] for i in sorted(alarm_idx)]
    q = (f"These are photos from {n} cameras on a plant inspection round, each labelled with its camera number and "
         f"gauge tag ({', '.join(tags)}). Each gauge has its own range, unit and coloured bands (green = normal, "
         f"yellow = warning, red = danger). Log the reading of every gauge in its own unit, taking into account "
         f"everything printed on the dial, then list every gauge whose needle is in its red danger band. "
         + ROUND_FORMAT)
    t = Task("", FAMILY, q, {"readings": readings, "alarms": alarms}, "round", None,
             gauges=[g.to_dict() for g in gauges],
             meta={"n_gauges": n, "tolerances": tols, "camera_retries": retries,
                   "cameras": [{"tag": g.tag, "unit": g.unit} for g in gauges]})
    return t, sheet, checks


# ---------------------------------------------------------------------------------------
# answer format and scoring
# ---------------------------------------------------------------------------------------
PAIR_RE = re.compile(r"([A-Za-z]{1,4}\s*-?\s*\d{2,4})\s*[=:]\s*([-−+]?\d[\d,]*(?:\.\d+)?|[-−+]?\.\d+)")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def format_answer(readings: dict, alarms: list) -> str:
    pairs = "; ".join(f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v}" for k, v in readings.items())
    return f"{pairs} | ALARMS: {', '.join(alarms) if alarms else 'none'}"


def parse_round(text: str, tags: list[str]) -> dict | None:
    """Readings and alarms from the text after the last 'ANSWER:' (may span lines)."""
    parts = re.split(r"ANSWER\s*[:：]", text or "", flags=re.IGNORECASE)
    if len(parts) < 2:
        return None
    seg = parts[-1].replace("**", "")
    by_norm = {_norm(t): t for t in tags}
    m = re.search(r"ALARMS?\s*[:：]?(.*)", seg, flags=re.IGNORECASE | re.DOTALL)
    reading_part = seg[:m.start()] if m else seg
    readings = {}
    for tag, num in PAIR_RE.findall(reading_part):
        k = by_norm.get(_norm(tag))
        if k and k not in readings:
            try:
                readings[k] = float(num.replace("−", "-").replace(",", ""))
            except ValueError:
                pass
    alarms = []
    if m:
        for tok in re.findall(r"[A-Za-z]{1,4}\s*-?\s*\d{2,4}", m.group(1)):
            k = by_norm.get(_norm(tok))
            if k and k not in alarms:
                alarms.append(k)
    if not readings and not m:
        return None
    return {"readings": readings, "alarms": alarms}


def score_round(task: dict, text: str) -> dict:
    key = task["answer"]
    tags = list(key["readings"])
    tols = task["meta"]["tolerances"]
    p = parse_round(text, tags)
    empty = {"parsed": None, "correct": False, "parse_ok": False, "abs_err": None, "err_tol_units": None,
             "round": {"readings_correct": 0, "readings_total": len(tags), "per_gauge": {},
                       "alarms_caught": [], "alarms_missed": list(key["alarms"]), "false_alarms": []}}
    if p is None:
        return empty
    per = {}
    for t in tags:
        v = p["readings"].get(t)
        err = None if v is None else abs(v - float(key["readings"][t]))
        per[t] = {"given": v, "key": key["readings"][t], "tolerance": tols[t],
                  "correct": err is not None and err <= tols[t] + 1e-9,
                  "err_tol_units": None if err is None or not tols[t] else err / tols[t]}
    want, got = set(key["alarms"]), set(p["alarms"])
    ok = sum(x["correct"] for x in per.values())
    rnd = {"readings_correct": ok, "readings_total": len(tags), "per_gauge": per,
           "alarms_caught": sorted(want & got), "alarms_missed": sorted(want - got), "false_alarms": sorted(got - want)}
    return {"parsed": format_answer({t: x["given"] for t, x in per.items() if x["given"] is not None}, p["alarms"]),
            "correct": ok == len(tags) and want == got, "parse_ok": True, "abs_err": None, "err_tol_units": None,
            "round": rnd}
