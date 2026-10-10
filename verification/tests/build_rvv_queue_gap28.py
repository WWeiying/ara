#!/usr/bin/env python3
"""Reuse the isolated compiler/Spike workflow, optionally freeze a READY handoff."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import build_rvv_memory_gaps as builder
import generate_rvv_queue_gap28 as generator


def pins(paths):
    return {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--ready", type=Path)
    args, remaining = parser.parse_known_args()
    if args.ready and ("--spike" not in remaining or "--case" in remaining):
        parser.error("READY requires the complete 36-case --spike precheck")
    if args.ready and args.ready.exists():
        parser.error("READY already exists; no overwrite")
    selection = Path(__file__).with_name("rvv_queue_gap28_selection.json").resolve()
    tests = ["rvv:" + c[0] for c in generator.cases()]
    if json.loads(selection.read_text()) != {"tests": tests}:
        raise ValueError("selection differs from generator")
    sources = [generator.DEST / (c[0] + ".c") for c in generator.cases()]
    for case, path in zip(generator.cases(), sources):
        if path.read_text() != generator.render(case):
            raise ValueError(f"generated source differs: {path}")
    sources += [selection, Path(__file__), Path(generator.__file__), Path(builder.__file__),
                Path(__file__).with_name("generate_rvv_memory_gaps.py"),
                generator.DEST / "vqueue_gap28_body.h"]
    root = generator.ROOT
    for directory in ("apps/common", "apps/riscv-tests/benchmarks/common",
                      "apps/riscv-tests/isa/macros/vector", "apps/riscv-tests/isa/macros/scalar",
                      "apps/include", "apps/riscv-tests/env"):
        sources += [p for p in (root / directory).rglob("*") if p.is_file() and
                    p.suffix in (".c", ".h", ".S", ".ld")]
    sources += [root / "install/riscv-llvm/bin/clang",
                root / "install/riscv-isa-sim/bin/spike"]
    before = pins(sources)
    sys.argv = [sys.argv[0], *remaining]
    builder.cases = generator.cases
    builder.main()
    if before != pins(sources):
        raise ValueError("source/tool drift during build and Spike precheck")
    if args.ready:
        out = Path(remaining[remaining.index("--output") + 1]).resolve()
        results_path = out / "spike_results.json"
        results = json.loads(results_path.read_text())
        if [r["test"] for r in results] != tests or any(r["returncode"] for r in results):
            raise ValueError("not an exact complete PASS precheck")
        artifacts = [results_path, out / "build_commands.json"]
        hashes = set()
        for name, *_ in generator.cases():
            log = out / (name + ".spike.log")
            if b"PASSED:" not in log.read_bytes():
                raise ValueError(f"missing selfcheck PASS: {name}")
            elf = root / "apps/bin" / ("rv64uv-ara-" + name)
            hashes.update(pins([elf]).values())
            artifacts += [elf, out / (name + ".spike"), log]
        if len(hashes) != 36:
            raise ValueError("duplicate ELF stimulus")
        files = dict(before, **pins(artifacts))
        record = {"status": "READY", "selection": str(selection), "tests": tests,
                  "files": files, "spike_results": str(results_path), "spike_passed": 36,
                  "timeout_s": 300, "rtl_changed": False,
                  "image_policy": "original frozen image underlying 473 PASS; no repaired image"}
        args.ready.parent.mkdir(parents=True, exist_ok=True)
        with args.ready.open("x") as stream:
            json.dump(record, stream, indent=2)
            stream.write("\n")
        print(f"READY: {args.ready.resolve()}")

if __name__ == "__main__":
    main()
