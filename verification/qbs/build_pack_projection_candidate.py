#!/usr/bin/env python3
"""Reuse frozen real-projection objects; substitute only the activation packer.

No production sources or baseline artifacts are modified. No simulation runs.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from run_half_scale_soc import ROOT, atomic_json, digest, hashes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline-build", type=Path, required=True)
    p.add_argument("--baseline-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    baseline = args.baseline_build.resolve(strict=True)
    report = json.loads((baseline / "build.json").read_text())
    app = report["app"]
    if app != "llama_qwen25_q8_0_prefill_m4_direct_qbs":
        raise ValueError("Only the measured complete DIRECT projection is supported")
    elf = baseline / (app + ".elf")
    if digest(elf) != args.baseline_sha256 or report["elf_sha256"] != args.baseline_sha256:
        raise ValueError("Baseline identity differs")
    commands = json.loads((baseline / "commands.json").read_text())
    link = commands[-1]["argv"]
    compile_command = next(c["argv"] for c in commands if
                           "-c" in c["argv"] and any(x.endswith("/qbs_runtime.c") for x in c["argv"]))
    compiler = Path(link[0]).resolve(strict=True)
    if "gcc" not in compiler.name or "zcc" in str(compiler).lower():
        raise ValueError("GNU compiler required")
    objects = [Path(arg) for arg in link if arg.endswith(".o")]
    if len(objects) != 10 or any(not obj.is_file() for obj in objects):
        raise ValueError("Unexpected frozen object set")
    source = ROOT / "verification/qbs/activation_pack_projection.c"
    header = source.with_name("activation_pack_rvv_candidate.h")
    script = Path(link[link.index("-T") + 1])
    pins = hashes([elf, baseline / "build.json", baseline / "commands.json", script,
                   *objects, compiler, source, header, Path(__file__),
                   ROOT / "software/qbs/include/qbs/qbs.h", ROOT / "apps/common/qbs_abi.h"])
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / "manifest.json", pins)
    replacements = {}
    for old in [*objects, script]:
        new = out / old.name
        shutil.copyfile(old, new)
        if digest(new) != pins[str(old)]:
            raise ValueError("Frozen input changed during copy")
        replacements[str(old)] = str(new)
    flags = compile_command[1:compile_command.index("-c")]
    wrapper = out / "pack-wrapper.o"
    build = [str(compiler), *flags, "-Wall", "-Wextra", "-Werror", "-c", str(source), "-o", str(wrapper)]
    native = out / app
    newlink = [replacements.get(arg, arg) for arg in link]
    newlink[newlink.index("-o") + 1] = str(native)
    newlink = ["-Wl,-Map=" + str(out / "link.map") if arg.startswith("-Wl,-Map=") else arg
               for arg in newlink]
    newlink[1:1] = [str(wrapper), "-Wl,--wrap=qbs_pack_activation_m4"]
    atomic_json(out / "commands.json", [build, newlink])
    for command, name in ((build, "compile"), (newlink, "link")):
        with (out / (name + ".log")).open("x") as log:
            subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=120)
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Pinned inputs changed")
    objdump = compiler.with_name(compiler.name.removesuffix("gcc") + "objdump")
    disassembly = subprocess.check_output([objdump, "-d", native], text=True)
    (out / "disassembly.txt").write_text(disassembly)
    if "<__wrap_qbs_pack_activation_m4>:" not in disassembly or "vsse8.v" not in disassembly:
        raise ValueError("Missing vector pack implementation")
    atomic_json(out / "build.json", dict(state="BUILT_NOT_EXECUTED", app=app,
                baseline_sha256=args.baseline_sha256, candidate_sha256=digest(native),
                object_sha256=hashes(out / obj.name for obj in objects),
                wrapper_sha256=digest(wrapper), manifest_sha256=digest(out / "manifest.json"),
                scope="same real full projection; only private M4 packing wrapper added"))
    print(native)


if __name__ == "__main__":
    main()
