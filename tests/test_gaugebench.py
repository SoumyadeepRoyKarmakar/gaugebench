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
