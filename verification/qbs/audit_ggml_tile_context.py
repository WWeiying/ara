#!/usr/bin/env python3
"""Recheck a completed GGML guest with unchanged inputs and a corrected checker."""
import argparse
import json
from pathlib import Path

from check_ggml_tile_context import check_output
from run_half_scale_soc import digest
from run_ggml_segmented import verify_native_build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve(strict=True)
    status = json.loads((run / "status.json").read_text())
    if status["state"] not in ("FAIL", "PASS") or status["child_pid"] is not None:
        raise ValueError("Run is not terminal")
    pins = json.loads((run / "manifest.json").read_text())
    checker = Path(__file__).with_name("check_ggml_tile_context.py").resolve()
    if str(checker) not in pins:
        raise ValueError("Original checker was not pinned")
    changed = [p for p, sha in pins.items() if digest(Path(p)) != sha]
    if any(Path(p) != checker for p in changed):
        raise ValueError(f"Source/image drift beyond checker correction: {changed}")
    qemu = Path(status["qemu"])
    verify_native_build(qemu)
    log = run / "qemu.log"
    result = check_output(log.read_text(errors="strict"))
    record = dict(state="PASS_REAUDITED", original_worker_state=status["state"],
                  original_error=status.get("error"), directory=str(run),
                  source_manifest_sha256=digest(run / "manifest.json"),
                  log_sha256=digest(log), checker_sha256=digest(checker),
                  original_checker_sha256=pins[str(checker)],
                  audit_sha256=digest(Path(__file__)),
                  non_checker_manifest_unchanged=True, result=result)
    with args.output.open("x") as target:
        json.dump(record, target, sort_keys=True, indent=2)
        target.write("\n")
    print(json.dumps(dict(state=record["state"], graphs=result["graphs"],
                         runs=len(result["runs"]))))


if __name__ == "__main__":
    main()
