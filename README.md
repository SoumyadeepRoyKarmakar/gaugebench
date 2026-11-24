# GaugeBench: a visual task factory for industrial gauge reading

**Innodata AI Hackathon, Track 2 (Visual Task Factory)**

**Live demo: [gaugebench-studio.onrender.com](https://gaugebench-studio.onrender.com)** (GaugeBench Studio: generate and read gauges, play the Daily, challenge Gemini, browse every result). On the free plan the first visit after a quiet spell takes about a minute to wake the server.

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

### Twelve task families on five instrument geometries (different reasoning, not just different wording)

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
| `dial_meter` | read a utility **clock-dial meter**: 4–5 small dials that turn in alternating directions, applying the "take the lower number" convention across them | exact integer (kWh) |
| `vernier` | read a **vernier caliper**: whole mm from the main scale (numbered in cm) plus tenths from the one vernier line that aligns, which is sub-division precision in its purest form | number ± 0.05 mm |
| `digital_display` | read a **7-segment panel meter** (LCD, red LED or VFD) with ghost segments, a decimal point and sometimes a lit ×10/×100 annunciator. It is the *digital control*: does a model's trouble come from analogue reading or from the photo? | number ± ½ last digit |

The three newer instruments have their own independent pixel readers: pointer angles per dial for the meter, tick-mask alignment for the vernier, and luminance at segment positions for the display. They also have their own ambiguity checks: no meter pointer sitting exactly on a number, and the vernier's aligned line resolvable after blur.

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

python -m pytest -q                          # 20 tests incl. mutation tests of the validator

python -m gaugebench app                     # GaugeBench Studio, the interactive web app
```

Evaluation runs are **resumable and cached**. Tasks already answered are never paid for twice. To add another provider, write a `Model` subclass in `gaugebench/models/` that returns `{"text": ...}`.

## GaugeBench Studio (interactive web app)

`python -m gaugebench app` opens a local web app at `http://127.0.0.1:8765`. It needs no extra installs (Python standard library server, vanilla JS front end).

**Bench**: the factory, live.
- Pick one of the 12 task families and set the 11 conditions on rotary knobs (or roll a random L1–L5 mix), then **Generate**. A new task is drawn, photographed and validated in about a second.
- Read it yourself, using the **loupe** (hover to magnify) if you like. You are scored with the same tolerance the models get, on a paper work order with a tolerance strip that shows your reading against the key.
- **Validator vision** shows what the independent checker measured: needle pixels in orange, set points in magenta, glare in cyan.
- The **factory floor** shows every candidate that was rejected before this task was published, and why (glare over the needle, numbers overlapping, needle on a zone edge...).
- **Ask Gemini** sends the exact same image and question to the model (needs `GEMINI_API_KEY` in `.env`) and puts its answer on the same strip, with its reasoning.
- The answer key and the true needle value stay on the server until you submit or reveal (enforced by a test).
- **Copy link** recreates exactly the task on screen (instrument, seed and conditions) for anyone running the app.
- **Task pack** downloads the image plus a JSON with the key, the factors and the full validation evidence, so any live task can join a dataset.

**Daily**: five gauges a day, the same for everyone (seeded by the date), ramping from a clean L1 to a brutal L5. You get one shot. Your result is a row of tiles you can copy and share (🟧 right, 🟨 right with a hint, ⬛ missed), with a day streak and a countdown to the next one.

**Challenge**: you against a model, head to head, on 5, 10 or 20 real tasks from a suite. After each answer you see the model's recorded answer and reasoning on the same image; at the end you get the final score and your time against the model's. It makes no API calls, because the model's answers come from the suite's results.

**Archive**: browse any suite in `runs/` as a grid, filter by family or by right/wrong for any model, and open a task to see the image, the key, every model's answer and reasoning, and all validator checks.

**Hints**: every task has a *Hint* button that explains how to read that instrument (division size, which ring, the multiplier, the meter's reading rule) without ever giving the value away (enforced by a test). Answers given after a hint are marked as assisted.

**Your record**: click your score in the header to see your rank (Trainee → Apprentice → Technician → Senior technician → Calibration engineer → Metrologist, based on recent accuracy), accuracy per instrument, best streak, and how you miss: near misses (snapping to a tick, like the models) or wild misses (a missed multiplier or the wrong scale). Rank-ups and 5-in-a-row streaks get a little celebration.

Small touches: synthesised mechanical sounds (knob clicks, the stamp, pass/fail chimes; `M` to mute), confetti on wins, and a shortcuts panel (`?`).

Keyboard: `G` generate, `Enter` submit, `1`–`9` pick a choice, `H` hint, `L` loupe, `V` validator vision, `M` sound, `R` your record, `?` shortcuts, `Esc` close.

### Putting it online

The repository is ready to host as a public site (`Dockerfile`, `render.yaml`). **The Gemini API key stays on the server**: it is set as a secret in the host's dashboard, read only by the Python backend, and never sent to the browser or stored in the image or the repository. Public mode (`GAUGEBENCH_PUBLIC=1`) also caps Ask Gemini per visitor and per day, ignores any model a visitor tries to choose, caches answers so a task is never paid for twice, limits generation work and request size, hides developer error details, and sends strict security headers (all enforced by a test). The large `v2` suite (171 MB of images) is kept out of git as an asset of the repository's `data` release and baked into the image at build time, so the hosted Archive and Challenge have the full results. Step-by-step instructions: [docs/DEPLOY.md](docs/DEPLOY.md).

## Code map

| File | Role |
|---|---|
| `scales.py` | value ↔ angle for linear, sqrt and log scales; ticks; tolerance |
| `spec.py` | factors, realistic range presets, sampler, zones |
| `render.py` | draws a gauge and its evidence layers (needle, tick masks, label positions) |
| `scene.py` | panels and pairs; glare, perspective, exposure, blur, noise, applied to the masks too |
| `validate.py` | independent pixel reader, visibility checks, margin checks |
| `tasks.py` | the nine dial and sight-glass task families with their ambiguity checks |
| `level.py` | tank level sight-glass renderer |
| `instruments.py` | clock-dial meter, vernier caliper and digital display: renderers, pixel readers, task builders |
| `generate.py` | sample → validate → publish or reject; deterministic seeds |
| `models/` | Claude and Gemini adapters (official SDKs) and offline baselines |
| `evaluate.py`, `score.py`, `report.py` | running models, scoring, and the HTML report |
| `app.py`, `web/` | GaugeBench Studio: JSON API and the interactive front end |

## Limitations (honest statement)

- Images are rendered, not real photos. Glare, tilt, blur and noise approximate camera effects, but there are no real-world textures, scratches or reflections on curved glass.
- The pixel reader uses label *positions and values* from the renderer instead of running OCR. Needle and tick evidence come from pixels.
- Answers are parsed from a final `ANSWER:` line. A model that ignores the format is scored as a parse failure, and the report shows these separately.
- Covered instruments: round dials (single, set-point and dual-scale) and level sight-glasses. Digital displays, multi-pointer clocks and strip-chart recorders are natural extensions.
