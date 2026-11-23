# Demo video script (target 3 minutes)

**Before recording:**
- Generate a fresh suite, run the models once so the results are cached, and open `report.html` in Chrome.
- Use a large terminal font (18 pt or more) and a clean desktop.
- Record with OBS or the Xbox Game Bar (Win+G) at 1080p.

| Time | Show on screen | Say (roughly) |
|---|---|---|
| 0:00–0:15 | Title slide, then one gauge image full screen | "Factories still run on analogue gauges, and companies want AI to read them from camera photos. But can it? We built GaugeBench to find out." |
| 0:15–0:35 | A grid of 4 different task images: glare dial, dual scale, panel, tank level | "GaugeBench is a factory. It generates gauge photos with questions and answers we already know: 9 kinds of questions and 11 difficulty settings, like glare, camera tilt and log scales." |
| 0:35–1:05 | Terminal: `python -m gaugebench generate runs/live --per-family 3 --sweep 0 --seed 42`. Then open one `task.json` and scroll to `"validation"` | "One command builds a new suite. Each task is checked before we keep it. A separate image reader re-reads the needle from the pixels and must agree with our answer. Here is the evidence for this task: every check, with numbers." |
| 1:05–1:25 | `generation_log.json`: the rejection reasons | "Candidates that fail are thrown away and regenerated, for example when glare hides the needle or the needle sits right on a zone boundary. That is how we guarantee every answer can actually be seen in the image." |
| 1:25–1:45 | Report: the scorer sanity table (oracle 100%, near-miss 0%) | "To prove the scoring works: an answerer that knows the key scores 100%, and one that is just outside the tolerance scores 0%. Random guessing sits near 9%." |
| 1:45–2:30 | Report: leaderboard → per-family table → one capability curve (glare or scale type) → range-trap or wrong-ring table | "Now a real model. Gemini 3.5 Flash-Lite gets 67% overall, and the split is the interesting part. It is perfect at saying which colour band a needle is in, but it reads the exact value right only 37% of the time. Here's a typical miss: the needle is at 4.6 bar and the model says 'approximately 4'. It snaps to the nearest tick. That's the gap between seeing a gauge and reading one." [[update numbers after the full run; optionally add one capability curve]] |
| 2:30–2:45 | Failure gallery: zoom into one striking failure | "Here the key is 4.2 bar, and the model said 42: it missed the multiplier. In a plant, that matters." |
| 2:45–3:00 | README / architecture slide | "Everything is reproducible from a seed, cached so we never pay twice, and extendable with new instruments. GaugeBench shows exactly where AI can be trusted to read instruments, and where it can't. Thank you." |

**Tips:**
- Record each part separately and join them in Clipchamp (built into Windows). Re-recording one part is easier than redoing the whole video.
- If generation feels slow on camera, cut the wait. Say "this takes about 10 seconds" and jump ahead.
- Keep the mouse still and zoom in (Win + Plus) when showing small numbers.
- Upload to YouTube as **Unlisted** or to Google Drive with link access, then check the link in a private window.
