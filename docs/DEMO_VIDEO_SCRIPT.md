# Demo video script (target 3 minutes)

The demo is built around **GaugeBench Studio**, because judges remember what they see working. Record it on the hosted site, https://gaugebench-studio.onrender.com (see [DEPLOY.md](DEPLOY.md)), or locally with `python -m gaugebench app`. The flow is the same.

**Before recording:**
- **Hosted:** open the site a minute early so a sleeping free-tier server is awake.
- **Local:** run `python -m gaugebench app`. Both versions have the full `v2` suite in the Archive (the hosted one downloads it from the repository's `data` release when it is built).
- Make the browser full screen at 1080p (F11). Zoom the page to about 110% if the text looks small.
- Do one practice generation so everything is warm. Pick a seed you like and note it, so you can get the same task again with **Lock** (or **Copy link**).
- Check that **Ask Gemini** works once. Each new task you ask about uses one request; asking about the same task again is free.
- **Don't play today's Daily before recording** if you want to show the one-shot play; otherwise show your finished result tiles.
- Turn the sound on (speaker button in the header). The knob clicks and the stamp make the video feel alive.
- Record with OBS or the Xbox Game Bar (Win+G).
- The welcome tour appears on a browser's first visit. Close it before recording (or record it as a 5-second intro: it shows the features, the AI model and the data policy at a glance).

| Time | Show on screen | Say (roughly) |
|---|---|---|
| 0:00–0:12 | Title slide, then the Studio with an empty inspection window | "Factories still run on analogue gauges, and companies want AI to read them from camera photos. But can it? We built GaugeBench to find out." |
| 0:12–0:35 | Bench: click **Read the value**, turn the Glare, Tilt and Multiplier knobs (knobs that don't apply to an instrument dim out), press **Generate** | "GaugeBench is a factory for visual tasks: twelve kinds of question on five instruments, from pressure dials and tank levels to electricity meters, vernier calipers, and a digital display as a control. I pick an instrument and the conditions: glare, camera tilt, a ×10 multiplier. Press Generate, and a brand-new task is drawn, photographed and checked in about a second." (Optional: click **Vernier caliper** and generate one. It looks great on camera.) |
| 0:35–0:55 | Toggle **Validator vision** (`V`), then point at the factory floor (a setting that produces rejects, e.g. Panel alarm with L5) | "Before any task is published, an independent checker re-reads the needle from the pixels. This is what it sees: needle in orange, glare in cyan. Down here is the factory floor: candidates it threw away because glare hid the needle or the numbers overlapped. Nobody, human or model, is ever asked an unreadable question." |
| 0:55–1:15 | Press **Hint** (`H`) and let it show for a second, use the **loupe**, type a reading, **Submit** → stamp + tolerance strip | "Stuck? A hint teaches how to read this instrument, the size of one division, without giving the value away. Now I read it with the loupe. The tolerance is half the smallest division, the same rule the models get. Within tolerance, so it's stamped PASS, and the strip shows my reading against the key." |
| 1:15–1:35 | **Ask Gemini** → its marker lands on the strip; open its reasoning | "Now the same image and question go to Gemini. Its answer lands on the same strip, with its reasoning. It snapped to the nearest tick: close, but outside tolerance." (If it gets it right, say so. Honesty plays well.) |
| 1:35–1:55 | **Daily** tab: press Start, play one or two gauges quickly (or show finished tiles), point at the streak and countdown | "There's a Daily too: five gauges a day, the same for everyone, from a clean dial to a brutal one. One shot each, and you get a row of tiles to share, like a word game for instrument technicians." |
| 1:55–2:10 | **Challenge** tab: start a 5-round challenge, play two rounds quickly (scoreboard and pips update), show the final score; then click your score in the header to open **Your record** (rank dial, per-instrument bars) | "Or go head to head with the model on real benchmark tasks: same images, same tolerance, and its recorded answers, so no API calls. Everything you play builds your record and your rank, from Trainee up to Metrologist." |
| 2:10–2:30 | **Archive** tab (`v2` suite): gemini-3.5-flash-lite selected, family chips show accuracy; filter **Wrong**, open one task in the drawer | "Across all 384 tasks, Gemini is perfect at judging which colour zone a needle is in, but reads the exact value right only about a third of the time. It reads a digital display fine, but not a vernier. And on a whole inspection round it never got everything right. Every wrong answer is here with the image, the key and the model's reasoning." |
| 2:30–2:42 | **Open full report** from the Archive: the scorer sanity table | "And the scoring is proven fair: an answerer with the key scores 100%, one just outside tolerance scores 0%, and random guessing about 7%." |
| 2:42–3:00 | The hosted site's address bar, then the architecture slide or README | "It's live on the web, with the API key kept on the server and usage capped. Everything is reproducible from a seed, cached so we never pay twice, and extendable to new instruments. GaugeBench shows exactly where AI can be trusted to read instruments, and where it can't. Thank you." |

**If you're short on time**, cut the Challenge row first (Daily already shows the game side), then the report row.

**Tips:**
- Record each part separately and join them in Clipchamp (built into Windows). Re-recording one part is easier than redoing the whole video.
- Gemini takes a few seconds to answer. Cut the wait in editing if it drags.
- Keep the mouse still when you're not pointing at something, and move it slowly when using the loupe.
- Keyboard shortcuts look slick on camera: `G` generate, `V` validator vision, `H` hint, `L` loupe, `R` your record.
- Upload to YouTube as **Unlisted** or to Google Drive with link access, then check the link in a private window.
