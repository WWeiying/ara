#!/usr/bin/env python3
"""Recover completed twins from the pinned PASS/passed wrapper mismatch.

Never rewrites the failed worker or reruns simulation. Only this specific
wrapper error is recoverable; raw simulation and oracle checks remain required.
"""
import argparse
import json
from pathlib import Path

from run_runtime_pack_projection import APP, audit, compare, digest, read_json
from run_runtime_pack_projection import verify_build, verify_pins
from run_half_scale_soc import hashes


def require_terminal(parent, child, mode):
    expected = f"RuntimeError('Projection worker failed: {mode}, returncode=0')"
    if (parent.get("state") != "FAIL" or parent.get("error") != expected or
            parent.get("mode") != mode or parent.get("child_pid") is not None):
        raise ValueError("Not the known wrapper-status failure")
    if (child.get("state") != "passed" or child.get("child_pid") is not None or
            child.get("selected_cases") != [APP] or
            child.get("cases", {}).get(APP, {}).get("state") != "passed"):
        raise ValueError("Child is not independently completed and passing")


def recover(directory, mode, build, build_pins):
    parent = read_json(directory / "status.json")
    child_dir = directory / mode
    child = read_json(child_dir / "status.json")
    require_terminal(parent, child, mode)
    manifest = directory / "manifest.json"
    pins = read_json(manifest)
    if (digest(manifest) != parent["manifest_sha256"] or
            digest(build / "build.json") != parent["build_sha256"] or
            any(pins.get(path) != value for path, value in build_pins.items())):
        raise ValueError("Worker/build provenance differs")
    verify_pins(pins)
    result = audit(child_dir, APP)
    if result["elf_sha256"] != digest(build / mode / APP):
        raise ValueError("Executed ELF is not the selected twin")
    evidence = hashes([directory / "status.json", manifest, child_dir / "status.json",
                       child_dir / APP / "work/run.vcs.log",
                       child_dir / APP / "uvm_result.json"])
    return result, evidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--scalar", type=Path, required=True)
    p.add_argument("--vector", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    build = args.build.resolve(strict=True)
    _, build_pins = verify_build(build)
    scalar, sp = recover(args.scalar.resolve(strict=True), "scalar", build, build_pins)
    vector, vp = recover(args.vector.resolve(strict=True), "vector", build, build_pins)
    result = dict(state="PASS", scalar=scalar, vector=vector,
                  comparison=compare(scalar, vector),
                  scope="Current-runtime scalar/vector packing; M4/N896/K896; not fused GGML or model timing",
                  recovery="Parent expected PASS but child records passed; original FAIL records retained",
                  deployment_approved=False,
                  evidence_sha256={**sp, **vp, **hashes([Path(__file__)])})
    verify_pins(result["evidence_sha256"])
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(result["comparison"], sort_keys=True))


if __name__ == "__main__":
    main()
