#!/usr/bin/env python3
"""Freeze and compile the isolated direct-lease TEST kernel; no live SDK edits."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
KERNEL = Path("software/llama/platform/linux/direct/kernel/v2")
TESTS = Path("verification/performance/resident_deployment/direct_cost/linux")
UAPI = Path("software/llama/platform/linux/direct/direct_uapi.h")
DEFAULT_BASE = Path("/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6")
DEFAULT_CROSS = "/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-"
OUT_ROOT = Path("/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def inventory(tree):
    return {str(p.relative_to(tree)): digest(p) for p in sorted(tree.rglob("*"))
            if p.is_file() and not p.is_symlink() and ".git" not in p.parts}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cross", default=DEFAULT_CROSS)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()
    base, out = args.base.resolve(), args.out.resolve()
    if OUT_ROOT.resolve() not in out.parents or out.exists():
        ap.error("--out must be a NEW directory below " + str(OUT_ROOT))
    if base == out or base in out.parents or out in base.parents:
        ap.error("base and output must be disjoint")
    if not (1 <= args.jobs <= 16) or not (60 <= args.timeout <= 7200):
        ap.error("jobs must be 1..16 and timeout 60..7200")
    version = (base / "Makefile").read_text().splitlines()[:5]
    if version[:3] != ["# SPDX-License-Identifier: GPL-2.0", "VERSION = 6", "PATCHLEVEL = 19"] or "SUBLEVEL = 6" not in version:
        ap.error("expected the local Linux 6.19.6 base")
    out.mkdir(parents=True)
    started = time.time()
    result = {"status": "PREPARING", "runtime_validated": False,
              "hardware_validated": False, "base": str(base), "output": str(out)}
    save(out / "result.json", result)
    commands = []
    pins = {}
    env = dict(os.environ, LC_ALL="C", KBUILD_BUILD_USER="akv-test",
               KBUILD_BUILD_HOST="frozen", KBUILD_BUILD_TIMESTAMP="2026-11-13 00:00:00 +0000")
    env.pop("CFLAGS", None)
    env.pop("LDFLAGS", None)

    def run(name, argv, timeout=120, cwd=None):
        argv = list(map(str, argv))
        commands.append({"name": name, "argv": argv, "cwd": str(cwd or out)})
        save(out / "commands.json", commands)
        print(name, flush=True)
        with (out / (name + ".log")).open("w") as log:
            # GNU timeout bounds and terminates the whole make process group.
            proc = subprocess.run(["timeout", "--signal=TERM", "--kill-after=10s",
                                   str(timeout), *argv], cwd=cwd or out, env=env,
                                  stdout=log, stderr=subprocess.STDOUT)
        if proc.returncode:
            raise RuntimeError("%s failed (%s), see %s.log" % (name, proc.returncode, name))

    try:
        inputs = out / "inputs"
        files = [p for p in (ROOT / KERNEL).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        files += [ROOT / TESTS / "build_v3.py", ROOT / TESTS / "test_policy_v1.c",
                  ROOT / UAPI, ROOT / "AGENTS.md"]
        for source in sorted(files):
            target = inputs / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            pins[str(source)] = digest(source)
            shutil.copy2(source, target)
            if digest(target) != pins[str(source)]:
                raise RuntimeError("input drift while freezing: " + str(source))
            pins[str(target)] = digest(target)
        for tool in [args.cross + suffix for suffix in ("gcc", "gcc.br_real", "as", "ld", "objdump")]:
            p = Path(tool)
            if p.is_file():
                pins[str(p)] = digest(p)
        save(out / "source-pins.json", pins)
        shutil.copy2(base / ".config", out / "base.config")
        pins[str(base / ".config")] = digest(base / ".config")
        tree = out / "linux"
        run("copy-linux", ["cp", "-a", "--reflink=auto", base, tree], timeout=300)
        # All generated-file cleanup is confined to the copied tree.
        run("mrproper-copy", ["make", "-C", tree, "ARCH=riscv", "mrproper"], timeout=180)
        base_files = inventory(tree)
        save(out / "base-source-sha256.json", base_files)
        for rel, sha in base_files.items():
            if not (base / rel).is_file() or digest(base / rel) != sha:
                raise RuntimeError("base drift while freezing: " + rel)
        spec = importlib.util.spec_from_file_location("akv_hooks", inputs / KERNEL / "hooks.py")
        hooks = importlib.util.module_from_spec(spec)
        sys.dont_write_bytecode = True
        spec.loader.exec_module(hooks)
        patch = out / "linux-hooks.patch"
        patch.write_text(hooks.patch(tree))
        pins[str(patch)] = digest(patch)
        run("apply-hooks", ["patch", "--batch", "--fuzz=0", "-p1", "-i", patch], cwd=tree)
        for source in (inputs / KERNEL / "overlay").rglob("*"):
            if source.is_file():
                target = tree / source.relative_to(inputs / KERNEL / "overlay")
                if target.exists():
                    raise RuntimeError("overlay collides with base: " + str(target))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        shutil.copy2(inputs / UAPI, tree / "include/uapi/linux/ara_akv_direct.h")
        save(out / "patched-source-sha256.json", inventory(tree))
        shutil.copy2(out / "base.config", tree / ".config")
        enables = ["RISCV_AKV_DIRECT", "FPU", "RISCV_ISA_V", "MMU", "PREEMPT_NONE"]
        disables = ["SMP", "PREEMPT_RT", "PREEMPT", "PREEMPT_VOLUNTARY", "PREEMPT_DYNAMIC",
                    "SUSPEND", "HIBERNATION", "CPU_IDLE", "KVM", "ACPI_PROCESSOR"]
        command = [tree / "scripts/config", "--file", tree / ".config"]
        for name in disables:
            command += ["--disable", name]
        for name in enables:
            command += ["--enable", name]
        command += ["--set-str", "LOCALVERSION", "-akv-direct-test-v2", "--disable", "LOCALVERSION_AUTO"]
        run("configure", command)
        make = ["make", "-C", tree, "ARCH=riscv", "CROSS_COMPILE=" + args.cross,
                "KBUILD_BUILD_VERSION=1", "-j" + str(args.jobs)]
        run("olddefconfig", make + ["olddefconfig"])
        config = (tree / ".config").read_text()
        for name in enables:
            if "CONFIG_%s=y\n" % name not in config:
                raise RuntimeError("required config not enabled: " + name)
        for name in disables:
            if "CONFIG_%s=y\n" % name in config or "CONFIG_%s=m\n" % name in config:
                raise RuntimeError("unsafe config enabled: " + name)
        shutil.copy2(tree / ".config", out / "test.config")
        (out / "config.diff").write_text("".join(difflib.unified_diff(
            (out / "base.config").read_text().splitlines(True), config.splitlines(True),
            "base.config", "test.config")))
        pins[str(out / "test.config")] = digest(out / "test.config")
        host_include = out / "host-include/linux"
        host_include.mkdir(parents=True)
        shutil.copy2(inputs / UAPI, host_include / "ara_akv_direct.h")
        for compiler, options in [("gcc", []), ("clang", ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"])]:
            binary = out / ("test-policy-" + compiler)
            run("host-build-" + compiler, [compiler, "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                *options, "-I" + str(host_include.parent),
                "-I" + str(inputs / KERNEL / "overlay/include"),
                inputs / TESTS / "test_policy_v1.c", "-o", binary])
            run("host-test-" + compiler, [binary])
        save(out / "source-pins.json", pins)
        result["status"] = "BUILDING_OBJECTS"
        save(out / "result.json", result)
        run("kernel-objects", make + ["arch/riscv/kernel/akv_direct.o", "arch/riscv/kernel/traps.o",
            "arch/riscv/kernel/signal.o", "arch/riscv/mm/fault.o", "kernel/exit.o",
            "kernel/sched/core.o", "kernel/module/main.o"], timeout=args.timeout)
        result["objects_compiled"] = True
        result["status"] = "BUILDING_IMAGE"
        save(out / "result.json", result)
        run("kernel-image", make + ["Image"], timeout=args.timeout)
        run("driver-disassembly", [args.cross + "objdump", "-dr", tree / "arch/riscv/kernel/akv_direct.o"])
        mismatches = [path for path, sha in pins.items() if not Path(path).is_file() or digest(Path(path)) != sha]
        save(out / "pin-check.json", {"match": not mismatches, "mismatches": mismatches})
        if mismatches:
            raise RuntimeError("source pin drift")
        image = tree / "arch/riscv/boot/Image"
        result.update(status="COMPILED_TEST_CANDIDATE_RUNTIME_PENDING", image=str(image),
                      image_sha256=digest(image), source_pins_match=True,
                      host_policy="GCC and Clang ASan/UBSan PASS")
    except BaseException as exc:
        result.update(status="FAILED", error=str(exc))
        raise
    finally:
        result["elapsed_seconds"] = round(time.time() - started, 3)
        save(out / "result.json", result)
        print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
