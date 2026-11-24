"""GaugeBench Studio: a local web app for interacting with the benchmark.

    python -m gaugebench app            # opens http://127.0.0.1:8765

* Bench:   generate a task live from chosen difficulty factors, read it yourself,
           get scored with the same tolerance a model gets, see what the validator
           saw and which candidates the factory rejected, and optionally ask Gemini.
* Archive: browse any generated suite in runs/ with every model's answers.

Standard library HTTP server only; the answer key of a live task never leaves the
server until you submit (or reveal) an answer.

Hosting it publicly (see docs/DEPLOY.md): set GAUGEBENCH_PUBLIC=1. The Gemini API key is
read from the server's environment and is only ever used server-side; public mode adds
per-visitor and daily limits on Gemini calls, caps on generation work and request size,
hides developer error details, and sends strict security headers.
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
from collections import defaultdict, deque
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
MAX_LIVE = 300                      # live tasks kept in memory (local default)
MAX_BODY = 32 * 1024                # largest JSON request body accepted
DEFAULT_GEMINI = "gemini-3.5-flash-lite"

FAMILY_LABELS = {
    "read_value": "Read the value", "zone_status": "Zone status", "setpoint_deviation": "Set-point deviation",
    "panel_alarm": "Panel alarm", "panel_max": "Panel max", "temporal_change": "Change over time",
    "dual_scale": "Dual scale", "level_reading": "Tank level", "panel_count": "Panel count",
    "dial_meter": "Clock-dial meter", "vernier": "Vernier caliper", "digital_display": "Digital display",
}

PHOTO = ["glare", "tilt", "blur", "noise", "lighting"]
ALL_FACTORS = list(FACTOR_DOMAINS)
# which conditions each family actually uses (others are fixed by the instrument)
APPLICABLE = {
    **{f: ALL_FACTORS for f in ("read_value", "zone_status", "setpoint_deviation", "panel_alarm", "panel_max",
                                "temporal_change", "panel_count")},
    "dual_scale": ["sweep", "face", *PHOTO],
    "level_reading": ["minors_per_major", "label_every", "face", *PHOTO],
    "dial_meter": ["face", *PHOTO],
    "vernier": PHOTO,
    "digital_display": ["multiplier", "face", *PHOTO],
}


def applicable_factors(family: str, factors: dict) -> dict:
    keep = APPLICABLE.get(family, ALL_FACTORS)
    return {k: v for k, v in factors.items() if k in keep}


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
        raise NoValidTask("These conditions are too harsh: every candidate was unreadable, so no task was "
                          "published. Try less glare, tilt or blur.", rejected)

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
    }


def public_view(rec: dict) -> dict:
    """The task as a reader sees it: no answer key, no true needle values."""
    t = rec["task"]
    return {
        "id": t["id"], "family": t["family"], "family_label": FAMILY_LABELS.get(t["family"], t["family"]),
        "question": _strip_format(t["question"]), "answer_type": t["answer_type"],
        "choices": t["choices"], "unit": t["unit"], "factors": applicable_factors(t["family"], t["factors"]),
        "seed": t["seed"],
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


def _num(v: float) -> str:
    return f"{v:.6g}"


def _division_hint(scale: dict, unit: str, mult: float = 1.0) -> str:
    """How to count divisions on a scale. Uses only the printed scale, never the needle value."""
    kind = scale.get("kind", "linear")
    if kind == "log":
        return ("It's a logarithmic scale: the gap from 1 to 10 is as wide as from 10 to 100, and the small "
                "ticks between them are 2, 3, 4 ... 9.")
    if kind == "sqrt":
        return ("It's a square-root (flow) scale: the divisions are squeezed together at the low end and spread "
                "out higher up, so count them carefully.")
    div = scale["major_step"] / max(1, scale["minors_per_major"])
    text = f"Each small division on the printed scale is {_num(div)}"
    if mult and mult != 1:
        text += (f". The dial is marked ×{_num(mult)}, so multiply what you read by {_num(mult)} to get {unit}.")
    else:
        text += f" {unit}."
    return text


def hint_for(t: dict) -> str:
    """A nudge on *how* to read this instrument, never the reading itself."""
    fam = t["family"]
    g = t["gauges"][0] if t.get("gauges") else None
    unit = t.get("unit", "")
    if fam in ("read_value", "level_reading") and g:
        lead = "Read at the top surface of the liquid. " if fam == "level_reading" else "Find the two labelled ticks either side of the needle. "
        return lead + _division_hint(g["scale"], unit, g.get("multiplier", 1.0))
    if fam == "dual_scale" and g:
        secondary = t["meta"].get("asked_scale") == "secondary"
        ring = "inner red ring" if secondary else "outer black ring"
        sc = g["secondary"] if secondary else g["scale"]
        return f"The question asks for {unit}: use the {ring} and ignore the other one. " + _division_hint(sc, unit)
    if fam == "setpoint_deviation" and g:
        return ("Read the black needle and the thin red set-point needle separately, then subtract: actual minus "
                "set point. " + _division_hint(g["scale"], unit, g.get("multiplier", 1.0)))
    if fam == "temporal_change" and g:
        return ("Read photo A and photo B on the same scale, then take B minus A (negative if it fell). "
                + _division_hint(g["scale"], unit, g.get("multiplier", 1.0)))
    if fam == "zone_status":
        return "Follow the needle tip outwards to the coloured arc behind it. The tip decides, not the needle's middle."
    if fam == "panel_alarm":
        return "Check each dial's tip against its own red band. The furthest-turned needle isn't necessarily the one in red."
    if fam == "panel_max":
        return ("Each dial has a different range, so convert every needle to bar using its own numbers. "
                "The needle turned furthest is often not the highest pressure.")
    if fam == "panel_count":
        return "Go dial by dial and ask one question: is the tip on green? Count the ones that aren't."
    if fam == "dial_meter":
        return ("Start at the left dial. On each dial take the number the pointer has just passed, in that dial's own "
                "direction (follow the red arrow). Then write the digits left to right.")
    if fam == "vernier":
        return ("Whole millimetres: the last main-scale line to the left of the vernier 0. Tenths: the one vernier line "
                "that lines up exactly with a main-scale line. Remember the big numbers are centimetres.")
    if fam == "digital_display":
        return "Read the digits and the decimal point, then look at the small ×10 / ×100 indicators in the top-right corner."
    return "Take it step by step: find the scale, then the pointer, then apply anything printed on the instrument."


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
        full["factors"] = applicable_factors(full["family"], full.get("factors", {}))
        answers = {}
        for m, rows in d["results"].items():
            r = rows.get(tid)
            if r:
                answers[m] = {k: r.get(k) for k in ("parsed", "correct", "err_tol_units", "error", "text",
                                                     "latency_s", "served_by")}
        return {"task": full, "answers": answers}

    def challenge(self, name: str, model: str, n: int, family: str | None, seed: int) -> dict:
        """Pick n tasks the model has answered; return them WITHOUT answer keys."""
        d = self.load(name)
        rows = d["results"].get(model)
        if not rows:
            raise ValueError(f"{model} hasn't answered any tasks in this suite yet. Pick another opponent.")
        pool = [t for t in d["tasks"] if t["id"] in rows and not rows[t["id"]].get("error")
                and (not family or t["family"] == family)]
        if not pool:
            raise ValueError("The opponent hasn't answered any tasks of that instrument. Pick another one.")
        rng = np.random.default_rng(seed)
        # spread across families: round-robin over shuffled per-family queues
        by_fam: dict[str, list] = {}
        for t in rng.permutation(len(pool)):
            by_fam.setdefault(pool[t]["family"], []).append(pool[t])
        fams = list(by_fam)
        rng.shuffle(fams)
        picked = []
        while len(picked) < min(n, len(pool)):
            for f in fams:
                if by_fam[f] and len(picked) < n:
                    picked.append(by_fam[f].pop())
        return {"suite": name, "model": model, "tasks": [{
            "id": t["id"], "family": t["family"], "family_label": FAMILY_LABELS.get(t["family"], t["family"]),
            "question": _strip_format(t["question"]), "answer_type": t["answer_type"], "choices": t["choices"],
            "unit": t["unit"], "image": f"/suites/{name}/{t['image']}",
        } for t in picked]}

    def challenge_answer(self, name: str, model: str, tid: str, answer: str) -> dict:
        d = self.load(name)
        task = next((t for t in d["tasks"] if t["id"] == tid), None)
        if task is None:
            raise KeyError(tid)
        s = score(task, f"ANSWER: {answer}")
        r = d["results"].get(model, {}).get(tid, {})
        return {"score": s, "key": key_view(task),
                "model": {"name": model, "parsed": r.get("parsed"), "correct": bool(r.get("correct")),
                          "latency_s": r.get("latency_s"), "text": r.get("text", "")}}

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
class BadRequest(ValueError):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; "
       "frame-ancestors 'self'; base-uri 'none'; form-action 'self'; object-src 'none'")


class TaskExpired(KeyError):
    """A live task is no longer held by the server (restart, or evicted after MAX_LIVE newer tasks)."""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Limits:
    """Usage limits. Locally everything is unlimited; in public mode they protect the
    server's Gemini quota (and bill) and its CPU/memory from any one visitor."""

    def __init__(self, public: bool):
        self.public = public
        self.gemini_daily = _env_int("GEMINI_DAILY_LIMIT", 150 if public else 0)       # 0 = unlimited
        self.gemini_per_ip_hour = _env_int("GEMINI_PER_IP_HOUR", 10 if public else 0)
        self.generate_per_ip_min = _env_int("GENERATE_PER_IP_MIN", 40 if public else 0)
        self.max_live = _env_int("MAX_LIVE_TASKS", 120 if public else MAX_LIVE)
        self.gen_slots = threading.BoundedSemaphore(max(1, _env_int("GENERATE_CONCURRENCY", 2 if public else 8)))
        self._lock = threading.Lock()
        self._hits: dict[tuple, deque] = defaultdict(deque)
        self._day = ""
        self._gemini_today = 0

    def _today(self) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        if day != self._day:
            self._day, self._gemini_today = day, 0

    def allow(self, kind: str, ip: str, limit: int, window_s: float) -> bool:
        """Sliding-window rate limit per (kind, visitor)."""
        if not limit:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[(kind, ip)]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self._hits) > 50_000:                # forget idle visitors
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > 3600]:
                    del self._hits[k]
            return True

    def gemini_left(self) -> int | None:
        if not self.gemini_daily:
            return None
        with self._lock:
            self._today()
            return max(0, self.gemini_daily - self._gemini_today)

    def take_gemini(self) -> bool:
        with self._lock:
            self._today()
            if self.gemini_daily and self._gemini_today >= self.gemini_daily:
                return False
            self._gemini_today += 1
            return True

    def give_back_gemini(self) -> None:
        """A call that failed before Gemini answered doesn't count against the day."""
        with self._lock:
            self._gemini_today = max(0, self._gemini_today - 1)


class State:
    def __init__(self, suites_root: Path, gemini_model: str, public: bool = False):
        self.suites = Suites(suites_root)
        self.gemini_model = gemini_model
        self.public = public
        self.limits = Limits(public)
        self.live: OrderedDict[str, dict] = OrderedDict()
        self.asked: OrderedDict[str, dict] = OrderedDict()   # Gemini answers, so a task is never paid for twice
        self.lock = threading.Lock()
        self.tmp = Path(tempfile.mkdtemp(prefix="gaugebench-"))

    def remember(self, rec: dict) -> None:
        with self.lock:
            self.live[rec["task"]["id"]] = rec
            while len(self.live) > self.limits.max_live:
                self.live.popitem(last=False)

    def get(self, tid: str) -> dict:
        with self.lock:
            if tid not in self.live:
                raise TaskExpired(tid)
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
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.send_header("Content-Security-Policy", CSP)
            if state.public:
                self.send_header("Strict-Transport-Security", "max-age=31536000")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _ip(self) -> str:
            """The visitor's address. Behind a hosting proxy the socket peer is the proxy,
            so use the address the proxy reports."""
            if state.public:
                for h in ("CF-Connecting-IP", "True-Client-IP", "X-Real-IP"):
                    if self.headers.get(h):
                        return self.headers[h].strip()
                fwd = self.headers.get("X-Forwarded-For")
                if fwd:
                    return fwd.split(",")[0].strip()
            return self.client_address[0]

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _err(self, code: int, msg: str, kind: str = "error", detail: str = ""):
            """msg is for people (short, plain); detail is for developers (shown only in the
            browser console locally; a public server logs it and never sends it)."""
            if state.public:
                if detail:
                    print(f"[{kind}] {urlparse(self.path).path}: {detail}", flush=True)
                detail = ""
            self._json({"error": msg, "code": kind, "detail": detail}, code)

        def _body(self) -> dict:
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise BadRequest("That request wasn't understood.")
            if n > MAX_BODY:
                raise BadRequest("That request is too large.", 413)
            if n <= 0:
                return {}
            try:
                body = json.loads(self.rfile.read(n))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise BadRequest("That request wasn't understood.")
            if not isinstance(body, dict):
                raise BadRequest("That request wasn't understood.")
            return body

        def do_HEAD(self):
            return self.do_GET()

        # -- routes -----------------------------------------------------------------
        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path in ("/", "/index.html"):
                    return self._static("index.html")
                if u.path == "/healthz":
                    return self._json({"ok": True, "version": __version__})
                if u.path.startswith("/static/"):
                    return self._static(u.path[len("/static/"):])
                if u.path == "/api/meta":
                    return self._json({
                        "version": __version__,
                        "families": [{"id": k, "label": FAMILY_LABELS.get(k, k)} for k in FAMILIES],
                        "factors": FACTOR_DOMAINS, "base": BASE_FACTORS, "applicable": APPLICABLE,
                        "gemini": {"available": gemini_available(), "model": state.gemini_model,
                                   "left_today": state.limits.gemini_left()},
                        "public": state.public,
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
                return self._err(404, "That page doesn't exist.", "not_found")
            except KeyError as e:
                return self._err(404, "We couldn't find that task or suite. It may have been moved or regenerated.",
                                 "not_found", f"unknown key {e}")
            except Exception as e:                           # pragma: no cover - surfaced in UI
                return self._err(500, "Something went wrong on our side. Please try again.", "server",
                                 f"{type(e).__name__}: {e}")

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
                if u.path == "/api/hint":
                    if body.get("suite"):                    # a Challenge round (task from a suite on disk)
                        tasks = state.suites.load(body["suite"])["tasks"]
                        task = next((t for t in tasks if t["id"] == body["id"]), None)
                        if task is None:
                            raise KeyError(body["id"])
                    else:                                    # a live Bench / Daily task
                        task = state.get(body["id"])["task"]
                    return self._json({"hint": hint_for(task)})
                if u.path == "/api/challenge/start":
                    n = max(1, min(30, int(body.get("n", 10))))
                    seed = int(body["seed"]) if str(body.get("seed", "")).isdigit() else secrets.randbits(32)
                    return self._json(state.suites.challenge(body["suite"], body["model"], n,
                                                             body.get("family") or None, seed))
                if u.path == "/api/challenge/answer":
                    return self._json(state.suites.challenge_answer(body["suite"], body["model"], body["id"],
                                                                    str(body.get("answer", "")).strip()))
                return self._err(404, "That action doesn't exist.", "not_found")
            except BadRequest as e:
                return self._err(e.status, str(e), "bad_request")
            except NoValidTask as e:
                return self._json({"error": str(e), "code": "no_valid_task", "rejected": e.rejected}, 422)
            except TaskExpired as e:
                return self._err(410, "This task has expired. Press Generate for a new one.", "task_expired",
                                 f"live task {e} is no longer in memory (server restarted or task evicted)")
            except KeyError as e:
                return self._err(404, "We couldn't find that task or suite. It may have been moved or regenerated.",
                                 "not_found", f"unknown key {e}")
            except ValueError as e:
                return self._err(422, str(e), "invalid")
            except Exception as e:                           # pragma: no cover
                return self._err(500, "Something went wrong on our side. Please try again.", "server",
                                 f"{type(e).__name__}: {e}")

        def _generate(self, body: dict):
            family = body.get("family", "read_value")
            if family not in FAMILIES:
                return self._err(400, "That instrument isn't available.", "invalid", f"unknown family {family}")
            factors = {}
            for k, v in (body.get("factors") or {}).items():
                if k in FACTOR_DOMAINS:
                    dom = FACTOR_DOMAINS[k]
                    match = [d for d in dom if str(d) == str(v)]
                    if match:
                        factors[k] = match[0]
            seed = int(body["seed"]) if str(body.get("seed", "")).isdigit() else secrets.randbits(40)
            seed %= 2 ** 63
            level = body.get("level")
            level = max(1, min(5, int(level))) if str(level or "").isdigit() else None
            lim = state.limits
            if not lim.allow("generate", self._ip(), lim.generate_per_ip_min, 60):
                return self._err(429, "You're generating tasks very quickly. Take a breath and try again in a minute.",
                                 "rate_limited")
            if not lim.gen_slots.acquire(timeout=20):
                return self._err(503, "The bench is busy with other visitors. Try again in a few seconds.", "busy")
            try:
                rec = make_live_task(family, {**BASE_FACTORS, **factors}, seed, level)
            finally:
                lim.gen_slots.release()
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
                msg = ("Ask Gemini is turned off on this server." if state.public
                       else "Ask Gemini isn't set up on this computer yet.")
                return self._err(400, msg, "gemini_missing", "No GEMINI_API_KEY found. Add it to .env and restart.")
            rec = state.get(body["id"])
            t = rec["task"]
            with state.lock:
                cached = state.asked.get(t["id"])
            if cached:                                       # the same task never costs a second request
                return self._json(cached)
            lim = state.limits
            if not lim.allow("gemini", self._ip(), lim.gemini_per_ip_hour, 3600):
                return self._err(429, "You've asked Gemini a lot in the last hour. Read a few yourself and try "
                                      "again later.", "gemini_rate_limited")
            if not lim.take_gemini():
                return self._err(503, "Ask Gemini has reached today's limit on this server. Try again tomorrow.",
                                 "gemini_quota")
            # always the server's own model: visitors can't pick a different (pricier) one
            from .models.gemini import Gemini
            img = state.tmp / f"{secrets.token_hex(8)}.png"
            img.write_bytes(base64.b64decode(rec["image"].split(",", 1)[1]))
            try:
                model = Gemini(state.gemini_model, max_tries=2)
                t0 = time.time()
                resp = model.answer(t, str(img))
            except BaseException:
                lim.give_back_gemini()
                raise
            finally:
                img.unlink(missing_ok=True)
            if resp.get("error"):
                lim.give_back_gemini()
                raw = resp["error"]
                low = raw.lower()
                if "per day" in low or "quota" in low:
                    msg, kind = "Gemini has used up today's free requests. Try again tomorrow.", "gemini_quota"
                elif "503" in raw or "high demand" in low or "429" in raw:
                    msg, kind = "Gemini is busy right now. Try again in a minute.", "gemini_busy"
                elif "network" in low or "timeout" in low or "deadline" in low:
                    msg, kind = "Couldn't reach Gemini. Check your internet connection and try again.", "gemini_network"
                else:
                    msg, kind = "Gemini couldn't answer this time. Please try again.", "gemini_error"
                return self._err(503, msg, kind, raw)
            s = score(t, resp.get("text", ""))
            out = {"model": model.name, "text": resp.get("text", ""), "score": s,
                   "seconds": round(time.time() - t0, 1), "key": key_view(t)}
            with state.lock:
                state.asked[t["id"]] = out
                while len(state.asked) > state.limits.max_live:
                    state.asked.popitem(last=False)
            return self._json(out)

        def _static(self, rel: str):
            p = (WEB / rel).resolve()
            if not p.is_relative_to(WEB.resolve()) or not p.is_file():
                return self._err(404, "not found")
            ctype = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                     ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}.get(p.suffix,
                                                                                         "application/octet-stream")
            return self._send(200, p.read_bytes(), ctype)

        def _suite_file(self, name: str, rel: str):
            base = state.suites.path(name).resolve()
            p = (base / rel).resolve()
            # images and the report only: task.json holds the answer key (Challenge rounds use these images)
            if not p.is_relative_to(base) or not p.is_file() or not (p.suffix == ".png" or p.name == "report.html"):
                return self._err(404, "not found")
            ctype = {".png": "image/png", ".html": "text/html; charset=utf-8"}[p.suffix]
            return self._send(200, p.read_bytes(), ctype, cache=p.suffix == ".png")

    return Handler


def serve(port: int = 8765, suites_root: Path = Path("runs"), open_browser: bool = True,
          gemini_model: str = DEFAULT_GEMINI, host: str = "127.0.0.1", public: bool = False) -> None:
    state = State(suites_root, gemini_model, public)
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.request_queue_size = 64
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}/"
    lim = state.limits
    print(f"GaugeBench Studio running at {url}  (Ctrl+C to stop)", flush=True)
    print(f"  mode: {'public' if public else 'local'} | Ask Gemini: "
          f"{'on (' + gemini_model + ')' if gemini_available() else 'off (no GEMINI_API_KEY)'} | suites: "
          f"{', '.join(state.suites.names()) or 'none'}", flush=True)
    if public:
        print(f"  limits: Gemini {lim.gemini_daily or 'unlimited'}/day, {lim.gemini_per_ip_hour}/visitor/hour; "
              f"generate {lim.generate_per_ip_min}/visitor/min", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
