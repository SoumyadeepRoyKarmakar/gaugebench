"""Run a model over a generated suite and score every answer.

Results go to <suite>/results/<model_name>.jsonl, one line per task. Runs are
resumable: tasks that already have a successful result are skipped, so an
interrupted (or rate-limited) run never pays twice for the same answer.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .models import Model
from .score import score


def load_manifest(suite: Path) -> list[dict]:
    with open(Path(suite) / "manifest.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def evaluate(suite: Path, model: Model, workers: int = 4, limit: int | None = None,
             families: list[str] | None = None, log=print) -> Path:
    suite = Path(suite)
    tasks = load_manifest(suite)
    if families:
        tasks = [t for t in tasks if t["family"] in families]
    if limit:
        tasks = tasks[:limit]
    out = suite / "results" / f"{_safe(model.name)}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    done: dict[str, dict] = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if not r.get("error"):
                done[r["id"]] = r
    todo = [t for t in tasks if t["id"] not in done]
    log(f"{model.name}: {len(tasks)} tasks, {len(done)} cached, {len(todo)} to run")

    lock = threading.Lock()
    t0 = time.time()

    def run(task: dict) -> dict:
        t1 = time.time()
        resp = model.answer(task, str(suite / task["image"]))
        rec = {"id": task["id"], "family": task["family"], "model": model.name,
               "latency_s": round(time.time() - t1, 2), **resp}
        rec.update(score(task, resp.get("text", "")))
        return rec

    n_ok = 0
    with ThreadPoolExecutor(max_workers=workers) as ex, open(out, "a", encoding="utf-8") as live:
        futs = [ex.submit(run, t) for t in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            with lock:
                done[rec["id"]] = rec
                n_ok += rec["correct"]
                live.write(json.dumps(rec, ensure_ascii=False) + "\n")   # saved immediately:
                live.flush()                                              # an interrupted run loses nothing
            if i % 10 == 0 or i == len(futs):
                log(f"  {i}/{len(futs)}  running acc {n_ok / i:.1%}  ({time.time() - t0:.0f}s)")

    with open(out, "w", encoding="utf-8") as f:
        for t in tasks:
            if t["id"] in done:
                f.write(json.dumps(done[t["id"]], ensure_ascii=False) + "\n")
    return out
