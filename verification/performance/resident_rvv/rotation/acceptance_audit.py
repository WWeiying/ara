#!/usr/bin/env python3
"""Successor audit; never edits the sealed running control or its evidence."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rotation_audit_contract", HERE / "experiment.py")
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)
require, sha = experiment.require, experiment.sha
FIELDS = "cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,wdata,nr_lanes,vlen_bits".split(",")


def strict_header(path):
    with Path(path).open(newline="") as stream:
        fields = next(csv.reader(stream), [])
    require(len(fields) == len(set(fields)), "Duplicate vector CSV columns")
    require(fields == FIELDS, "Unexpected vector CSV schema")
    return fields


def audit(directory):
    directory = directory.resolve(strict=True)
    receipt = directory / "result.json"
    result = json.loads(receipt.read_text())
    require(result["state"] == "PASS" and result["independent_protocol_checked"] and
            result["post_pins_match"], "Control has not passed all original gates")
    pins = directory / "source-pins.json"
    require(sha(pins) == result["source_pins_sha256"], "Worker pin inventory changed")
    experiment.contract.verify(json.loads(pins.read_text()))
    experiment.contract.verify(result["artifacts"])
    build = Path(result["build"])
    meta = experiment.verify_build(build)
    require(meta["elf_sha256"] == result["software_sha256"], "Control ELF identity mismatch")
    vector, log = directory / "work/vector_trace.csv", directory / "work/run.vcs.log"
    require(all(result["artifacts"].get(str(p)) == sha(p) for p in (vector, log)),
            "Missing accepted raw evidence")
    header = strict_header(vector)
    measured = experiment.check_run(log, build)
    work = experiment.check_vector_workcounts(vector, build)
    require(measured == result["measured"] and work == result["vector_command_work"],
            "Repeated control acceptance differs")
    return dict(state="CONTROL_INDEPENDENT_AUDIT_PASS", raw_receipt=str(receipt),
        raw_receipt_sha256=sha(receipt), schema_checked=header,
        source_pins_sha256=sha(pins), measured=measured, vector_command_work=work,
        arithmetic_scope="RNE, D128/H2/T137, two complete native-auto arms",
        causal_scope="Combined register rotation and two-row loop layout; not isolated rotation cost",
        hardware_changed=False, auditor_sha256=sha(__file__))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.run.resolve()),
            "Successor audit must not alter the original evidence directory")
    result = audit(args.run)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(state=result["state"], output=str(args.output))))
