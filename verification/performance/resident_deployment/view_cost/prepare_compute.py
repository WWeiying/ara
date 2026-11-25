#!/usr/bin/env python3
"""Build three real captured-data Sv39 calls against one exact kernel object."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
HERE = Path(__file__).resolve().parent
GNU = Path("/home/wangwy/llama/platforms/cva6-qemu/tools/bin")
ORACLE = ROOT / "verification/performance/resident_rvv/qk_shared/full_call_sdk/fixture.py"
DEFAULT_COMPUTE = OUT / "resident_view_module_20261113_01"
STATE = "REAL_KERNEL_VIEWS_BUILT_NOT_EXECUTED"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, "Input drift: " + str(path))


def mutated(data):
    result = dict(data)
    for name, rotation in (("key", 1), ("value", 7)):
        raw = data[name]
        words = struct.unpack("<" + "H" * (len(raw) // 2), raw)
        changed = list(words)
        for token in range(65):
            for dim in range(128):
                value = words[token * 128 + (dim + rotation) % 128]
                changed[token * 128 + dim] = value ^ (0x8000 if name == "value" and dim % 2 == 0 else 0)
        result[name] = struct.pack("<" + "H" * len(changed), *changed)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compute-output", type=Path, default=DEFAULT_COMPUTE)
    parser.add_argument("--core-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out, compute = args.output.resolve(), args.compute_output.resolve()
    require(out.parent == compute.parent == OUT, "Outputs must be direct signoff/out children")
    require(out.name.startswith("resident_view_compute_") and not out.exists(), "Use a fresh resident_view_compute_ output")
    core = compute / "module/sdk/ara_resident_compute_core.o"
    header = compute / "module/sdk/kernel_compute.h"
    module = compute / "module/ara_resident.ko"
    receipt = read(compute / "result.json")
    require(receipt["state"] == "MODULE_BUILT_NOT_EXECUTED" and receipt["pins_match"], "Module build not sealed")
    require(sha(core) == args.core_sha256 == receipt["core_sha256"], "Exact core hash required")
    require(sha(module) == receipt["module_sha256"], "Module hash drift")
    verify(read(compute / "source-pins.json"))
    out.mkdir()
    inputs = out / "inputs"
    inputs.mkdir()
    pins = {}

    def pin(path):
        pins[str(path)] = sha(path)

    for path in (Path(__file__).resolve(), ORACLE, core, header, module,
                 compute / "result.json", compute / "source-pins.json"):
        pin(path)
    commands = []

    def run(name, argv):
        argv = list(map(str, argv))
        with (out / (name + ".log")).open("x") as log:
            completed = subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        commands.append(dict(name=name, argv=argv, returncode=completed.returncode))
        save(out / (name + ".command.json"), commands[-1])
        require(completed.returncode == 0, "Command failed: " + name)
        return (out / (name + ".log")).read_text()

    spec = importlib.util.spec_from_file_location("resident_view_independent_fixture", ORACLE)
    oracle = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(oracle)
    captures, capture_pins = oracle.inputs()
    pins.update({str(p): h for p, h in capture_pins.items()})
    original = captures[0]
    updated = mutated(original)
    case = dict(name="qwen3_d128h2t65", requested=1, dimension=128, heads=2,
                kv_heads=1, tokens=65, capacity=256, initial_flags=0)
    base = oracle.reference(case, original)
    live = oracle.reference(case, updated)
    require(base["bits"] != live["bits"], "Mutation must change the independently calculated output")
    require(base["query_half"] == live["query_half"], "Q must remain unchanged")
    require(len(base["bits"]) == len(live["bits"]) == 256, "Unexpected oracle shape")
    pins.update(base["oracle_pins"])
    pins.update(live["oracle_pins"])
    save(inputs / "oracle-original.json", base)
    save(inputs / "oracle-updated.json", live)
    save(inputs / "case.json", case)
    changed_halfwords = sum(a != b for name in ("key", "value") for a, b in zip(
        oracle.unpack(original[name][:65 * 256], 16), oracle.unpack(updated[name][:65 * 256], 16)))
    require(changed_halfwords > 0, "No live input mutation")
    binaries = dict(
        capture_query=bytes.fromhex(base["query_half"]),
        capture_key=original["key"][:65 * 256], capture_value=original["value"][:65 * 256],
        capture_mask=original["mask"][:130],
        updated_key=updated["key"][:65 * 256], updated_value=updated["value"][:65 * 256],
        expected_output=oracle.pack(base["bits"] + base["bits"] + live["bits"], 32),
        expected_flags=struct.pack("<III", base["natural_flags"], base["natural_flags"], live["natural_flags"]))
    assembly = [".section .rodata"]
    for symbol, raw in binaries.items():
        path = inputs / (symbol + ".bin")
        with path.open("xb") as stream:
            stream.write(raw)
        assembly += [".balign 64", ".global " + symbol, symbol + ":", ".incbin " + json.dumps(str(path))]
    assembly += ['.section .note.GNU-stack,"",@progbits', ""]
    with (inputs / "data.S").open("x") as stream:
        stream.write("\n".join(assembly))
    for source, name in ((HERE / "compute_views.c", "compute_views.c"),
                         (HERE.parent / "compute_start_sv39.S", "compute_start_sv39.S"),
                         (HERE.parent / "client.ld", "client.ld"),
                         (header, "kernel_compute.h"), (core, "compute.o"),
                         (compute / "module/sdk/shim/stdint.h", "stdint.h")):
        pin(source)
        shutil.copyfile(source, inputs / name)
    for path in inputs.iterdir():
        pin(path)
    compiler = GNU / "riscv64-linux-gcc"
    readelf = GNU / "riscv64-linux-readelf"
    for path in (compiler, readelf):
        pin(path)
    run("compiler-version", [compiler, "--version"])
    flags = ["-O2", "-Wall", "-Wextra", "-Werror", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64",
             "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-ffreestanding", "-fno-builtin",
             "-fno-stack-protector", "-fno-tree-loop-distribute-patterns", "-fno-tree-vectorize",
             "-fno-tree-slp-vectorize", "-fno-fast-math", "-ffp-contract=off", "-I" + str(inputs)]
    objects = [inputs / "compute.o"]
    for name in ("compute_views.c", "compute_start_sv39.S", "data.S"):
        obj = out / (name + ".o")
        run("build-" + name, [compiler, *flags, "-c", inputs / name, "-o", obj])
        objects.append(obj)
    elf = out / "compute-views.elf"
    run("link", [compiler, *flags, "-nostdlib", "-static", "-Wl,--no-relax",
                 "-T" + str(inputs / "client.ld"), *objects, "-o", elf])
    for path in (core, elf):
        description = run("elf-" + path.stem, [readelf, "-h", path])
        require("soft-float ABI" in description, "LP64 ABI required")
    relocations = run("core-relocations", [readelf, "-rW", core])
    require("R_RISCV_ALIGN" not in relocations and "R_RISCV_RELAX" not in relocations, "Core must be norelax")
    cases = [dict(index=i, name=name, expected_outputs=result["bits"], expected_flags=result["natural_flags"],
                  key_token_stride=0 if i == 0 else 512, value_token_stride=0 if i == 0 else 512,
                  changed_halfwords=changed_halfwords if i == 2 else 0)
             for i, (name, result) in enumerate((("packed", base), ("head_interleaved_nan", base), ("same_storage_updated", live)))]
    verify(pins)
    save(out / "source-pins.json", pins)
    save(out / "commands.json", commands)
    build = dict(state=STATE, elf=str(elf), elf_sha256=sha(elf), core_sha256=sha(core),
                 module_sha256=sha(module), compute_output=str(compute), module_executed=False,
                 supervisor_sv39_high_va=True, kernel_booted=False, board_executed=False,
                 dimension=128, heads=2, tokens=65, scale_bits=0x3db504f3, cases=cases,
                 nan_padding_halfwords_per_strided_call=2 * 65 * 128, selected_kv_head=1,
                 golden="independent captured-data SoftFloat/tile64 fixture; recomputed after mutation",
                 mutation="K row rotate dimensions +1; V row rotate +7 and flip even-dimension signs",
                 data_capture=str(oracle.DATA), source_pins_sha256=sha(out / "source-pins.json"))
    save(out / "build.json", build)
    print(json.dumps({k: v for k, v in build.items() if k != "cases"}))


if __name__ == "__main__":
    main()
