#!/usr/bin/env python3
"""One normal-archive RVV-only boot, bounded to 180 seconds; no repairs."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from check import check, require

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "verification/out/m4-stride-rvv-fallback-20261027-01"
RUNTIME = ROOT / "verification/out/m4-prepared-installed-build-20261027-01"
PRIOR = ROOT / "verification/out/m4-packed-stride-repro-20261027-01"
REFERENCE = ROOT / "verification/out/m4-vector-runtime-graph-20261027-01"
ACTIVE = ROOT / "verification/out/m4-packed-qkv-vcs-20261027-01/source-pins.json"
CAPTURE = Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators/blk_0_attn_q_weight")
ACTIVE_SHA = "06097034f29a8f21b0b83e877ba9aebecb4e9ea7b4356cefb119bab4449f475d"
RUNTIME_SHA = "7e01c4446b81f73705f61fc4e76977057662bd9f587aa39060d219ba9ed49c84"


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save(name, value):
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def merge(pins, added):
    for path, value in added.items():
        require(path not in pins or pins[path] == value, "Conflicting pin: " + path)
        pins[path] = value


def verify(pins):
    bad = [path for path, value in pins.items() if not Path(path).is_file() or digest(path) != value]
    require(not bad, "Pinned input drift: " + repr(bad))


def main():
    require(len(sys.argv) == 1 and ROOT == Path("/home/wangwy/openproject/ara_dsa_signoff_integration"), "Fixed recipe/worktree")
    OUT.mkdir(parents=True, exist_ok=False)
    state = dict(state="PREFLIGHT", pid=os.getpid(), child_pid=None, qemu_runs=0,
                 qemu_limit_seconds=180, object_overrides=False, installed=False,
                 rtl_changed=False, performance_measured=False)
    pins = {}

    def pin(paths):
        merge(pins, {str(p): digest(p) for p in paths})

    def run(command, label, limit, binary=None):
        command = list(map(str, command))
        save(label + ".command.json", dict(argv=command, cwd=str(OUT), limit_seconds=limit))
        state.update(state=label.upper(), child_pid=None)
        save("status.json", state)
        begin = time.monotonic()
        with (OUT / (label + ".log")).open("xb") as log:
            target = binary.open("xb") if binary else log
            try:
                with subprocess.Popen(command, cwd=OUT, stdout=target, stderr=log) as process:
                    state["child_pid"] = process.pid
                    save("status.json", state)
                    print(f"{label.upper()} pid={process.pid}", flush=True)
                    try:
                        code = process.wait(timeout=limit)
                    except BaseException:
                        process.kill()
                        process.wait()
                        save(label + ".exit.json", dict(interrupted=True, limit_seconds=limit))
                        raise
            finally:
                if binary:
                    target.close()
        save(label + ".exit.json", dict(returncode=code, host_elapsed_seconds=time.monotonic()-begin))
        require(code == 0, label + " process failed")

    try:
        require(digest(ACTIVE) == ACTIVE_SHA and digest(RUNTIME / "manifest.json") == RUNTIME_SHA, "Accepted inventory identities")
        active, installed = read(ACTIVE), read(RUNTIME / "manifest.json")
        merge(pins, active)
        merge(pins, installed)
        sources = sorted(HERE.glob("*"))
        require(all(p.is_file() for p in sources), "Standalone owned source files only")
        require(not any(p.startswith(str(HERE) + "/") for p in active), "Owned directory already sealed")
        report = read(RUNTIME / "result.json")
        require(report["state"] == "PASS", "Normal build prerequisite")
        libs = report["libraries"]
        require(len(libs) == 4 and all(p in installed for p in libs), "Pinned normal libraries")
        require({Path(p).name for p in libs} == {"libllama.a", "libggml.a", "libggml-cpu.a", "libggml-base.a"}, "Unexpected archives")
        prior = read(PRIOR / "manifest.json")
        qemu = read(PRIOR / "qemu.command.json")
        cpu = qemu[qemu.index("-cpu")+1]
        require(cpu == "rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true", "Reviewed QEMU CPU")
        qemu[qemu.index("-cpu")+1] = cpu.replace("xaraqbs=true", "xaraqbs=false")
        entries = [shlex.split(line) for line in (PRIOR / "initramfs.list").read_text().splitlines() if line.strip()]
        init, = [Path(row[2]) for row in entries if row[:2] == ["file", "/init"]]
        cpio = Path("/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio")
        assets = [init, cpio, Path(qemu[0]), Path(qemu[qemu.index("-bios")+1]), Path(qemu[qemu.index("-kernel")+1]),
                  CAPTURE / "activation_f32.bin", REFERENCE / "compile-test.command.json"]
        require(all(str(p) in prior for p in assets), "Unpinned prior assets")
        merge(pins, {str(p): prior[str(p)] for p in assets})
        require(str(CAPTURE / "weight_q4_K.bin") in active, "Weights absent from active inventory")
        require(read(CAPTURE / "weight_q4_K.json")["shape"] == [1536, 1536, 1, 1] and
                read(CAPTURE / "activation_f32.json")["shape"] == [1536, 15, 1, 1], "Capture geometry")
        pin([*sources, ACTIVE, RUNTIME / "manifest.json", RUNTIME / "result.json", PRIOR / "manifest.json",
             PRIOR / "qemu.command.json", PRIOR / "initramfs.list", CAPTURE / "weight_q4_K.json",
             CAPTURE / "activation_f32.json"])
        command = read(REFERENCE / "compile-test.command.json")
        compiler = Path(command[0])
        pin([compiler, compiler.resolve()])
        verify(pins)
        save("source-pins.json", pins)
        save("preflight.json", dict(active_entries=len(active), installed_entries=len(installed), merged_entries=len(pins),
                                   active_inventory_sha256=ACTIVE_SHA, inherited_hash_check="PASS", conflicts=0,
                                   captured_weights=True, capture_selection="first 512 elements / two blocks per original 1536-element row",
                                   qemu_xaraqbs=False, stop_after_first_mismatch=True))
        command[command.index("-c")+1] = str(HERE / "test.cpp")
        command[command.index("-o")+1] = str(OUT / "test.o")
        run(command, "compile-test", 120)
        run([compiler, "-static", OUT / "test.o", *libs, "-ldl", "-lm", "-pthread",
             "-Wl,-Map=" + str(OUT / "link.map"), "-o", OUT / "test"], "link", 120)
        linkmap = (OUT / "link.map").read_text()
        require("libggml-cpu.a(repack.cpp.o)" in linkmap and "ggml_gemm_q4_K_32x1_q8_K" in linkmap and
                "ggml_gemv_q4_K_32x1_q8_K" in linkmap, "Normal repack objects/RVV symbols missing")
        require(sum(row[:2] == ["file", "/test"] for row in entries) == 1 and
                sum(row[:2] == ["file", "/activation.bin"] for row in entries) == 1, "Initramfs recipe")
        for row in entries:
            if row[:2] == ["file", "/test"]:
                row[2] = str(OUT / "test")
        entries.append(["file", "/weights.bin", str(CAPTURE / "weight_q4_K.bin"), "444", "0", "0"])
        listing = OUT / "initramfs.list"
        listing.write_text("".join(" ".join(row) + "\n" for row in entries))
        run([cpio, listing], "initramfs", 30, OUT / "initramfs.cpio")
        pin([OUT / "test.o", OUT / "test", OUT / "link.map", listing, OUT / "initramfs.cpio"])
        save("manifest.json", pins)
        qemu[qemu.index("-initrd")+1] = str(OUT / "initramfs.cpio")
        state["qemu_runs"] = 1
        run(qemu, "qemu", 180)
        log = (OUT / "qemu.log").read_text()
        save("first-mismatch.json", dict(raw_line=next((l for l in log.splitlines() if l.startswith("RF_FIRST ")), None)))
        measured = check(log)
        save("comparison.json", measured)
        verify(pins)
        state.update(state="FAIL" if measured["conclusion"] == "CONFIRMED" else "NOT_REPRODUCED",
                     measured=measured, active_inventory_unchanged=True, input_sha_check_after="PASS",
                     log_sha256=digest(OUT / "qemu.log"), normal_libraries=libs,
                     scope="Ordinary RVV software functional mismatch only; no RTL or timing claim")
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
    finally:
        if (OUT / "qemu.log").exists() and not (OUT / "first-mismatch.json").exists():
            log = (OUT / "qemu.log").read_text(errors="replace")
            save("first-mismatch.json", dict(raw_line=next((l for l in log.splitlines() if l.startswith("RF_FIRST ")), None)))
        state["child_pid"] = None
        save("status.json", state)
        save("result.json", state)
        print(json.dumps(state, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
