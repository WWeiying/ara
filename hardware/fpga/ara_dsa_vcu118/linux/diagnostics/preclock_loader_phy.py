#!/usr/bin/env python3
"""Guarded cold-board PHY-clock sequencing experiment, not a production fix."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tools", type=Path, required=True)
    p.add_argument("--probes", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--vivado", required=True)
    p.add_argument("--xsct", required=True)
    a = p.parse_args()
    sys.path.insert(0, str(a.tools / "ethernet"))
    import ara_init
    a.out.mkdir(parents=True, exist_ok=False)
    report = {"diagnostic_only": True, "passed": False, "memory_writes": False}
    try:
        with ara_init.load.VivadoTransport(a.out / "guard", vivado=a.vivado,
                                           probes=a.probes) as t:
            report["fresh_guard"] = ara_init.fresh_guard(t)
        with (a.out / "xsct.log").open("w") as log:
            subprocess.run([a.xsct, str(Path(__file__).with_suffix(".tcl")),
                            "--cold-board-confirmed"], stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=60)
        report.update(passed=True, state="clock_prepared_firmware_not_started")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report.update(state="failed", error=str(exc))
    finally:
        (a.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
