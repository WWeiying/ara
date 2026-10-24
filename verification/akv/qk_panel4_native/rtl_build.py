#!/usr/bin/env python3
"""Build only: captured QK singles/PANEL4 against independent scalar host fmaf."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CAPTURE = Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252/kv128")
CC = Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
HOST_FLAGS = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-fno-fast-math",
              "-ffp-contract=off", "-frounding-math", "-fexcess-precision=standard",
              "-fno-builtin-fmaf", "-fno-tree-vectorize"]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def cases():
    return [dict(id=i, head=i // 4, tile=0 if i % 4 < 2 else 64,
                 vl=(1, 64, 7, 63)[i % 4], stride=320 if i % 4 < 2 else 256)
            for i in range(8)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "verification/out/akv-qk-panel4-rtl-gate-build-20261023-01")
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    commands, pins = [], {}

    def pin(paths):
        for path in paths:
            path = Path(path).resolve(strict=True)
            digest = sha(path)
            if str(path) in pins and pins[str(path)] != digest:
                raise ValueError("Input changed during preparation: " + str(path))
            pins[str(path)] = digest

    def run(argv, name):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        write_json(out / "commands.json", commands)
        with (out / (name + ".log")).open("x") as stream:
            subprocess.run(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=120, check=True)
        return (out / (name + ".log")).read_text()

    helper = ROOT / "verification/akv/refill_overlap_probe/build.py"
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("elf_tools", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    common = ROOT / "apps/common"
    hostcc = Path("/usr/bin/gcc")
    objdump = CC.with_name("riscv64-unknown-elf-objdump")
    readelf = CC.with_name("riscv64-unknown-elf-readelf")
    accepted = ROOT / "verification/out/akv-refill-attention-abba-20261023-01/manifest.json"
    simroot = ROOT / "verification/out/qbacc-soc-20261023-02"
    simv = simroot / "build/sim/simv"
    pin([*HERE.glob("rtl_*"), helper, CC, hostcc, objdump, readelf, sys.executable,
         common / "arch.link.ld", accepted, simv, simroot / "source-pins.json",
         simroot / "status.json"])
    run([sys.executable, "-B", "-m", "unittest", "discover", "-s", HERE,
         "-p", "rtl_test.py", "-v"], "host-tests")
    original = json.loads(accepted.read_text())
    capture_files = [CAPTURE / "decode/block" / (name + suffix)
                     for name in ("attn_q_input-0", "attn_k_input-0", "attn_v_input-0",
                                  "attn_mask_input-0", "kqv_out-0")
                     for suffix in (".json", ".bin")]
    capture_files += [CAPTURE / "replay/manifest.json",
                      CAPTURE / "replay/cases/operator/decode/attention_core/case.json"]
    if any(original.get(str(f)) != sha(f) for f in capture_files):
        raise ValueError("Capture differs from accepted KV128 source pins")
    pin(capture_files)
    geometry = {
        "attn_q_input-0": ("f32", [128, 1, 12, 1], [4, 512, 512, 6144], 6144),
        "attn_k_input-0": ("f16", [128, 256, 2, 1], [2, 256, 65536, 131072], 131072),
        "attn_v_input-0": ("f16", [128, 256, 2, 1], [2, 256, 65536, 131072], 131072),
    }
    for name, expected in geometry.items():
        meta = json.loads((CAPTURE / "decode/block" / (name + ".json")).read_text())
        if (meta["type"], meta["shape"], meta["strides"], meta["nbytes"]) != expected:
            raise ValueError("Unexpected captured tensor geometry")
        if (CAPTURE / "decode/block" / (name + ".bin")).stat().st_size != expected[3]:
            raise ValueError("Bad captured tensor length")
    mask = (CAPTURE / "decode/block/attn_mask_input-0.bin").read_bytes()
    visible = [i for i, (v,) in enumerate(struct.iter_unpack("<e", mask)) if v != -math.inf]
    if visible != list(range(128)):
        raise ValueError("Require the genuine visible KV128 capture")
    q32 = (CAPTURE / "decode/block/attn_q_input-0.bin").read_bytes()
    if not all(math.isfinite(v) for (v,) in struct.iter_unpack("<f", q32)):
        raise ValueError("Nonfinite captured Query")
    q16 = b"".join(struct.pack("<e", v) for (v,) in struct.iter_unpack("<f", q32))
    (out / "query_f16.bin").write_bytes(q16)
    for toolchain in (hostcc, CC):
        run([toolchain, "--version"], "version-" + toolchain.name)
        for tool in ("cc1", "as", "ld"):
            path = run([toolchain, "-print-prog-name=" + tool], toolchain.name + "-" + tool).strip()
            import shutil
            pin([path if "/" in path else shutil.which(path)])
    pin([run([CC, "-print-libgcc-file-name"], "libgcc-path").strip()])
    hostdeps = run([hostcc, *HOST_FLAGS, "-M", "-MT", "oracle", HERE / "rtl_oracle.c"], "host-deps")
    pin(shlex.split(hostdeps.replace("\\\n", " ").split(":", 1)[1]))
    oracle = out / "host_oracle"
    run([hostcc, *HOST_FLAGS, HERE / "rtl_oracle.c", "-lm", "-o", oracle], "host-compile")
    dynamic = run(["/usr/bin/ldd", oracle], "host-libraries")
    pin(re.findall(r"(/[^\s()]+)", dynamic))
    pin(["/usr/bin/ldd", "/usr/bin/objdump"])
    host_disasm = run(["/usr/bin/objdump", "-d", oracle], "host-disassembly")
    if not re.search(r"call[^\n]*<fmaf@plt>", host_disasm):
        raise ValueError("Oracle must call the pinned host libm fmaf")
    generated = run([oracle, out / "query_f16.bin", CAPTURE / "decode/block/attn_k_input-0.bin",
                     out / "golden.bin"], "host-oracle")
    records = cases()
    lines = generated.splitlines()
    if len(lines) != 8 or (out / "golden.bin").stat().st_size != 12288:
        raise ValueError("Incomplete independent oracle")
    for c, line in zip(records, lines):
        prefix = (f"ORACLE case={c['id']} kvhead={c['head']} tile={c['tile']} "
                  f"vl={c['vl']} stride={c['stride']} outputs={6*c['vl']} fcsr=")
        if not line.startswith(prefix) or not line[len(prefix):].isdigit():
            raise ValueError("Oracle shape/flags record mismatch")
        c["fcsr"] = int(line[len(prefix):])
        if c["fcsr"] & ~31:
            raise ValueError("Invalid mapped floating-point flags")
    header = ("#include <stdint.h>\nstatic const struct { unsigned head,tile,vl,stride,fcsr; } rtl_cases[8] = {\n" +
              "".join("{%d,%d,%d,%d,%d},\n" % tuple(c[k] for k in ("head", "tile", "vl", "stride", "fcsr")) for c in records) + "};\n")
    (out / "rtl_data.h").write_text(header)
    blobs = {"rtl_q": out / "query_f16.bin", "rtl_k": CAPTURE / "decode/block/attn_k_input-0.bin",
             "rtl_v": CAPTURE / "decode/block/attn_v_input-0.bin", "rtl_golden": out / "golden.bin"}
    data = ".section .rodata.rtl_inputs,\"a\",@progbits\n" + "".join(
        f".balign 64\n.global {name}\n{name}:\n.incbin \"{path}\"\n" for name, path in blobs.items())
    (out / "rtl_data.S").write_text(data)
    template = (common / "arch.link.ld").read_text()
    if template.count("LENGTH = 0x00100000") != 1 or template.count("*(.bss)") != 1:
        raise ValueError("Link script template changed")
    (out / "rtl_link.ld").write_text(template.replace("ALIGNMENT", "16").replace(
        "LENGTH = 0x00100000", "LENGTH = 0x01000000").replace("*(.bss)", "*(.bss .bss.*)"))
    flags = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-mcmodel=medany", "-mno-relax",
             "-O3", "-std=gnu11", "-fno-fast-math", "-ffp-contract=off", "-fno-tree-vectorize",
             "-fno-common", "-ffunction-sections", "-fdata-sections", "-ffreestanding",
             "-fno-builtin", "-fno-tree-loop-distribute-patterns", "-DAKV_REFILL_OVERLAP=0",
             "-DNR_LANES=4", "-DVLEN=1024", "-Wno-unknown-pragmas",
             "-I" + str(ROOT), "-I" + str(out), "-I" + str(common),
             "-I" + str(ROOT / "software/akv/include"), "-I" + str(ROOT / "apps/include")]
    sources = [HERE / "rtl_main.c", HERE / "rtl_native.c",
               ROOT / "software/akv/src/akv_runtime.c", ROOT / "software/akv/src/akv_native_riscv.c",
               ROOT / "software/akv/src/akv_v2_attention_rvv.S",
               *[common / n for n in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c")],
               out / "rtl_data.S"]
    for i, source in enumerate(sources):
        dep = run([CC, *flags, "-M", "-MT", "object", source], f"deps-{i}")
        pin(shlex.split(dep.replace("\\\n", " ").split(":", 1)[1]))
    pin([out / "rtl_link.ld", *blobs.values(), oracle])
    write_json(out / "source-pins.json", pins)
    objects = []
    for i, source in enumerate(sources):
        obj = out / f"{i}.o"
        extra = ["-Wall", "-Wextra", "-Werror"] if source == HERE / "rtl_main.c" else []
        run([CC, *flags, *extra, "-c", source, "-o", obj], f"compile-{i}")
        if source == common / "string.c":
            module.check_libc(run([objdump, "-dr", obj], "libc-disassembly"))
        objects.append(obj)
    elf = out / "akv_qk_panel4_rtl.elf"
    run([CC, *flags, "-static", "-nostdlib", "-nostartfiles", *objects,
         "-Wl,--gc-sections", "-Wl,-Map=" + str(out / "link.map"),
         "-T", out / "rtl_link.ld", "-lgcc", "-o", elf], "link")
    disasm = run([objdump, "-d", elf], "disassembly")
    for name in ("akv_device_query", "akv_native_info", "rtl_akv_full", "rtl_akv_release",
                 "akv_v2_compute_scores_f16_d128_gqa6", "akv_v2_compute_scores_f16_d128_gqa6_panel4"):
        if f"<{name}>:" not in disasm or (name != "akv_native_info" and not re.search(r"\b(?:jalr?|jr?)\b[^\n]*<" + re.escape(name) + ">", disasm)):
            raise ValueError("Missing native call/symbol: " + name)
    sections = module.alloc_sections(elf)
    if min(s["address"] for s in sections) < 0x80000000 or max(s["address"] + s["bytes"] for s in sections) > 0x81000000 - 65536:
        raise ValueError("ELF outside 16 MiB image/stack bounds")
    run([readelf, "-lW", elf], "elf-segments")
    if any(sha(path) != digest for path, digest in pins.items()):
        raise ValueError("Source/tool/generated input drift")
    artifacts = {str(f): sha(f) for f in sorted(out.iterdir()) if f.is_file()}
    write_json(out / "build.json", dict(state="BUILT_NOT_EXECUTED", execution="NOT_RUN",
        elf=str(elf), elf_sha256=sha(elf), source_pins_sha256=sha(out / "source-pins.json"),
        artifact_sha256=artifacts, post_pins_match=True, cases=records, sections=sections,
        source_pins=str(out / "source-pins.json"), capture=str(CAPTURE), simv=str(simv),
        simulator_prior_status=json.loads((simroot / "status.json").read_text())["state"],
        simulator_pass_receipt_required_from_parent=True,
        expected=dict(pairs=8, runs=16, outputs=3240, tailwords=2904, full=16, release=16,
                      column_single=1024, column_panel4=256, logical_columns=2048, commands=1312),
        oracle="Python struct <e RNE conversion; independent scalar host libm fmaf, dimensions 0..127; explicit FE-to-RISC-V flag map",
        scope="Score kernel only; direct calls OFF/ON, not getenv selection or whole-Attention; NO simulator run or performance claim"))
    print(json.dumps(dict(state="BUILT_NOT_EXECUTED", elf=str(elf), elf_sha256=sha(elf))))


if __name__ == "__main__":
    main()
