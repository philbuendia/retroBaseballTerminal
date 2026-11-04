"""Retro Diamond 100-point eval harness (pass bar >= 90).

Usage:
  .venv/bin/python evals/run_evals.py --json /tmp/eval.json --threshold 90

Exits 0 iff total score >= threshold. Prints per-category earned/possible
plus failing check ids, and writes the full report to --json when given.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from scenarios import state_machine, batting, pitching, innings, hitscoring
from scenarios import terminal_client, integration

SCENARIOS = (state_machine, batting, pitching, innings, hitscoring,
             terminal_client, integration)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Retro Diamond eval harness")
    ap.add_argument("--json", default=None, help="write full report here")
    ap.add_argument("--threshold", type=int, default=90)
    args = ap.parse_args(argv)

    report = {"categories": {}, "failed_checks": [], "score": 0,
              "possible": 0, "threshold": args.threshold, "pass": False}
    for sc in SCENARIOS:
        try:
            res = sc.run()
        except Exception as exc:  # a broken scenario scores 0, never crashes
            res = {"category": getattr(sc, "CATEGORY", sc.__name__),
                   "earned": 0, "possible": getattr(sc, "WEIGHT", 0),
                   "failed": ["scenario_error"], "checks": {},
                   "error": repr(exc)}
        cat = res["category"]
        report["categories"][cat] = res
        report["score"] += res["earned"]
        report["possible"] += res["possible"]
        report["failed_checks"] += res.get("failed", [])

    report["pass"] = report["score"] >= args.threshold
    for cat, res in report["categories"].items():
        line = "%-15s %3d/%3d" % (cat, res["earned"], res["possible"])
        if res.get("failed"):
            line += "  FAILING: " + ", ".join(res["failed"])
        print(line)
    print("TOTAL %d/%d (threshold %d) -> %s"
          % (report["score"], report["possible"], args.threshold,
             "PASS" if report["pass"] else "FAIL"))
    if report["failed_checks"]:
        print("failing checks: " + ", ".join(report["failed_checks"]))
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print("wrote %s" % args.json)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
