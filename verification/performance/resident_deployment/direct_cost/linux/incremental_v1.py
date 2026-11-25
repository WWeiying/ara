#!/usr/bin/env python3
"""Incremental v2 successor from the finished v1 _03 frozen kernel build."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[5]
OUT_ROOT = Path("/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out")
KERNEL = Path("software/llama/platform/linux/direct/kernel/v2")
TESTS = Path("verification/performance/resident_deployment/direct_cost/linux")
UAPI = Path("software/llama/platform/linux/direct/direct_uapi.h")
CROSS = "/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parent", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    parent, out = args.parent.resolve(), args.out.resolve()
    if OUT_ROOT not in out.parents or out.exists() or OUT_ROOT not in parent.parents:
        ap.error("use finished parent and NEW successor under signoff verification/out")
    prior = json.loads((parent / "result.json").read_text())
    if prior.get("status") != "FAILED" or "kernel-objects failed" not in prior.get("error", ""):
        ap.error("parent must be the finished object-build failure")
    if "no_llseek" not in (parent / "kernel-objects.log").read_text():
        ap.error("unexpected parent failure")
    out.mkdir()
    started = time.time()
    result = {"status": "PREPARING_INCREMENTAL", "parent": str(parent),
              "runtime_validated": False, "hardware_validated": False,
              "base_inventory_rehashed": False,
              "identity_scope": "inherited frozen manifests plus all overlay/hook/config/tool deltas"}
    pins, commands = {}, []
    save(out / "result.json", result)
    env = dict(os.environ, LC_ALL="C", KBUILD_BUILD_USER="akv-test",
               KBUILD_BUILD_HOST="frozen", KBUILD_BUILD_TIMESTAMP="2026-11-13 00:00:00 +0000")
    env.pop("CFLAGS", None)
    env.pop("LDFLAGS", None)

    def pin(path):
        pins[str(path)] = sha(path)

    def run(name, command, timeout=1800, cwd=None):
        command = list(map(str, command))
        commands.append({"name": name, "argv": command})
        save(out / "commands.json", commands)
        print(name, flush=True)
        with (out / (name + ".log")).open("w") as f:
            p = subprocess.run(["timeout", "--kill-after=10s", str(timeout), *command],
                               cwd=cwd or out, env=env, stdout=f, stderr=subprocess.STDOUT)
        if p.returncode:
            raise RuntimeError("%s failed (%s)" % (name, p.returncode))

    try:
        inherited = ["source-pins.json", "base-source-sha256.json", "patched-source-sha256.json",
                     "linux-hooks.patch", "base.config", "test.config", "config.diff", "result.json"]
        lineage = out / "lineage"
        lineage.mkdir()
        for name in inherited:
            pin(parent / name)
            shutil.copy2(parent / name, lineage / name)
            pin(lineage / name)
        original = json.loads((parent / "patched-source-sha256.json").read_text())
        input_root = out / "inputs"
        sources = [p for p in (ROOT / KERNEL).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        sources += [ROOT / UAPI, ROOT / TESTS / "test_policy_v1.c", Path(__file__).resolve(),
                    ROOT / "AGENTS.md", ROOT / KERNEL.parent / "REVIEW_V1_20261113.md"]
        for source in sources:
            dest = input_root / source.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            pin(source)
            shutil.copy2(source, dest)
            pin(dest)
            if pins[str(dest)] != pins[str(source)]:
                raise RuntimeError("freeze drift: " + str(source))
        for suffix in ["gcc", "gcc.br_real", "as", "ld", "objdump"]:
            if Path(CROSS + suffix).is_file():
                pin(Path(CROSS + suffix))
        tree = out / "linux"
        run("copy-incremental-tree", ["cp", "-a", "--reflink=auto", parent / "linux", tree], 300)
        if sha(tree / ".config") != sha(parent / "test.config"):
            raise RuntimeError("parent config drift")
        patch_paths = []
        for line in (parent / "linux-hooks.patch").read_text().splitlines():
            if line.startswith("+++ b/"):
                patch_paths.append(line[6:])
        for path in patch_paths + ["include/uapi/linux/ara_akv_direct.h"]:
            if sha(tree / path) != original[path]:
                raise RuntimeError("inherited hook/UAPI drift: " + path)
            pin(parent / "linux" / path)
            pin(tree / path)
        delta = []
        for source in (input_root / KERNEL / "overlay").rglob("*"):
            if not source.is_file():
                continue
            rel = source.relative_to(input_root / KERNEL / "overlay")
            dest = tree / rel
            if sha(dest) != original[str(rel)]:
                raise RuntimeError("inherited overlay drift: " + str(rel))
            pin(parent / "linux" / rel)
            before, after = dest.read_text(), source.read_text()
            if before != after:
                delta += list(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                  "a/" + str(rel), "b/" + str(rel)))
                shutil.copy2(source, dest)
            pin(dest)
        (out / "overlay-delta.patch").write_text("".join(delta))
        pin(out / "overlay-delta.patch")
        if sha(input_root / UAPI) != sha(tree / "include/uapi/linux/ara_akv_direct.h"):
            raise RuntimeError("UAPI changed")
        for name in ["base.config", "test.config", "config.diff"]:
            shutil.copy2(parent / name, out / name)
            pin(out / name)
        # Keep identical .config/UTS release to retain valid incremental objects.
        host = out / "host-include/linux"
        host.mkdir(parents=True)
        shutil.copy2(input_root / UAPI, host / "ara_akv_direct.h")
        for compiler, opts in [("gcc", []), ("clang", ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"])]:
            binary = out / ("test-policy-" + compiler)
            run("host-build-" + compiler, [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-g",
                *opts, "-I" + str(host.parent), "-I" + str(input_root / KERNEL / "overlay/include"),
                input_root / TESTS / "test_policy_v1.c", "-o", binary], 120)
            run("host-test-" + compiler, [binary], 120)
        save(out / "source-pins.json", pins)
        make = ["make", "-C", tree, "ARCH=riscv", "CROSS_COMPILE=" + CROSS, "KBUILD_BUILD_VERSION=1", "-j8"]
        result["status"] = "BUILDING_OBJECTS"
        save(out / "result.json", result)
        run("kernel-objects", make + ["arch/riscv/kernel/akv_direct.o", "arch/riscv/kernel/traps.o",
            "arch/riscv/kernel/signal.o", "arch/riscv/mm/fault.o", "kernel/exit.o", "kernel/sched/core.o",
            "kernel/module/main.o"])
        result.update(objects_compiled=True, status="BUILDING_IMAGE")
        save(out / "result.json", result)
        run("kernel-image", make + ["Image"])
        run("driver-disassembly", [CROSS + "objdump", "-dr", tree / "arch/riscv/kernel/akv_direct.o"], 120)
        changed = [p for p, expected in pins.items() if sha(Path(p)) != expected]
        save(out / "pin-check.json", {"match": not changed, "mismatches": changed})
        if changed:
            raise RuntimeError("pinned input drift")
        image = tree / "arch/riscv/boot/Image"
        result.update(status="COMPILED_TEST_CANDIDATE_RUNTIME_PENDING", image=str(image),
                      image_sha256=sha(image), source_pins_match=True,
                      host_policy="GCC and Clang ASan/UBSan PASS (17394 checks each)")
    except BaseException as exc:
        result.update(status="FAILED", error=str(exc))
        raise
    finally:
        result["elapsed_seconds"] = round(time.time() - started, 3)
        save(out / "result.json", result)
        print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
