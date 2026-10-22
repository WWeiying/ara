#!/usr/bin/env python3
"""Build only this diagnostic in a fresh directory using the existing LLVM."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    apps = root / "apps"
    common = apps / "common"
    isa = apps / "riscv-tests/isa"
    llvm = root / "install/riscv-llvm"
    cc = llvm / "bin/clang"
    source = Path(__file__).with_name("gap29_fp16_rne_diag.c")
    flags = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d",
             "--target=riscv64-unknown-elf", "-mcmodel=medany", "-mno-relax",
             "-O2", "-std=gnu99", "-fno-vectorize", "-fno-slp-vectorize",
             "-mno-implicit-float", "-fno-common", "-fno-builtin-printf",
             "-ffunction-sections", "-fdata-sections", "-DNR_LANES=4", "-DVLEN=1024"]
    includes = [f"-I{apps / 'include'}", f"-I{common}",
                f"-I{isa / 'macros/scalar'}", f"-I{isa / 'macros/vector'}"]
    commands = []
    inputs = [source, Path(__file__), isa / "rv64uv/vrvv_gap29_fp16_rne_m4.c",
              isa / "rv64uv/vrvv_gap29_body.h", cc, llvm / "bin/ld.lld"]
    for directory in (common, apps / "include", isa / "macros"):
        inputs.extend(p for p in directory.rglob("*")
                      if p.is_file() and p.suffix in (".c", ".h", ".S", ".ld"))
    pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    (out / "input_hashes.json").write_text(json.dumps(pins, indent=2) + "\n")

    def command(argv):
        argv = list(map(str, argv))
        commands.append(argv)
        (out / "build_commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        subprocess.run(argv, check=True, cwd=root)

    objects = []
    for filename in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c"):
        obj = out / (filename + ".o")
        command([cc, *flags, *includes, "-c", common / filename, "-o", obj])
        objects.append(obj)
    elf = out / "gap29_fp16_rne_diag.elf"
    command([cc, *flags, *includes, "-fuse-ld=lld", "-static", "-nostartfiles",
             "-Wl,--gc-sections", f"-T{common / 'link.ld'}", source, *objects,
             "-lm", f"-L{llvm.resolve() / 'lib/generic'}",
             "-lclang_rt.builtins-riscv64", "-o", elf])
    with (out / "gap29_fp16_rne_diag.dump").open("x") as stream:
        subprocess.run([llvm / "bin/llvm-objdump", "-d", elf], stdout=stream, check=True)
    if pins != {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}:
        raise RuntimeError("source/tool drift during diagnostic build")
    print(elf)


if __name__ == "__main__":
    main()
