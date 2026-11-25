#!/usr/bin/env python3
"""Freeze and qualify userspace for the live-KV successor. No board operations."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
GNU = "/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-"


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, data): p.write_text(json.dumps(data, indent=2) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--module", type=Path, required=True)
    p.add_argument("--reuse-built", type=Path, help="Reuse unchanged ELF after a CSR harness-only failure")
    a = p.parse_args()
    out, module_root = a.output.resolve(), a.module.resolve()
    assert out.parent == module_root.parent == OUT
    assert out.name.startswith("resident_board_pair_views_") and not out.exists()
    mr = json.loads((module_root / "result.json").read_text())
    assert mr["state"] == "MODULE_BUILT_NOT_EXECUTED"
    build_root = out / "build"
    if a.reuse_built:
        old = a.reuse_built.resolve()
        assert old.parent == OUT and old.name.startswith("resident_board_pair_views_")
        inherited = json.loads((old / "qualification-source-pins.json").read_text())
        allowed = {str(HERE / "prepare.py"), str(HERE / "test_client_csr.c")}
        for path, expected in inherited.items():
            assert path in allowed or sha(path) == expected, "reuse source drift: " + path
        built = json.loads((old / "result.json").read_text())
        assert built["state"] == "BUILT_NOT_BOARD_TESTED" and sha(old / "board/resident-ggml-pair") == built["elf_sha256"]
        assert json.loads((old / "qualification.json").read_text())["state"] == "FAIL"
        out.mkdir()
        shutil.copytree(old / "inputs", out / "inputs")
        shutil.copytree(old / "board", out / "board")
        inherited.update({path: sha(path) for path in allowed})
        save(out / "source-pins.json", inherited)
        save(out / "reuse.json", dict(build=str(old), scope="Unchanged production ELF; only freestanding CSR harness and orchestration updated",
            previous_failure=json.loads((old / "qualification.json").read_text()), elf_sha256=built["elf_sha256"]))
        save(out / "result.json", built)
        build_root = old / "build"
    else:
        subprocess.run([sys.executable, HERE.parent / "board_pair/build.py", "--view-cost", "--output", out], check=True)
    checks = out / "checks"
    checks.mkdir()
    linux = out / "inputs/sdk/software/llama/platform/linux"
    sdk, llama = out / "inputs/sdk", out / "inputs/llama"
    pins = json.loads((out / "source-pins.json").read_text())
    commands = []
    result = dict(state="FAIL", rtl_changed=False, board_tested=False, performance_claim=False)

    def run(name, argv):
        argv = list(map(str, argv))
        with (checks / (name + ".log")).open("x") as log:
            rc = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=180).returncode
        commands.append(dict(name=name, argv=argv, returncode=rc))
        assert not rc, name
        return (checks / (name + ".log")).read_text()

    try:
        for name in ("test_layout.c", "test_compute.c", "test_analyze.py", "analyze.py", "prepare.py", "test_client_csr.c"):
            dest = out / "inputs" / name
            shutil.copyfile(HERE / name, dest)
            pins[str(HERE / name)] = sha(HERE / name)
            pins[str(dest)] = sha(dest)
        old_csr = HERE.parent / "test_client_csr.c"
        shutil.copyfile(old_csr, out / "inputs/old_client_csr.c")
        pins[str(old_csr)] = sha(old_csr)
        pins[str(out / "inputs/old_client_csr.c")] = sha(out / "inputs/old_client_csr.c")
        inc = ["-I" + str(llama / d) for d in ("ggml/include", "ggml/src", "ggml/src/ggml-cpu")]
        for mode, cc, cxx, sanitizer in (("host", "gcc", "g++", []),
                ("asan-ubsan", "clang", "clang++", ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"])):
            flags = ["-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", *sanitizer]
            obj, exe = checks / (mode + ".o"), checks / (mode + "-portal")
            run(mode + "-client", [cc, *flags, "-DARA_RESIDENT_CLIENT_TEST=1",
                                    "-Dara_resident_test_syscall=ara_resident_views_syscall", "-I" + str(linux),
                                    "-c", linux / "client_v2.c", "-o", obj])
            run(mode + "-portal-build", [cxx, *flags, "-std=c++17", "-DGGML_RISCV_ACCEL_AUTO=1", *inc,
                "-I" + str(linux), llama / "tests/test-ara-linux-resident-views.cpp", obj, "-pthread", "-o", exe])
            run(mode + "-portal", [exe])
            exe = checks / (mode + "-layout")
            run(mode + "-layout-build", [cc, *flags, "-I" + str(linux), out / "inputs/test_layout.c", "-o", exe])
            run(mode + "-layout", [exe])
            exe = checks / (mode + "-compute")
            run(mode + "-compute-build", [cc, "-O2", *sanitizer, "-ffp-contract=off", "-fno-tree-vectorize",
                "-ffunction-sections", "-fdata-sections", "-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1",
                "-I" + str(out / "inputs"), "-I" + str(sdk), "-I" + str(sdk / "software/akv/include"),
                "-I" + str(linux / "sdk"), out / "inputs/test_compute.c", linux / "sdk/kernel_entry.c",
                sdk / "software/akv/src/akv_runtime.c", "-Wl,--gc-sections", "-lm", "-o", exe])
            run(mode + "-compute", [exe])
        run("report-tests", [sys.executable, "-m", "unittest", "discover", "-s", out / "inputs", "-p", "test_analyze.py", "-v"])
        audit_file = HERE.parent / "session_cost/audit.py"
        shutil.copyfile(audit_file, out / "inputs/entry_audit.py")
        pins[str(audit_file)] = sha(audit_file)
        pins[str(out / "inputs/entry_audit.py")] = sha(out / "inputs/entry_audit.py")
        spec = importlib.util.spec_from_file_location("view_entry_audit", out / "inputs/entry_audit.py")
        audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
        obj = build_root / "ggml/src/CMakeFiles/ggml-cpu.dir/ggml-cpu/arch/riscv/akv.cpp.o"
        dis = run("portal-disassembly", [GNU + "objdump", "-dr", obj])
        syms = run("portal-symbols", [GNU + "nm", "-S", "--defined-only", obj])
        save(checks / "entry-audit.json", audit.preguard(dis, syms))
        obj = checks / "scalar-client.o"
        run("scalar-client-build", [GNU + "gcc", "-O3", "-march=rv64gc", "-mabi=lp64d", "-fno-tree-vectorize",
            "-fno-tree-slp-vectorize", "-ffreestanding", "-fno-builtin", "-I" + str(linux), "-c", linux / "client_v2.c", "-o", obj])
        dis = run("scalar-client-disassembly", [GNU + "objdump", "-dr", obj])
        ops = re.findall(r"^\s*[0-9a-f]+:\s+[0-9a-f]+\s+([a-z][a-z0-9_.]*)", dis, re.M)
        assert ops and not any(op.startswith(("v", "f", "csr")) for op in ops)
        csr_elf = checks / "client-csr.elf"
        run("csr-build", [GNU + "gcc", "-O2", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-mcmodel=medany",
            "-mno-relax", "-msmall-data-limit=0", "-fno-stack-protector", "-fno-tree-vectorize", "-ffreestanding",
            "-fno-builtin", "-nostdlib", "-static", "-I" + str(linux), "-I" + str(out / "inputs"),
            "-T" + str(out / "inputs/client.ld"), out / "inputs/client_start.S", out / "inputs/test_client_csr.c",
            linux / "client_rv64.S", "-lgcc", "-o", csr_elf])
        symbols = run("csr-symbols", [GNU + "nm", "-n", csr_elf])
        exits = re.findall(r"^([0-9a-f]+) T test_exit$", symbols, re.M)
        assert len(exits) == 1
        debug = checks / "spike.cmd"
        debug.write_text("until pc 0 " + exits[0] + "\nreg 0 a0\nquit\n")
        spike = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike")
        pins[str(spike)] = sha(spike)
        text = run("csr-spike", [spike, "-d", "--debug-cmd=" + str(debug), "--isa=rv64gcv_zfh_zvfh_zvl1024b", "-m2", csr_elf])
        assert re.findall(r"^0x[0-9a-f]+$", text, re.M) == ["0x0000000000000000"], text
        for source in (module_root / "module").rglob("*"):
            if source.is_file() and (source.suffix in (".c", ".h", ".S") or source.name.startswith(("Makefile", "Kbuild"))):
                relative = source.relative_to(module_root / "module")
                # Exclude generated module metadata, not an input to the compute implementation.
                if relative.name.endswith(".mod.c") or relative.name == ".module-common.c": continue
                assert sha(source) == sha(linux / relative), "module differs: " + str(relative)
                pins[str(source)] = sha(source)
        ko = module_root / "module/ara_resident.ko"
        assert sha(ko) == mr["module_sha256"]
        pins[str(ko)] = sha(ko)
        pins[str(module_root / "result.json")] = sha(module_root / "result.json")
        assert all(sha(path) == value for path, value in pins.items()), "source drift"
        board = out / "board"
        shutil.copyfile(ko, board / "ara_resident.ko")
        manifest = json.loads((board / "manifest.json").read_text())
        manifest.update(module_sha256=sha(ko), kernel_module_source=str(module_root),
            numerical_check="independent captured-data original/negative/zero V bit patterns and flags",
            kv_heads=[1, 4], query_heads=[2, 8], stream_capacity=256,
            data_note="Four heads replicate captured head with alternating V signs; not a new model-layer capture",
            linux_lifecycle_pending=True, rtl_compute_pending=True)
        save(board / "manifest.json", manifest)
        result.update(state="HOST_SANITIZER_RV64_CHECKED_LINUX_RTL_BOARD_PENDING", module_sha256=sha(ko),
                      elf_sha256=sha(board / "resident-ggml-pair"), pins_match=True)
        save(board / "software-qualification.json", result)
        (board / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(board.iterdir())
                                                if p.is_file() and p.name != "SHA256SUMS"))
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        save(out / "qualification.json", result)
        save(out / "qualification-commands.json", commands)
        save(out / "qualification-source-pins.json", pins)
    print(json.dumps(result), flush=True)


if __name__ == "__main__": main()
