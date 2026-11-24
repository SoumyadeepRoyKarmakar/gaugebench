# GaugeBench: technical explanation

This document covers the design decisions, core assumptions, reused components, model choices and task-variation strategy behind GaugeBench (Innodata AI Hackathon, Track 2: Visual Problem & Model Evaluation). The evidence that the pipeline works is in [VALIDATION.md](VALIDATION.md); how to run it is in the [README](../README.md).

## 1. The visual problem

**Image family:** photographs of industrial analogue instruments (pressure, temperature, flow and level gauges; utility clock-dial meters; vernier calipers) plus a 7-segment digital panel meter as a control.

**Why it matters:** plants and utilities increasingly point cameras at legacy instruments and ask a model to log readings or raise alarms. A reading that is off by a few divisions, or a missed red needle, is a safety and cost problem. The question GaugeBench answers is *which visual skills behind instrument reading current multimodal models actually have*, with evidence precise enough to set guard rails.

## 2. Architecture

```
spec.py ──> render.py / level.py / instruments.py ──> scene.py ──> tasks.py / inspection.py
 sample      draw the instrument + evidence masks     photograph      write question + key
                                                      (masks too)     + ambiguity checks
                                        │
                                        v
             validate.py (independent pixel reader, visibility, legibility)
                                        │ pass                 │ fail
                                        v                      v
                     generate.py: publish task package   reject, log reason, new seed
                                        │
                                        v
          evaluate.py (models/: Gemini, Claude, 4 offline baselines; cached, resumable)
                                        │
                                        v
                 score.py ──> report.py (report.html) ──> app.py + web/ (Studio)
```

One Python package, one CLI (`python -m gaugebench generate | evaluate | report | all | app | fetch-suite`). No GPU, no training, no external datasets.

## 3. Design decisions

| Decision | Why |
|---|---|
| **Synthesise instead of collecting photos** | The answer key is known exactly (the generator chooses the needle value), tasks can be regenerated without limit, and a fresh seed produces tasks no model can have memorised. |
| **Render "evidence masks" alongside every image** | The renderer also outputs the needle, tick and label masks, and every photographic effect (perspective, glare, blur) is applied to the masks too. The validator can then check what is actually visible in the final photo, not what was intended. |
| **Validate with an independent reader, not the generator's formula** | A key computed by the same code that drew the image proves nothing. `validate.cv_read` finds the needle from pixels, finds individual ticks (connected components), attaches the printed labels, counts divisions and interpolates, like a technician. Its reading must agree with the key within tolerance. |
| **Reject and regenerate, never repair** | A candidate that fails any check is discarded with its reason logged and a new seed is drawn. No published task is ever edited by hand, so every task is reproducible from its seed. |
| **Tolerance = half the smallest local division** | This is the instrument-reading convention: you cannot read a dial more precisely than half a division. For answers combining two readings (set-point deviation, change over time) both tolerances are added. |
| **Answer contract: a final `ANSWER:` line** | One parser for every model; reasoning is kept for analysis. Parse failures are counted separately so formatting problems are not confused with reading problems. |
| **Error in "tolerance units"** | Storing |answer − key| / tolerance distinguishes a near miss (snapping to a tick, ≤ 2×) from a wild error (wrong scale or missed multiplier, > 20×). |
| **Deterministic seeds** | Each task's seed is a SHA-256 of (suite seed, family, level/factor, index, attempt). The same command produces byte-identical suites. |
| **Offline reference answerers** | `oracle`, `near_miss`, `random` and `shortcut` cost nothing and prove the scorer separates right from almost right before any API money is spent. |
| **Cache and resume every model call** | Answers are written as they arrive; failed calls (quota, network) are never cached as answers and are retried on the next run. Nothing is paid for twice. |
| **A digital display as a control** | If a model fails analogue dials but reads digits, the weakness is analogue reading itself rather than image quality. |
| **Inspection rounds as a job-level task** | Single questions test perception; a round (log 4–6 gauges, flag the red ones) tests whether a model can do the actual work, scored per reading and per alarm, passing only when everything is right. |
| **Studio keeps keys on the server** | The answer key is released only after the reader answers; the model API key lives only on the server, with per-visitor and daily caps in public mode. |

## 4. Core assumptions

- **Rendered images stand in for photos.** Glare, perspective tilt, blur, sensor noise and exposure approximate camera effects; real scratches, textures and curved-glass reflections are not modelled. A small real-photo validation set is the main next step.
- **The pixel reader takes label positions and values from the renderer** rather than running OCR. Needle and tick evidence come from the pixels.
- **One reading per question.** Ambiguous situations (needle on a zone boundary, near-ties between gauges, overlapping needles) are rejected rather than scored with a judgement call.
- **The answer format is part of the task.** A model that ignores the `ANSWER:` line is counted as a parse failure (Gemini had none across 428 answers).
- **Sample sizes:** the mixed suite has 20 tasks per family; single-factor sweeps have 6 tasks per setting. Sweep differences are reported as signals, not precise curves.

## 5. Reused components

All images and tasks are generated by this project; no image dataset or pretrained vision model is reused.

| Component | Used for |
|---|---|
| Pillow | 2× supersampled rendering of dials, meters, calipers and displays |
| NumPy | geometry, masks, photographic effects |
| OpenCV (headless) | perspective warp; connected components in the independent pixel reader |
| `google-genai` SDK | Gemini adapter (`models/gemini.py`) |
| `anthropic` SDK | Claude adapter (`models/claude.py`) |
| pytest | the 23-test suite |
| DejaVu Sans / Arial | dial lettering (whichever the OS provides) |
| Python standard library `http.server` + vanilla JS | GaugeBench Studio (no web framework) |
| Docker, Render | hosting the Studio |

## 6. Model choices

| Model | Role | Settings |
|---|---|---|
| **Gemini 3.5 Flash-Lite** (`gemini-3.5-flash-lite`) | The evaluated model: all 384 v2 tasks, 24 instrument tasks, 20 inspection rounds | Google GenAI SDK, system prompt "experienced plant technician", default thinking, image + question, 2-minute timeout, back-off retries, fail-fast on the free-tier daily cap. Chosen because it is a current multimodal model available on a free tier, so the whole benchmark could be run at no cost. |
| **Claude** (`claude-opus-5-5` by default) | Supported adapter, not part of the reported results | Anthropic SDK, configurable effort. Selectable in the Studio and the CLI when `ANTHROPIC_API_KEY` is set. |
| `oracle`, `near_miss`, `random`, `shortcut` | Scorer sanity and shortcut detection | Offline, deterministic. `shortcut` uses cheap heuristics a model might fall back on: mid-scale for numbers, "normal" for zones, the furthest-turned needle for panel max, and reading a display while ignoring its ×10/×100 indicator. |

The same image bytes and question text go to every model; nothing is resized or re-prompted per model.

## 7. Task-variation strategy

Variation is in **what has to be seen and reasoned about**, not in wording.

1. **Thirteen task types on five instrument geometries.** Twelve families test distinct skills: precise reading (linear, offset, square-root, log scales; printed multipliers), zone judgement (high- and low-alarm layouts), two-needle subtraction, panel scanning, comparison across *different ranges* (with a recorded "range trap" where the furthest-turned needle is not the highest value), change over two photos, choosing the right ring on dual-scale dials, a vertical sight-glass, counting out-of-band dials, the clock-meter "take the lower number" rule, vernier alignment, and the digital control. The inspection round adds a 13th, job-level type.
2. **Eleven recorded difficulty factors:** scale type, sweep (270/180/90°), minor divisions, label density, multiplier, face colour, glare, camera tilt, blur, noise, exposure.
3. **Mixed difficulty levels 1–5:** level *L* lets each factor range over the first 35% + 65%·(L−1)/4 of its domain, so level 1 is clean and level 5 can combine strong glare, 40° tilt, blur and a dark face.
4. **Single-factor sweeps:** the same clean dial with exactly one factor changed, so a capability curve isolates one visual skill.
5. **Per-camera variety in inspection rounds:** every camera gets its own dial type, range, unit, multiplier and photographic conditions, and some rounds contain no alarms at all.
6. **Unlimited fresh suites:** a new suite seed regenerates every task, so the benchmark can be refreshed whenever a model may have trained on an old one.

## 8. Limitations and next steps

- Add a small set of real photographs with hand-verified readings to measure the synthetic-to-real gap.
- Replace renderer-supplied label values with OCR in the validator.
- Add more instruments (strip-chart recorders, multimeters with range switches) and a blind no-image ablation run.
- Evaluate more models with the existing adapters (the Claude adapter is ready; it needs an API key).
