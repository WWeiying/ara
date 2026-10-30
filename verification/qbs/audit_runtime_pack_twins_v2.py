#!/usr/bin/env python3
"""Bind recovered child results to parent image pins and saved raw evidence."""
import argparse
import json
from pathlib import Path

from audit_runtime_pack_twins import APP, recover, compare, read_json, verify_build
from run_half_scale_soc import hashes
from build_runtime_pack_projection import verify_pins


def validate_binding(parent_pins, image, entry, result):
    files = image.get("files", {})
    if not files or image.get("simv") not in files:
        raise ValueError("Incomplete child image record")
    if any(parent_pins.get(path) != value for path, value in files.items()):
        raise ValueError("Child image not bound to parent manifest")
    if entry.get("result_sha256") != result["report_sha256"]:
        raise ValueError("Saved result checksum differs")
    if entry.get("projection") != result["projection"]:
        raise ValueError("Saved projection differs from raw-log reaudit")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "scalar", "vector", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    build = args.build.resolve(strict=True)
    _, pins = verify_build(build)
    cases, evidence = {}, {}
    for mode in ("scalar", "vector"):
        directory = getattr(args, mode).resolve(strict=True)
        result, consumed = recover(directory, mode, build, pins)
        child = directory / mode
        image_path = child / "image-pins.json"
        image = read_json(image_path)
        entry = read_json(child / "status.json")["cases"][APP]
        validate_binding(read_json(directory / "manifest.json"), image, entry, result)
        cases[mode] = result
        evidence.update(consumed)
        evidence.update(hashes([image_path, child / "input-pins.json"]))
    evidence.update(hashes([Path(__file__), Path(__file__).with_name("audit_runtime_pack_twins.py")]))
    verify_pins(evidence)
    report = dict(state="PASS", cases=cases, evidence_sha256=evidence,
                  comparison=compare(cases["scalar"], cases["vector"]),
                  deployment_approved=False,
                  scope="Current-runtime scalar/vector packing on same pinned image; one real M4/N896/K896 projection",
                  original_fail_records_preserved=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(report["comparison"], sort_keys=True))


if __name__ == "__main__":
    main()
