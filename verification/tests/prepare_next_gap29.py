#!/usr/bin/env python3
"""Freeze prechecked Gap29 stimuli without launching an RTL simulation."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASELINE = ROOT / "verification/out/vcs-original473-gap28-20260928-01"
INPUTS = (
    HERE / "rvv_gap29_ready.json",
    HERE / "akv_d96_gap29_ready.json",
)
SELECTION = HERE / "next_gap29_selection.json"
OUTPUT = HERE / "next_gap29_ready.json"


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan = read(BASELINE / "plan.json")
    image = plan["simv"]
    if image != str(ROOT / "verification/out/repair-closure-coverage-20260927-01/sim/simv"):
        raise ValueError("running batch does not use the original image")
    if len(plan["cases"]) != 521:
        raise ValueError("unexpected running batch size")
    prior_names = {item["test"] for item in plan["cases"] if item.get("test")}
    prior_elf_hashes = {item["elf_sha256"] for item in plan["cases"]}
    selected = read(SELECTION)["tests"]
    if len(selected) != len(set(selected)):
        raise ValueError("duplicate new test")

    all_tests = []
    pins = {str(SELECTION): digest(SELECTION),
            str(Path(__file__).resolve()): digest(Path(__file__).resolve())}
    for ready_path in INPUTS:
        ready = read(ready_path)
        if ready["status"] != "READY" or ready.get("vcs_launched", False):
            raise ValueError(f"input not prechecked: {ready_path}")
        if ready.get("vcs_authorized", False):
            raise ValueError(f"input unexpectedly authorizes VCS: {ready_path}")
        for name, expected in ready["files"].items():
            path = Path(name)
            if not path.is_file() or digest(path) != expected:
                raise ValueError(f"input pin drift: {path}")
            if name in pins and pins[name] != expected:
                raise ValueError(f"conflicting pin: {path}")
            pins[name] = expected
        pins[str(ready_path)] = digest(ready_path)
        all_tests.extend(ready["tests"])
    if selected != all_tests or len(selected) != 7:
        raise ValueError("selection is not the exact union of checked inputs")
    if prior_names.intersection(selected):
        raise ValueError("test already present in current campaign")

    for test in selected:
        kind, stem = test.split(":", 1)
        binary = (ROOT / "apps/bin" /
                  ("rv64uv-ara-" + stem if kind == "rvv" else stem))
        if str(binary) not in pins or digest(binary) != pins[str(binary)]:
            raise ValueError(f"unfrozen ELF: {binary}")
        if pins[str(binary)] in prior_elf_hashes:
            raise ValueError(f"ELF already present in current campaign: {binary}")
    output = {
        "status": "READY",
        "selection": str(SELECTION),
        "tests": selected,
        "files": pins,
        "source_manifests": [str(path) for path in INPUTS],
        "previous": str(BASELINE),
        "image": image,
        "vcs_launched": False,
        "manual_launch_required": True,
        "scope": "six Spike-checked FP16 cases and one host-reference-checked AKV D96 case",
    }
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n")
    print(f"PREPARED {len(selected)} tests; VCS not started")


if __name__ == "__main__":
    main()
