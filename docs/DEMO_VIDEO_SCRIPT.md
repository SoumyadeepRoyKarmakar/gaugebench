# Demo video script (target 3 minutes)

The demo is built around **GaugeBench Studio** (`python -m gaugebench app`), because judges remember what they see working.

**Before recording:**
- Run `python -m gaugebench app`, and make the browser window full screen at 1080p (F11). Zoom the page to about 110% if the text looks small.
- Do one practice generation so everything is warm. Pick a seed you like and note it, so you can get the same task again with **Lock**.
- Make sure `.env` has `GEMINI_API_KEY` and you still have free-tier quota (each "Ask Gemini" is one request).
- Record with OBS or the Xbox Game Bar (Win+G).

| Time | Show on screen | Say (roughly) |
|---|---|---|
| 0:00–0:15 | Title slide, then Studio with an empty inspection window | "Factories still run on analogue gauges, and companies want AI to read them from camera photos. But can it? We built GaugeBench to find out." |
| 0:15–0:40 | Bench: click **Read the value**, turn the Glare, Tilt and Multiplier knobs, press **Generate** | "GaugeBench is a factory for visual tasks: twelve kinds of question on five instruments, from pressure dials and tank levels to electricity meters, vernier calipers, and a digital display as a control. I pick an instrument and the conditions: glare, camera tilt, a ×10 multiplier. Press Generate, and a brand-new task is drawn, photographed and checked in about a second." (Optional: click **Vernier caliper** and generate one. It looks great on camera.) |
| 0:40–1:05 | Toggle **Validator vision**, then point at the factory floor (choose a setting that produces rejects, e.g. Panel alarm with L5) | "Before any task is published, an independent checker re-reads the needle from the pixels. This is what it sees: needle in orange, glare in cyan. Down here is the factory floor: candidates it threw away because glare hid the needle or the numbers overlapped. Nobody, human or model, is ever asked an unreadable question." |
| 1:05–1:30 | Hover the **loupe** over the dial, type a reading, **Submit** → stamp + tolerance strip | "Now I read it myself, with the loupe. The tolerance is half the smallest division, the same rule the models get. I'm within tolerance, so it's stamped PASS, and the strip shows my reading against the key." |
| 1:30–1:55 | **Ask Gemini** → its marker lands on the strip; open its reasoning | "Now the same image and question go to Gemini. Here's its answer on the same strip, and its reasoning. It snapped to the nearest tick: close, but outside tolerance." (If it gets it right, say so. Honesty plays well.) |
| 1:55–2:15 | **Challenge** tab: start a 5-round challenge, play two rounds quickly (the scoreboard and pips update), show the final score screen | "You can even go head to head. Same images, same tolerance, and after each answer you see what the model said. No API calls: its answers were recorded when we ran the benchmark." |
| 2:15–2:30 | **Archive** tab: gemini-3.5-flash-lite selected, family chips show accuracy; filter **Wrong**, open one task in the drawer | "Across the whole suite: Gemini is perfect at judging which colour zone a needle is in, but reads the exact value right only about a third of the time. Every wrong answer is here with the image, the key and the model's reasoning." |
| 2:30–2:45 | Open **full report** from the Archive: the scorer sanity table | "And the scoring is proven fair: an answerer with the key scores 100%, one just outside tolerance scores 0%, and random guessing about 7%." |
| 2:45–3:00 | Architecture slide or README | "Everything is reproducible from a seed, cached so we never pay twice, and extendable to new instruments. GaugeBench shows exactly where AI can be trusted to read instruments, and where it can't. Thank you." |

**Tips:**
- Record each part separately and join them in Clipchamp (built into Windows). Re-recording one part is easier than redoing the whole video.
- Gemini takes a few seconds to answer. Cut the wait in editing if it drags.
- Keep the mouse still when you're not pointing at something, and move it slowly when using the loupe.
- Upload to YouTube as **Unlisted** or to Google Drive with link access, then check the link in a private window.
