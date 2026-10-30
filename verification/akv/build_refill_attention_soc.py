#!/usr/bin/env python3
"""Build isolated shared-runtime REFILL schedule twins from a real capture."""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification/qbs"))
from run_half_scale_soc import atomic_json, digest, hashes
from importlib.util import spec_from_file_location, module_from_spec
from refill_overlap_probe.build import alloc_sections, check_libc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture = args.capture.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    gcc = Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
    objdump = gcc.with_name("riscv64-unknown-elf-objdump")
    generator = ROOT / "apps/llama_q4km_operator/script/gen_data.py"
    env = os.environ.copy()
    env["Q4KM_CAPTURE_ROOT"] = str(capture)
    spec = spec_from_file_location("attention_data", generator)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CAPTURE_ROOT = capture
    kind, flags, shape, _, blobs = module.make_spec("operator/decode/attention_core", "akv_v2")
    if (kind != "attention_core" or flags != 8 or
            shape[:5] != [128, 1, 12, 256, 2]):
        raise ValueError("Require the pinned D128/12Q/2KV real capture layout")
    # The physical capture has 256 entries, only the causal 128-prefix is live.
    mask = blobs["input_d"]["data"].read_bytes()
    import struct
    active = [i for i, (v,) in enumerate(struct.iter_unpack("<e", mask))
              if v != float("-inf")]
    if active != list(range(128)):
        raise ValueError("Expected exactly 128 active causal KV positions")
    common = ROOT / "apps/common"
    sources = [ROOT / "verification/akv/refill_attention_soc.c",
               ROOT / "apps/llama_q4km_operator/akv_runtime.c",
               ROOT / "apps/llama_q4km_operator/akv_prefill_reference.c",
               ROOT / "apps/llama_q4km_operator/akv_attention.S",
               ROOT / "apps/llama_q4km_operator/akv_v2_attention.S",
               *[common / n for n in ("crt0.S", "printf.c", "string.c",
                                      "serial.c", "util.c", "print_trap_cause.c")]]
    flags = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-mcmodel=medany",
             "-mno-relax", "-O3", "-std=gnu11", "-fno-fast-math",
             "-ffp-contract=off", "-fno-tree-vectorize", "-fno-common",
             "-ffunction-sections", "-fdata-sections", "-ffreestanding",
             "-fno-builtin", "-fno-tree-loop-distribute-patterns",
             "-DNR_LANES=4", "-DVLEN=1024", "-Wno-unknown-pragmas",
             "-I" + str(common), "-I" + str(ROOT / "apps/include")]
    commands = []

    def run(argv, label, environment=None):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        atomic_json(out / "commands.json", commands)
        with (out / (label + ".log")).open("x") as stream:
            subprocess.run(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                           env=environment, check=True, timeout=120)
        return (out / (label + ".log")).read_text()

    pins = {generator, Path(__file__), common / "arch.link.ld",
            ROOT / "verification/qbs/run_half_scale_soc.py",
            ROOT / "verification/akv/refill_overlap_probe/build.py",
            capture / "replay/manifest.json",
            capture / "replay/cases/operator/decode/attention_core/case.json",
            gcc.resolve(), objdump.resolve()}
    for value in blobs.values():
        if value:
            pins.update((value["meta"], value["data"]))
    for i, source in enumerate(sources):
        depfile = out / f"deps-{i}.d"
        run([gcc, *flags, "-DAKV_REFILL_OVERLAP=1", "-M", "-MF", depfile,
             "-MT", "object", source], f"deps-{i}")
        body = depfile.read_text().replace("\\\n", " ").split(":", 1)[1]
        pins.update(Path(p).resolve(strict=True) for p in shlex.split(body))
    for name in ("libm.a", "libgcc.a"):
        pins.add(Path(subprocess.check_output(
            [gcc, "-print-file-name=" + name], text=True).strip()).resolve(strict=True))
    before = hashes(pins)
    atomic_json(out / "manifest.json", before)
    generated = subprocess.check_output(
        [sys.executable, generator, "operator/decode/attention_core", "akv_v2"],
        cwd=out, env=env, text=True)
    data = out / "data.S"
    data.write_text(generated)
    link = out / "link.ld"
    template = (common / "arch.link.ld").read_text()
    if template.count("LENGTH = 0x00100000") != 1:
        raise ValueError("Link script template changed")
    link.write_text(template.replace("ALIGNMENT", "16").replace(
        "LENGTH = 0x00100000", "LENGTH = 0x01000000"))
    builds = {}
    for overlap in (0, 1):
        objects = []
        for i, source in enumerate([*sources, data]):
            obj = out / f"schedule{overlap}-{i}.o"
            run([gcc, *flags, f"-DAKV_REFILL_OVERLAP={overlap}", "-c", source,
                 "-o", obj], f"compile-{overlap}-{i}")
            if source == common / "string.c":
                check_libc(run([objdump, "-dr", obj], f"libc-{overlap}"))
            objects.append(obj)
        elf = out / f"attention_schedule{overlap}.elf"
        run([gcc, *flags, "-static", "-nostdlib", "-nostartfiles", *objects,
             "-Wl,--gc-sections", "-Wl,-Map=" + str(out / f"schedule{overlap}.map"),
             "-T", link, "-lm", "-lgcc", "-o", elf], f"link-{overlap}")
        disassembly = run([objdump, "-d", elf], f"disassembly-{overlap}")
        # Both entries share one assembly section; presence is not execution.
        called = re.search(r"\b(?:jalr?|jr?)\b[^\n]*"
                           r"<akv_v2_update_outputs_f16_d128_gqa6_refill>",
                           disassembly) is not None
        if called != bool(overlap):
            raise ValueError("Candidate REFILL entry reachability mismatch")
        sections = alloc_sections(elf)
        if (min(s["address"] for s in sections) < 0x80000000 or
            max(s["address"] + s["bytes"] for s in sections) > 0x81000000 - 65536):
            raise ValueError("ELF violates 16 MiB L2 / 64 KiB stack reserve")
        builds[str(overlap)] = dict(elf=str(elf), elf_sha256=digest(elf), sections=sections)
    if hashes(pins) != before:
        raise ValueError("Build input drift")
    atomic_json(out / "build.json", dict(state="BUILT_NOT_EXECUTED", variants=builds,
        manifest_sha256=digest(out / "manifest.json"),
        generated_sha256=hashes([data, link]), effective_kv=128,
        capture=str(capture), outputs=1536, head_dim=128, q_heads=12, kv_heads=2,
        scope="Complete captured Decode Attention through shared production runtime"))


if __name__ == "__main__":
    main()
