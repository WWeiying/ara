#!/usr/bin/env python3
"""Compare the sealed scalar/vector packing full-projection runs."""
import argparse
import json
from pathlib import Path

from audit_projection_soc_pair import audit
from run_half_scale_soc import PROJECTION_CASES, digest, hashes


def compare(baseline, candidate):
    if baseline["image_pins_sha256"] != candidate["image_pins_sha256"]:
        raise ValueError("Different simulator images")
    old, new = baseline["projection"]["result"], candidate["projection"]["result"]
    for key in ("checksum", "k", "rows", "inputs", "outputs", "tiles", "operations",
                "quantizations", "activation_context", "logical_read_bytes", "timing_scope"):
        if old[key] != new[key]:
            raise ValueError("Different workload/result: " + key)
    phases = {key: dict(baseline=int(old[key]), candidate=int(new[key])) for key in
              ("quantize_cycles", "pack_cycles", "matmul_cycles", "timed_cycles")}
    b, c = phases["timed_cycles"]["baseline"], phases["timed_cycles"]["candidate"]
    return dict(state="PASS", baseline=baseline, candidate=candidate, phases=phases,
                total_speedup=b / c, total_cycle_reduction_percent=100 * (b - c) / b,
                scope="Real M4/N896/K896 row-quantize plus packing projection, not fused GGML M4 or whole model")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    case = PROJECTION_CASES[0]
    old, new = audit(args.baseline, case), audit(args.candidate, case)
    build = args.build.resolve(strict=True)
    report = json.loads((build / "build.json").read_text())
    pins = json.loads((build / "manifest.json").read_text())
    if hashes(map(Path, pins)) != pins or hashes(map(Path, report["object_sha256"])) != report["object_sha256"]:
        raise ValueError("Candidate inputs/objects drifted")
    if (old["elf_sha256"] != report["baseline_sha256"] or
            new["elf_sha256"] != report["candidate_sha256"] or
            digest(build / "pack-wrapper.o") != report["wrapper_sha256"]):
        raise ValueError("Executable/object provenance mismatch")
    result = compare(old, new)
    result["build_report_sha256"] = digest(build / "build.json")
    result["audit_sources"] = hashes([Path(__file__), Path(__file__).with_name("audit_projection_soc_pair.py"),
                                      Path(__file__).with_name("run_half_scale_soc.py")])
    with args.output.open("x") as target:
        json.dump(result, target, indent=2, sort_keys=True)
        target.write("\n")
    print(json.dumps({k: result[k] for k in ("state", "phases", "total_speedup", "total_cycle_reduction_percent")}))


if __name__ == "__main__":
    main()
