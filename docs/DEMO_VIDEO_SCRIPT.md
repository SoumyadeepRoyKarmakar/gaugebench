# Demo video script (target 3 minutes)

The demo is built around **GaugeBench Studio**, because judges remember what they see working, with four slides from the deck cut in where they explain something faster than the app can. Record the Studio on the hosted site, https://gaugebench-studio.onrender.com (see [DEPLOY.md](DEPLOY.md)), or locally with `python -m gaugebench app`. The flow is the same.

**Slides used** (from the built deck, in this order): *Brief about the idea* (slide 2), *Every answer is proven readable* (after Process flow), *Inspection rounds*, *What we found* (after Results), *Architecture*. Present the deck full screen (Ctrl+F5 in Google Slides) and record each slide for the few seconds shown below.

**Before recording:**
- **Hosted:** open the site a minute early so a sleeping free-tier server is awake.
- **Local:** run `python -m gaugebench app`. Both versions have the full `v2` and inspection-rounds suites in the Archive (the hosted one downloads them from the repository's `data` release when it is built).
- Make the browser full screen at 1080p (F11). Zoom the page to about 110% if the text looks small.
- Do one practice generation so everything is warm. Pick a seed you like and note it, so you can get the same task again with **Lock** (or **Copy link**).
- Check that the **Ask** button works once ("Ask Gemini 3.5 Flash-Lite to read it"). Each new task you ask about uses one request from the free daily quota; asking about the same task again is free.
- **Don't play today's Daily before recording** if you want to show the one-shot play; otherwise show your finished result tiles.
- Turn the sound on (speaker button in the header). The knob clicks and the stamp make the video feel alive.
- The welcome tour appears on a browser's first visit. Close it before recording, or record its first step as a 3-second intro.
- Record with OBS or the Xbox Game Bar (Win+G).

| Time | Show on screen | Say (roughly) |
|---|---|---|
| 0:00–0:12 | Title slide, then **slide: Brief about the idea** (the three stat tiles) | "Factories still run on analogue gauges, and companies want AI to read them from camera photos. But can it? GaugeBench is a factory that makes gauge-reading tasks whose answers we can prove, and measures where AI stops being trustworthy." |
| 0:12–0:32 | Studio, Bench: click **Read the value**, turn the Glare, Tilt and Multiplier knobs, press **Generate** (click **View all 13 instruments** first to show the full list) | "Twelve kinds of question on five instruments, from pressure dials and tank levels to electricity meters, vernier calipers and a digital display as a control. I pick an instrument and the conditions: glare, camera tilt, a ×10 multiplier. Press Generate, and a brand-new task is drawn, photographed and checked in about a second." |
| 0:32–0:50 | Toggle **Validator vision** (`V`), point at the factory floor (a setting that produces rejects, e.g. Panel alarm with L5), then cut to **slide: Every answer is proven readable** | "Before any task is published, an independent checker re-reads the needle from the pixels: needle in orange, glare in cyan. Down here are the candidates it threw away. Forty percent of candidates are rejected, so nobody, human or model, is ever asked an unreadable question." |
| 0:50–1:06 | Press **Hint** (`H`), use the **loupe**, type a reading, **Submit** → stamp + tolerance strip | "A hint teaches how to read this instrument without giving the value away. I read it with the loupe. The tolerance is half the smallest division, the same rule the models get. Within tolerance: PASS, and the strip shows my reading against the key." |
| 1:06–1:22 | **Ask Gemini 3.5 Flash-Lite to read it** → its marker lands on the strip; open its reasoning | "Now the same image and question go to Gemini. Its answer lands on the same strip, with its reasoning. It snapped to the nearest tick: close, but outside tolerance." (If it gets it right, say so. Honesty plays well.) |
| 1:22–1:45 | **Slide: Inspection rounds** (2 s), then Bench → **Inspection round**: Generate, type two readings, toggle **ALARM** on a gauge in the red, Submit → gauge-by-gauge table | "A single question tests reading. A plant needs the whole job: log every gauge on a camera round and catch the ones in the red. Every reading is checked against its own tolerance, and alarms are counted as caught, missed or false. A round passes only if everything is right." |
| 1:45–2:00 | **Daily** tab: show today's five gauges (or your result tiles); click your score in the header for **Your record** (rank dial) | "There's a Daily too: five gauges a day, the same for everyone, from easy to brutal, with shareable tiles and a rank from Trainee to Metrologist. Your progress stays in your own browser: no account, no cookies." |
| 2:00–2:15 | **Archive** tab (`v2` suite): gemini-3.5-flash-lite selected, family chips show accuracy; filter **Wrong**, open one task in the drawer | "All 384 tasks, every answer, the key and the model's reasoning, browsable." |
| 2:15–2:40 | **Slide: What we found** (the four tiles and the takeaway) | "Here's what we found. Gemini is perfect at colour zones but reads the exact value right only 36 percent of the time. Its misses are near misses: it snaps to the nearest tick. It reads a digital display at 62 percent but a vernier at zero, so the trouble is analogue reading, not the photo. And on twenty inspection rounds it never got a single round fully right. It can triage a panel, but it can't be trusted to log readings unattended." |
| 2:40–3:00 | **Slide: Architecture**, then the hosted site's address bar | "Everything runs from a seed, is cached so we never pay twice, and extends to new instruments. It's live on the web with the API key kept on the server. GaugeBench shows exactly where AI can be trusted to read instruments, and where it can't. Thank you." |

**If you're short on time**, cut the Daily row first (keep the record-and-privacy line by saying it over the Archive), then shorten the Bench row to a single Generate.

**Optional extras** (if you have time, or for a longer cut):
- **Challenge** tab: play two rounds against the model's recorded answers. "Head to head on real benchmark tasks, no API calls."
- **Open full report** from the Archive: the scorer sanity table. "An answerer with the key scores 100%, one just outside tolerance scores 0%, random guessing about 7%."

**Tips:**
- Record each part separately and join them in Clipchamp (built into Windows). Re-recording one part is easier than redoing the whole video.
- Gemini takes a few seconds to answer. Cut the wait in editing if it drags.
- Keep the mouse still when you're not pointing at something, and move it slowly when using the loupe.
- Keyboard shortcuts look slick on camera: `G` generate, `V` validator vision, `H` hint, `L` loupe, `R` your record.
- Upload to YouTube as **Unlisted** or to Google Drive with link access, then check the link in a private window.
