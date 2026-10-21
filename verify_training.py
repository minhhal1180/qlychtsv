"""Success means baseline is clean and training exposes exactly the ten known tests."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
reports = {}
for mode, name in [("0", "baseline"), ("1", "training")]:
    output = ROOT / "test-results" / f"{name}.json"
    output.unlink(missing_ok=True)
    print(f"\n=== TRAINING_BUGS={mode}: {name} ===", flush=True)
    run = subprocess.run([sys.executable, "-X", "utf8", "-m", "tests.run_suite", "--json", str(output)],
                         env={**os.environ, "TRAINING_BUGS": mode})
    if not output.exists() or run.returncode not in (0, 1):
        raise SystemExit("Test runner did not complete.")
    reports[name] = json.loads(output.read_text(encoding="utf-8"))

baseline, training = reports["baseline"], reports["training"]
expected = {f"B{i:02d}" for i in range(1, 11)}
observed = {name.split("test_")[-1].split("_")[0] for name in training["failures"]}
passed = (baseline["total"] == training["total"] and baseline["total"] > 10
          and not baseline["failures"] and not baseline["errors"] and not baseline["skipped"]
          and not training["errors"] and not training["skipped"]
          and len(training["failures"]) == 10 and observed == expected
          and all("DefectTests.test_B" in name for name in training["failures"]))
print(f'\nBaseline: {baseline["total"]} tests, {len(baseline["failures"])} failures, {len(baseline["errors"])} errors.')
print(f'Training: {training["total"]} tests, {len(training["failures"])} failures, {len(training["errors"])} errors.')
print("PASS: all ten seeded defects detected; guard tests pass." if passed else "FAIL: outcomes differ from the required defect manifest.")
raise SystemExit(0 if passed else 1)
