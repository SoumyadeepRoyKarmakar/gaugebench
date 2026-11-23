"""GaugeBench Studio: a local web app for interacting with the benchmark.

    python -m gaugebench app            # opens http://127.0.0.1:8765

* Bench:   generate a task live from chosen difficulty factors, read it yourself,
           get scored with the same tolerance a model gets, see what the validator
           saw and which candidates the factory rejected, and optionally ask Gemini.
* Archive: browse any generated suite in runs/ with every model's answers.

Standard library HTTP server only; the answer key of a live task never leaves the
server until you submit (or reveal) an answer.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import secrets
import tempfile
import threading
import time
import webbrowser
from collections import OrderedDict
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np
from PIL import Image

from . import __version__
from .score import score
from .spec import BASE_FACTORS, FACTOR_DOMAINS, sample_factors
from .tasks import FAMILIES, Reject

WEB = Path(__file__).parent / "web"
MAX_ATTEMPTS = 25
MAX_LIVE = 300                      # live tasks kept in memory
DEFAULT_GEMINI = "gemini-3.5-flash-lite"

FAMILY_LABELS = {
    "read_value": "Read the value", "zone_status": "Zone status", "setpoint_deviation": "Set-point deviation",
    "panel_alarm": "Panel alarm", "panel_max": "Panel max", "temporal_change": "Change over time",
    "dual_scale": "Dual scale", "level_reading": "Tank level", "panel_count": "Panel count",
}


# ---------------------------------------------------------------------------------------
# Live task generation
# ---------------------------------------------------------------------------------------
def _png_data_url(arr: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _jpg_data_url(arr: np.ndarray, size: int = 220) -> str:
    im = Image.fromarray(arr)
    im.thumbnail((size, size))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def validator_vision(scene) -> np.ndarray:
    """What the validator 'sees': the photo dimmed to grey, needle pixels in orange,
    set-point needles in magenta, glare in cyan."""
    img = scene.image.astype(np.float32)
    luma = img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114
    out = np.repeat((luma * 0.32 + 18)[..., None], 3, axis=2)

    def tint(mask: np.ndarray, rgb, strength: float = 1.0):
        a = np.clip(mask, 0, 1)[..., None] * strength
        out[:] = out * (1 - a) + np.array(rgb, np.float32) * a

    tint(scene.glare_alpha, (70, 210, 255), 0.85)
    for m in scene.setpoint_masks:
        if m is not None:
            tint(m, (255, 70, 200))
    for m in scene.needle_masks:
        tint(m, (255, 128, 30))
    return np.clip(out, 0, 255).astype(np.uint8)


class NoValidTask(ValueError):
    def __init__(self, msg: str, rejected: list):
        super().__init__(msg)
        self.rejected = rejected


def make_live_task(family: str, factors: dict, seed: int, level: int | None = None) -> dict:
    """Run the same sample -> render -> photograph -> validate loop as the suite
    generator, but for one task, and keep a record of every rejected candidate.
    With `level`, conditions are re-rolled on every attempt (as in a suite);
    otherwise the chosen factors are held fixed."""
    builder = FAMILIES[family]
    rejected = []
    t0 = time.time()
    for attempt in range(MAX_ATTEMPTS):
        rng = np.random.default_rng([seed, attempt])
        f = sample_factors(rng, level) if level else sample_factors(rng, None, factors)
        try:
            task, scene, checks = builder(rng, f)
        except Reject as e:
            rejected.append({"attempt": attempt + 1, "reasons": [{"name": f"reject:{e}", "detail": str(e)}],
                             "thumb": None})
            continue
        failed = [c for c in checks if not c.passed]
        if failed:
            rejected.append({"attempt": attempt + 1,
                             "reasons": [{"name": c.name, "detail": c.detail} for c in failed],
                             "thumb": _jpg_data_url(scene.image) if len(rejected) < 8 else None})
            continue
        break
    else:
        raise NoValidTask(f"The factory rejected all {MAX_ATTEMPTS} candidates with these settings, so it "
                          "refused to publish a task. Try easier conditions (less glare or tilt).", rejected)

    task.id = f"live-{family}-{seed:x}"
    task.seed = seed
    task.factors = f
    rec = task.to_dict()
    return {
        "task": rec,
        "image": _png_data_url(scene.image),
        "vision": _png_data_url(validator_vision(scene)),
        "checks": [c.to_dict() for c in checks],
        "rejected": rejected,
        "attempts": attempt + 1,
        "ms": round((time.time() - t0) * 1000),
        "png": scene.image,
    }


def public_view(rec: dict) -> dict:
    """The task as a reader sees it: no answer key, no true needle values."""
    t = rec["task"]
    return {
        "id": t["id"], "family": t["family"], "family_label": FAMILY_LABELS.get(t["family"], t["family"]),
        "question": _strip_format(t["question"]), "answer_type": t["answer_type"],
        "choices": t["choices"], "unit": t["unit"], "factors": t["factors"], "seed": t["seed"],
        "n_gauges": len(t["gauges"]) or 1,
        "image": rec["image"], "vision": rec["vision"], "checks": redact_checks(rec["checks"]),
        "rejected": rec["rejected"], "attempts": rec["attempts"], "ms": rec["ms"],
    }


def redact_checks(checks: list[dict]) -> list[dict]:
    """Pixel re-read details contain the true needle value, so hide them until the
    reader has committed to an answer."""
    return [{**c, "detail": "measured value hidden until you answer"} if c["name"].startswith("pixel_reread")
            else c for c in checks]


def _strip_format(q: str) -> str:
    """Hide the 'finish with ANSWER: ...' instruction written for models."""
    q = re.split(r"\s*Respond with your reasoning", q)[0].strip()
    return re.sub(r"\s*Allowed options:.*$", "", q).strip()       # shown as buttons instead


def key_view(t: dict) -> dict:
    return {"answer": t["answer"], "tolerance": t["tolerance"], "unit": t["unit"],
            "answer_type": t["answer_type"], "choices": t["choices"]}


# ---------------------------------------------------------------------------------------
# Suites on disk (Archive)
# ---------------------------------------------------------------------------------------
class Suites:
    def __init__(self, root: Path):
        self.root = Path(root)

    def names(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir() if (p / "manifest.jsonl").exists())

    def path(self, name: str) -> Path:
        if name not in self.names():
            raise KeyError(name)
        return self.root / name

    def summary(self) -> list[dict]:
        out = []
        for n in self.names():
            p = self.root / n
            with open(p / "manifest.jsonl", encoding="utf-8") as f:
                count = sum(1 for line in f if line.strip())
            models = sorted(r.stem for r in (p / "results").glob("*.jsonl")) if (p / "results").exists() else []
            out.append({"name": n, "tasks": count, "models": models, "report": (p / "report.html").exists()})
        return out

    @lru_cache(maxsize=16)
    def _load(self, name: str, stamp: float) -> dict:
        p = self.root / name
        tasks = [json.loads(l) for l in open(p / "manifest.jsonl", encoding="utf-8") if l.strip()]
        results = {}
        for rf in sorted((p / "results").glob("*.jsonl")) if (p / "results").exists() else []:
            rows = {}
            for line in open(rf, encoding="utf-8"):
                if line.strip():
                    r = json.loads(line)
                    rows[r["id"]] = r
            results[rf.stem] = rows
        return {"tasks": tasks, "results": results}

    def load(self, name: str) -> dict:
        p = self.path(name)
        stamp = max([f.stat().st_mtime for f in [p / "manifest.jsonl", *(p / "results").glob("*.jsonl")]
                     if f.exists()] or [0])
        return self._load(name, stamp)

    def listing(self, name: str) -> dict:
        d = self.load(name)
        tasks = [{
            "id": t["id"], "family": t["family"], "answer": t["answer"], "answer_type": t["answer_type"],
            "tolerance": t["tolerance"], "unit": t["unit"], "level": t["meta"].get("level"),
            "sweep": t["meta"].get("sweep_factor"), "factors": t["factors"],
        } for t in d["tasks"]]
        res = {m: {i: {"parsed": r.get("parsed"), "correct": bool(r.get("correct")),
                       "err": r.get("err_tol_units"), "error": bool(r.get("error"))}
                   for i, r in rows.items()} for m, rows in d["results"].items()}
        return {"name": name, "tasks": tasks, "results": res, "family_labels": FAMILY_LABELS}

    def detail(self, name: str, tid: str) -> dict:
        d = self.load(name)
        if tid not in {t["id"] for t in d["tasks"]}:
            raise KeyError(tid)
        full = json.loads((self.path(name) / "tasks" / tid / "task.json").read_text(encoding="utf-8"))
        full["question"] = _strip_format(full["question"])
        answers = {}
        for m, rows in d["results"].items():
            r = rows.get(tid)
            if r:
                answers[m] = {k: r.get(k) for k in ("parsed", "correct", "err_tol_units", "error", "text",
                                                     "latency_s", "served_by")}
        return {"task": full, "answers": answers}

    @lru_cache(maxsize=2048)
    def thumb(self, name: str, tid: str) -> bytes:
        im = Image.open(self.path(name) / "tasks" / tid / "image.png").convert("RGB")
        im.thumbnail((300, 300))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82)
        return buf.getvalue()


# ---------------------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------------------
class State:
    def __init__(self, suites_root: Path, gemini_model: str):
        self.suites = Suites(suites_root)
        self.gemini_model = gemini_model
        self.live: OrderedDict[str, dict] = OrderedDict()
        self.lock = threading.Lock()
        self.tmp = Path(tempfile.mkdtemp(prefix="gaugebench-"))

    def remember(self, rec: dict) -> None:
        with self.lock:
            self.live[rec["task"]["id"]] = rec
            while len(self.live) > MAX_LIVE:
                self.live.popitem(last=False)

    def get(self, tid: str) -> dict:
        with self.lock:
            if tid not in self.live:
                raise KeyError(tid)
            return self.live[tid]


def gemini_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"GaugeBench/{__version__}"

        def log_message(self, fmt, *args):      # quiet console
            pass

        # -- helpers ----------------------------------------------------------------
        def _send(self, code: int, body: bytes, ctype: str, cache: bool = False):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _err(self, code: int, msg: str):
            self._json({"error": msg}, code)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        # -- routes -----------------------------------------------------------------
        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path in ("/", "/index.html"):
                    return self._static("index.html")
                if u.path.startswith("/static/"):
                    return self._static(u.path[len("/static/"):])
                if u.path == "/api/meta":
                    return self._json({
                        "version": __version__,
                        "families": [{"id": k, "label": FAMILY_LABELS.get(k, k)} for k in FAMILIES],
                        "factors": FACTOR_DOMAINS, "base": BASE_FACTORS,
                        "gemini": {"available": gemini_available(), "model": state.gemini_model},
                        "suites": state.suites.summary(),
                    })
                if u.path == "/api/suite":
                    return self._json(state.suites.listing(q["name"]))
                if u.path == "/api/task":
                    return self._json(state.suites.detail(q["suite"], q["id"]))
                m = re.fullmatch(r"/thumb/([^/]+)/([^/]+)\.jpg", u.path)
                if m:
                    name, tid = unquote(m[1]), unquote(m[2])
                    state.suites.detail(name, tid)          # validates both
                    return self._send(200, state.suites.thumb(name, tid), "image/jpeg", cache=True)
                m = re.fullmatch(r"/suites/([^/]+)/(.+)", u.path)
                if m:
                    return self._suite_file(unquote(m[1]), unquote(m[2]))
                return self._err(404, "not found")
            except KeyError as e:
                return self._err(404, f"unknown: {e}")
            except Exception as e:                           # pragma: no cover - surfaced in UI
                return self._err(500, f"{type(e).__name__}: {e}")

        def do_POST(self):
            u = urlparse(self.path)
            try:
                body = self._body()
                if u.path == "/api/generate":
                    return self._generate(body)
                if u.path == "/api/sample-factors":
                    level = int(body.get("level", 1))
                    rng = np.random.default_rng(secrets.randbits(48))
                    return self._json({"factors": sample_factors(rng, max(1, min(5, level)))})
                if u.path == "/api/answer":
                    return self._answer(body)
                if u.path == "/api/reveal":
                    rec = state.get(body["id"])
                    return self._json({"key": key_view(rec["task"]), "checks": rec["checks"]})
                if u.path == "/api/ask":
                    return self._ask(body)
                return self._err(404, "not found")
            except NoValidTask as e:
                return self._json({"error": str(e), "rejected": e.rejected}, 422)
            except KeyError as e:
                return self._err(404, f"unknown task {e} (the server may have restarted; generate a new one)")
            except ValueError as e:
                return self._err(422, str(e))
            except Exception as e:                           # pragma: no cover
                return self._err(500, f"{type(e).__name__}: {e}")

        def _generate(self, body: dict):
            family = body.get("family", "read_value")
            if family not in FAMILIES:
                return self._err(400, f"unknown family {family}")
            factors = {}
            for k, v in (body.get("factors") or {}).items():
                if k in FACTOR_DOMAINS:
                    dom = FACTOR_DOMAINS[k]
                    match = [d for d in dom if str(d) == str(v)]
                    if match:
                        factors[k] = match[0]
            seed = int(body["seed"]) if str(body.get("seed", "")).isdigit() else secrets.randbits(40)
            level = body.get("level")
            level = max(1, min(5, int(level))) if str(level or "").isdigit() else None
            rec = make_live_task(family, {**BASE_FACTORS, **factors}, seed, level)
            state.remember(rec)
            return self._json(public_view(rec))

        def _answer(self, body: dict):
            rec = state.get(body["id"])
            t = rec["task"]
            raw = str(body.get("answer", "")).strip()
            s = score(t, f"ANSWER: {raw}")
            return self._json({"score": s, "key": key_view(t), "checks": rec["checks"]})

        def _ask(self, body: dict):
            if not gemini_available():
                return self._err(400, "No Gemini API key configured. Add GEMINI_API_KEY to .env and restart.")
            rec = state.get(body["id"])
            t = rec["task"]
            img = state.tmp / f"{t['id']}.png"
            if not img.exists():
                Image.fromarray(rec["png"]).save(img)
            from .models.gemini import Gemini
            model = Gemini(body.get("model") or state.gemini_model, max_tries=2)
            t0 = time.time()
            resp = model.answer(t, str(img))
            if resp.get("error"):
                msg = resp["error"]
                if "per day" in msg.lower() or "quota" in msg.lower():
                    msg = "Gemini's free-tier daily quota is used up. It resets at midnight Pacific time."
                elif "503" in msg or "high demand" in msg.lower():
                    msg = "Gemini is overloaded right now. Try again in a minute."
                return self._err(503, msg)
            s = score(t, resp.get("text", ""))
            return self._json({"model": model.name, "text": resp.get("text", ""), "score": s,
                               "seconds": round(time.time() - t0, 1), "key": key_view(t)})

        def _static(self, rel: str):
            p = (WEB / rel).resolve()
            if not str(p).startswith(str(WEB.resolve())) or not p.is_file():
                return self._err(404, "not found")
            ctype = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                     ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}.get(p.suffix,
                                                                                         "application/octet-stream")
            return self._send(200, p.read_bytes(), ctype)

        def _suite_file(self, name: str, rel: str):
            base = state.suites.path(name).resolve()
            p = (base / rel).resolve()
            if not str(p).startswith(str(base)) or not p.is_file() or p.suffix not in (".png", ".html", ".json"):
                return self._err(404, "not found")
            ctype = {".png": "image/png", ".html": "text/html; charset=utf-8",
                     ".json": "application/json"}[p.suffix]
            return self._send(200, p.read_bytes(), ctype, cache=p.suffix == ".png")

    return Handler


def serve(port: int = 8765, suites_root: Path = Path("runs"), open_browser: bool = True,
          gemini_model: str = DEFAULT_GEMINI, host: str = "127.0.0.1") -> None:
    state = State(suites_root, gemini_model)
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    url = f"http://{host}:{port}/"
    print(f"GaugeBench Studio running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
