#!/usr/bin/env python3
"""Fail-closed native AKV prerequisite probe, not an Attention numeric gate."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import shlex
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_QEMU = ROOT / "verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64"
DEFAULT_CC = Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
CPU = "rv64,v=true,vlen=1024,elen=64,xaraqbs=true,zfh=true,zvfh=true"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def classify(text, returncode, info_pc):
    pattern = (r"AKV_PROBE_BEGIN\nAKV_PROBE_TRAP cause=0000000000000002 "
               r"pc=([0-9a-f]{16}) value=000000000005455b\n")
    match = re.fullmatch(pattern, text)
    if not match or returncode != 2 or int(match[1], 16) != info_pc:
        raise RuntimeError("Unexpected native probe result; no numerical PASS accepted")
    return {"state": "BLOCKED", "reason": "actual_akv_native_info_illegal_instruction",
            "numerical_cases_executed": 0, "native_panel4_proven": False,
            "mcause": 2, "mtval": 0x0005455b, "mepc": info_pc}


def run_bounded(command, timeout):
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except BaseException:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        raise
    return p.returncode, out, err


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--cc", type=Path, default=DEFAULT_CC)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    qemu, cc = args.qemu.resolve(), args.cc.resolve()
    report = {"state": "FAIL", "scope": "native-capability-preflight-only",
              "cpu": CPU, "commands": [], "numerical_cases_executed": 0}
    pins = {}
    sys.dont_write_bytecode = True
    verifier = ROOT / "verification/qbs/run_ggml_segmented.py"
    spec = importlib.util.spec_from_file_location("attestation", verifier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def pin(paths):
        for path in paths:
            path = Path(path).resolve()
            pins[str(path)] = sha(path)

    def command(argv, timeout=120):
        argv = list(map(str, argv))
        report["commands"].append(argv)
        rc, stdout, stderr = run_bounded(argv, timeout)
        index = len(report["commands"])
        (out / f"command-{index}.stdout").write_bytes(stdout)
        (out / f"command-{index}.stderr").write_bytes(stderr)
        if rc:
            raise RuntimeError(f"Command {index} failed ({rc}): {stderr.decode(errors='replace')}")
        return stdout.decode()

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError("SIGTERM")))
    try:
        attested = module.verify_native_build(qemu)
        model = qemu.parent.parent / "qemu-10.2.0/target/riscv"
        inputs = [*attested, qemu, cc, verifier,
                  *HERE.glob("*.py"), HERE / "probe.c", HERE / "start.S", HERE / "link.ld",
                  ROOT / "software/akv/src/akv_runtime.c",
                  ROOT / "software/akv/src/akv_native_riscv.c",
                  ROOT / "software/akv/src/akv_v2_native_riscv.c",
                  ROOT / "software/akv/src/akv_v2_attention_rvv.S",
                  *sorted((ROOT / "software/akv/include/akv").glob("*.h")),
                  model / "Xaraqbs.decode", model / "insn32.decode",
                  model / "insn_trans/trans_xaraqbs.c.inc", model / "helper.h"]
        pin(inputs)
        accepted = ROOT / "verification/out/akv-refill-attention-abba-20261023-01/manifest.json"
        capture = Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252/kv128")
        original = json.loads(accepted.read_text())
        captured = [capture / "decode/block" / (name + suffix)
                    for name in ("attn_q_input-0", "attn_k_input-0", "attn_v_input-0",
                                 "attn_mask_input-0", "kqv_out-0")
                    for suffix in (".bin", ".json")]
        captured += [capture / "replay/manifest.json",
                     capture / "replay/cases/operator/decode/attention_core/case.json"]
        if any(original.get(str(p)) != sha(p) for p in captured):
            raise RuntimeError("Real KV128 capture differs from accepted ABBA pins")
        mask = (capture / "decode/block/attn_mask_input-0.bin").read_bytes()
        half = struct.unpack("<" + "H" * (len(mask) // 2), mask)
        if len(half) < 128 or any(x & 0x7fff for x in half[:128]) or any(x != 0xfc00 for x in half[128:]):
            raise RuntimeError("Capture does not have the original 128-token visible prefix")
        pin([accepted, *captured])
        report["capture_provenance_only"] = {"root": str(capture), "visible_prefix": 128,
                                             "used_for_numerical_execution": False}
        for tool in ("cc1", "as", "ld"):
            pin([command([cc, f"-print-prog-name={tool}"]).strip()])
        libgcc = command([cc, "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d",
                          "-print-libgcc-file-name"]).strip()
        pin([libgcc])
        objdump = cc.with_name("riscv64-unknown-elf-objdump")
        pin([objdump])
        command([cc, "--version"])
        command([qemu, "--version"])
        for source in (HERE / "probe.c", ROOT / "software/akv/src/akv_runtime.c",
                       ROOT / "software/akv/src/akv_native_riscv.c"):
            deps = command([cc, "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d",
                            "-I", ROOT / "software/akv/include", "-M", "-MT", "deps", source])
            pin(shlex.split(deps.replace("\\\n", " ").split(":", 1)[1]))
        elf = out / "probe.elf"
        command([cc, "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-mcmodel=medany",
                 "-O2", "-Wall", "-Wextra", "-Werror", "-ffreestanding", "-fno-builtin",
                 "-ffunction-sections", "-fdata-sections", "-nostdlib",
                 "-I", ROOT / "software/akv/include", "-T", HERE / "link.ld",
                 HERE / "start.S", HERE / "probe.c",
                 ROOT / "software/akv/src/akv_runtime.c",
                 ROOT / "software/akv/src/akv_native_riscv.c",
                 "-Wl,--gc-sections", "-Wl,-Map=" + str(out / "probe.map"),
                 "-lgcc", "-o", elf])
        disasm = command([objdump, "-d", elf])
        (out / "probe.disasm").write_text(disasm)
        body = re.search(r"<akv_native_info>:\n(.*?)(?:\n\n|\Z)", disasm, re.S)
        matches = [] if body is None else re.findall(r"^\s*([0-9a-f]+):\s+0005455b\b", body[1], re.M)
        if len(matches) != 1:
            raise RuntimeError("Cannot attest actual linked AKV INFO instruction")
        info_pc = int(matches[0], 16)
        # Never start QEMU after any input drift during compilation.
        if any(sha(p) != digest for p, digest in pins.items()):
            raise RuntimeError("Source/tool drift before QEMU")
        argv = list(map(str, [qemu, "-machine", "virt", "-cpu", CPU, "-smp", "1",
                             "-m", "128M", "-bios", "none", "-kernel", elf,
                             "-display", "none", "-monitor", "none", "-serial", "stdio",
                             "-no-reboot"]))
        report["commands"].append(argv)
        started = time.monotonic()
        rc, stdout, stderr = run_bounded(argv, 60)
        report["qemu_elapsed_seconds"] = time.monotonic() - started
        report["qemu_returncode"] = rc
        (out / "qemu.log").write_bytes(stdout)
        (out / "qemu.stderr").write_bytes(stderr)
        report.update(classify(stdout.decode("ascii"), rc, info_pc))
    except Exception as exc:
        report.update(state="FAIL", error=str(exc))
    finally:
        report["source_sha256"] = pins
        report["post_pins_match"] = all(Path(p).is_file() and sha(p) == digest
                                         for p, digest in pins.items())
        if not report["post_pins_match"]:
            report.update(state="FAIL", error="Source/tool drift")
        report["artifact_sha256"] = {str(p): sha(p) for p in sorted(out.iterdir()) if p.is_file()}
        (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("state", "scope", "numerical_cases_executed")}))
    return 2 if report["state"] == "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
