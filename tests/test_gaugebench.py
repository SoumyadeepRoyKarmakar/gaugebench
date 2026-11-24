"""Tests that back the validity claims: scales are consistent, generation is
deterministic, the independent reader is accurate, the validator *rejects*
corrupted answer keys, and the scorer separates right from almost-right."""
import json

import numpy as np
import pytest

from gaugebench.generate import generate, plan_suite
from gaugebench.render import render_gauge
from gaugebench.scales import Scale
from gaugebench.score import parse_choice, parse_number, score
from gaugebench.spec import sample_factors, sample_gauge
from gaugebench.validate import check_reading, cv_read


@pytest.mark.parametrize("kind,vmin,vmax", [("linear", 0, 10), ("linear", -40, 60), ("sqrt", 0, 100), ("log", 1, 1000)])
def test_scale_roundtrip(kind, vmin, vmax):
    sc = Scale(vmin=vmin, vmax=vmax, kind=kind, major_step=10 if kind != "linear" else (vmax - vmin) / 5)
    for f in np.linspace(0, 1, 23):
        assert sc.fraction(sc.value_at_fraction(f)) == pytest.approx(f, abs=1e-9)
    assert sc.angle(vmin) == pytest.approx(sc.start_angle)
    assert sc.angle(vmax) == pytest.approx(sc.end_angle)


def test_ticks_sorted_and_ends_labeled():
    sc = Scale(vmin=0, vmax=16, major_step=2, minors_per_major=5, label_every=2)
    vals = [t.value for t in sc.ticks]
    assert vals == sorted(vals)
    assert sc.ticks[0].labeled and sc.ticks[-1].labeled


def test_independent_reader_accuracy():
    """Pixel reader agrees with the key within tolerance on the vast majority of clean dials."""
    rng = np.random.default_rng(123)
    ok = 0
    n = 120
    for _ in range(n):
        g = sample_gauge(rng, sample_factors(rng, 3))
        r = render_gauge(g)
        ok += check_reading(r, g.value, g.scale.reading_tolerance(g.value)).passed
    assert ok / n >= 0.97


def test_validator_rejects_corrupted_key():
    """Mutation test: shift the answer key by 3 tolerances -> the pixel re-read must flag it."""
    rng = np.random.default_rng(5)
    caught = 0
    n = 60
    for _ in range(n):
        g = sample_gauge(rng, sample_factors(rng, 2))
        r = render_gauge(g)
        tol = g.scale.reading_tolerance(g.value)
        if not check_reading(r, g.value, tol).passed:
            n -= 1
            continue
        caught += not check_reading(r, g.value + 3 * tol, tol).passed
    assert caught == n


def test_generation_is_deterministic(tmp_path):
    jobs = plan_suite(1, 0, ["read_value", "panel_max"])
    a = generate(tmp_path / "a", jobs, seed=11, log=lambda *x: None)
    b = generate(tmp_path / "b", jobs, seed=11, log=lambda *x: None)
    ma = (tmp_path / "a" / "manifest.jsonl").read_text(encoding="utf-8")
    mb = (tmp_path / "b" / "manifest.jsonl").read_text(encoding="utf-8")
    assert ma == mb and a["published"] == b["published"] == 2
    for rec in map(json.loads, ma.splitlines()):
        ia = (tmp_path / "a" / rec["image"]).read_bytes()
        ib = (tmp_path / "b" / rec["image"]).read_bytes()
        assert ia == ib


def test_every_published_task_passed_all_checks(tmp_path):
    jobs = plan_suite(2, 0)
    generate(tmp_path, jobs, seed=3, log=lambda *x: None)
    for line in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        tj = json.loads((tmp_path / "tasks" / rec["id"] / "task.json").read_text(encoding="utf-8"))
        assert tj["validation"] and all(c["passed"] for c in tj["validation"])


def test_parsers():
    assert parse_number("blah\nANSWER: -12.5 bar") == -12.5
    assert parse_number("ANSWER: 1,250") == 1250
    assert parse_number("ANSWER: **4.2**") == 4.2
    assert parse_number("no final line 42") is None
    assert parse_choice("I think...\nANSWER: pi-204", ["PI-201", "PI-204"]) == "PI-204"
    assert parse_choice("ANSWER: Danger", ["normal", "warning", "danger"]) == "danger"


def test_scoring_separates_right_from_near_miss():
    task = {"answer_type": "number", "answer": 5.0, "tolerance": 0.1}
    assert score(task, "ANSWER: 5.08")["correct"]
    assert not score(task, "ANSWER: 5.25")["correct"]
    ch = {"answer_type": "choice", "answer": "warning", "choices": ["normal", "warning", "danger"]}
    assert score(ch, "ANSWER: warning")["correct"] and not score(ch, "ANSWER: danger")["correct"]


def test_dual_scale_and_level_readers():
    """The independent reader also handles the inner red ring and the vertical sight-glass."""
    from gaugebench.level import render_level
    from gaugebench.spec import GaugeSpec, sample_value
    from gaugebench.tasks import DUAL_PAIRS
    rng = np.random.default_rng(9)
    for (u1, vmin, vmax, step, mn), (u2, k, off, step2, mn2) in DUAL_PAIRS:
        sc = Scale(vmin=vmin, vmax=vmax, major_step=step, minors_per_major=mn)
        sc2 = Scale(vmin=vmin * k + off, vmax=vmax * k + off, major_step=step2, minors_per_major=mn2, tick_origin=0.0)
        for _ in range(4):
            g = GaugeSpec(scale=sc, value=sample_value(rng, sc), unit=u1, secondary=sc2, secondary_unit=u2)
            r = render_gauge(g)
            v2 = g.value * k + off
            assert check_reading(r, v2, sc2.reading_tolerance(v2), ring="secondary").passed
            assert not check_reading(r, v2 + 3 * sc2.reading_tolerance(v2), sc2.reading_tolerance(v2), ring="secondary").passed
    for _ in range(20):
        sc = Scale(vmin=0, vmax=5000, major_step=1000, minors_per_major=5)
        g = GaugeSpec(scale=sc, value=sample_value(rng, sc, 0.05, 0.95), unit="L")
        r = render_level(g)
        tol = sc.reading_tolerance(g.value)
        assert check_reading(r, g.value, tol).passed
        assert not check_reading(r, g.value + 3 * tol, tol).passed


def test_gemini_adapter_offline(monkeypatch, tmp_path):
    """Adapter builds an image request, retries on 429, and parses the reply (no network)."""
    from types import SimpleNamespace
    from google.genai import errors
    import gaugebench.models.gemini as gm

    calls = []

    class FakeModels:
        def generate_content(self, model, contents, config):
            calls.append(contents)
            if len(calls) == 1:
                raise errors.ClientError(429, {"error": {"code": 429, "message": "slow down", "status": "RESOURCE_EXHAUSTED"}})
            return SimpleNamespace(text="Reading...\nANSWER: 4.2", model_version=model,
                                   candidates=[SimpleNamespace(finish_reason="STOP")],
                                   usage_metadata=SimpleNamespace(prompt_token_count=600, candidates_token_count=20))

    monkeypatch.setattr(gm.genai, "Client", lambda **kw: SimpleNamespace(models=FakeModels()))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gm.time, "sleep", lambda s: None)
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG fake")
    out = gm.Gemini("some-gemini-model").answer({"question": "Q?"}, str(img))
    assert len(calls) == 2 and out["text"].endswith("4.2") and out["input_tokens"] == 600
    assert score({"answer_type": "number", "answer": 4.2, "tolerance": 0.05}, out["text"])["correct"]


def test_label_overlap_detected():
    """Crowded printed numbers (e.g. 9 labels squeezed onto a 90-degree dial) must be flagged."""
    from gaugebench.validate import _label_clash
    sc = Scale(vmin=0, vmax=40, start_angle=-45, sweep=90, major_step=5, minors_per_major=5)
    crowded = render_gauge(sample_gauge_fixed(sc))
    assert _label_clash(crowded.labels) is not None
    roomy = render_gauge(sample_gauge_fixed(Scale(vmin=0, vmax=40, major_step=5, minors_per_major=5)))
    assert _label_clash(roomy.labels) is None


def sample_gauge_fixed(sc):
    from gaugebench.spec import GaugeSpec
    return GaugeSpec(scale=sc, value=(sc.vmin + sc.vmax) / 2, unit="rpm")


def test_studio_api_hides_key_until_answered(tmp_path):
    """The web app must never leak the answer key (or the true needle value) before
    the reader commits, and must score answers exactly like the benchmark."""
    import json as _json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from gaugebench.app import State, make_handler

    state = State(tmp_path, "unused")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(path, body=None):
        req = urllib.request.Request(base + path, data=None if body is None else _json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return _json.loads(r.read())

    try:
        meta = call("/api/meta")
        assert "read_value" in [f["id"] for f in meta["families"]]
        t = call("/api/generate", {"family": "read_value", "factors": {}, "seed": "4242"})
        blob = _json.dumps(t)
        assert "answer" not in t and "tolerance" not in t and "gauges" not in t
        assert "key=" not in blob and "cv=" not in blob
        key = state.get(t["id"])["task"]
        right = call("/api/answer", {"id": t["id"], "answer": str(key["answer"])})
        assert right["score"]["correct"] and right["key"]["answer"] == key["answer"]
        wrong = call("/api/answer", {"id": t["id"], "answer": str(key["answer"] + 10 * key["tolerance"])})
        assert not wrong["score"]["correct"]
    finally:
        httpd.shutdown()


def test_new_instrument_readers():
    """The clock-meter, vernier and digital readers recover the drawn value from pixels,
    and the vernier reader notices when the drawing does not match the key."""
    from gaugebench.instruments import (cv_read_dial_meter, cv_read_digital, cv_read_vernier,
                                        render_dial_meter, render_digital, render_vernier)
    full = 4372.45
    pos = [(full / 10 ** k) % 10 for k in (3, 2, 1, 0)]
    read = cv_read_dial_meter(render_dial_meter(pos))
    assert "".join(str(int(p)) for p in read) == "4372"
    assert max(min(abs(a - b), 10 - abs(a - b)) for a, b in zip(read, pos)) < 0.15
    for v in (3.4, 57.9, 120.1):
        got, margin = cv_read_vernier(render_vernier(v))
        assert got == pytest.approx(v) and margin > 2.0
    assert cv_read_vernier(render_vernier(57.9))[0] != pytest.approx(57.8)
    for text, style in (("-12.48", "led"), ("905.1", "lcd"), ("0.007", "vfd"), ("3", "lcd")):
        assert cv_read_digital(render_digital(text, "bar", style, "×10")) == text


def test_new_families_publish_valid_tasks(tmp_path):
    from gaugebench.generate import generate, plan_suite
    jobs = plan_suite(2, 0, ["dial_meter", "vernier", "digital_display"], [])
    summary = generate(tmp_path, jobs, seed=3, log=lambda *a: None)
    assert summary["published"] == 6
    for line in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        t = json.loads(line)
        rec = json.loads((tmp_path / t["image"]).with_name("task.json").read_text(encoding="utf-8"))
        assert all(c["passed"] for c in rec["validation"])
        assert score(t, f"ANSWER: {t['answer']}")["correct"]


def test_challenge_api_hides_key_until_answered(tmp_path):
    """Challenge rounds come from a suite on disk: the start response must carry no
    answer key, tolerance, gauge spec or model answer; only /answer reveals them."""
    import json as _json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from gaugebench.app import State, make_handler
    from gaugebench.evaluate import evaluate
    from gaugebench.models import get_model

    suite = tmp_path / "suite"
    generate(suite, plan_suite(1, 0, ["read_value", "panel_max", "vernier", "digital_display"], []),
             seed=5, log=lambda *a: None)
    evaluate(suite, get_model("near_miss"), workers=1, log=lambda *a: None)
    manifest = {t["id"]: t for t in map(_json.loads, (suite / "manifest.jsonl").read_text(encoding="utf-8").splitlines())}

    state = State(tmp_path, "unused")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(path, body):
        req = urllib.request.Request(base + path, data=_json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return _json.loads(r.read())

    try:
        d = call("/api/challenge/start", {"suite": "suite", "model": "near_miss", "n": 10, "seed": "1"})
        assert len(d["tasks"]) == 4
        for t in d["tasks"]:
            assert set(t) == {"id", "family", "family_label", "question", "answer_type", "choices", "unit", "image"}
            key = manifest[t["id"]]
            if key["answer_type"] == "number":          # the number must not appear anywhere in the round
                assert f"{key['answer']}" not in _json.dumps({k: v for k, v in t.items() if k not in ("id", "image")})
        t = d["tasks"][0]
        key = manifest[t["id"]]
        r = call("/api/challenge/answer", {"suite": "suite", "model": "near_miss", "id": t["id"],
                                           "answer": str(key["answer"])})
        assert r["score"]["correct"] and r["key"]["answer"] == key["answer"]
        assert r["model"]["correct"] is False             # near_miss is always just wrong
        try:                                              # unknown suites are refused, not read from disk
            call("/api/challenge/start", {"suite": "../suite", "model": "near_miss", "n": 3})
            assert False, "path traversal accepted"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        httpd.shutdown()


def test_hints_never_contain_the_answer():
    """Hints teach how to read an instrument; they must not leak the key for any family."""
    from gaugebench.app import hint_for, make_live_task
    from gaugebench.spec import BASE_FACTORS
    from gaugebench.tasks import FAMILIES
    for fam in FAMILIES:
        for seed in (11, 12):
            t = make_live_task(fam, {**BASE_FACTORS, "multiplier": "x10"}, seed)["task"]
            h = hint_for(t)
            assert 20 < len(h) < 400
            if t["answer_type"] == "number":
                assert f"{t['answer']}" not in h and f"{t['answer']:g}" not in h.split("division")[0]
            elif t["answer_type"] == "round":
                assert not any(f"{v:g}" in h for v in t["answer"]["readings"].values())
                assert not any(tag in h for tag in t["answer"]["readings"])
            else:
                assert t["answer"] not in h


def test_public_mode_protects_key_and_quota(tmp_path, monkeypatch):
    """Hosted for strangers: the API key is never sent to the browser, visitors can't
    choose the model, Gemini calls are capped per visitor and per day (and a task is
    never paid for twice), error details stay on the server, and the answer-holding
    task.json files of a suite are not served."""
    import json as _json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from gaugebench import app as studio
    from gaugebench.models import gemini as gem

    secret = "AIza-test-secret-value-0000"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    monkeypatch.setenv("GEMINI_DAILY_LIMIT", "3")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ASK_MODELS", raising=False)
    monkeypatch.setenv("GEMINI_PER_IP_HOUR", "2")
    calls = []

    class FakeGemini:
        def __init__(self, model, **kw):
            self.name = model
            calls.append(model)

        def answer(self, task, image_path):
            return {"text": f"ANSWER: {task['answer']}"}

    monkeypatch.setattr(gem, "Gemini", FakeGemini)
    suite = tmp_path / "suite"
    generate(suite, plan_suite(1, 0, ["read_value"], []), seed=2, log=lambda *a: None)
    state = studio.State(tmp_path, "server-model", public=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), studio.make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(path, body=None, ip="1.1.1.1"):
        req = urllib.request.Request(base + path, data=None if body is None else _json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "X-Forwarded-For": ip})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode(errors="replace"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), dict(e.headers)

    try:
        code, body, headers = call("/api/meta")
        assert code == 200 and secret not in body and _json.loads(body)["public"] is True
        assert "script-src 'self'" in headers["Content-Security-Policy"]
        assert headers["X-Content-Type-Options"] == "nosniff"
        ids = [_json.loads(call("/api/generate", {"family": "read_value", "seed": str(s)})[1])["id"]
               for s in (1, 2, 3, 4)]
        code, body, _ = call("/api/ask", {"id": ids[0], "model": "gemini:gemini-ultra-expensive"})
        assert code == 400 and _json.loads(body)["code"] == "model_unavailable"   # not on the server's list
        assert calls == []
        assert [m["id"] for m in _json.loads(call("/api/meta")[1])["ai"]["models"]] == ["gemini:server-model"]
        code, body, _ = call("/api/ask", {"id": ids[0], "model": "gemini:server-model"})
        assert code == 200 and _json.loads(body)["score"]["correct"] and secret not in body
        assert calls == ["server-model"]
        assert call("/api/ask", {"id": ids[0]})[0] == 200 and len(calls) == 1   # cached, not paid twice
        assert call("/api/ask", {"id": ids[1]})[0] == 200
        code, body, _ = call("/api/ask", {"id": ids[2]})        # 3rd paid call from this visitor this hour
        assert code == 429 and _json.loads(body)["code"] == "ai_rate_limited"
        assert call("/api/ask", {"id": ids[2]}, ip="2.2.2.2")[0] == 200       # daily total now 3
        code, body, _ = call("/api/ask", {"id": ids[3]}, ip="3.3.3.3")
        assert code == 503 and _json.loads(body)["code"] == "ai_quota" and len(calls) == 3
        code, body, _ = call("/api/answer", {"id": "live-nope"})
        assert code == 410 and _json.loads(body)["detail"] == ""   # no developer details in public mode
        code, _, _ = call("/api/generate", {"pad": "x" * 40_000})
        assert code == 413
        tid = _json.loads((suite / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[0])["id"]
        assert call(f"/suites/suite/tasks/{tid}/image.png")[0] == 200
        assert call(f"/suites/suite/tasks/{tid}/task.json")[0] == 404
        assert call("/healthz")[0] == 200
    finally:
        httpd.shutdown()


def test_fetch_suite_unpacks_and_refuses_unsafe_zips(tmp_path):
    """Hosted suites arrive as zips: a real suite unpacks, while entries escaping the
    destination or non-suite files are refused."""
    import zipfile
    from gaugebench.__main__ import fetch_suite
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("demo/manifest.jsonl", "{}\n")
        z.writestr("demo/tasks/t1/image.png", b"png")
    assert fetch_suite(str(good), tmp_path / "runs") == ["demo"]
    assert (tmp_path / "runs/demo/tasks/t1/image.png").read_bytes() == b"png"
    for name in ("../evil/manifest.jsonl", "demo/run.py"):
        bad = tmp_path / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr(name, "x")
        with pytest.raises(SystemExit):
            fetch_suite(str(bad), tmp_path / "runs2")
    assert not (tmp_path / "evil").exists()


def test_inspection_round_publishes_valid_tasks_and_scores_partial_credit(tmp_path):
    """A round is only 'correct' when every reading is in tolerance and the alarm list is
    exact; partial credit, missed alarms and false alarms are all reported."""
    from gaugebench.inspection import format_answer, parse_round
    summary = generate(tmp_path, plan_suite(3, 0, ["inspection_round"], []), seed=4, log=lambda *a: None)
    assert summary["published"] == 3
    for line in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        t = json.loads(line)
        rec = json.loads((tmp_path / t["image"]).with_name("task.json").read_text(encoding="utf-8"))
        assert all(c["passed"] for c in rec["validation"])
        assert sum(c["name"].startswith("pixel_reread") for c in rec["validation"]) == t["meta"]["n_gauges"]
        key = t["answer"]
        tags = list(key["readings"])
        assert score(t, "ANSWER: " + format_answer(key["readings"], key["alarms"]))["correct"]
        off = dict(key["readings"])
        off[tags[0]] += 3 * t["meta"]["tolerances"][tags[0]]
        s = score(t, "ANSWER: " + format_answer(off, key["alarms"]))
        assert not s["correct"] and s["round"]["readings_correct"] == len(tags) - 1
        wrong_alarms = [x for x in tags if x not in key["alarms"]][:1]
        s = score(t, "ANSWER: " + format_answer(key["readings"], wrong_alarms))
        assert not s["correct"] and s["round"]["false_alarms"] == wrong_alarms
        assert s["round"]["alarms_missed"] == sorted(key["alarms"])
    # lenient parsing: answer spread over lines, spaces in tags, 'none'
    p = parse_round("blah\nANSWER:\nPI - 301 = 4.5;\nPI-302: 1,200\n| ALARMS: none", ["PI-301", "PI-302"])
    assert p == {"readings": {"PI-301": 4.5, "PI-302": 1200.0}, "alarms": []}
    assert parse_round("no final line here", ["PI-301"]) is None


def test_evaluate_limit_keeps_earlier_answers(tmp_path):
    """A partial run (--limit / --families) must never drop answers cached by an earlier run."""
    from gaugebench.evaluate import evaluate
    from gaugebench.models import get_model
    generate(tmp_path, plan_suite(2, 0, ["read_value", "zone_status"], []), seed=8, log=lambda *a: None)
    evaluate(tmp_path, get_model("oracle"), workers=1, log=lambda *a: None)
    evaluate(tmp_path, get_model("oracle"), workers=1, limit=1, log=lambda *a: None)
    evaluate(tmp_path, get_model("oracle"), workers=1, families=["zone_status"], log=lambda *a: None)
    rows = (tmp_path / "results" / "oracle.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 4
