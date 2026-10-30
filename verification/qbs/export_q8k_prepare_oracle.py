#!/usr/bin/env python3
"""Export independently executed production Q8_K bytes for a VCS ABBA test."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from run_half_scale_soc import ROOT, atomic_json, digest, hashes
from run_tile_context_engine import run_command
from run_ggml_segmented import verify_native_build


def check_output(text):
    if re.search(r"Kernel panic|Illegal instruction|Segmentation fault|qemu: fatal", text, re.I):
        raise ValueError("Guest failure")
    records = [line.strip() for line in text.splitlines() if "Q8K_ORACLE_" in line]
    if len(records) != 114 or records[0] != "Q8K_ORACLE_BEGIN m=4 k=1536 bytes=7008":
        raise ValueError("Missing or extra records")
    csr = re.fullmatch(r"Q8K_ORACLE_CSR fcsr=(\d+) vcsr=5", records[1])
    if not csr or int(csr[1]) > 31:
        raise ValueError("Wrong CSR result")
    data = bytearray()
    for line in records[2:-2]:
        row = re.fullmatch(r"Q8K_ORACLE_HEX offset=(\d+) data=([0-9a-f]+)", line)
        count = min(64, 7008 - len(data))
        if not row or int(row[1]) != len(data) or len(row[2]) != count*2 or count <= 0:
            raise ValueError("Malformed/reordered output bytes")
        data.extend(bytes.fromhex(row[2]))
    if len(data) != 7008 or records[-2:] != ["Q8K_ORACLE_END bytes=7008", "Q8K_ORACLE_EXIT=0"]:
        raise ValueError("Incomplete output or failed guest")
    return bytes(data), int(csr[1])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("native-build", "native-run", "production-build", "configuration", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    build, run, prod = [x.resolve(strict=True) for x in (a.native_build, a.native_run, a.production_build)]
    config = json.loads(a.configuration.read_text())
    platform, qemu = Path(config["platform"]), Path(config["qemu"])
    status = json.loads((run / "status.json").read_text())
    pins = json.loads((run / "manifest.json").read_text())
    if status["state"] != "PASS" or status["checks"] != 12000 or digest(run / "manifest.json") != status["manifest_sha256"]:
        raise ValueError("Require completed native gate")
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Native evidence drift")
    if str(build / "manifest.json") not in pins or str(prod / "manifest.json") not in pins:
        raise ValueError("Build identities not covered by native gate")
    capture = build / "real_attn_first.bin"
    if capture.stat().st_size != 4*1536*4 or str(capture) not in pins:
        raise ValueError("Wrong real capture")
    source = ROOT / "verification/qbs/q8k_prepare_oracle_init.cpp"
    cxx = platform / "tools/bin/riscv64-linux-g++"
    cpio = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    libs = [prod / "build/tile-support/ggml/src" / ("lib"+n+".a") for n in ("ggml", "ggml-cpu", "ggml-base")]
    if any(str(lib) not in pins for lib in libs):
        raise ValueError("Unpinned production archive")
    pins.update(hashes([Path(__file__), source, a.configuration.resolve(), cxx.resolve(), cpio,
                       run / "status.json", run / "manifest.json", *map(Path, verify_native_build(qemu))]))
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / "manifest.json", pins)
    state = dict(state="BUILDING", pid=os.getpid(), child_pid=None)
    def save(): atomic_json(out / "status.json", state)
    def started(pid):
        state.update(child_pid=pid)
        save()
    save()
    try:
        ggml = Path("/home/wangwy/llama/llama.cpp/ggml")
        includes = [s for d in (ggml/"include", ggml/"src", ggml/"src/ggml-cpu") for s in ("-isystem", str(d))]
        command = list(map(str, [cxx, "-std=c++17", "-march=rv64gcv", "-mabi=lp64d", "-O3", "-static",
                 "-fno-fast-math", *includes, source, "-Wl,--start-group", *libs, "-Wl,--end-group", "-lm", "-ldl", "-o", out/"init"]))
        atomic_json(out / "compile-command.json", command)
        if run_command(command, out/"build.log", 120, os.environ.copy(), started):
            raise RuntimeError("Export executable build failed")
        listing = out/"init.list"
        listing.write_text(f"dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\nfile /init {out/'init'} 755 0 0\nfile /capture.bin {capture} 444 0 0\n")
        with (out/"init.cpio").open("xb") as stream:
            subprocess.run([cpio, listing], stdout=stream, check=True, timeout=60)
        artifacts = hashes([out/"init", out/"init.cpio", listing, out/"compile-command.json"])
        atomic_json(out/"artifacts-before.json", artifacts)
        command = list(map(str, [qemu, "-M", "virt", "-cpu", "rv64,v=true,vlen=1024,elen=64,xaraqbs=true",
                 "-smp", "1", "-m", "512M", "-display", "none", "-monitor", "none", "-serial", "stdio",
                 "-bios", platform/"images/fw_dynamic.bin", "-kernel", platform/"images/Image",
                 "-initrd", out/"init.cpio", "-append", "console=ttyS0 rdinit=/init"]))
        state.update(state="RUNNING", command=command)
        if run_command(command, out/"qemu.log", 600, os.environ.copy(), started):
            raise RuntimeError("Oracle guest failed")
        state["child_pid"] = None
        data, fcsr = check_output((out/"qemu.log").read_text())
        if hashes(map(Path, pins)) != pins or hashes(map(Path, artifacts)) != artifacts:
            raise ValueError("Source or executable drift")
        (out/"golden.bin").write_bytes(data)
        atomic_json(out/"golden.json", dict(state="PASS", m=4, k=1536, bytes=len(data), fcsr=fcsr, vcsr=5,
            capture=str(capture), capture_sha256=digest(capture), golden_sha256=digest(out/"golden.bin"),
            log_sha256=digest(out/"qemu.log"), manifest_sha256=digest(out/"manifest.json"), artifacts=artifacts,
            oracle="linked production ggml_quantize_mat_q8_K_4x1_ara_generic"))
        state.update(state="PASS", fcsr=fcsr, bytes=len(data))
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        state["child_pid"] = None
        save()


if __name__ == "__main__":
    main()
