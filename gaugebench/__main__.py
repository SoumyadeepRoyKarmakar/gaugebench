"""Command line interface.

    python -m gaugebench generate  runs/demo --per-family 20 --sweep 6 --seed 7
    python -m gaugebench evaluate  runs/demo --model oracle
    python -m gaugebench evaluate  runs/demo --model claude:claude-opus-5-5 --workers 4
    python -m gaugebench evaluate  runs/demo --model claude:claude-opus-5-5 --blind --limit 60
    python -m gaugebench evaluate  runs/demo --model gemini:<model-id> --workers 1   (free tier)
    python -m gaugebench list-models gemini
    python -m gaugebench report    runs/demo
    python -m gaugebench all       runs/demo --per-family 20 --sweep 6   (generate + baselines + report)
    python -m gaugebench app                                              (interactive web app)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .evaluate import evaluate
from .generate import generate, plan_suite
from .models import get_model
from .models.baselines import BASELINES
from .report import build_report
from .spec import FACTOR_DOMAINS
from .tasks import FAMILIES


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Read KEY=VALUE lines from a local, git-ignored .env file into the environment
    (variables already set in the shell win). Keeps API keys out of code and out of git."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def fetch_suite(src: str, dest: Path) -> list[str]:
    """Unpack a zipped suite (URL or local file) into dest. Refuses entries that would
    land outside dest, and anything that isn't a suite file."""
    import io
    import shutil
    import urllib.request
    import zipfile

    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src, timeout=300) as r:
            data = io.BytesIO(r.read())
    else:
        data = open(src, "rb")
    dest = dest.resolve()
    names = set()
    with data, zipfile.ZipFile(data) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest) or target.suffix not in (".png", ".json", ".jsonl", ".html"):
                raise SystemExit(f"refusing suspicious zip entry: {info.filename}")
            names.add(Path(info.filename).parts[0])
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as fsrc, open(target, "wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)
    for n in names:
        if not (dest / n / "manifest.jsonl").exists():
            raise SystemExit(f"{src}: '{n}' is not a suite (no manifest.jsonl)")
    return sorted(names)


def main(argv=None) -> int:
    _load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="gaugebench")
    sub = p.add_subparsers(dest="cmd", required=True)

    def gen_args(sp):
        sp.add_argument("--per-family", type=int, default=20, help="mixed-difficulty tasks per family")
        sp.add_argument("--sweep", type=int, default=6, help="tasks per value in single-factor sweeps (0 = none)")
        sp.add_argument("--seed", type=int, default=7)
        sp.add_argument("--families", nargs="*", choices=list(FAMILIES))
        sp.add_argument("--sweep-factors", nargs="*", choices=list(FACTOR_DOMAINS))

    g = sub.add_parser("generate", help="generate and validate a task suite")
    g.add_argument("suite", type=Path)
    gen_args(g)

    e = sub.add_parser("evaluate", help="run a model on a suite")
    e.add_argument("suite", type=Path)
    e.add_argument("--model", required=True, help=f"{' | '.join(BASELINES)} | claude:<model-id> | gemini:<model-id>")
    e.add_argument("--effort", default=None,
                   help="Claude effort low|medium|high|xhigh|max (default medium); Gemini thinking level, optional")
    e.add_argument("--blind", action="store_true", help="ablation: send the question without the image")
    e.add_argument("--workers", type=int, default=4)
    e.add_argument("--limit", type=int)
    e.add_argument("--families", nargs="*", choices=list(FAMILIES))

    r = sub.add_parser("report", help="build report.html")
    r.add_argument("suite", type=Path)

    fs = sub.add_parser("fetch-suite", help="download / unpack suite zips (e.g. from a GitHub release) into runs/")
    fs.add_argument("sources", nargs="+", help="https:// URLs or local .zip files, each holding <suite>/manifest.jsonl ...")
    fs.add_argument("--dest", type=Path, default=Path("runs"))

    lm = sub.add_parser("list-models", help="list model ids your API key can use")
    lm.add_argument("provider", choices=["gemini"])

    a = sub.add_parser("all", help="generate + offline baselines + report (no API calls)")
    a.add_argument("suite", type=Path)
    gen_args(a)

    ap = sub.add_parser("app", help="open GaugeBench Studio, the interactive web app")
    public_env = os.environ.get("GAUGEBENCH_PUBLIC", "").lower() in ("1", "true", "yes")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8765)),
                    help="port to listen on (default: $PORT or 8765)")
    ap.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0" if public_env else "127.0.0.1"),
                    help="address to bind (use 0.0.0.0 inside a container)")
    ap.add_argument("--public", action="store_true", default=public_env,
                    help="hosting for other people: usage limits, no error details (or GAUGEBENCH_PUBLIC=1)")
    ap.add_argument("--suites", type=Path, default=Path("runs"), help="folder holding generated suites")
    ap.add_argument("--gemini-model", default=os.environ.get("GEMINI_MODEL"), help="model id for the Ask Gemini button")
    ap.add_argument("--no-browser", action="store_true")

    args = p.parse_args(argv)
    if args.cmd == "app":
        from .app import DEFAULT_GEMINI, serve
        serve(args.port, args.suites, not (args.no_browser or args.public), args.gemini_model or DEFAULT_GEMINI,
              args.host, args.public)
        return 0
    if args.cmd == "fetch-suite":
        for src in args.sources:
            print(f"{src} -> {', '.join(fetch_suite(src, args.dest))}")
        return 0
    if args.cmd == "list-models":
        from .models.gemini import list_models
        print("\n".join(list_models()))
        return 0
    if args.cmd in ("generate", "all"):
        jobs = plan_suite(args.per_family, args.sweep, args.families, args.sweep_factors)
        print(f"generating {len(jobs)} tasks -> {args.suite}")
        print(json.dumps(generate(args.suite, jobs, args.seed), indent=2, ensure_ascii=False))
    if args.cmd == "evaluate":
        evaluate(args.suite, get_model(args.model, args.effort, args.blind), args.workers, args.limit, args.families)
    if args.cmd == "all":
        for name in BASELINES:
            evaluate(args.suite, get_model(name))
    if args.cmd in ("report", "all", "evaluate"):
        print(f"report: {build_report(args.suite)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
