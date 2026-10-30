#!/usr/bin/env python3
"""Continue the prepared image after auditing duplicate archive member basenames.

The original preparation FAIL and all sealed sources remain unchanged. This
successor audits actual symbol ownership, never changes the numerical checker,
and does not recompile/relink the already built driver.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
from run import ACTIVE, CAPTURE, HERE, OUT, PRIOR, RUNTIME, digest, read, save, verify
from check import check, matrix, require


def audit_map(path):
    lines = path.read_text().split("Linker script and memory map", 1)[1].splitlines()
    provider = None
    symbols = {}
    for line in lines:
        section = re.match(r"^\s*(?:\.\S+\s+)?0x[0-9a-f]+\s+0x[0-9a-f]+\s+(.+\.o\)?)$", line)
        if section:
            provider = section[1]
        if "ggml_backend_cpu_repack_buffer_type()" in line or (
                "::forward_mul_mat(ggml_compute_params*, ggml_tensor*)" in line and
                any("ggml_riscv_qbs_" + t + "_tag," in line for t in ("q4_k", "q6_k", "q4_0", "q8_0"))):
            symbol = line.split(None, 1)[1]
            require(symbol not in symbols, "duplicate linked symbol")
            symbols[symbol] = dict(provider=provider, line=line.strip())
    require(len(symbols) == 5 and all(v["provider"] == str(PRIOR / "repack.o") for v in symbols.values()),
            "private integration symbols not selected: " + repr(symbols))
    return symbols


def main():
    require(len(sys.argv) == 1 and not (OUT / "acceptance-result.json").exists(), "fixed fresh successor")
    preparation = read(OUT / "result.json")
    require(preparation["error"] == "ValueError('link override not effective')" and preparation["qemu_runs"] == 0,
            "only known preparation-only false rejection may continue")
    pins = read(OUT / "manifest.json")
    state = dict(state="PREFLIGHT", pid=os.getpid(), child_pid=None, planned_cases=65, completed_cases=0, qemu_runs=0,
                 qemu_limit_seconds=300, object_overrides=True, production_modified=False, rtl_changed=False,
                 performance_measured=False, preparation_failure_preserved="result.json")

    def pin(paths):
        for p in paths:
            h = digest(p)
            require(str(p) not in pins or pins[str(p)] == h, "sealed input drift: " + str(p))
            pins[str(p)] = h

    def run(argv, label, limit, binary=None):
        argv = list(map(str, argv))
        save(OUT / (label + ".command.json"), dict(argv=argv, cwd=str(OUT), timeout_seconds=limit,
                                                  stdout=str(binary) if binary else label + ".log"))
        state.update(state=label.upper(), child_pid=None)
        save(OUT / "acceptance-status.json", state)
        rc, timeout = None, False
        with (OUT / (label + ".log")).open("xb") as log:
            stream = binary.open("xb") if binary else log
            try:
                with subprocess.Popen(argv, cwd=OUT, stdout=stream, stderr=log) as proc:
                    state["child_pid"] = proc.pid
                    save(OUT / "acceptance-status.json", state)
                    try:
                        rc = proc.wait(timeout=limit)
                    except subprocess.TimeoutExpired:
                        timeout = True
                        proc.kill()
                        rc = proc.wait()
            finally:
                if binary:
                    stream.close()
                save(OUT / (label + ".exit.json"), dict(returncode=rc, timeout=timeout, limit_seconds=limit))
        require(rc == 0 and not timeout, label + " failed")

    try:
        verify(pins)
        require(read(OUT / "compile-test.exit.json")["returncode"] == read(OUT / "link.exit.json")["returncode"] == 0,
                "prepared build commands")
        link = read(OUT / "link.command.json")["argv"]
        require([a for a in link if a.endswith(".o")] == [str(PRIOR / "repack.o"), str(OUT / "test.o")], "explicit object order")
        require([a for a in link if a.endswith(".a")] == read(RUNTIME / "result.json")["libraries"], "normal archives")
        symbols = audit_map(OUT / "link.map")
        original = audit_map(PRIOR / "link.map")
        require(set(symbols) == set(original), "accepted link provider comparison")
        save(OUT / "link-audit.json", dict(result="PASS", symbols=symbols, accepted_symbols=original,
             explanation="Archive repack.cpp.o is arch/riscv/repack.cpp (ggml_quantize_mat_q8_0_4x8); private general repack supplies all integration dispatch symbols."))
        pin([*HERE.glob("*.py"), HERE / "README.md", HERE / "test.cpp", OUT / "result.json", OUT / "status.json",
             OUT / "test", OUT / "test.o", OUT / "link.map", OUT / "link-audit.json", OUT / "matrix.json",
             OUT / "compile-test.command.json", OUT / "compile-test.exit.json", OUT / "link.command.json", OUT / "link.exit.json"])
        cases = matrix()
        require(read(OUT / "matrix.json") == cases, "sealed matrix")
        entries = [shlex.split(l) for l in (PRIOR / "initramfs.list").read_text().splitlines() if l.strip()]
        require(sum(r[:2] == ["file", "/test"] for r in entries) == 1, "initramfs test")
        for row in entries:
            if row[:2] == ["file", "/test"]:
                row[2] = str(OUT / "test")
        cpio = Path("/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio")
        require(str(cpio) in pins and str(CAPTURE) in pins, "pinned tools/capture")
        measured = []
        for typ in ("Q4_K", "Q6_K", "Q4_0", "Q8_0"):
            selected = [c for c in cases if c["type"] == typ]
            directory = OUT / typ
            directory.mkdir()
            recipe = directory / "cases.txt"
            recipe.write_text("".join(" ".join(str(c[k]) for k in ("id", "type", "k", "m", "element", "pad", "wide", "threads")) + "\n" for c in selected))
            listing = directory / "initramfs.list"
            listing.write_text("".join(" ".join(r) + "\n" for r in entries) + f"file /cases.txt {recipe} 444 0 0\n")
            image = directory / "initramfs.cpio"
            run([cpio, listing], typ + "/initramfs", 60, image)
            pin([recipe, listing, image])
            save(OUT / "acceptance-manifest.json", pins)
            verify(pins)
            cmd = read(PRIOR / "qemu.command.json")
            cmd[cmd.index("-initrd")+1] = str(image)
            cmd[cmd.index("-smp")+1] = "2"
            state["qemu_runs"] += 1
            run(cmd, typ + "/qemu", 300)
            log = (directory / "qemu.log").read_text()
            save(directory / "first-failure.json", dict(lines=[l for l in log.splitlines() if l.startswith(("XS_ERROR", "XS_FIRST_MISMATCH"))]))
            result = check(log, selected)
            save(directory / "comparison.json", result)
            measured.extend(result)
            state["completed_cases"] = len(measured)
            pin([directory / "qemu.log", directory / "comparison.json"])
            save(OUT / "comparison.json", measured)
            print(json.dumps(dict(shard=typ, checked_cases=len(result), total=len(measured))), flush=True)
        run([sys.executable, "-B", HERE / "test_check.py"], "checker-tests", 60)
        pin([OUT / "checker-tests.log", OUT / "checker-tests.exit.json"])
        verify(pins)
        save(OUT / "acceptance-manifest.json", pins)
        state.update(state="PASS", paired_cases=len(measured), matmuls=2*len(measured),
                     paired_outputs=sum(c["outputs"] for c in measured), native_commands=sum(c["native"]["native_qbexec"] for c in measured),
                     checker_tests="PASS", active_complete_sha_check_after="PASS", all_inputs_sha_check_after="PASS",
                     active_inventory_sha256=digest(ACTIVE), scope="Private object functional graphs only; no production/RTL/timing claim")
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        save(OUT / "acceptance-manifest.json", pins)
    finally:
        state["child_pid"] = None
        save(OUT / "acceptance-status.json", state)
        save(OUT / "acceptance-result.json", state)
    print(json.dumps(state, sort_keys=True), flush=True)
    return 0 if state["state"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
