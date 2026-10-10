#!/usr/bin/env python3
"""Bounded read-only DVE metadata session using one already accepted test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE = ROOT / "verification/out/gap79-old-image-20261006-01"
SCOPE = ("ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane."
         "i_operand_queues.i_operand_queue_mfpu_a.genblk3.genblk1[0].leading_zero_e16_i")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists() or not output.is_relative_to(ROOT / "verification/out"):
        parser.error("fresh output under verification/out required")
    state = json.loads((BASELINE / "status.json").read_text())
    if state.get("coverage_status") != "COMPLETE" or state.get("aggregate_passed") != 685:
        parser.error("completed 685 baseline required")
    case = BASELINE / "results/vgap79_add16"
    audit = json.loads((case / "audit.json").read_text())
    if audit.get("status") != "PASS" or audit.get("checks", 0) <= 0:
        parser.error("independently accepted test required")
    inputs = (BASELINE / "combined-inputs.txt").read_text().splitlines()
    if audit["vdb"] not in inputs[1:]:
        parser.error("test not admitted to baseline")
    image_pins = json.loads((BASELINE / "source-pins.json").read_text())
    plan = json.loads((ROOT / "verification/out/closure90-current-20261005-01/plan.json").read_text())
    design = Path(plan["design_vdb"])
    design_xml = design / "snps/coverage/db/design/verilog.design.xml"
    if str(design) != inputs[0]:
        parser.error("foreign design")
    for filename, expected in plan["image"].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
            parser.error("old image drift")
    for filename in (case / "input.elf",):
        if hashlib.sha256(filename.read_bytes()).hexdigest() != image_pins[str(filename)]:
            parser.error("accepted ELF drift")
    tools = [shutil.which(name) for name in ("xvfb-run", "dve")]
    if not all(tools):
        parser.error("host DVE/Xvfb missing")
    output.mkdir()
    (output / "inputs.txt").write_text(inputs[0] + "\n" + audit["vdb"] + "\n")
    pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (design_xml, case / "audit.json", BASELINE / "status.json",
             BASELINE / "combined-inputs.txt", HERE / "discover_lzc_vectors.tcl",
             HERE / "export_dve_coverage.tcl", Path(__file__).resolve())}
    (output / "pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    command = [tools[0], "-a", tools[1], "-full64", "-cov", "-script",
               str(HERE / "export_dve_coverage.tcl")]
    (output / "command.json").write_text(json.dumps(command) + "\n")
    env = dict(os.environ, DVE_COVERAGE_OUTPUT=str(output), LZC_DISCOVERY_SCOPE=SCOPE,
               DVE_REVIEWED_WAIVERS=str(HERE / "discover_lzc_vectors.tcl"))
    status = dict(status="RUNNING", scope=SCOPE, no_exclusions=True, application_approval=False)
    (output / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    try:
        with (output / "dve.log").open("w") as log:
            subprocess.run(command, cwd=output, env=env, stdout=log,
                           stderr=subprocess.STDOUT, timeout=300, check=True)
        text = (output / "DVEfiles/dve_gui.log").read_text()
        if ("LZC_READ_ONLY_DISCOVERY_DONE" not in text or "DVE_COVERAGE_EXPORT_DONE" not in text
                or "DVE_COVERAGE_EXPORT_FAILED" in text):
            raise RuntimeError("native discovery did not complete")
        for filename, expected in pins.items():
            if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
                raise RuntimeError("bound evidence changed")
        status.update(status="DISCOVERY_COMPLETE_NOT_QUALIFICATION")
    except Exception as error:
        status.update(status="FAILED", reason=f"{type(error).__name__}: {error}")
        raise
    finally:
        (output / "status.json").write_text(json.dumps(status, indent=2) + "\n")


if __name__ == "__main__":
    main()
