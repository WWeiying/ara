#!/usr/bin/env python3
"""Package only current-source, Spike-passed gap35 ELFs for the shared runner."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "ara_tb.dut.i_ara_soc.i_system.i_ara."
ISA = ROOT / "apps/riscv-tests/isa/rv64uv"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    build, audit_path = args.build.resolve(), args.audit.resolve()
    baseline = json.loads(audit_path.read_text())
    cache = json.loads(Path(baseline["cache"]).read_text())
    assert len(cache["tests"]) == baseline["tests"] == 620
    checked = 0
    for name, metrics in baseline["instances"].items():
        for metric, row in metrics.items():
            original = cache["metrics"][metric][name]
            assert row["total"] == original["width"]
            assert int(row["bits"], 2) == int(original["bits"], 16)
            checked += 1

    # All 56 explicit SLDU case arms agree between branch-vector reversal and linebb.
    dp = baseline["instances"][PREFIX + "i_sldu.i_sldu_op_dp"]
    branch_lines = set()
    for point in dp["branch"]["missing"]:
        vector = point["vector"][::-1]
        for item in point["case_items"]:
            if vector[int(item["index"]) - 1] == "1":
                branch_lines.add(item["case_alt_line_num"])
    line_lines = {p["line_num"] for p in dp["line"]["missing"]}
    assert branch_lines == line_lines and len(line_lines) == 12

    specs = [
        ("mask_ta", "i_masku", [], [57],
         "ta with vstart=0 skips old-vd fetch/merge for all eight mask-logical ops; "
         "259 bits cross the 256-bit aggregate boundary. Not a SEW/LMUL sweep.",
         "Independent Boolean bit oracle for every active bit; source masks defined; "
         "mask-agnostic tail excluded; all bytes beyond the exact mask-store extent guarded."),
        ("carry_ta", "i_masku", [], [54],
         "ta with vstart=0 skips old-vd merge for VMADC/VMSBC; paired carry/no-carry forms "
         "exercise carry input as data, then vstart=61 checks preserved prefix.",
         "Unsigned scalar carry/borrow oracle including equality and overflow; every active bit "
         "and restart-prefix bit checked; mask tail excluded and store guard checked."),
        ("slide_bound", "i_dispatcher", [47], [1200],
         "VL=7 and offsets 2041/4089 make slide_bound end-index low word zero before decrement "
         "(11-bit vlen_t); contrasts wholly out-of-range zero-fill with source index 127.",
         "Full 128-byte tu/mu destination oracle, vstart=3 prefix, masked-off bytes, tail and "
         "store guard checked; vstart sampled immediately after slide."),
        ("vstart_csr", "i_dispatcher", [1386, 1407, 1422], [],
         "CSRR(C), CSRRSI and CSRRCI update VSTART through three previously unhit assignments; "
         "old-value chain 0,5,15,3,35 leaves restart index 1 for a masked vadd.",
         "Checks all CSR return values and the full 128-byte arithmetic result, restart prefix, "
         "mask-disabled bytes, tail and store guard; observes immediate vstart reset."),
        ("memory_noop", "i_dispatcher", [1348], [1139],
         "vs2r with vstart=evl=256 takes whole-register store no-op; empty segment store/load "
         "tests reservation cancellation before a nonempty dependent segment round trip. "
         "Branch 1139 is a secondary scheduling-sensitive prediction.",
         "Whole destination region and load registers checked unchanged after empty ops; "
         "following interleaved segment data, full register tails and both memory guards checked."),
        ("carry_illegal", "i_dispatcher", [330, 333, 339, 342], [],
         "Four rejected OPIVV encodings isolate VADC/VSBC vm=1 and vd=v0 checks at "
         "RTL lines 1814,1817,1831,1833. Same-base mask-result overlaps are intentionally not classified illegal.",
         "Each trap checks count, cause=2, exact instruction mtval, fault PC, unchanged vstart=3, "
         "vl, vtype, fcsr, vcsr; all bytes of v0/v8/v9/v10 remain unchanged. Handler saves scratch GPRs.")]
    results = json.loads((build / "spike_results.json").read_text())
    assert {r["test"] for r in results} == {"rvv:vgap35_" + s[0] for s in specs}
    cases = []
    evidence = {"status": "SPIKE_PREFLIGHT_ONLY", "vcs_started": False,
                "baseline_tests": 620, "cache_bitmaps_crosschecked": checked,
                "branch_order_crosscheck": "12/12 missing SLDU datapath arms match explicit linebb coordinates",
                "limits": baseline["limits"], "cases": []}
    for suffix, instance, line_indices, branch_indices, why, oracle in specs:
        name = "vgap35_" + suffix
        row = next(r for r in results if r["test"] == "rvv:" + name)
        assert row["status"] == "PASS" and row["returncode"] == 0
        assert "PASSED:" in Path(row["log"]).read_text()
        assert digest(Path(row["binary"])) == row["binary_sha256"]
        for path, sha in row["source_hashes"].items():
            assert digest(Path(path)) == sha, path
        metrics = baseline["instances"][PREFIX + instance]
        points = []
        for metric, indices in (("line", line_indices), ("branch", branch_indices)):
            by_index = {p["bit_index"]: p for p in metrics[metric]["missing"]}
            for index in indices:
                assert metrics[metric]["bits"][index] == "0"
                points.append({"instance": PREFIX + instance, "metric": metric,
                               "checksum": metrics[metric]["checksum"], "baseline": 0,
                               "point": by_index[index]})
        sources = [ISA / (name + ".c"), ISA / "vgap35_common.h",
                   ROOT / "verification/tests/build_gap35_rvv.py",
                   ROOT / "verification/tests/audit_gap35_rvv.py", Path(__file__).resolve()]
        record = {"name": "rvv:" + name, "binary": row["binary"], "sources": list(map(str, sources)),
                  "evidence": [str(build / "spike_results.json"), row["log"], row["spike_binary"],
                               str(build / "build_commands.json"), str(build / (name + ".dis")),
                               str(audit_path), str(build / "source_audit.json"), str(build / "HANDOFF.txt")],
                  "source_audit": "Spike PASS with campaign-pinned restart-capable model. " + oracle +
                                  " All cases check fcsr=117, vcsr=5 and final vstart=0.",
                  "targets": [PREFIX + instance], "rationale": why, "timeout_s": 600}
        cases.append(record)
        evidence["cases"].append({"name": record["name"], "source_audit": record["source_audit"],
                                  "rationale": why, "predicted_points": points,
                                  "elf_sha256": row["binary_sha256"], "spike_seconds": row["seconds"]})
    spec = {"baseline": str(ROOT / "verification/out/gap34-current-20261001-01"),
            "baseline_bits": baseline["cache"], "cases": cases}
    for filename, value in (("selection.json", spec), ("source_audit.json", evidence)):
        with (build / filename).open("x") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
    print(f"READY: {len(cases)} Spike-passed cases; {build / 'selection.json'}")


if __name__ == "__main__":
    main()
