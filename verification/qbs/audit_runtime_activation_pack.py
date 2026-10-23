#!/usr/bin/env python3
"""Archive completed native public-packer checks without claiming RTL timing."""
import argparse
import json
from pathlib import Path

from run_half_scale_soc import digest, hashes
from run_runtime_activation_pack import check_log


CONFIGURATIONS = [("scalar", 1024, 0), ("vector", 128, 0),
                  ("vector", 1024, 0), ("vector", 1024, 7)]


def audit(directory):
    directory = directory.resolve(strict=True)
    state = json.loads((directory / "status.json").read_text())
    pins = json.loads((directory / "manifest.json").read_text())
    if state["state"] != "PASS" or state["child_pid"] is not None:
        raise ValueError("Native test has not completed successfully")
    if not pins or hashes(map(Path, pins)) != pins:
        raise ValueError("Native input/tool identity changed")
    cases = state["cases"]
    if [(c["mode"], c["vlen"], c["avl_limit"]) for c in cases] != CONFIGURATIONS:
        raise ValueError("Missing/duplicate configuration")
    artifacts = [directory / "status.json", directory / "manifest.json"]
    for case in cases:
        name = f"{case['mode']}-avl{case['avl_limit']}"
        log = directory / f"vlen{case['vlen']}-{name}.log"
        elf = directory / f"init-{name}"
        counts = check_log(log.read_text())
        if (counts != {"cases": case["cases"], "invalid_cases": case["invalid_cases"]}
                or digest(log) != case["log_sha256"] or digest(elf) != case["elf_sha256"]):
            raise ValueError("Native result or executable identity mismatch")
        artifacts.extend([log, elf])
    return dict(state="PASS", schema_version=1, worker=str(directory), cases=cases,
                layout_checks=sum(c["cases"] for c in cases),
                invalid_checks=sum(c["invalid_cases"] for c in cases),
                evidence_sha256=hashes(artifacts),
                scope="Public runtime packers; Linux QEMU functional evidence only",
                checked=["Q8_0 and Q8_K exact layout", "M4 through M24 and padded tails",
                         "unaligned buffers", "unchanged source and guards", "short buffers",
                         "overflow rejection", "fcsr/vcsr preservation", "VLEN and short AVL"],
                limitations=["No RTL timing or whole-model performance claim",
                             "No floating-point quantization is performed by these packers"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worker", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = audit(args.worker)
    with args.output.open("x") as target:
        json.dump(result, target, indent=2, sort_keys=True)
        target.write("\n")
    print(json.dumps({key: result[key] for key in ("state", "layout_checks", "invalid_checks")}))


if __name__ == "__main__":
    main()
