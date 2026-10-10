#!/usr/bin/env python3
"""Produce a three-case selection for run_targeted_extension; no RTL launch."""
import argparse
import json
from pathlib import Path
from build_gap35_accel import ROOT, NAMES, save, sha

PREFIX = "ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu."
Q = "i_qbs_engine"
A = "i_akv_engine"
TARGET_LINES = {
    NAMES[0]: {Q + ".i_descriptor_decoder": [92, 94, 98, 102, 112, 119, 124, 131, 137, 145, 149]},
    NAMES[1]: {Q + ".i_commit": [98],
               Q + ".i_compute_engine.i_block_adapter_bank0": [660],
               Q + ".i_compute_engine.i_block_adapter_bank1": [660]},
    NAMES[2]: {A: [401, 403, 407, 409, 412, 423, 434, 436, 1039]},
}
RATIONALE = {
    NAMES[0]: "18 invalid descriptors isolate 11 previously zero decoder basic blocks; aligned legal custom encodings reach descriptor validation, then one valid Q4_K command proves recovery. No reset/fault injection.",
    NAMES[1]: "Q8_0 x Q8_0, M5/N9/K2, R4 weights/M8 activations: reaches the unhit FP16-scale M8 unpack path in both banks and N>8 wide commit. Non-affine multi-context entries also target missing FP FSM edges. Immediate masked tu/mu RVV consumes v8.",
    NAMES[2]: "23 invalid descriptors isolate format/rows/dim/length/reserved/V2-alignment/overflow/tile checks, including separately mutated Q/K/V fields; final valid V2 fill and V row replay prove recovery.",
}
CONTRACT = {
    NAMES[0]: "Every rejected command: exactly one cause-2 trap at its instruction PC, tval zero or instruction; all 256 uint32 destination elements unchanged. Valid recovery: result 256.0f, legacy 31-element zero tail, all other registers unchanged. Existing qbs_ref checks exact status against case-authored classifications.",
    NAMES[1]: "45 outputs equal independent integer sum_k(32*(n-4+k)*(m+k+1)) converted exactly to FP32; 211 inactive/reserved elements retain distinct sentinels. Immediate integer masked add changes only v8 elements 0/2/4/6 by one bit; VL7 masked and tail elements remain intact. No trap is accepted. Host executes qbs_ref, then models the simple RVV post-op; no custom ISA/RTL execution is claimed.",
    NAMES[2]: "Every rejected fill: exactly one cause-2 trap at its instruction PC, tval zero or instruction; all v8-v11 halfwords preserved. Last valid fill: no trap, V2 row2's 64 payload halfwords match independently generated stream/row/dimension pattern, remaining 192 sentinel halfwords unchanged; release succeeds. Host uses existing ABI validation and akv_v2_reference data API.",
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / "verification/out") or not out.name.startswith("gap35-accel-"):
        p.error("use an independent verification/out/gap35-accel-* directory")
    out.mkdir(parents=True, exist_ok=False)
    baseline = ROOT / "verification/out/gap34-current-20261001-01"
    cache = ROOT / "verification/out/gap35-analysis-20261004-01/baseline-bits.json"
    audit = ROOT / "verification/out/gap35-accel-20261004-01/baseline-points.json"
    bits = json.loads(cache.read_text())
    points = json.loads(audit.read_text())
    inputs = (baseline / "combined-dve/inputs.txt").read_text().splitlines()
    assert bits["tests"] == inputs[1:] and len(bits["tests"]) == points["tests"] == 620
    comparisons = 0
    for name, metrics in points["instances"].items():
        for metric, row in metrics.items():
            other = bits["metrics"][metric][name]
            assert row["total"] == other["width"] and int(row["bits"], 2) == int(other["bits"], 16)
            assert not other["checksum"] or row["checksum"] == other["checksum"]
            comparisons += 1
    pins_path = ROOT / "verification/out/repaired-aligned-build-20260930-01/build-source-pins.json"
    pins = json.loads(pins_path.read_text())
    matched = {path: h for path, h in pins.items() if "/vlsu/qbs/" in path or "/vlsu/akv/" in path or
               path.endswith(("ara_dispatcher.sv", "ara_pkg.sv", "akv_pkg.sv", "qbs_pkg.sv", "default.mk"))}
    assert len(matched) == 21 and all(sha(path) == h for path, h in matched.items())
    build = json.loads((args.build / "build-results.json").read_text())
    assert [r["name"] for r in build["cases"]] == NAMES
    cases = []
    for row in build["cases"]:
        name = row["name"]
        assert sha(row["binary"]) == row["binary_sha256"]
        assert all(sha(path) == h for path, h in row["source_hashes"].items())
        proof = []
        for suffix, lines in TARGET_LINES[name].items():
            instance = PREFIX + suffix
            metric = points["instances"][instance]["line"]
            for line in lines:
                candidates = [r for r in metric["missing"] if r["line"] == str(line) and r["ignore"] == "0"]
                assert len(candidates) == 1, (name, suffix, line)
                proof.append({"instance": instance, "metric": "line", "mapping": metric["mapping"],
                              "baseline_bit": 0, **candidates[0]})
        fsm = []
        if name == NAMES[1]:
            instance = PREFIX + Q + ".i_compute_engine.i_fp_accumulator"
            edges = {"FP_DOT_CONVERT -> FP_SCALE_MULTIPLY", "FP_SCALE_MULTIPLY -> FP_ACCUMULATE_DOT",
                     "FP_ACCUMULATE_DOT -> FP_DOT_CONVERT"}
            fsm = [{"instance": instance, **r} for r in points["instances"][instance]["fsm"]["missing"]
                   if r["expression"] in edges]
            assert len(fsm) == 36
        proof_path = out / (name + ".source-audit.json")
        save(proof_path, {"name": name, "rationale": RATIONALE[name], "selfcheck_contract": CONTRACT[name],
             "predicted_new_raw_line_bins": len(proof), "line_zero_evidence": proof,
             "candidate_new_raw_fsm_edges": fsm,
             "fsm_prediction_limit": "Inferred raw FSM layout, not vendor point validation. M5's first wave exercises streams row*4+context in slots 0..15; repeated row tiles/K2 permit non-affine terminal re-entry. These 36 edges are predictions only.",
             "condition_branch_prediction": "Additional predicate outcomes expected; no numeric forecast from inferred layouts.",
             "cycle_discriminators": ("descriptor_valid=0 and decoder error class in VALIDATE, no payload request, no commit" if "descriptor" in name else
                                       "M8 scale_bytes=2 on both adapter banks; commit n_q=9, two words/context, 10 completed words; second word enables only lane0's low half; integer_result_stream selects FP entries 0..15"),
             "coverage_status": "PREDICTED_ONLY_RTL_NOT_RUN", "raw_counts_are_dve_denominators": False})
        targets = [PREFIX + suffix for suffix in TARGET_LINES[name]]
        if name == NAMES[1]: targets.append(PREFIX + Q + ".i_compute_engine.i_fp_accumulator")
        cases.append({"name": "app:" + name, "binary": row["binary"],
            "sources": row["sources"], "evidence": [str(proof_path), row["host_log"], row["elf_fit"],
                str(args.build.resolve() / (name + ".precheck.json")), str(out / "audit-summary.json")],
            "source_audit": CONTRACT[name], "targets": targets, "rationale": RATIONALE[name], "timeout_s": 300})
    save(out / "audit-summary.json", {"baseline_tests": 620, "independent_bitmap_comparisons": comparisons,
        "matched_frozen_sources": matched, "files": {str(path): sha(path) for path in
          (audit, cache, pins_path, baseline / "combined-dve/inputs.txt", baseline / "combined-dve/summary.csv")},
        "not_selected": [
          "Repeated reset matrices: already in baseline; main QBS/AKV FSM raw states/transitions already full.",
          "QBS M/K range: 3-bit M+1 is 1..8; 8-bit K+1 is 1..256, exactly configured maxima.",
          "QBS descriptor/activation/destination alignment checks preempted by dispatcher before descriptor fetch.",
          "AKV illegal panel count/destination/unaligned selector preempted by dispatcher; panel overrun impossible for aligned dimension and D64/96/128.",
          "Context mismatch and V1 halfword-skew paths are reachable, but deferred to honor final three-case scope."],
        "spike": "Installed Spike rejects --isa=rv64gcv_zfh_xaraqbs: cannot find araqbs in libcustomext.so; no custom-instruction precheck claimed.",
        "tools_not_run": ["VCS", "DVE", "URG", "Verilator", "ZCC"],
        "coverage_limits": points["limits"]})
    save(out / "selection-fragment.json", {"baseline": str(baseline), "baseline_bits": str(cache), "cases": cases})
    print(out / "selection-fragment.json")


if __name__ == "__main__":
    main()
