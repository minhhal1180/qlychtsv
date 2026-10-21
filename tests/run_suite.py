"""Run actual assertions; JSON keeps the dual-mode verifier independent of log text."""
import argparse
import json
import sys
import unittest
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--json", required=True)
args = parser.parse_args()
suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
report = {"total": result.testsRun, "failures": [test.id() for test, _ in result.failures],
          "errors": [test.id() for test, _ in result.errors], "skipped": len(result.skipped)}
path = Path(args.json)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(report, indent=2), encoding="utf-8")
raise SystemExit(0 if result.wasSuccessful() else 1)
