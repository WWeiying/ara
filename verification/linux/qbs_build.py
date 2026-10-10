#!/usr/bin/env python3
"""Build the fixed, isolated Linux QBS captured-tile prerequisite."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
from build_userspace import (DEFAULT_BASE_INITRAMFS, DEFAULT_CC, REPO_ROOT,
                             archive_names, file_record, find_tool, install_file)

OUT = REPO_ROOT / "verification/out/linux-qbs-native-20260922"
CAPTURE = Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/decode/operators/blk_0_attn_q_weight")
QEMU_ROOT = Path("/home/wangwy/openproject/ara_dsa_qbs_adaptive/verification/qbs/qemu/build")
QEMU = QEMU_ROOT / "qemu-10.2.0-build/qemu-system-riscv64"
QEMU_SOURCE = QEMU_ROOT / "qemu-10.2.0/target/riscv"
SDK = Path("/home/wangwy/openproject/cva6/cva6-sdk")
KERNEL = REPO_ROOT / "hardware/fpga/ara_dsa_vcu118/linux/artifacts/Image"
FIRMWARE = SDK / "install64_qemu/fw_dynamic.bin"
LINUX = REPO_ROOT / "verification/linux"
CAPTURE_HASHES = {
    "weight_q4_K.bin": "f578b25b8fe8ce69119c2dfd157ed1a98021d699fd6d678a1f8d6aeec4029825",
    "activation_f32.bin": "c053e6e62ba859c90be074c06c449fdc21117beb407e1afc864313cee39044f1",
    "output_f32.bin": "796b1dd56a51e4ff907b36c8f1f053126789f570920f093660720bb6a14684b3",
}
ABI_HASH = "86fb8f1b48ad1ba23d0af07307285f323282ead735354f002db8f5b1d0707015"
QEMU_HASH = "5c586c418708712e5ad1bf377ff9c2f89b3114e2e1178e0aa25b7f053b156068"

INIT = """#!/bin/busybox sh
export PATH=/sbin:/bin:/usr/sbin:/usr/bin
rc=1
mode=unknown
if mkdir -p /proc /sys /dev && mount -t proc proc /proc &&
   mount -t sysfs sysfs /sys && mount -t devtmpfs devtmpfs /dev &&
   cd /qbs && sha256sum -c SHA256SUMS; then
    echo '[QBS_INIT] HASHES PASS'
    case "$(cat /proc/cmdline)" in
      *qbs_mode=native*)
        mode=native
        /usr/bin/qbs_native --require-qbs
        rc=$?
        ;;
      *qbs_mode=fallback*)
        mode=fallback
        /usr/bin/qbs_native --disable-qbs
        rc=$?
        ;;
      *qbs_mode=unsupported*)
        mode=unsupported
        /usr/bin/qbs_native --auto
        auto_rc=$?
        /usr/bin/qbs_native --require-qbs
        require_rc=$?
        echo "[QBS_INIT] auto_rc=$auto_rc require_rc=$require_rc"
        if [ "$auto_rc" -eq 0 ] && [ "$require_rc" -eq 77 ]; then rc=0; fi
        ;;
    esac
fi
echo "[QBS_INIT] mode=$mode rc=$rc"
sync
poweroff -f
while :; do sleep 1; done
"""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="ascii")


def experiment_root(attempt: str | None) -> Path:
    check(attempt is None or re.fullmatch(r"attempt-[0-9]+", attempt) is not None,
          "attempt must be attempt-N")
    path = OUT / attempt if attempt else OUT
    check(not OUT.is_symlink() and not path.is_symlink() and
          path.resolve().is_relative_to(OUT.resolve()), "output escapes sidecar")
    return path


def verify_record(record: dict) -> None:
    check(file_record(Path(record["path"]))["sha256"] == record["sha256"],
          f"hash changed: {record['path']}")


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def quantize(data: bytes) -> bytes:
    check(len(data) == 6144, "activation size")
    values = struct.unpack("<1536f", data)
    check(all(math.isfinite(x) for x in values), "nonfinite activation")
    result = bytearray()
    for start in range(0, 1536, 256):
        block = values[start:start + 256]
        low, high = min(block), max(block)
        peak = high if abs(high) > abs(low) else low
        scale = f32(-127.0 / peak) if peak else 0.0
        quants = [round(f32(x * scale)) for x in block]
        sums = [sum(quants[i:i + 16]) for i in range(0, 256, 16)]
        result.extend(struct.pack("<f256b16h", f32(1.0 / scale) if scale else 0.0,
                                  *quants, *sums))
    return bytes(result)


def freeze_capture(directory: Path, destination: Path) -> dict:
    specifications = {
        "weight_q4_K": ("q4_K", [1536, 1536, 1, 1], [144, 864, 1327104, 1327104], 1327104),
        "activation_f32": ("f32", [1536, 1, 1, 1], [4, 6144, 6144, 6144], 6144),
        "output_f32": ("f32", [1536, 1, 1, 1], [4, 6144, 6144, 6144], 6144),
    }
    source_records, blobs = {}, {}
    for stem, (kind, shape, strides, size) in specifications.items():
        meta_path, data_path = directory / (stem + ".json"), directory / (stem + ".bin")
        meta = json.loads(meta_path.read_text())
        check((meta["type"], meta["shape"], meta["strides"], meta["nbytes"]) ==
              (kind, shape, strides, size), f"capture metadata mismatch: {stem}")
        blob = data_path.read_bytes()
        digest = hashlib.sha256(blob).hexdigest()
        check(len(blob) == size and digest == CAPTURE_HASHES[data_path.name],
              f"capture hash/size mismatch: {stem}")
        source_records[meta_path.name] = file_record(meta_path)
        source_records[data_path.name] = {"path": str(data_path), "sha256": digest}
        blobs[stem] = blob
    op_path = directory / "operator.json"
    op = json.loads(op_path.read_text())
    check(op == {"op": "GGML_OP_MUL_MAT", "phase": "decode",
                 "weight": "blk.0.attn_q.weight", "weight_type": "q4_K",
                 "activation_quantization": "Q8_K", "result_type": "F32"}, "operator metadata")
    source_records[op_path.name] = file_record(op_path)
    data = {"weight.bin": blobs["weight_q4_K"][:27648],
            "activation.bin": blobs["activation_f32"],
            "golden.bin": blobs["output_f32"][:128],
            "activation_q8.bin": quantize(blobs["activation_f32"])}
    golden = struct.unpack("<32f", data["golden.bin"])
    check(all(math.isfinite(x) for x in golden) and any(x != 0 for x in golden),
          "invalid frozen oracle")
    destination.mkdir()
    for name, blob in data.items():
        (destination / name).write_bytes(blob)
    return {"shape": {"m": 1, "n": 32, "k": 1536, "k_blocks": 6},
            "source": source_records,
            "oracle": "Frozen captured GGML output; not QEMU qbs_ref.c",
            "atol": 0.002, "rtol": 0.002,
            "files": {name: {**file_record(destination / name), "bytes": len(blob)}
                      for name, blob in data.items()}}


def validate_elf(path: Path, readelf: str, disassembly: str) -> None:
    header = path.read_bytes()[:64]
    check(header[:7] == b"\x7fELF\x02\x01\x01" and
          struct.unpack_from("<HH", header, 16) == (2, 243), "not RV64 LE EXEC ELF")
    check(struct.unpack_from("<I", header, 48)[0] & 6 == 4, "not LP64D ELF")
    check("INTERP" not in readelf and "NEEDED" not in readelf, "not static ELF")
    check("Tag_RISCV_stack_align: 16" in readelf and
          "_v1p0" in readelf and "_zfh1p0" in readelf and "_zvfh1p0" in readelf,
          "ISA/stack attributes")
    check("0005155b" in disassembly and "00b5045b" in disassembly,
          "native qbinfo/qbexec opcodes absent")


def build(attempt: str | None = None) -> dict:
    output = experiment_root(attempt) / "payload"
    check(not output.exists() and not output.is_symlink(), f"refuse overwrite: {output}")
    pinned = {QEMU: QEMU_HASH,
              REPO_ROOT / "software/qbs/include/qbs/qbs_abi.h": ABI_HASH,
              REPO_ROOT / "apps/common/qbs_abi.h": ABI_HASH,
              QEMU_SOURCE / "qbs_abi.h": ABI_HASH,
              QEMU_SOURCE / "qbs_helper.c": "5ed80e3807f078b75be6c89dc2825af8268fbe04d581fe4623d450b2fcc2c2fd",
              QEMU_SOURCE / "qbs_ref.c": "b694b0e2be20b1bada5388cbf4d23d43c401d67cef827024a5be4966f7fa08fe"}
    for path, digest in pinned.items():
        check(file_record(path)["sha256"] == digest, f"readiness fingerprint changed: {path}")
    compiler = find_tool(DEFAULT_CC)
    objdump = compiler.with_name(compiler.name[:-3] + "objdump")
    readelf = compiler.with_name(compiler.name[:-3] + "readelf")
    sources = [LINUX / "qbs_native.c", REPO_ROOT / "software/qbs/src/qbs_runtime.c",
               REPO_ROOT / "software/qbs/src/qbs_native_riscv.c",
               REPO_ROOT / "apps/llama_q4km_micro/micro_kernels.c"]
    inputs = [*sources, *pinned, compiler, objdump, readelf, find_tool("cpio"),
              find_tool("gdb"), find_tool("timeout"), KERNEL, FIRMWARE,
              DEFAULT_BASE_INITRAMFS, LINUX / "build_userspace.py", LINUX / "run_stage.py",
              LINUX / "qbs_build.py", LINUX / "qbs_trace.gdb", LINUX / "qbs_run.py",
              REPO_ROOT / "software/qbs/include/qbs/qbs.h",
              REPO_ROOT / "apps/llama_q4km_micro/micro_kernels.h",
              REPO_ROOT / "config/qbs_abi.json", QEMU_SOURCE / "Xaraqbs.decode"]
    manifest = {"status": "BUILDING", "inputs": [file_record(p) for p in dict.fromkeys(inputs)],
                "commands": [], "scope": "single-process Linux QEMU QBS DIRECT only",
                "OS_CUSTOM_CONTEXT": "NOT_VALIDATED", "AKV_NATIVE_COMPUTE": "UNAVAILABLE"}
    output.mkdir(parents=True)
    (output / "tmp").mkdir()
    environment = {"PATH": os.environ.get("PATH", os.defpath), "LC_ALL": "C", "TZ": "UTC",
                   "SOURCE_DATE_EPOCH": "0", "TMPDIR": str(output / "tmp")}
    manifest["environment"] = environment

    def run(argv, *, cwd=output, incoming=None, outgoing=None):
        manifest["commands"].append({"argv": list(map(str, argv)), "cwd": str(cwd),
                                     "stdin": getattr(incoming, "name", None),
                                     "stdout": getattr(outgoing, "name", "build.log")})
        dump(output / "manifest.json", manifest)
        with (output / "build.log").open("ab") as log:
            subprocess.run(list(map(str, argv)), cwd=cwd, env=environment, check=True,
                           stdin=incoming or subprocess.DEVNULL, stdout=outgoing or log,
                           stderr=log, timeout=120, umask=0o022)

    capture = freeze_capture(CAPTURE, output / "data")
    dump(output / "capture.json", capture)
    flags = ["-static", "-O2", "-Wall", "-Wextra", "-Werror", "-march=rv64gcv_zfh_zvfh",
             "-mabi=lp64d", "-fno-fast-math", "-ffp-contract=off", "-fno-tree-vectorize",
             "-fno-tree-slp-vectorize", "-ffunction-sections", "-fdata-sections",
             "-Wl,--gc-sections", f"-ffile-prefix-map={REPO_ROOT}=."]
    run([compiler, "--version"])
    run([compiler, *flags, "-I", REPO_ROOT / "software/qbs/include", "-I",
         REPO_ROOT / "apps/llama_q4km_micro", *sources, "-lm", "-o", "qbs_native"])
    for tool, args, name in [(readelf, ["-h", "-l", "-A", "-d"], "elf.txt"),
                             (objdump, ["-d"], "elf.objdump")]:
        with (output / name).open("wb") as stream:
            run([tool, *args, "qbs_native"], outgoing=stream)
    validate_elf(output / "qbs_native", (output / "elf.txt").read_text(),
                 (output / "elf.objdump").read_text())
    rootfs = output / "rootfs"
    rootfs.mkdir(mode=0o755)
    with DEFAULT_BASE_INITRAMFS.open("rb") as incoming:
        run(["cpio", "-idm", "--no-absolute-filenames", "--no-preserve-owner"],
            cwd=rootfs, incoming=incoming)
    if not (rootfs / "lib64").exists() and not (rootfs / "lib64").is_symlink():
        (rootfs / "lib64").symlink_to("lib")
    (output / "init").write_text(INIT, encoding="ascii")
    install_file(output / "init", rootfs / "init", rootfs)
    install_file(output / "qbs_native", rootfs / "usr/bin/qbs_native", rootfs)
    checksums = [f"{file_record(output / 'qbs_native')['sha256']}  /usr/bin/qbs_native\n"]
    for name, record in capture["files"].items():
        install_file(Path(record["path"]), rootfs / "qbs" / name, rootfs)
        checksums.append(f"{record['sha256']}  {name}\n")
    (output / "SHA256SUMS").write_text("".join(checksums), encoding="ascii")
    install_file(output / "SHA256SUMS", rootfs / "qbs/SHA256SUMS", rootfs)
    names = archive_names(rootfs)
    for name in names:
        os.utime(rootfs / name, (0, 0), follow_symlinks=False)
    (output / "cpio-files.list").write_bytes(b"".join(os.fsencode(n) + b"\0" for n in names))
    with (output / "cpio-files.list").open("rb") as incoming, (output / "initramfs.cpio").open("wb") as outgoing:
        run(["cpio", "--null", "-o", "-H", "newc", "--reproducible", "--owner=0:0"],
            cwd=rootfs, incoming=incoming, outgoing=outgoing)
    for record in [*manifest["inputs"], *capture["source"].values(), *capture["files"].values()]:
        verify_record(record)
    manifest["outputs"] = {p.name: file_record(p) for p in output.iterdir()
                           if p.is_file() and p.name != "manifest.json"}
    manifest["status"] = "BUILT"
    dump(output / "manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt")
    args = parser.parse_args()
    build(args.attempt)
    print(json.dumps({"status": "BUILT", "output": str(experiment_root(args.attempt) / "payload")}))
