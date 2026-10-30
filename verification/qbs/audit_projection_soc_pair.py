#!/usr/bin/env python3
"""Reaudit existing full-projection evidence without rewriting worker records."""
import argparse
import json
from pathlib import Path

from run_half_scale_soc import (PROJECTION_CASES, check_projection_app,
                                check_result, digest, hashes, image_files)


def audit(directory, case):
    directory = directory.resolve(strict=True)
    state = json.loads((directory / "status.json").read_text())
    entry = state["cases"][case]
    if entry.get("returncode") != 0:
        raise ValueError("Simulation did not finish successfully")
    pin = directory / "image-pins.json"
    if digest(pin) != state["image_pins_sha256"]:
        raise ValueError("Image identity record changed")
    image = json.loads(pin.read_text())
    if hashes(image_files(Path(image["simv"]))) != image["files"]:
        raise ValueError("Simulator image changed")
    inputs = directory / "input-pins.json"
    if digest(inputs) != state["input_pins_sha256"]:
        raise ValueError("Input identity record changed")
    frozen = json.loads(inputs.read_text())["elfs"]
    if hashes(map(Path, frozen)) != frozen:
        raise ValueError("Frozen ELF changed")
    executed = directory / case / "work/input.elf"
    if digest(executed) != entry["elf_sha256"]:
        raise ValueError("Executed ELF differs")
    report = directory / case / "uvm_result.json"
    check_result(report, entry["elf_sha256"], image["files"])
    log = directory / case / "work/run.vcs.log"
    checked = check_projection_app(log.read_text(), case)
    return dict(directory=str(directory), original_worker_state=state["state"],
                elf_sha256=entry["elf_sha256"], log_sha256=digest(log),
                report_sha256=digest(report), image_pins_sha256=digest(pin),
                input_pins_sha256=digest(inputs), projection=checked)


def compare(direct, context):
    if direct["image_pins_sha256"] != context["image_pins_sha256"]:
        raise ValueError("Pair did not use the same simulator image")
    d = direct["projection"]["result"]
    c = context["projection"]["result"]
    if d["checksum"] != c["checksum"]:
        raise ValueError("Output bit checksums differ")
    return dict(state="PASS", scope="one real M4/N896/K896 projection, not whole model",
                direct=direct, context=context,
                total_cycle_change_percent=100 * (int(c["timed_cycles"]) /
                                                   int(d["timed_cycles"]) - 1),
                logical_read_bytes_saved=int(d["logical_read_bytes"]) -
                                         int(c["logical_read_bytes"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direct", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(audit(args.direct, PROJECTION_CASES[0]),
                     audit(args.context, PROJECTION_CASES[1]))
    result["audit_sources"] = hashes((Path(__file__),
                                      Path(__file__).with_name("run_half_scale_soc.py")))
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, sort_keys=True)
        output.write("\n")
    print(json.dumps({key: result[key] for key in
                      ("state", "scope", "total_cycle_change_percent",
                       "logical_read_bytes_saved")}))


if __name__ == "__main__":
    main()
