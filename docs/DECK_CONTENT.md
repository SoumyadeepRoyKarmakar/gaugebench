# Deck content: GaugeBench

Paste each section into the matching slide of the **official Hack2skill template** (Resources tab). The template is mandatory, so this file is content only.
`[[ ... ]]` marks things to fill in after the real model run.

---

## Slide 1: Title / team
- **Project:** GaugeBench, a visual task factory for industrial gauge reading
- **Track:** Track 2, Visual Task Factory
- **Team:** [[team name, members, college]]
- **One-liner:** We generate gauge photos whose answers we already know, check every answer independently, and measure where frontier AI models stop being trustworthy at reading instruments.

## Slide 2: The problem
- Plants, utilities and refineries still run on **analogue dials**: pressure, temperature, flow, tank level.
- Companies now point cameras or phones at those dials and ask AI to **log readings and raise alarms**.
- **Errors are costly.** A misread pressure gauge can mean a missed over-pressure, a false shutdown, or a wrong maintenance call.
- Reading a dial looks easy, but it combines skills where models are weak:
  - finding the exact needle angle
  - handling non-linear scales and printed multipliers ("×10")
  - choosing the right one of two scales
  - comparing dials with different ranges
  - coping with glare and camera tilt
- **Big question:** which of these visual skills do today's models really have, and how do we test that reliably?

## Slide 3: Our solution (the factory)
- A **reusable, automated pipeline**: sample → render → photograph → **validate** → publish (or reject and retry).
- Every task package contains the image, the question, the answer key with a tolerance, all difficulty factors, the seed, and the full validation evidence.
- **Deterministic:** the same seed gives byte-identical tasks. A fresh seed gives brand-new tasks, so the benchmark can be regenerated whenever a model may have trained on the old one (no contamination).
- One command builds a suite of any size. The 210-task sample takes about 1.5 minutes on a laptop.

## Slide 4: Meaningful variation (9 task families)
| Family | Visual skill tested |
|---|---|
| Read value | precise reading on linear, √, log and negative-range scales, with printed multipliers |
| Zone status | needle position vs coloured safety bands (high and low alarm layouts) |
| Set-point deviation | read two needles and subtract |
| Panel alarm | scan 3–6 dials and find the one in red |
| Panel max | compare dials with **different ranges** (built-in "range trap") |
| Change over time | read the same dial in two photos and compute the change |
| Dual scale | pick the right ring (bar/psi, °C/°F); the other ring is a distractor |
| Tank level | vertical sight-glass, a different instrument geometry |
| Panel count | count the dials outside their green band |

Plus **11 recorded difficulty factors**: scale type, sweep, division density, label density, multiplier, face colour, glare, camera tilt, blur, noise, exposure.

## Slide 5: How we know the answers are right (validity)
Three independent guards, applied to **every** task before it is published:

1. **Pixel re-reading.** A separate computer-vision reader reads the dial like a technician: it finds the needle from pixels, finds the tick marks, counts the divisions between the printed labels, and interpolates. It never uses the generator's formula. Its reading must match the answer key within tolerance.
2. **Visibility checks on the final photo:** glare not covering the needle, enough contrast, ticks at least 3 px apart, labels at least 9 px tall.
3. **Ambiguity checks:** the needle is not sitting on a zone boundary, the "highest" gauge wins by a clear margin, the needles don't overlap.

- **Tolerance** = half of the smallest local division, the standard rule for reading analogue instruments.
- **Sample suite:** 309 candidates generated and 99 rejected. The top reasons were glare covering the needle (69) and needles too close to a zone boundary (23). One candidate can fail more than one check.
- **12 automated tests**, including mutation tests: if the answer key is shifted by 3 tolerances, the validator **always** catches it.

## Slide 6: Scoring separates right from wrong
| Reference answerer | Score |
|---|---|
| Oracle (correct key) | **100%** |
| Near-miss (just outside tolerance) | **0%** |
| Random guess | 8.6% |
| Shortcut heuristics (mid-scale, "always normal", furthest needle) | 8.1% |

- **Blind ablation:** the same questions sent **without the image** show the tasks need vision. [[blind score]]

## Slide 7: Results on frontier models
[[Fill in after the run: leaderboard bar chart + per-family table from report.html]]
- Overall accuracy: [[model A %]], [[model B %]]
- Strongest skill: [[e.g. zone status]]. Weakest skill: [[e.g. log scales / dual-scale ring]]
- **Capability curves:** accuracy as one factor gets harder (glare, tilt, scale type, …): [[1–2 key curves]]
- **Error size:** [[x%]] of wrong numbers are near misses (1–2× tolerance) and [[y%]] are wild (>20×), meaning a misread scale or multiplier rather than imprecision.
- **Range trap:** [[n/m]] wrong panel-max answers picked the furthest-turned needle.
- **Wrong ring:** [[n/m]] wrong dual-scale answers were the reading of the other scale.

## Slide 8: Architecture
```
spec.py (factors, ranges) → render.py / level.py (dial + evidence masks)
   → scene.py (panel, glare, tilt, blur, noise; masks transformed too)
   → tasks.py (9 families + ambiguity checks) → validate.py (pixel reader, visibility)
   → generate.py (publish / reject + log) → evaluate.py (models, cached, resumable)
   → score.py → report.html
```
- **Stack:** Python, Pillow, OpenCV, NumPy, Anthropic SDK. No GPU needed.
- **Responsible resource use:** answers are cached and resumable (never pay twice), offline baselines need no API calls, and the suite size is configurable.

## Slide 9: Impact
- **For industry:** before deploying camera-based meter reading, run GaugeBench to see *which* conditions break the model (glare, tilt, log scales) and set up guard rails.
- **For model builders:** a training and evaluation data source that can be regenerated without limit and can't be memorised.
- **For Innodata:** a template for "verifiable visual task factories". The same pattern (generate → re-verify from pixels → reject) extends to schematics, charts and documents.

## Slide 10: Limitations and next steps
- Rendered images, not real photos. Next: real textures, curved-glass reflections, and a small real-photo validation set.
- The pixel reader takes label values from the renderer instead of running OCR.
- Next instrument families: digital displays, multi-pointer dials, strip-chart recorders.
- Next analysis: compare effort levels, and fine-tune or prompt fixes for the weakest skills.

## Slide 11: Links
- GitHub: [[repo URL]]
- Demo video: [[URL]]
