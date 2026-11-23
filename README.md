# GaugeBench: a visual task factory for industrial gauge reading

**Innodata AI Hackathon, Track 2 (Visual Task Factory)**

GaugeBench generates synthetic photos of analogue industrial gauges, writes questions about them, and stores answer keys that are known exactly and checked independently of the model under test. It then measures how well multimodal AI models actually *read* instruments.

## Why this problem matters

Plants still run on analogue dials: pressure, temperature, flow and vacuum. Utilities and factories increasingly point cameras or phones at those dials and ask an AI to log the reading or raise an alarm. A misread pressure gauge can mean a missed over-pressure, a wrong maintenance call, or a false shutdown. Reading a dial looks easy but combines several skills where models are known to be weak:

- finding the needle angle precisely
- mapping that angle onto a scale that may be non-linear
- applying a printed multiplier
- comparing dials with different ranges
- coping with glare and camera tilt

## What the factory produces

Each **task package** is one folder:

```
tasks/<task_id>/image.png     the photographed gauge / panel
tasks/<task_id>/task.json     question, answer key, tolerance, every visual factor,
                              gauge specs, seed, and the full validation evidence
manifest.jsonl                one line per published task
generation_log.json           attempts, acceptances, and rejection reasons
results/<model>.jsonl         raw model outputs and per-task scores
report.html                   leaderboard, capability curves, error analysis, failure gallery
```

### Nine task families (different reasoning, not just different wording)

| Family | What the model must do | Answer |
|---|---|---|
| `read_value` | precise reading, including non-linear (√, log) scales, offset/negative ranges and printed multipliers (×10, ×0.1) | number ± tolerance |
| `zone_status` | relate the needle to coloured safety bands (high- *and* low-alarm layouts) | normal / warning / danger |
| `setpoint_deviation` | read two needles (actual and red set point) and subtract | signed number |
| `panel_alarm` | scan a 3–6 gauge panel and find the one in its red zone | instrument tag |
| `panel_max` | compare values across dials with **different ranges**; the furthest-turned needle is often *not* the highest value (a recorded "range trap") | instrument tag |
| `temporal_change` | read the same dial in two photos and compute the change | signed number |
| `dual_scale` | pick the right ring on a two-scale dial (bar/psi, kPa/psi, °C/°F) — the other ring is a built-in distractor | number ± tolerance |
| `level_reading` | read a vertical tank sight-glass (a different instrument geometry: linear, vertical, liquid surface) | number ± tolerance |
| `panel_count` | count how many of 4–6 dials are outside their green band (counting + per-dial judgement) | exact integer |

### Eleven visual difficulty factors, all recorded per task

| Factor | Values |
|---|---|
| Scale type | linear, offset, sqrt, log |
| Sweep | 270°, 180°, 90° |
| Minor divisions | 2, 5, 10 |
| Label density | every major tick, or every other one |
| Multiplier | ×1, ×10, ×100, ×0.1 |
| Dial face | light, dark |
| Glare | none, mild, strong |
| Camera tilt | 0–40° |
| Blur | 0–2 px |
| Sensor noise | 0–16 |
| Exposure | 1.0 down to 0.45 |

A suite contains two parts:

- **Mixed tasks** at difficulty levels 1–5.
- **Single-factor sweeps**: a clean dial where exactly one factor changes. These produce capability curves that pinpoint which visual skill fails.

## How the answer keys are verified (independently of the model)

The generator chooses the needle value, so it knows the answer. That alone does not prove the *image* shows it. Every candidate task therefore passes three groups of checks before it is published. A failed candidate is regenerated with a new seed, and the rejection reason is logged.

1. **Independent pixel re-reading** (`validate.cv_read`). A deterministic computer-vision reader reads the dial the way a technician does, and never uses the generator's value→angle formula:
   - finds the needle direction from needle pixels
   - finds individual tick marks from tick pixels (connected components)
   - attaches the printed labels to their ticks
   - counts the divisions between the two labels on either side of the needle
   - interpolates within the division

   Its reading must match the key within tolerance. On clean dials its error averages under 0.15× the tolerance, and dials too dense to resolve are rejected.
2. **Visibility checks on the final photographed image**:
   - glare must not cover the needle
   - the needle must contrast with its surroundings
   - neighbouring tick marks must stay at least 3 px apart after perspective
   - printed numbers must be at least 9 px tall
3. **Ambiguity checks per family**:
   - the needle is not on a zone boundary
   - the "highest" gauge wins by more than twice the combined reading error
   - the set-point and actual needles do not overlap
   - a change is larger than its reading error

**Tolerance** follows instrument-reading practice: **half of the smallest local division**. When an answer combines two readings, both tolerances are added.

### Proof that scoring separates right from wrong

`python -m gaugebench all` runs four offline reference answerers on every suite:

| Answerer | What it does | Expected |
|---|---|---|
| `oracle` | returns the key | 100% |
| `near_miss` | key shifted by 2.5× tolerance, or a wrong option | 0% |
| `random` | uniform guess | chance (~9%) |
| `shortcut` | mid-scale guess, always "normal", always 1, furthest-turned needle | low (~8%) |

There is also a **blind ablation**: `--blind` sends the same question without the image, to show the tasks really need vision.

## Quick start

```bash
pip install -r requirements.txt

# generate + validate + offline baselines + report (no API key needed)
python -m gaugebench all runs/demo --per-family 20 --sweep 6 --seed 7

# evaluate a Claude model (credentials come from ANTHROPIC_API_KEY — never commit keys)
python -m gaugebench evaluate runs/demo --model claude:claude-opus-5-5 --workers 4
python -m gaugebench evaluate runs/demo --model claude:claude-opus-5-5 --blind --limit 60
# evaluate a Gemini model — free API key from https://aistudio.google.com
# put keys in a local .env file (git-ignored, loaded automatically):  GEMINI_API_KEY=...  ANTHROPIC_API_KEY=...
python -m gaugebench list-models gemini      # which model ids your key can use
python -m gaugebench evaluate runs/demo --model gemini:<model-id> --workers 1   # free tier is rate-limited

python -m gaugebench report runs/demo        # open runs/demo/report.html

python -m pytest -q                          # 12 tests incl. mutation tests of the validator
```

Evaluation runs are **resumable and cached**. Tasks already answered are never paid for twice. To add another provider, write a `Model` subclass in `gaugebench/models/` that returns `{"text": ...}`.

## Code map

| File | Role |
|---|---|
| `scales.py` | value ↔ angle for linear, sqrt and log scales; ticks; tolerance |
| `spec.py` | factors, realistic range presets, sampler, zones |
| `render.py` | draws a gauge and its evidence layers (needle, tick masks, label positions) |
| `scene.py` | panels and pairs; glare, perspective, exposure, blur, noise, applied to the masks too |
| `validate.py` | independent pixel reader, visibility checks, margin checks |
| `tasks.py` | the nine task families with their ambiguity checks |
| `level.py` | tank level sight-glass renderer |
| `generate.py` | sample → validate → publish or reject; deterministic seeds |
| `models/` | Claude and Gemini adapters (official SDKs) and offline baselines |
| `evaluate.py`, `score.py`, `report.py` | running models, scoring, and the HTML report |

## Limitations (honest statement)

- Images are rendered, not real photos. Glare, tilt, blur and noise approximate camera effects, but there are no real-world textures, scratches or reflections on curved glass.
- The pixel reader uses label *positions and values* from the renderer instead of running OCR. Needle and tick evidence come from pixels.
- Answers are parsed from a final `ANSWER:` line. A model that ignores the format is scored as a parse failure, and the report shows these separately.
- Covered instruments: round dials (single, set-point and dual-scale) and level sight-glasses. Digital displays, multi-pointer clocks and strip-chart recorders are natural extensions.
