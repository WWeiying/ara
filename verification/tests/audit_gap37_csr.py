#!/usr/bin/env python3
"""Offline gap37 evidence; imports the reviewed Design class without running it."""
import csv
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "verification/out/gap35-vector-checked-preflight-20261004-03"
OUT = ROOT / "verification/out/gap37-csr-analysis-20261004-01"
HELPER = ROOT / "verification/coverage/reviewed_20261004/audit_readonly.py"
spec = importlib.util.spec_from_file_location("gap37_readonly", HELPER)
reviewed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewed)
SCOPE = reviewed.CORE + ".csr_regfile_i"


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    if OUT.exists():
        raise ValueError("A new output directory is required")
    inputs = (BASE / "combined-inputs.txt").read_text().splitlines()
    cache = reviewed.jread(BASE / "combined-bits.json")
    assert len(cache["tests"]) == 630 and cache["tests"] == inputs[1:]
    design = reviewed.Design(inputs[0])
    source = design.source(SCOPE)
    pins_path = Path(inputs[0]).parents[1] / "build-source-pins.json"
    pins = reviewed.jread(pins_path)
    relatives = ["hardware/deps/cva6/core/csr_regfile.sv", "hardware/src/ara_soc.sv",
                 "hardware/src/ara_system.sv", "hardware/include/ara_pkg.sv",
                 "hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv",
                 "hardware/deps/cva6/core/include/build_config_pkg.sv"]
    verified = reviewed.verify_hashes({str(ROOT / p): pins[str(ROOT / p)] for p in relatives})
    lines = Path(source["resolved_path"]).read_text().splitlines()
    with (BASE / "combined-dve/summary.csv").open() as stream:
        dve = [r for r in csv.DictReader(stream) if r["Name"] == "csr_regfile_i"]
    assert len(dve) == 1 and [dve[0][m] for m in ("Line", "Condition", "Branch")] == ["46.90%", "39.75%", "32.75%"]
    record = {"scope": SCOPE, "source": source, "tests": 630, "dve": dve[0],
              "source_pins": verified, "metrics": {}, "provenance": {}}
    for p in [HELPER, Path(__file__), pins_path, BASE / "combined-bits.json",
              BASE / "combined-inputs.txt", BASE / "combined-dve/summary.csv",
              ROOT / "verification/tests/audit_gap35_rvv.py"]:
        record["provenance"][str(p)] = reviewed.sha(p)
    blocks, branches = {}, {}
    for metric in ("line", "branch"):
        definition = design.definition(SCOPE, metric)
        row = cache["metrics"][metric][SCOPE]
        assert row["checksum"] in (None, definition.get("chksum"))
        bits = format(int(row["bits"], 16), f"0{row['width']}b")
        points = []
        if metric == "line":
            for bb in definition.iter("linebb"):
                index = int(bb.get("index"))
                statements = [dict(n.attrib, source=lines[int(n.get("line_num")) - 1]) for n in bb]
                point = dict(native=f"Block {bb.get('id')}", raw_index=index,
                             hit=int(bits[index]), xml=dict(bb.attrib), statements=statements)
                points.append(point)
                blocks[int(bb.get("id"))] = point
            assert len({p["raw_index"] for p in points}) == len(points)
            assert max(p["raw_index"] for p in points) + 1 == row["width"]
        else:
            for branch in definition.iter("branch_spec"):
                exprs = [dict(n.attrib) for n in branch if n.tag in ("branch_expr", "branch_cexpr")]
                items = [dict(n.attrib) for n in branch.iter("branch_citem")]
                for vector in branch.findall("branch_vector"):
                    index, base, width, _ = reviewed.branch_index(definition, branch.get("id"), vector.get("id"))
                    point = dict(native=f"Branch {branch.get('id')} ({vector.get('id')})",
                                 raw_index=index, hit=int(bits[index]), spec=dict(branch.attrib),
                                 vector=dict(vector.attrib), expressions=exprs, case_items=items,
                                 spec_base=base, spec_width=width)
                    points.append(point)
                    branches[int(branch.get("id")), int(vector.get("id"))] = point
            assert sorted(p["raw_index"] for p in points) == list(range(row["width"]))
        record["metrics"][metric] = dict(checksum=definition.get("chksum"),
            definition_sha256=reviewed.tree_digest(definition), width=row["width"],
            raw_covered=bits.count("1"), raw_bits=bits, points=points)
    # Preserve condition shape and bits without assuming an unreviewed row packing.
    cond = reviewed.xml(design.db / "shape/cond.verilog.shape.xml")
    conddef = [n for n in cond if n.get("id") == design.hierarchy[SCOPE].get("id")]
    assert len(conddef) == 1
    row = cache["metrics"]["cond"][SCOPE]
    assert row["checksum"] == conddef[0].get("chksum")
    record["metrics"]["cond"] = dict(row, definition_sha256=reviewed.tree_digest(conddef[0]),
        individual_mapping="Not asserted: native condregid/truth tables retained; no guessed raw row order.")
    cases = {
        "gap37_csr_alias_tvm": {
            "branch_ids": [(3, 50), (17, 59), (3, 78), (17, 85)],
            "block_ids": [71, 72, 108, 402, 403, 404, 446],
            "rationale": "SIE/MIE alias gated by MIDELEG, then SATP TVM read/write rejection in S and M bypass.",
            "hypothesis": "Legal SIE accesses reach read case 491/492 and update 1347/1350. S+TVM=1 reaches 556/1419; M+TVM=1 and S+TVM=0 do not reject.",
            "discriminators": ["csr_op_i/csr_addr_i/csr_we/csr_read", "priv_lvl_o/mstatus_q.tvm",
                "mideleg_q/mie_q/mie_d", "read_access_exception/update_access_exception/csr_exception_o", "commit_ack_i/ex_i"],
        },
        "gap37_csr_counters": {
            "branch_ids": [(3, 151), (17, 167), (17, 172), (17, 175)],
            "block_ids": [576, 577, 584, 588],
            "rationale": "Read/write MCOUNTINHIBIT; exact 64-bit MCYCLE/MINSTRET RMW while stopped; independent CY/IR hold/resume.",
            "hypothesis": "PerfCounterEn=1 permits CY/IR inhibit. Explicit writes reach 1732/1745/1749; inhibited counters hold despite commit, then independently progress after clearing the selected bit.",
            "discriminators": ["csr_op_i/csr_addr_i/csr_wdata", "mcountinhibit_q/mcountinhibit_d",
                "cycle_q/cycle_d/instret_q/instret_d", "commit_ack_i/ex_i.valid/debug_mode_q"],
        },
    }
    for case in cases.values():
        case["branches"] = [branches[tuple(key)] for key in case.pop("branch_ids")]
        case["blocks"] = [blocks[key] for key in case.pop("block_ids")]
        assert all(p["hit"] == 0 for p in case["branches"] + case["blocks"])
    OUT.mkdir()
    save(OUT / "native-points.json", record)
    save(OUT / "source-audit.json", dict(cases=cases, profile=dict(
        XLEN=64, RVS=1, RVU=1, RVV=1, RVH=0, FpPresent=1, EnableAccelerator=1,
        PerfCounterEn=1, DebugEn=1, NrPMPEntries=0, RVSCLIC=0, RVXHCLIC=0, RVZCMT=0),
        limits="Prospective control points only; Spike is not DUT coverage. Raw bits are not DVE denominators. No waiver edits."))
    with (OUT / "condition-shape.xml").open("x") as stream:
        stream.write(reviewed.ET.tostring(conddef[0], encoding="unicode"))
    print("630 PASS baseline pinned:", {m: (r.get("raw_covered"), r["width"]) for m, r in record["metrics"].items()})
    print("Selected", sum(len(c["branches"]) for c in cases.values()), "missing native branches; no VCS launched")


if __name__ == "__main__":
    main()
