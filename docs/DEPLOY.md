# Deploying GaugeBench Studio

GaugeBench Studio is one small Python web server plus a static front end. It runs in a container on any host. The instructions below use **Render** (free tier, deploys straight from GitHub). The same image also works on Railway, Fly.io, Google Cloud Run and Hugging Face Spaces (Docker).

## How the Gemini API key is kept safe

```
browser ──(image + question only)──▶  GaugeBench server  ──(GEMINI_API_KEY)──▶  Gemini API
         ◀──(answer + score)────────                        ◀──(answer)──────────
```

- **Where the key lives.** It is set as a **secret environment variable** in the host's dashboard. The Python backend reads it and sends it straight to Google's API, and nothing else ever sees it.
- **Never in the image or the repo.** It is not in the repository or the Docker image (`.env` is git-ignored and excluded by `.dockerignore`).
- **Never sent to browsers.** No API response, page or script contains it, and the front end never talks to Google directly. The tests enforce this.

Public mode (`GAUGEBENCH_PUBLIC=1`, already set in the Dockerfile) also keeps the key from being *abused*:

| Protection | Default | Change with |
|---|---|---|
| Ask Gemini calls for the whole site, per day (UTC) | 150 | `GEMINI_DAILY_LIMIT` |
| Ask Gemini calls per visitor, per hour | 10 | `GEMINI_PER_IP_HOUR` |
| Same task asked twice | answered from cache, not paid again | |
| Visitors choosing another (pricier) model | ignored; always `GEMINI_MODEL` | `GEMINI_MODEL` |
| Task generations per visitor, per minute | 40 | `GENERATE_PER_IP_MIN` |
| Generations running at once (CPU) | 2 | `GENERATE_CONCURRENCY` |
| Live tasks kept in memory | 120 (about 70 MB at most) | `MAX_LIVE_TASKS` |
| Request size | 32 KB | |
| Developer error details | logged on the server, never sent to visitors | |
| Security headers | CSP (scripts only from the site itself), nosniff, HSTS, no framing by other sites | |
| Answer files of suites (`task.json`) | not served, so Challenge answers can't be looked up | |

Also set a budget alert or quota for the key in Google AI Studio / Google Cloud. That way a mistake can never cost more than you allow.

## Deploy on Render (about 5 minutes)

1. Sign in at [render.com](https://render.com) with your GitHub account.
2. Click **New → Blueprint** and pick the `gaugebench` repository. Render reads `render.yaml`.
3. When asked for **GEMINI_API_KEY**, paste your key. It is stored encrypted in Render. Don't put it anywhere else.
4. Click **Apply**. The first build takes a few minutes. When it finishes, your site is live at `https://gaugebench-studio.onrender.com` (or a similar name).
5. Open the site and check that **Ask Gemini** works. Then open **Logs**: the first lines show `mode: public | Ask Gemini: on (...)`.

Notes:
- **Free tier sleep.** A free Render service sleeps after 15 minutes without visitors. The next visit wakes it in about 30–60 seconds, so open the site a minute before a demo.
- **Lost state on restart.** A restart clears live tasks and today's Gemini counter. Players' Daily results, streaks and ranks are stored in their own browsers, so they are kept.
- **Changing or removing the key.** Edit it in the service's **Environment** tab. Delete it there to turn Ask Gemini off (the rest of the app keeps working).

## Any other Docker host

```powershell
docker build -t gaugebench .
docker run -p 8765:8765 -e GEMINI_API_KEY=your-key gaugebench
```

Hosts set `PORT` themselves, and the server listens on it automatically. Give the key through the host's secrets or environment settings, never as a build argument.

Without Docker (for example on a VM):

```powershell
pip install -r requirements.txt
$env:GEMINI_API_KEY = "your-key"
python -m gaugebench app --public --host 0.0.0.0 --port 8765
```

Put a reverse proxy with HTTPS (Caddy, nginx) in front of it. Behind a proxy, per-visitor limits use the `X-Forwarded-For` / `CF-Connecting-IP` header. The daily total limit protects the key no matter what.

## What the hosted site includes

- **Bench, Daily and hints:** work fully (tasks are generated live on the server).
- **Ask Gemini:** works while the key is set and within the limits.
- **Archive and Challenge:** use the suites committed in `runs/` (`sample` with recorded Gemini answers, and `instruments`). The large `runs/v2` suite (171 MB of images) is kept out of git, so it isn't on the hosted site. To include more suites, commit them under `runs/` and un-ignore them in `.gitignore`.
