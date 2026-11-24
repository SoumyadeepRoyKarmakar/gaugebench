# Deck content: GaugeBench

Paste each section into the matching slide of the **official Hack2skill template** (Resources tab). The template is mandatory, so this file is content only.
`[[ ... ]]` marks things to fill in after the real model run.

**Built deck (official template, filled in):** Google Slides copy in the team leader's Drive, titled "Larp-Maxxing | GaugeBench | Innodata Idea Submission". Update it there after the full run.

---

## Slide 1: Title / team
- **Project:** GaugeBench, a visual task factory for industrial gauge reading
- **Track:** Track 2, Visual Task Factory
- **Team:** Larp-Maxxing (leader: Soumyadeep Roy Karmakar)
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

## Slide 4: Meaningful variation (12 task families, 5 instrument geometries)
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
| Clock-dial meter | utility meter with 4–5 dials turning in alternating directions; apply the "take the lower number" convention |
| Vernier caliper | find the one aligned vernier line: sub-division precision at its purest |
| Digital display | 7-segment LCD/LED/VFD with ghost segments and a ×10 annunciator: the digital control for the analogue tasks |

Plus **11 recorded difficulty factors**: scale type, sweep, division density, label density, multiplier, face colour, glare, camera tilt, blur, noise, exposure.

## Slide 5: How we know the answers are right (validity)
Three independent guards, applied to **every** task before it is published:

1. **Pixel re-reading.** A separate computer-vision reader reads the dial like a technician: it finds the needle from pixels, finds the tick marks, counts the divisions between the printed labels, and interpolates. It never uses the generator's formula. Its reading must match the answer key within tolerance.
2. **Visibility checks on the final photo:** glare not covering the needle, enough contrast, ticks at least 3 px apart, labels at least 9 px tall.
3. **Ambiguity checks:** the needle is not sitting on a zone boundary, the "highest" gauge wins by a clear margin, the needles don't overlap.

- **Tolerance** = half of the smallest local division, the standard rule for reading analogue instruments.
- **Main suite (384 tasks):** 636 candidates generated and 252 rejected (40%). The top reasons were glare covering the needle (185), printed labels overlapping (146) and needles too close to a zone boundary (80). One candidate can fail more than one check.
- **20 automated tests**, including mutation tests: if the answer key is shifted by 3 tolerances, the validator **always** catches it.
- **The validator caught a real flaw:** a model miss led us to a cramped dial where the printed numbers ran together. We added an overlap check, and it now rejects those dials automatically.

## Slide 6: Scoring separates right from wrong
| Reference answerer | Score |
|---|---|
| Oracle (correct key) | **100%** |
| Near-miss (just outside tolerance) | **0%** |
| Random guess | 7.0% |
| Shortcut heuristics (mid-scale, "always normal", furthest needle) | 12.0% |

- **Blind ablation:** the same questions sent **without the image** show the tasks need vision. [[blind score]]

## Slide 7: Results on frontier models
*Gemini 3.5 Flash-Lite, 198 of 384 tasks answered so far (free-tier daily cap); refresh after the full run.* [[update with final numbers]]

| Skill | Accuracy |
|---|---|
| Zone status | **100%** |
| Panel max (mixed ranges) | 95% |
| Panel alarm | 85% |
| Set-point deviation | 69% |
| Panel count | 68% |
| Dual scale | 65% |
| Tank level | 65% |
| Change over time | 50% |
| **Read the exact value** | **37%** |
| **Overall** | **67%** |

- **Headline:** the model is near-perfect at "roughly where is the needle?" but reads the exact value correctly only about a third of the time. In a plant, the exact value is the job.
- **It snaps to tick marks:** a needle at 4.6 bar was reported as "approximately 4". 23 of 56 wrong numbers (41%) were near misses within 2× the tolerance; only 1 was wild (>20×). The errors are imprecision, not misread scales.
- **Difficulty barely matters:** accuracy is 72% on clean dials (level 1) and 69% on the hardest mixed dials (level 5), so the main weakness is precise reading itself, not glare or tilt.
- **Capability curves:** accuracy as one factor gets harder (glare, tilt, scale type, …): [[1–2 key curves, after full run]]
- **Range trap:** the model avoided it. 0 of 1 wrong panel-max answers picked the furthest-turned needle.
- **Wrong ring:** 0 of 7 wrong dual-scale answers were the other scale's reading. It finds the right ring and then misreads it.

## Slide 7b: New instruments (in the built deck after "Example tasks")
Images from `runs/instruments`: a clock-dial meter (key 8072 kWh), a vernier caliper (key 57.5 mm), and an LCD showing 469.9 with ×10 lit (key 4699 V).
- Each has its own independent pixel re-reader and ambiguity checks.
- The digital display is the control: is the models' trouble analogue reading itself, or the photo? [[add Gemini's digital vs analogue accuracy after the run]]

## Slide 7c: GaugeBench Studio (in the built deck after "Features")
Screenshot: `docs/images/studio-bench.png`.
- **Bench:** generate any task live from 11 condition knobs. Read it with a loupe, see what the validator measured and which candidates were rejected, then ask Gemini the same question. Any task can be shared as a link.
- **Challenge + Daily:** go head to head with the model on real suite tasks (no API calls), or play the Daily: five gauges, the same for everyone, L1 to L5, with a shareable result and day streaks.
- **Archive, hints and rank:** browse every suite and answer. Hints teach how to read each instrument without giving the value away, and your record ranks you from Trainee to Metrologist.
- Live: https://gaugebench-studio.onrender.com (Gemini key kept server-side, usage capped), or run `python -m gaugebench app`

## Slide 8: Architecture
```
spec.py (factors, ranges) → render.py / level.py (dial + evidence masks)
   → scene.py (panel, glare, tilt, blur, noise; masks transformed too)
   → tasks.py + instruments.py (12 families + ambiguity checks) → validate.py (pixel reader, visibility)
   → generate.py (publish / reject + log) → evaluate.py (models, cached, resumable)
   → score.py → report.html
```
- **Stack:** Python, Pillow, OpenCV, NumPy, Anthropic SDK, Google GenAI SDK. No GPU needed.
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
- GitHub: https://github.com/SoumyadeepRoyKarmakar/gaugebench
- Live demo: https://gaugebench-studio.onrender.com
- Demo video: [[URL]]
