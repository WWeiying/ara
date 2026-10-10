#!/usr/bin/env python3
"""Bind VCS generate annotations to each exact compiled branch specification."""
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import capture_operand_debug_branch_v4 as previous

base = previous.base
HERE = Path(__file__).resolve().parent
base.TEST = HERE / "test_capture_operand_debug_branch_v5.py"
frozen_bind = previous.bind_native
previous_prepare = base.prepare
FAILED = base.debug.OUT / "operand-debug-branch-native1832-20261006-01"


def bind_native(raw, config):
    base.require(raw.endswith(b"\n") and b"\r" not in raw and b"\x00" not in raw,
                 "Invalid native bytes")
    lines = raw.decode("ascii").splitlines()
    expected = {}
    for scope, metrics in config["plan"]["scopes"].items():
        base.require(set(metrics) == {"branch"}, "Branch only")
        for row in metrics["branch"]:
            if row["target"]:
                p = row["point"]
                key = scope, "Branch %s (%s)" % (p["native_id"], p["vector"])
                base.require(key not in expected, "Duplicate expected point")
                gen = p["attributes"].get("generate_info")
                base.require(gen is None or re.fullmatch(r"requester_index=[0-8]", gen),
                             "Unsupported compiled generate identity")
                expected[key] = base.debug.ANNOTATION if gen is None else (
                    "vcs_gen_start:" + gen + ":vcs_gen_end:" + base.debug.ANNOTATION)
    annotations = {}
    normalized = list(lines)
    scope = None
    for i, line in enumerate(lines):
        if line.startswith("INSTANCE:"):
            match = re.fullmatch(r"INSTANCE: ?([A-Za-z_][A-Za-z0-9_.\[\]]*)", line)
            base.require(match is not None, "Invalid native instance")
            scope = match[1]
        if line.startswith("ANNOTATION:"):
            base.require(i + 1 < len(lines), "Dangling annotation")
            match = re.fullmatch(r'Branch (0|[1-9][0-9]*) "[0-9]+" ".*" \((0|[1-9][0-9]*)\) ".*"', lines[i + 1])
            base.require(match is not None, "Annotation must precede exact branch")
            key = scope, "Branch %s (%s)" % (match[1], match[2])
            base.require(key in expected and key not in annotations, "Extra/duplicate native annotation")
            base.require(line == 'ANNOTATION: "' + expected[key] + '"',
                         "Native annotation differs from compiled generate_info")
            annotations[key] = line
            normalized[i] = 'ANNOTATION: "' + base.debug.ANNOTATION + '"'
    rows = frozen_bind(("\n".join(normalized) + "\n").encode("ascii"), config)
    base.require(set(annotations) == set(expected), "Missing exact annotations")
    for row in rows:
        row["native_annotation"] = annotations[row["scope"], row["point"]]
    return rows


def prior_evidence():
    state = json.loads((FAILED / "status.json").read_bytes())
    base.require(state["status"] == "FAILED" and state["reason"] == "ValueError: Missing native evidence",
                 "Prior failure must remain intact")
    config = json.loads((FAILED / "config.json").read_bytes())
    base.capture.check_inputs(config)
    rows = bind_native((FAILED / "first.el").read_bytes(), config)
    base.require(len(rows) == 1832, "Prior full first population differs")
    identities = None
    for stage in ("before", "selected", "final"):
        identities = base.audit_states(FAILED / ("states_%s.tsv" % stage), config, stage, identities)
    for name in ("initial-empty.el", "final-empty.el"):
        base.require((FAILED / name).read_bytes() == b"", "Prior cleanup not empty")
    return rows


def prepare(output, mode, pilot=None, pilot_seal=None, pilot_result_seal=None):
    prior_evidence()
    previous_prepare(output, mode, pilot, pilot_seal, pilot_result_seal)
    config = json.loads((output / "config.json").read_bytes())
    paths = [Path(__file__).resolve(), HERE / "test_capture_operand_debug_branch_v4.py"]
    paths += [FAILED / n for n in ("config.json", "status.json", "first.el", "initial-empty.el",
        "final-empty.el", "states_before.tsv", "states_selected.tsv", "states_final.tsv", "DVEfiles/dve_gui.log")]
    for path in paths:
        config["pins"][str(path)] = base.sha(path)
    selection = output / "selection.tcl"
    with selection.open("a") as stream:
        stream.write("set dbg_driver " + base.capture.literal(str(Path(__file__).resolve())) + "\n")
    config["pins"][str(selection)] = base.sha(selection)
    config["native_annotation_binding"] = "exact compiled branch generate_info plus exact review annotation; retained in roundtrip comparison"
    base.write(output / "config.json", config)
    base.capture.check_inputs(config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, mode=mode,
        targets=config["targets"], protected=config["protected"], application_approval=False))
    print("BRANCH_V5_FINAL_SEAL " + seal, flush=True)


base.debug.bind_native = bind_native
base.prepare = prepare
if __name__ == "__main__":
    base.main()
