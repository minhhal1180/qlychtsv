"""Run a bounded, read-only availability smoke against the user-provided partner URL."""
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if __name__=="__main__":
    # The script intentionally has no load switch while target/SRS/accounts are unresolved.
    raise SystemExit(subprocess.run(["node",str(ROOT/"submission/partner/tooling/partner-smoke.cjs")],cwd=ROOT).returncode)
