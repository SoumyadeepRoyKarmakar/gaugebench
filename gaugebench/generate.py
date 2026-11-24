"""Suite generation: sample -> render -> photograph -> validate -> publish (or reject).

Output layout (one *task package* per folder):

    <out>/
      manifest.jsonl            one line per published task (question, answer key, factors...)
      generation_log.json       counts of attempts, acceptances and rejection reasons
      tasks/<task_id>/image.png
      tasks/<task_id>/task.json task + full validation evidence (every check and its detail)
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from . import __version__
from .spec import FACTOR_DOMAINS, BASE_FACTORS, sample_factors
from .tasks import FAMILIES, Reject

MAX_ATTEMPTS = 25


def _seed(*parts) -> int:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:12], 16)


def plan_suite(n_per_family: int, sweep_per_value: int, families: list[str] | None = None,
               sweep_factors: list[str] | None = None) -> list[dict]:
    """A list of job descriptions. 'mixed' jobs sample a difficulty level 1..5;
    'sweep' jobs vary exactly one factor from the clean base (read_value family)."""
    jobs = []
    for fam in families or list(FAMILIES):
        for k in range(n_per_family):
            jobs.append({"kind": "mixed", "family": fam, "level": 1 + k % 5, "k": k})
    for factor in sweep_factors if sweep_factors is not None else list(FACTOR_DOMAINS):
        for value in FACTOR_DOMAINS[factor]:
            for k in range(sweep_per_value):
                jobs.append({"kind": "sweep", "family": "read_value", "factor": factor,
                             "value": value, "k": k})
    return jobs


def generate(out: Path, jobs: list[dict], seed: int = 0, log=print) -> dict:
    out = Path(out)
    (out / "tasks").mkdir(parents=True, exist_ok=True)
    manifest = []
    rejections: Counter = Counter()
    attempts = 0
    t0 = time.time()
    for j, job in enumerate(jobs):
        builder = FAMILIES[job["family"]]
        for attempt in range(MAX_ATTEMPTS):
            attempts += 1
            s = _seed(seed, job["kind"], job["family"], job.get("factor"), job.get("value"),
                      job.get("level"), job["k"], attempt)
            rng = np.random.default_rng(s)
            if job["kind"] == "mixed":
                factors = sample_factors(rng, job["level"])
            else:
                factors = sample_factors(rng, None, {job["factor"]: job["value"]})
            try:
                task, scene, checks = builder(rng, factors)
            except Reject as e:
                rejections[f"reject:{e}"] += 1
                continue
            failed = [c for c in checks if not c.passed]
            if failed:
                for c in failed:
                    rejections[c.name] += 1
                continue
            break
        else:
            log(f"  !! gave up on job {job} after {MAX_ATTEMPTS} attempts")
            continue

        if job["kind"] == "mixed":
            tid = f"{job['family']}-L{job['level']}-{job['k']:04d}"
        else:
            tid = f"sweep-{job['factor']}-{job['value']}-{job['k']:03d}"
        for name, k in task.meta.get("camera_retries", {}).items():   # re-shot cameras in an inspection round
            rejections[name] += k                                      # count as rejected candidates too
            attempts += k
        task.id = tid
        task.seed = s
        task.factors = factors
        task.meta.update({"suite_kind": job["kind"], "level": job.get("level"),
                          "sweep_factor": job.get("factor"), "attempts": attempt + 1,
                          "generator_version": __version__})
        d = out / "tasks" / tid
        d.mkdir(parents=True, exist_ok=True)
        Image.fromarray(scene.image).save(d / "image.png", optimize=True)
        rec = task.to_dict()
        rec["image"] = f"tasks/{tid}/image.png"
        (d / "task.json").write_text(json.dumps({**rec, "validation": [c.to_dict() for c in checks]},
                                                indent=2, ensure_ascii=False), encoding="utf-8")
        manifest.append(rec)
        if (j + 1) % 25 == 0:
            log(f"  {j + 1}/{len(jobs)} tasks  ({time.time() - t0:.0f}s)")

    with open(out / "manifest.jsonl", "w", encoding="utf-8") as f:
        for rec in manifest:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    summary = {
        "generator_version": __version__, "seed": seed, "jobs": len(jobs), "published": len(manifest),
        "attempts": attempts, "rejected_attempts": attempts - len(manifest),
        "rejection_reasons": dict(rejections.most_common()), "seconds": round(time.time() - t0, 1),
        "families": dict(Counter(r["family"] for r in manifest)),
    }
    (out / "generation_log.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
