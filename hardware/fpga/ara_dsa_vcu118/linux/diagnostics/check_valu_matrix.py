"""Exercise a compiled VALU test with data, tail and backpressure variations."""
import argparse
import itertools
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("simv", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    simv = args.simv.resolve(strict=True)
    args.out.mkdir(parents=True, exist_ok=False)
    rows = []
    try:
        for vl, gap, pressure, pattern in itertools.product(
                (1, 7, 8, 9, 255, 256), (0, 7), (0, 1), (0, 1)):
            name = f"vl{vl}_gap{gap}_bp{pressure}_pat{pattern}"
            command = [str(simv), "-no_save", f"+VL={vl}", f"+GAP={gap}",
                       f"+BACKPRESSURE={pressure}", f"+PATTERN={pattern}"]
            with (args.out / f"{name}.log").open("w") as log:
                result = subprocess.run(command, cwd=simv.parent, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=60)
            output = (args.out / f"{name}.log").read_text()
            passed = (result.returncode == 0 and "VALU_DISCARD_PASS" in output
                      and "Fatal:" not in output)
            rows.append({"case": name, "passed": passed})
            if not passed:
                raise RuntimeError(f"Failed: {name}; inspect saved log")
        print(f"PASS {len(rows)}/{len(rows)}: {args.out}")
    finally:
        (args.out / "results.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
