#!/usr/bin/env python3
"""Compare packed preparation with the installed production generic across K/CSR boundaries."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "verification/qbs"))
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.resolve()
    if not out.is_relative_to(ROOT / "verification/out") or out.exists():
        raise ValueError("Fresh independent output required")
    accepted = ROOT / "verification/out/m4-packed-reference-20261027-01"
    pins = json.loads((accepted / "manifest.json").read_text())
    if json.loads((accepted / "result.json").read_text())["state"] != "PASS" or hashes(map(Path, pins)) != pins:
        raise ValueError("Accepted producer/library identity changed")
    source = HERE / "extent_test.cpp"
    compile_cmd = json.loads((accepted / "compile-2.command.json").read_text())
    link_cmd = json.loads((accepted / "link.command.json").read_text())
    qemu_cmd = json.loads((accepted / "qemu-1024.command.json").read_text())
    pins.update(hashes([Path(__file__), source, accepted / "result.json",
                       accepted / "compile-2.command.json", accepted / "link.command.json",
                       accepted / "qemu-1024.command.json"]))
    out.mkdir(parents=True)
    state = dict(state="PREPARING", pid=os.getpid(), child_pid=None, performance_measured=False)

    def save():
        atomic_json(out / "status.json", state)

    def started(pid):
        state["child_pid"] = pid
        save()

    def run(command, name, limit):
        command = list(map(str, command))
        atomic_json(out / (name + ".command.json"), command)
        state.update(state=name.upper(), child_pid=None)
        save()
        if run_command(command, out / (name + ".log"), limit, os.environ.copy(), started):
            raise RuntimeError(name + " failed")

    try:
        obj = out / "extent.o"
        compile_cmd[compile_cmd.index("-c") + 1] = str(source)
        compile_cmd[compile_cmd.index("-o") + 1] = str(obj)
        run(compile_cmd, "compile", 180)
        old_test = str(accepted / "2.o")
        if link_cmd.count(old_test) != 1:
            raise ValueError("Unreviewed link shape")
        link_cmd[link_cmd.index(old_test)] = str(obj)
        link_cmd[link_cmd.index("-o") + 1] = str(out / "test")
        run(link_cmd, "link", 180)
        init = ROOT / "verification/out/q8k-decode-layout-full-20261026-01/init"
        cpio = Path("/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio")
        recipe = out / "initramfs.list"
        recipe.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n" +
                          f"file /init {init} 755 0 0\nfile /test {out / 'test'} 755 0 0\n")
        with (out / "initramfs.cpio").open("xb") as stream:
            subprocess.run([str(cpio), str(recipe)], stdout=stream, check=True, timeout=60)
        pins.update(hashes([obj, out / "test", recipe, out / "initramfs.cpio", init, cpio]))
        atomic_json(out / "manifest.json", pins)
        qemu_cmd[qemu_cmd.index("-initrd") + 1] = str(out / "initramfs.cpio")
        configurations = []
        for vlen in (128, 256, 512, 1024):
            command = list(qemu_cmd)
            command[command.index("-cpu") + 1] = f"rv64,v=true,vlen={vlen},elen=64,zfh=true,zvfh=true,xaraqbs=false"
            name = "qemu-" + str(vlen)
            run(command, name, 600)
            log = out / (name + ".log")
            lines = log.read_text().splitlines()
            marker = "PACKED_EXTENT_PASS checks=576 domain_checks=28 shapes=8 patterns=12 max_k=8192"
            if lines.count(marker) != 1 or lines.count("GUEST_TEST_EXIT=0") != 1:
                raise ValueError("Missing complete extent comparison")
            configurations.append(dict(vlen=vlen,checks=576,domain_checks=28,log_sha256=digest(log)))
        if hashes(map(Path, pins)) != pins:
            raise ValueError("Source drift")
        state.update(state="PASS", configurations=configurations,
                     scope="Production generic/original/packed exact bytes, flags, guards and admission; no timing")
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        state["child_pid"] = None
        save()
        atomic_json(out / "result.json", state)


if __name__ == "__main__":
    main()
