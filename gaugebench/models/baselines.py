"""Offline reference 'models'. They cost nothing and prove the scorer works:

* oracle     — returns the answer key. Must score 100% (scorer/parsing sanity).
* near_miss  — answer key shifted by 2.5x the tolerance / a wrong option.
               Must score 0%: shows scoring separates right from *almost* right.
* random     — uniform guess over the dial range / options. Chance level.
* shortcut   — cheap heuristics a model might fall back on without real reading:
               mid-scale for numbers, 'normal' for zones, '1' for counts, and for
               panel_max the gauge whose needle is turned furthest (ignores the ranges).
"""
from __future__ import annotations

import random

from .base import Model


class Oracle(Model):
    name = "oracle"

    def answer(self, task, image_path):
        return {"text": f"ANSWER: {task['answer']}"}


class NearMiss(Model):
    name = "near_miss"

    def answer(self, task, image_path):
        if task["answer_type"] == "number":
            off = 2.5 * float(task["tolerance"]) or 1      # exact-count questions: off by one
            return {"text": f"ANSWER: {float(task['answer']) + off}"}
        wrong = [c for c in task["choices"] if c != task["answer"]]
        return {"text": f"ANSWER: {wrong[0]}"}


class RandomGuess(Model):
    name = "random"

    def answer(self, task, image_path):
        rng = random.Random(task["id"])
        if task["answer_type"] == "choice":
            return {"text": f"ANSWER: {rng.choice(task['choices'])}"}
        if task["family"] == "panel_count":
            return {"text": f"ANSWER: {rng.randint(0, task['meta']['n_gauges'])}"}
        g = task["gauges"][0]
        if task["family"] == "dual_scale" and task["meta"]["asked_scale"] == "secondary":
            g = {"scale": g["secondary"], "multiplier": 1.0}
        lo, hi = g["scale"]["vmin"] * g["multiplier"], g["scale"]["vmax"] * g["multiplier"]
        if task["family"] in ("setpoint_deviation", "temporal_change"):
            span = hi - lo
            return {"text": f"ANSWER: {rng.uniform(-span, span)}"}
        return {"text": f"ANSWER: {rng.uniform(lo, hi)}"}


class Shortcut(Model):
    name = "shortcut"

    def answer(self, task, image_path):
        fam = task["family"]
        if fam == "zone_status":
            return {"text": "ANSWER: normal"}
        if fam == "panel_max":
            return {"text": f"ANSWER: {task['meta']['trap_tag']}"}
        if fam == "panel_alarm":
            return {"text": f"ANSWER: {task['choices'][0]}"}
        if fam == "panel_count":
            return {"text": "ANSWER: 1"}
        if fam in ("setpoint_deviation", "temporal_change"):
            return {"text": "ANSWER: 0"}
        g = task["gauges"][0]
        mid = (g["scale"]["vmin"] + g["scale"]["vmax"]) / 2  # ignores multiplier and non-linearity
        return {"text": f"ANSWER: {mid}"}


BASELINES = {m.name: m for m in (Oracle, NearMiss, RandomGuess, Shortcut)}
