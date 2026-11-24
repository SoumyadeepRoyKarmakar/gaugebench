"""Build a self-contained HTML report for a suite: generation evidence, scorer
sanity checks, leaderboard, per-family accuracy, capability curves from the
single-factor sweeps, error-size analysis and a gallery of model failures."""
from __future__ import annotations

import html
import json
from collections import defaultdict
from pathlib import Path

from .evaluate import load_manifest
from .models.baselines import BASELINES
from .spec import FACTOR_DOMAINS

SERIES = ["var(--s1)", "var(--s2)", "var(--s3)"]
FACTOR_LABELS = {
    "scale_kind": "Scale type", "sweep": "Dial sweep (deg)", "minors_per_major": "Minor divisions per major",
    "label_every": "Label every Nth major", "multiplier": "Printed multiplier", "face": "Dial face",
    "glare": "Glare level", "tilt": "Camera tilt (deg)", "blur": "Blur (px)", "noise": "Sensor noise",
    "lighting": "Exposure gain",
}
FAMILY_LABELS = {
    "read_value": "Read value", "zone_status": "Zone status", "setpoint_deviation": "Set-point deviation",
    "panel_alarm": "Panel alarm", "panel_max": "Panel max (mixed ranges)", "temporal_change": "Change over time",
    "dual_scale": "Dual scale", "level_reading": "Tank level", "panel_count": "Panel count",
    "dial_meter": "Clock-dial meter", "vernier": "Vernier caliper", "digital_display": "Digital display",
    "inspection_round": "Inspection round",
}

CSS = """
:root{--bg:#fcfcfb;--card:#ffffff;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--grid:#e6e5e0;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--good:#008300;--bad:#e34948;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141413;--card:#1a1a19;--ink:#f0efec;
--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2b;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--good:#0ca30c;--bad:#e66767;color-scheme:dark}}
:root[data-theme=dark]{--bg:#141413;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2e2e2b;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--good:#0ca30c;--bad:#e66767;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}h1{font-size:28px;margin:0 0 4px}h2{font-size:20px;margin:40px 0 8px}
h3{font-size:15px;margin:0 0 6px;color:var(--ink2);font-weight:600}.sub{color:var(--ink2);margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--grid);border-radius:12px;padding:16px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
.tile b{display:block;font-size:28px;font-variant-numeric:tabular-nums}.tile span{color:var(--ink2);font-size:13px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:6px 8px;border-bottom:1px solid var(--grid);text-align:right}
th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600;font-size:13px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--ink2);margin:4px 0 8px}
.legend i{display:inline-block;width:12px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
svg text{fill:var(--ink2);font-size:11px}svg .ax{stroke:var(--grid)}.ok{color:var(--good)}.no{color:var(--bad)}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.gallery img{width:100%;border-radius:8px;display:block}.gallery p{margin:6px 0 0;font-size:13px;color:var(--ink2)}
.scroll{overflow-x:auto}code{font-size:13px}
"""


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.0f}%"


def _acc(rows: list[dict]) -> float | None:
    return sum(r["correct"] for r in rows) / len(rows) if rows else None


def _hbar(items: list[tuple[str, float, str]], maxv: float, color: str = "var(--s1)", fmt=lambda v: f"{v:.0f}") -> str:
    h, lw, w = 26, 200, 640
    out = [f'<svg viewBox="0 0 {w} {len(items) * h + 6}" width="100%" role="img">']
    for i, (label, v, tip) in enumerate(items):
        y = i * h + 4
        bw = 0 if maxv <= 0 else (w - lw - 60) * v / maxv
        out.append(f'<text x="0" y="{y + 15}">{html.escape(label)}</text>')
        out.append(f'<rect x="{lw}" y="{y + 3}" width="{max(bw, 1):.1f}" height="16" rx="4" fill="{color}">'
                   f'<title>{html.escape(tip)}</title></rect>')
        out.append(f'<text x="{lw + bw + 6:.1f}" y="{y + 15}">{fmt(v)}</text>')
    out.append("</svg>")
    return "".join(out)


def _curve(xlabels: list[str], series: list[tuple[str, list[float | None], str]], title: str) -> str:
    w, h, l, r, t, b = 340, 200, 38, 12, 10, 34
    pw, ph = w - l - r, h - t - b
    xs = [l + (pw * i / max(1, len(xlabels) - 1) if len(xlabels) > 1 else pw / 2) for i in range(len(xlabels))]
    out = [f'<div class="card"><h3>{html.escape(title)}</h3><svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    for v in (0, 0.5, 1.0):
        y = t + ph * (1 - v)
        out.append(f'<line class="ax" x1="{l}" x2="{w - r}" y1="{y}" y2="{y}"/><text x="{l - 6}" y="{y + 4}" text-anchor="end">{int(v * 100)}%</text>')
    for x, lab in zip(xs, xlabels):
        out.append(f'<text x="{x}" y="{h - 12}" text-anchor="middle">{html.escape(lab)}</text>')
    for name, vals, color in series:
        pts = [(x, t + ph * (1 - v)) for x, v in zip(xs, vals) if v is not None]
        if len(pts) > 1:
            out.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}"/>')
        for (x, y), v, lab in zip(pts, [v for v in vals if v is not None], [lb for lb, v in zip(xlabels, vals) if v is not None]):
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" stroke="var(--card)" stroke-width="2">'
                       f'<title>{html.escape(name)} · {html.escape(lab)}: {v * 100:.0f}%</title></circle>')
    out.append("</svg></div>")
    return "".join(out)


def build_report(suite: Path) -> Path:
    suite = Path(suite)
    tasks = {t["id"]: t for t in load_manifest(suite)}
    gen = json.loads((suite / "generation_log.json").read_text(encoding="utf-8"))
    results: dict[str, list[dict]] = {}
    for f in sorted((suite / "results").glob("*.jsonl")) if (suite / "results").exists() else []:
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows = [r for r in rows if r["id"] in tasks and not r.get("error")]
        if rows:
            results[rows[0]["model"]] = rows
    baselines = {k: v for k, v in results.items() if k in BASELINES}
    models = {k: v for k, v in results.items() if k not in BASELINES}
    colors = {m: SERIES[i % 3] for i, m in enumerate(models)}

    # pixel re-reader agreement, from each task's validation evidence
    rereads = []
    for tid in tasks:
        tj = json.loads((suite / "tasks" / tid / "task.json").read_text(encoding="utf-8"))
        for c in tj["validation"]:
            if c["name"].startswith("pixel_reread"):
                try:
                    parts = dict(p.split("=") for p in c["detail"].split())
                    rereads.append(float(parts["err"]) / float(parts["tol"]))
                except (ValueError, KeyError, ZeroDivisionError):
                    pass

    H = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>GaugeBench Report</title><style>{CSS}</style></head><body><main>",
         "<h1>GaugeBench report</h1>",
         f"<p class=sub>Suite <code>{html.escape(suite.name)}</code> · generator v{gen['generator_version']} · seed {gen['seed']}</p>"]

    # ---- generation evidence
    acc_rate = gen["published"] / gen["attempts"] if gen["attempts"] else 0
    H.append("<div class=tiles>")
    for val, lab in [(gen["published"], "tasks published"), (len(gen["families"]), "task families"),
                     (gen["rejected_attempts"], "candidates rejected by validator"),
                     (f"{acc_rate:.0%}", "candidate acceptance rate"),
                     (f"{(sum(x <= 1 for x in rereads) / len(rereads)) if rereads else 0:.0%}", "published tasks re-read within tolerance"),
                     (f"{max(rereads) if rereads else 0:.2f}", "worst re-read error (× tolerance)")]:
        H.append(f"<div class='card tile'><b>{val}</b><span>{lab}</span></div>")
    H.append("</div>")
    H.append("<h2>Why candidates were rejected</h2><p class=sub>Every candidate image is re-read from pixels and checked for "
             "visibility and ambiguity before it is published. Rejected candidates are regenerated with a new seed.</p>")
    rej = sorted(gen["rejection_reasons"].items(), key=lambda kv: -kv[1])
    if rej:
        H.append("<div class=card>" + _hbar([(k, v, f"{k}: {v}") for k, v in rej], max(v for _, v in rej)) + "</div>")

    # ---- scorer sanity
    if baselines:
        H.append("<h2>Scorer sanity checks</h2><p class=sub>Reference answerers with known behaviour. "
                 "Oracle must score 100%; near-miss (just outside tolerance) must score 0%; shortcut heuristics should stay low.</p>")
        H.append("<div class='card scroll'><table><tr><th>Answerer</th><th>Overall</th>" +
                 "".join(f"<th>{FAMILY_LABELS.get(f, f)}</th>" for f in FAMILY_LABELS) + "</tr>")
        for name in [n for n in BASELINES if n in baselines]:
            rows = baselines[name]
            H.append(f"<tr><td>{name}</td><td><b>{_pct(_acc(rows))}</b></td>" +
                     "".join(f"<td>{_pct(_acc([r for r in rows if r['family'] == f]))}</td>" for f in FAMILY_LABELS) + "</tr>")
        H.append("</table></div>")

    # ---- inspection rounds: a job, scored reading by reading and alarm by alarm
    round_rows = []
    for m, rows in {**models, **baselines}.items():
        rr = [r for r in rows if tasks[r["id"]]["answer_type"] == "round" and r.get("round")]
        if not rr:
            continue
        got = sum(r["round"]["readings_correct"] for r in rr)
        tot = sum(r["round"]["readings_total"] for r in rr)
        want = sum(len(tasks[r["id"]]["answer"]["alarms"]) for r in rr)
        caught = sum(len(r["round"]["alarms_caught"]) for r in rr)
        false = sum(len(r["round"]["false_alarms"]) for r in rr)
        round_rows.append(f"<tr><td>{html.escape(m)}</td><td>{len(rr)}</td><td>{_pct(_acc(rr))}</td>"
                          f"<td>{_pct(got / tot if tot else None)}</td><td>{caught}/{want}</td><td>{false}</td></tr>")
    if round_rows:
        H.append("<h2>Inspection rounds</h2><p class=sub>A job rather than a question: log every gauge seen by 4–6 "
                 "cameras and flag every one in its red band. A round counts as perfect only if every reading is "
                 "within tolerance and the alarm list is exactly right.</p><div class=card><table>"
                 "<tr><th>Model</th><th>Rounds</th><th>Perfect rounds</th><th>Readings right</th>"
                 "<th>Alarms caught</th><th>False alarms</th></tr>" + "".join(round_rows) + "</table></div>")

    if not models:
        H.append("<h2>Model results</h2><div class=card>No model runs yet. Run "
                 "<code>python -m gaugebench evaluate SUITE --model claude:claude-opus-5-5</code>.</div>")
    else:
        # ---- leaderboard
        H.append("<h2>Leaderboard</h2>")
        items = sorted(((m, _acc(rows), f"{m}: {_acc(rows) * 100:.1f}% of {len(rows)}") for m, rows in models.items()),
                       key=lambda x: -x[1])
        H.append("<div class=card>" + _hbar([(m, a * 100, tip) for m, a, tip in items], 100, fmt=lambda v: f"{v:.0f}%") + "</div>")
        H.append("<div class='card scroll'><table><tr><th>Model</th><th>Tasks</th><th>Overall</th>" +
                 "".join(f"<th>{FAMILY_LABELS.get(f, f)}</th>" for f in FAMILY_LABELS) + "<th>Parse fails</th></tr>")
        for m, rows in models.items():
            H.append(f"<tr><td>{html.escape(m)}</td><td>{len(rows)}</td><td><b>{_pct(_acc(rows))}</b></td>" +
                     "".join(f"<td>{_pct(_acc([r for r in rows if r['family'] == f]))}</td>" for f in FAMILY_LABELS) +
                     f"<td>{sum(not r['parse_ok'] for r in rows)}</td></tr>")
        H.append("</table></div>")

        # ---- difficulty level
        H.append("<h2>Accuracy by difficulty level</h2><p class=sub>Mixed suite: level 1 = clean dial, level 5 = all factors may be hard at once.</p>")
        H.append('<div class=legend>' + "".join(f'<span><i style="background:{colors[m]}"></i>{html.escape(m)}</span>' for m in models) + "</div>")
        lv = [str(i) for i in range(1, 6)]
        series = [(m, [_acc([r for r in rows if tasks[r["id"]]["meta"].get("level") == int(l)]) for l in lv], colors[m])
                  for m, rows in models.items()]
        H.append("<div class=grid>" + _curve([f"L{l}" for l in lv], series, "All families") + "</div>")

        # ---- capability curves
        H.append("<h2>Capability curves (one factor at a time)</h2><p class=sub>Read-value tasks on a clean dial where exactly "
                 "one visual factor is changed. A drop pinpoints the specific visual skill the model lacks.</p>")
        H.append('<div class=legend>' + "".join(f'<span><i style="background:{colors[m]}"></i>{html.escape(m)}</span>' for m in models) + "</div><div class=grid>")
        for factor, dom in FACTOR_DOMAINS.items():
            series = []
            for m, rows in models.items():
                vals = []
                for v in dom:
                    sel = [r for r in rows if tasks[r["id"]]["meta"].get("sweep_factor") == factor
                           and str(tasks[r["id"]]["factors"][factor]) == str(v)]
                    vals.append(_acc(sel))
                series.append((m, vals, colors[m]))
            if any(v is not None for _, vals, _ in series for v in vals):
                H.append(_curve([str(v) for v in dom], series, FACTOR_LABELS[factor]))
        H.append("</div>")

        # ---- error analysis
        H.append("<h2>How wrong are the wrong numbers?</h2><p class=sub>Numeric answers, error measured in multiples of the "
                 "allowed tolerance (1× = half a dial division). Near misses suggest imprecise reading; large errors suggest "
                 "misreading the scale, multiplier or needle.</p><div class='card scroll'><table><tr><th>Model</th>"
                 "<th>≤1× (correct)</th><th>1–2×</th><th>2–5×</th><th>5–20×</th><th>&gt;20×</th><th>No number</th></tr>")
        bins = [(0, 1), (1, 2), (2, 5), (5, 20), (20, float("inf"))]
        for m, rows in models.items():
            num = [r for r in rows if tasks[r["id"]]["answer_type"] == "number" and tasks[r["id"]]["tolerance"]]
            if not num:
                continue
            cells = []
            for lo, hi in bins:
                k = sum(1 for r in num if r["err_tol_units"] is not None and (lo < r["err_tol_units"] <= hi or (lo == 0 and r["err_tol_units"] <= 1)))
                cells.append(f"<td>{k / len(num):.0%}</td>")
            H.append(f"<tr><td>{html.escape(m)}</td>{''.join(cells)}<td>{sum(r['parsed'] is None for r in num) / len(num):.0%}</td></tr>")
        H.append("</table></div>")

        # ---- panel_max trap
        trap_rows = []
        for m, rows in models.items():
            pm = [r for r in rows if r["family"] == "panel_max" and tasks[r["id"]]["meta"].get("angle_trap")]
            wrong = [r for r in pm if not r["correct"]]
            fell = sum(r["parsed"] == tasks[r["id"]]["meta"]["trap_tag"] for r in wrong)
            if pm:
                trap_rows.append(f"<tr><td>{html.escape(m)}</td><td>{len(pm)}</td><td>{_pct(_acc(pm))}</td><td>{fell}/{len(wrong)}</td></tr>")
        if trap_rows:
            H.append("<h2>Range trap (panel max)</h2><p class=sub>Tasks where the needle turned furthest is <em>not</em> the "
                     "highest pressure because the dials have different ranges. 'Fell for trap' counts wrong answers that "
                     "picked the furthest-turned needle.</p><div class=card><table><tr><th>Model</th><th>Trap tasks</th>"
                     "<th>Accuracy</th><th>Fell for trap</th></tr>" + "".join(trap_rows) + "</table></div>")

        # ---- dual-scale: did wrong answers come from reading the other ring?
        ring_rows = []
        for m, rows in models.items():
            ds = [r for r in rows if r["family"] == "dual_scale"]
            wrong = [r for r in ds if not r["correct"] and r["parsed"] is not None]
            other = 0
            for r in wrong:
                g = tasks[r["id"]]["gauges"][0]
                v = g["value"]
                sec = g["secondary"]
                k = (sec["vmax"] - sec["vmin"]) / (g["scale"]["vmax"] - g["scale"]["vmin"])
                other_val = v if tasks[r["id"]]["meta"]["asked_scale"] == "secondary" else (v - g["scale"]["vmin"]) * k + sec["vmin"]
                if abs(r["parsed"] - other_val) <= 2 * tasks[r["id"]]["tolerance"] * max(k, 1):
                    other += 1
            if ds:
                ring_rows.append(f"<tr><td>{html.escape(m)}</td><td>{len(ds)}</td><td>{_pct(_acc(ds))}</td><td>{other}/{len(wrong)}</td></tr>")
        if ring_rows:
            H.append("<h2>Wrong ring (dual scale)</h2><p class=sub>On two-scale dials, how many wrong answers were actually "
                     "the reading of the <em>other</em> scale (e.g. bar given when psi was asked).</p><div class=card><table>"
                     "<tr><th>Model</th><th>Tasks</th><th>Accuracy</th><th>Read the other ring</th></tr>" + "".join(ring_rows) + "</table></div>")

        # ---- failure gallery
        best = max(models, key=lambda m: _acc(models[m]))
        fails = [r for r in models[best] if not r["correct"]][:12]
        if fails:
            H.append(f"<h2>Failure gallery — {html.escape(best)}</h2><div class=gallery>")
            for r in fails:
                t = tasks[r["id"]]
                if t["answer_type"] == "round":
                    from .inspection import format_answer
                    key = format_answer(t["answer"]["readings"], t["answer"]["alarms"])
                else:
                    key = t["answer"] if t["answer_type"] == "choice" else f"{t['answer']} ± {t['tolerance']:.3g}"
                H.append(f"<div class=card><img loading=lazy src='{t['image']}' alt='{html.escape(t['id'])}'>"
                         f"<p><b>{html.escape(FAMILY_LABELS.get(t['family'], t['family']))}</b> · <code>{html.escape(t['id'])}</code><br>"
                         f"Key: <span class=ok>{html.escape(str(key))}</span> · Model: <span class=no>{html.escape(f"{r['parsed']:.4g}" if isinstance(r['parsed'], float) else str(r['parsed']))}</span></p></div>")
            H.append("</div>")

    H.append("</main></body></html>")
    out = suite / "report.html"
    out.write_text("\n".join(H), encoding="utf-8")
    return out
