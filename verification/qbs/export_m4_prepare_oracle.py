#!/usr/bin/env python3
"""Export the actual Linux GGML M4 generic's bytes, never candidate output.

Run this worker directly under systemd. It creates a fresh output directory,
builds one sidecar against sealed libraries, and runs one bounded QEMU boot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess

from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "verification/out"
EXPECTED_BYTES = 3808


def check_output(text, vlen=1024):
    if re.search(r"M4_ORACLE_FAIL|Kernel panic|Illegal instruction|Assertion .*failed|"
                 r"Segmentation fault|qemu: fatal", text, re.I):
        raise ValueError("Guest failure in oracle log")
    lines = text.splitlines()
    records = [line for line in lines if "M4_ORACLE_" in line]
    begin = f"M4_ORACLE_BEGIN m=4 k=896 elements=3584 bytes=3808 vlen={vlen}"
    if len(records) != 64 or records[0] != begin:
        raise ValueError("Missing, malformed or duplicate oracle protocol")
    csr = re.fullmatch(r"M4_ORACLE_CSR initial_fcsr=0 initial_vcsr=5 fcsr=(\d+) vcsr=5", records[1])
    if not csr or int(csr[1]) > 31:
        raise ValueError("Wrong CSR environment or non-restored frm/vcsr")
    result = bytearray()
    for line in records[2:-2]:
        row = re.fullmatch(r"M4_ORACLE_HEX offset=(\d+) data=([0-9a-f]+)", line)
        count = min(64, EXPECTED_BYTES - len(result))
        if (not row or count <= 0 or int(row[1]) != len(result)
                or len(row[2]) != count * 2):
            raise ValueError("Missing, reordered, malformed or duplicate hex chunk")
        result.extend(bytes.fromhex(row[2]))
    if (len(result) != EXPECTED_BYTES or records[-2:] !=
            ["M4_ORACLE_END bytes=3808", "M4_ORACLE_EXIT=0"]):
        raise ValueError("Wrong output length or guest exit")
    return bytes(result), dict(initial_fcsr=0, initial_vcsr=5, fcsr=int(csr[1]), vcsr=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT / "qbs-m4-oracle-20261023-01")
    parser.add_argument("--qemu", type=Path, default=OUT /
                        "qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64")
    parser.add_argument("--ggml-build", type=Path, default=OUT /
                        "qbs-ggml-tile-context-20261023-01/build")
    parser.add_argument("--prior", type=Path, default=OUT / "qbs-m4-prepare-native-20261023-02")
    parser.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    parser.add_argument("--platform", type=Path, default=Path("/home/wangwy/llama/platforms/cva6-qemu"))
    parser.add_argument("--capture", type=Path, default=ROOT /
                        "apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/generated/activation_f32.bin")
    parser.add_argument("--vlen", type=int, choices=(128, 1024), default=1024)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 600:
        parser.error("QEMU timeout must be 1..600 seconds")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state="preparing", pid=os.getpid(), child_pid=None, commands=[])

    def save():
        atomic_json(out / "status.json", state)

    def interrupted(signum, _frame):
        raise InterruptedError(f"signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)

    def run(command, name, timeout):
        command = list(map(str, command))
        state["commands"].append(command)

        def started(pid):
            state.update(child_pid=pid, active_log=name)
            save()
        try:
            code = run_command(command, out / name, timeout, os.environ.copy(), started)
            if code:
                raise RuntimeError(f"{name}: return code {code}")
        finally:
            state["child_pid"] = None
            save()

    save()
    try:
        ggml = args.llama.resolve(strict=True) / "ggml"
        build = args.ggml_build.resolve(strict=True)
        platform = args.platform.resolve(strict=True)
        prior_dir = args.prior.resolve(strict=True)
        qemu = args.qemu.resolve(strict=True)
        capture = args.capture.resolve(strict=True)
        if capture.stat().st_size != 14336:
            raise ValueError("Expected 3584 real FP32 activation elements")
        cxx = platform / "tools/bin/riscv64-linux-g++"
        cpio = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
        source = ROOT / "verification/qbs"
        libraries = [build / "ggml/src" / name for name in
                     ("libggml.a", "libggml-cpu.a", "libggml-base.a")]
        provenance = prior_dir / "manifest.json"
        prior_status = prior_dir / "status.json"
        prior = json.loads(provenance.read_text())
        status = json.loads(prior_status.read_text())
        if status.get("state") != "PASS" or [case.get("vlen") for case in status.get("cases", [])] != [128, 1024]:
            raise ValueError("Require the completed two-VLEN production-oracle gate")
        inherited = {path: value for path, value in prior.items()
                     if Path(path).is_relative_to(ggml)}
        required = [ggml / "src/ggml-cpu/repack.cpp", *libraries, capture,
                    build / "compile_commands.json", build.parent / "manifest.json"]
        for path in required:
            if str(path) not in prior:
                raise ValueError(f"Missing original provenance pin: {path}")
            inherited[str(path)] = prior[str(path)]
        if hashes(map(Path, inherited)) != inherited:
            raise ValueError("Reused production sources/libraries/capture changed")
        commands = json.loads((build / "compile_commands.json").read_text())
        oracle = [entry for entry in commands if Path(entry["file"]).resolve() ==
                  (ggml / "src/ggml-cpu/repack.cpp").resolve()]
        if len(oracle) != 1:
            raise ValueError("Missing unique production repack compilation")
        flags = shlex.split(oracle[0]["command"])
        if "-march=rv64gcv" not in flags or "-ffast-math" in flags or "-Ofast" in flags:
            raise ValueError("Unexpected production ISA/FP flags")
        atomic_json(out / "oracle_compile.json", oracle[0])
        sources = [Path(__file__).resolve(), source / "m4_prepare_oracle_init.cpp",
                   source / "run_half_scale_soc.py", source / "run_tile_context_engine.py",
                   provenance, prior_status, *map(Path, inherited), qemu, cpio.resolve(strict=True),
                   cxx.resolve(strict=True), Path(str(cxx) + ".br_real").resolve(strict=True),
                   platform / "images/Image", platform / "images/fw_dynamic.bin"]
        sources += list(ggml.rglob("*.h"))
        for name in ("libm.a", "libc.a", "libstdc++.a", "libgcc.a", "libgcc_eh.a",
                     "crt1.o", "crti.o", "crtn.o", "crtbeginT.o", "crtend.o"):
            path = subprocess.check_output([cxx, "-print-file-name=" + name], text=True, timeout=30).strip()
            sources.append(Path(path).resolve(strict=True))
        for name in ("cc1plus", "as", "ld"):
            path = subprocess.check_output([cxx, "-print-prog-name=" + name], text=True, timeout=30).strip()
            sources.append(Path(path).resolve(strict=True))
        pins = hashes(sources)
        atomic_json(out / "start-pins.json", pins)
        start_hash = digest(out / "start-pins.json")

        def gate(label):
            observed = hashes(sources)
            if (observed != pins or digest(out / "start-pins.json") != start_hash
                    or hashes(map(Path, inherited)) != inherited):
                raise ValueError(f"Source/input/tool provenance drift: {label}")
            atomic_json(out / f"{label}-pins.json", observed)

        gate("prebuild")
        state["state"] = "building"
        binary = out / "init"
        run([cxx, "-std=gnu++17", "-march=rv64gcv", "-mabi=lp64d", "-O3", "-static",
             "-fno-fast-math", "-Wall", "-Wextra", "-Werror",
             "-isystem", ggml / "include", "-isystem", ggml / "src",
             "-isystem", ggml / "src/ggml-cpu", source / "m4_prepare_oracle_init.cpp",
             "-Wl,--start-group", *libraries, "-Wl,--end-group", "-lm", "-ldl", "-pthread",
             "-o", binary], "build.log", 120)
        listing = out / "init.list"
        listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"
                           f"file /init {binary} 755 0 0\nfile /capture.bin {capture} 444 0 0\n")
        archive = out / "init.cpio"
        with archive.open("xb") as target, (out / "cpio.log").open("x") as log:
            subprocess.run([cpio, listing], stdout=target, stderr=log, check=True, timeout=60)
        artifacts = hashes([binary, listing, archive, out / "oracle_compile.json", out / "build.log"])
        atomic_json(out / "pre-exec-artifacts.json", artifacts)
        artifact_pin = digest(out / "pre-exec-artifacts.json")
        gate("pre-exec")
        state["state"] = "running"
        run([qemu, "-M", "virt", "-cpu", f"rv64,v=true,vlen={args.vlen},elen=64",
             "-smp", "1", "-m", "512M", "-display", "none", "-monitor", "none",
             "-serial", "stdio", "-bios", platform / "images/fw_dynamic.bin",
             "-kernel", platform / "images/Image", "-initrd", archive,
             "-append", "console=ttyS0 rdinit=/init"], "qemu.log", args.timeout)
        gate("post")
        if (hashes(map(Path, artifacts)) != artifacts or
                digest(out / "pre-exec-artifacts.json") != artifact_pin):
            raise ValueError("Executed ELF/initramfs/build artifacts changed")
        log = out / "qemu.log"
        log_hash = digest(log)
        data, csr = check_output(log.read_text(), args.vlen)
        if digest(log) != log_hash:
            raise ValueError("QEMU log changed while parsing")
        golden = out / "golden.bin"
        with golden.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        report = dict(state="PASS", golden_sha256=hashlib.sha256(data).hexdigest(),
                      capture_sha256=pins[str(capture)], bytes=len(data), m=4, k=896,
                      elements=3584, layout="Q8_0_M4_interleaved_4x1", vlen=args.vlen,
                      oracle="ggml_quantize_mat_q8_0_4x1_generic (RISC-V alias 4x1)",
                      **csr, source_pins=pins, log_pins={str(log): log_hash},
                      start_pins_sha256=start_hash, post_pins_sha256=digest(out / "post-pins.json"),
                      pre_exec_artifacts=artifacts, provenance=str(provenance),
                      guest_exit=0, qemu_exit=0)
        if digest(golden) != report["golden_sha256"]:
            raise ValueError("Golden output write failed")
        atomic_json(out / "golden.json", report)
        atomic_json(out / "artifacts.json", hashes([golden, out / "golden.json", log,
                    out / "start-pins.json", out / "post-pins.json", out / "pre-exec-artifacts.json",
                    out / "prebuild-pins.json", out / "pre-exec-pins.json", out / "cpio.log",
                    *map(Path, artifacts)]))
        state.update(state="PASS", golden=str(golden), golden_sha256=report["golden_sha256"], **csr)
        print(json.dumps({key: state[key] for key in ("state", "golden", "golden_sha256", "fcsr", "vcsr")}))
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
