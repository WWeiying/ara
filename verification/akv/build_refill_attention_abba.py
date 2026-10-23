#!/usr/bin/env python3
"""Link both shared-runtime schedules into one fixed-address ABBA ELF."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification/qbs"))
from run_half_scale_soc import atomic_json, digest, hashes
from refill_overlap_probe.build import alloc_sections


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    previous = args.previous.resolve(strict=True)
    report = json.loads((previous / "build.json").read_text())
    pins = json.loads((previous / "manifest.json").read_text())
    if (report["state"] != "BUILT_NOT_EXECUTED" or
        digest(previous / "manifest.json") != report["manifest_sha256"] or
        hashes(map(Path, pins)) != pins or
        hashes(map(Path, report["generated_sha256"])) != report["generated_sha256"]):
        raise ValueError("Previous build identity drift")
    commands = json.loads((previous / "commands.json").read_text())
    old_link = [c["argv"] for c in commands if "-nostdlib" in c["argv"]]
    old_compile = [c["argv"] for c in commands if "-c" in c["argv"] and
                   str(previous / "schedule0-0.o") in c["argv"]]
    if len(old_link) != 2 or len(old_compile) != 1:
        raise ValueError("Ambiguous previous build commands")
    gcc = Path(old_compile[0][0])
    nm = gcc.with_name("riscv64-unknown-elf-nm")
    objdump = gcc.with_name("riscv64-unknown-elf-objdump")
    objects = [previous / f"schedule0-{i}.o" for i in range(12)]
    main = ROOT / "verification/akv/refill_attention_abba_soc.c"
    runtime = ROOT / "apps/llama_q4km_operator/akv_runtime.c"
    pins.update(hashes([Path(__file__), main, previous / "commands.json", previous / "build.json",
                       *objects, nm.resolve(), objdump.resolve(), *map(Path, report["generated_sha256"])]))
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    issued = []
    def invoke(argv, name):
        argv = list(map(str, argv)); issued.append(argv)
        atomic_json(out / "commands.json", issued)
        with (out / (name + ".log")).open("x") as stream:
            subprocess.run(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=120, check=True)
        return (out / (name + ".log")).read_text()
    # Authenticate the otherwise unsealed old objects by reproducing the ELF.
    replay = [str(out / "replayed.elf") if t == report["variants"]["0"]["elf"] else
              "-Wl,-Map=" + str(out / "replayed.map") if t.startswith("-Wl,-Map=") else t
              for t in old_link[0]]
    invoke(replay, "relink-baseline")
    if digest(out / "replayed.elf") != report["variants"]["0"]["elf_sha256"]:
        raise ValueError("Old objects do not reproduce the accepted baseline")
    flags = old_compile[0][1:old_compile[0].index("-c")]
    main_object, candidate = out / "main.o", out / "candidate.o"
    invoke([gcc, *flags, "-c", main, "-o", main_object], "main")
    exports = invoke([nm, "--defined-only", "-g", objects[1]], "exports")
    symbols = [line.split()[-1] for line in exports.splitlines() if line.split()[1] == "T"]
    if len(symbols) != 21 or any(not n.startswith("akv_") for n in symbols):
        raise ValueError("Shared runtime export boundary changed")
    flags_on = [f for f in flags if not f.startswith("-DAKV_REFILL_OVERLAP=")]
    invoke([gcc, *flags_on, "-DAKV_REFILL_OVERLAP=1",
            *[f"-D{n}={n}_candidate" for n in symbols], "-c", runtime, "-o", candidate], "candidate")
    elf = out / "attention_abba.elf"
    link = [str(main_object) if t == str(objects[0]) else
            str(elf) if t == report["variants"]["0"]["elf"] else
            "-Wl,-Map=" + str(out / "link.map") if t.startswith("-Wl,-Map=") else t
            for t in old_link[0]]
    link[link.index("-lm"):link.index("-lm")] = [str(candidate), "-Wl,--wrap=akv_attention_execute_v2_native"]
    invoke(link, "link")
    sections = alloc_sections(elf)
    if (min(s["address"] for s in sections) < 0x80000000 or
        max(s["address"]+s["bytes"] for s in sections) > 0x81000000-65536):
        raise ValueError("ELF exceeds the L2/stack bound")
    listing = invoke([objdump, "-d", elf], "disassembly")
    for name in ("__wrap_akv_attention_execute_v2_native",
                 "akv_attention_execute_v2_native_candidate",
                 "akv_attention_execute_v2_native"):
        if "<" + name + ">:" not in listing:
            raise ValueError("Missing runtime variant/wrapper")
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Input drift")
    pins.update(hashes(path for path in out.iterdir() if path.is_file()))
    atomic_json(out / "manifest.json", pins)
    atomic_json(out / "build.json", dict(state="READY", execution="NOT_RUN",
        elf=str(elf), elf_sha256=digest(elf), manifest_sha256=digest(out / "manifest.json"),
        scope="One ELF, identical capture/scratch/output addresses; ABBA shared-runtime schedule comparison"))


if __name__ == "__main__":
    main()
