"""Source-pinned raw707 CSR diagnostic inventory; not native qualification or waiver."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from inventory_operand_debug import Design
from closure_point_inventory import points, read_xml
from reviewed_20261004.audit_readonly import sha, require, tree_digest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "verification/out"
BASE = OUT / "gap98-offline-admitted-707-20261006-02"
BUILD = OUT / "repaired-aligned-build-20260930-01"
SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i"
SOURCE = ROOT / "hardware/deps/cva6/core/csr_regfile.sv"
CONFIG = ROOT / "hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv"


def locations(point, metric):
    texts = [point.get("line", "")]
    texts += [s.get("line_num", "") for s in point.get("statements", [])]
    texts += [s.get("id", "") for s in point.get("expressions", [])]
    if not texts or any(not str(t).isdigit() for t in texts):
        return []
    return [int(t) for t in texts]


def classify(point, metric):
    loc = locations(point, metric)
    # This whole source arm is under `if (CVA6Cfg.RVH)` at line2503.
    if loc and all(2504 <= line <= 2565 for line in loc):
        return "RVH0_INACTIVE_PRIVILEGE_ARM", "csr_regfile.sv:2503 RVH=0; non-H else starts2566"
    expr = re.sub(r"\s+", "", point.get("expression", ""))
    if metric == "cond":
        impossible = {"(1'b1&&debug_req_i)": "-1", "(1'b1&&ipi_i)": "-1"}
        if expr in impossible and point["vector"] == impossible[expr]:
            return "TIED_INPUT_BOOLEAN_TRUE_IMPOSSIBLE", "ara_system.sv:183/185 input tied0; exact boolean row only"
    if "pmpcfg" in expr or "pmpaddr" in expr:
        return "PMP0_CONTEXT_HOLD", "NrPMPEntries=0; no PMP deny; CSR decode/loop must be reviewed individually"
    if any(word in expr for word in ("debug_mode", "debug_req", "dcsr", "DRET", "DEBUG_REQUEST")):
        return "DEBUG_NORMAL_RUN_INVARIANT_REVIEW", "DebugEn=1, external request0; debug entry/reset/write closure needed"
    if any(word in expr for word in ("v_q", "vsstatus", "vsatp", "hgatp", "hstatus", "hcounteren", "clic")):
        return "CONFIG_CONTEXT_HOLD", "RVH0/CLIC0 do not by themselves classify every row of a mixed expression"
    if metric == "cond" and point["raw_index"] == 155 and point["line"] == "1425":
        return "DIRECTED_SATP_UNSUPPORTED_MODE", "M-mode legal SATP write reserved RV64 MODE1 ignored; both comparisons false"
    if metric == "cond" and point["raw_index"] == 334 and point["line"] == "2330":
        return "DIRECTED_MPRV_BARE_NONM", "MPRV1, satp Bare0, MPP=S/U; translation conjunction false"
    return "FUNCTIONAL_REACHABILITY_REVIEW", "Unhit alone proves neither reachability nor unreachability"


def mapped_points(metric, definition, record):
    mapped = points(metric, definition, record["width"])
    missing = sorted(set(range(record["width"])) - {p["raw_index"] for p in mapped})
    if metric == "line":
        require(record["width"] == 974 and record["checksum"] == "2614139268" and len(mapped) == 969 and
                missing == [268, 608, 641, 932, 959], "Unexpected CSR line shape or missing positions")
    else:
        require(len(mapped) == record["width"] and not missing, "Incomplete condition/branch point mapping")
    return mapped, missing


def inventory():
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        actual = sha(path)
        require(expected is None or actual == expected, "Frozen/source drift: " + str(path))
        require(str(path) not in pins or pins[str(path)] == actual, "Snapshot conflict")
        pins[str(path)] = actual
        return path
    state = json.loads(pin(BASE / "status.json").read_bytes())
    bitmap = json.loads(pin(BASE / "combined-bits.json").read_bytes())
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 707 and
            len(bitmap["tests"]) == len(set(bitmap["tests"])) == 707, "Not admitted707")
    require(pin(BASE / "combined-inputs.txt").read_text().splitlines() ==
            [str(BUILD / "sim/simv.vdb"), *bitmap["tests"]], "Exact707 membership/order differs")
    sources = json.loads(pin(BUILD / "build-source-pins.json").read_bytes())
    for path in (SOURCE, CONFIG, ROOT / "hardware/src/ara_soc.sv", ROOT / "hardware/src/ara_system.sv",
                 ROOT / "hardware/deps/cva6/core/include/build_config_pkg.sv"):
        pin(path, sources[str(path)])
    cfg, soc, system = CONFIG.read_text(), (ROOT / "hardware/src/ara_soc.sv").read_text(), (ROOT / "hardware/src/ara_system.sv").read_text()
    for fragment in ("CVA6ConfigHExtEn = 0;", "CVA6ConfigPerfCounterEn = 1;", "DebugEn: bit'(1)",
                     "RVS: bit'(1)", "RVU: bit'(1)", "CVA6ConfigSclicExtEn = 0;", "CVA6ConfigXhclicExtEn = 0;"):
        require(fragment in cfg, "Config fact changed: " + fragment)
    require("cfg.NrPMPEntries          = 0;" in soc and "gen_usr_cva6_config(cva6_config_pkg::cva6_cfg)" in soc,
            "Final zeroPMP override absent")
    for name in ("debug_req_i", "ipi_i", "time_irq_i", "irq_i"):
        require(re.search(r"\." + name + r"\s*\(\s*'0\s*\)", system), "Untied external input: " + name)
    design = Design(BUILD / "sim/simv.vdb")
    require(design.source(SCOPE)["resolved_path"] == str(SOURCE), "Wrong compiled CSR source")
    require(str(CONFIG) in {s["name"] for s in design.sources.values()}, "Selected config absent from compiled inputs")
    for relative, expected in bitmap["design"].items():
        pin(design.db / relative, expected)
    for relative in ("auxiliary/verilog.sourceinfo.xml", "shape/line.verilog.shape.xml", "shape/branch.verilog.shape.xml",
                     "shape/cond.verilog.shape.xml", "shape/cond.verilog.info.xml", "shape/tgl.verilog.shape.xml"):
        pin(design.db / relative)
    condition = read_xml(design.db / "shape/cond.verilog.shape.xml")
    info = read_xml(design.db / "shape/cond.verilog.info.xml")
    matches = [n for n in info.iter("instance_data") if n.get("name") == SCOPE]
    require(len(matches) == 1, "Ambiguous condition instance")
    lines = SOURCE.read_text().splitlines()
    rows, stats, definitions = [], {}, {}
    for metric in ("line", "branch", "cond"):
        record = bitmap["metrics"][metric][SCOPE]
        if metric == "cond":
            require(matches[0].get("chksum") == record["checksum"], "Condition checksum differs")
            candidates = [n for n in condition if n.get("id") == design.hierarchy[SCOPE].get("id") and
                          n.get("chksum") == record["checksum"]]
            require(len(candidates) == 1, "Ambiguous condition definition")
            definition = candidates[0]
        else:
            definition = design.definition(SCOPE, metric)
        require(definition.get("chksum") == record["checksum"] and
                0 <= int(record["bits"], 16) < 1 << record["width"], "Shape/bitmap mismatch")
        definitions[metric] = tree_digest(definition)
        mapped, missing = mapped_points(metric, definition, record)
        for raw in missing:
            mapped.append(dict(raw_index=raw, native_id=None, line=None, expression="", vector="",
                               mapping="UNMAPPED_LINE_POSITION_NOT_AN_INDEPENDENT_NATIVE_BLOCK"))
        hit_count = 0
        for point in mapped:
            hit = bool(int(record["bits"], 16) & (1 << (record["width"] - 1 - point["raw_index"])))
            hit_count += int(hit)
            decision, reason = (("UNMAPPED_LINE_POSITION_HOLD", "No independent native block mapping")
                                if point.get("mapping") else
                                ("RETAIN_HIT", "Already covered") if hit else classify(point, metric))
            loc = locations(point, metric)
            require(all(1 <= line <= len(lines) for line in loc), "Source coordinates outside file")
            rows.append(dict(scope=SCOPE, metric=metric, point=point, hit=hit, decision=decision, reason=reason,
                             source_lines={str(line): lines[line - 1] for line in sorted(set(loc))},
                             checksum=record["checksum"], width=record["width"]))
        stats[metric] = dict(total=record["width"], hit=hit_count, unhit=record["width"] - hit_count,
                            unresolved_raw_positions=missing)
    evidence = OUT / "gap37-csr-analysis-20261004-01/selection-checked.json"
    pin(evidence)
    for path in (ROOT / "apps/riscv-tests/isa/rv64uv/gap37_csr_counters.c",
                 ROOT / "apps/riscv-tests/isa/rv64uv/gap37_csr_alias_tvm.c",
                 ROOT / "apps/riscv-tests/isa/rv64uv/csr_gap35_counteren.c",
                 ROOT / "apps/riscv-tests/isa/rv64uv/vgap97_csr_large_avl.c",
                 Path(__file__).resolve(), Path(__file__).with_name("test_inventory_csr_707.py"),
                 ROOT / "verification/coverage/closure_point_inventory.py",
                 ROOT / "verification/coverage/reviewed_20261004/audit_readonly.py"):
        pin(path)
    for path, expected in pins.items():
        require(sha(path) == expected, "Input drift at finish")
    return dict(status="CSR_RAW707_DIAGNOSTIC_NOT_WAIVER_NOT_ADMISSION", baseline_tests=707,
                source=str(SOURCE), scope=SCOPE, pins=pins, design=bitmap["design"],
                compiled_definition_hashes=definitions, compiled_tgl_parameters=dict(design.definition(SCOPE, "tgl").attrib),
                config=dict(RVH=0, NrPMPEntries=0, DebugEn=1, external_debug_req=0, external_irq=0,
                            PerfCounterEn=1, RVS=1, RVU=1, RVSCLIC=0, RVXHCLIC=0),
                metrics=stats, unhit_decisions=dict(Counter(r["decision"] for r in rows if not r["hit"])), points=rows,
                native_qualified=False, exclusions_generated=False, official_denominator_verified=False,
                line_native_mapping_complete=False, condition_branch_mapping_complete=True,
                case_targets={name: [r for r in rows if r["decision"] == name] for name in
                              ("DIRECTED_SATP_UNSUPPORTED_MODE", "DIRECTED_MPRV_BARE_NONM")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inventory()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(output=str(args.output), seal=sha(args.output), metrics=result["metrics"],
                          decisions=result["unhit_decisions"], targets={k: len(v) for k, v in result["case_targets"].items()})))
