#!/usr/bin/env python3
"""Freeze, check and package call-cost software; never contacts the FPGA."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
GNU = Path("/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-")
KERNEL = Path("/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6")
SPIKE = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike")
SMOKE = OUT / "resident_deployment_linux_smoke_20261112_030729"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--reuse-built", type=Path, help="Reuse an identical frozen ELF build after a harness-only failure")
    a = p.parse_args()
    out = a.output.resolve()
    if out.parent != OUT or not out.name.startswith("resident_board_pair_cost_") or out.exists():
        p.error("use a new signoff verification/out/resident_board_pair_cost_* directory")
    build_root = out / "build"
    inherited = None
    if a.reuse_built:
        old = a.reuse_built.resolve()
        assert old.parent == OUT and old.name.startswith("resident_board_pair_cost_")
        inherited = json.loads((old / "source-pins.json").read_text())
        # The only changed input may be this orchestration helper, never code or checkers.
        for path, expected in inherited.items():
            if Path(path) != Path(__file__).resolve():
                assert sha(path) == expected, path
        assert sha(old / "board/resident-ggml-pair") == json.loads((old / "result.json").read_text())["elf_sha256"]
        out.mkdir()
        shutil.copytree(old / "inputs", out / "inputs")
        shutil.copytree(old / "board", out / "board")
        build_root = old / "build"
        (out / "reuse.json").write_text(json.dumps({"build": str(old), "old_qualification": json.loads((old / "qualification.json").read_text()),
            "purpose": "Reuse frozen code and ELF, rerun all checks; original failure unchanged",
            "old_helper_sha256": inherited[str(Path(__file__).resolve())], "new_helper_sha256": sha(__file__)}, indent=2) + "\n")
        inherited[str(Path(__file__).resolve())] = sha(__file__)
        inherited.update({str(f): sha(f) for f in (out / "inputs").rglob("*") if f.is_file()})
        (out / "source-pins.json").write_text(json.dumps(inherited, indent=2) + "\n")
    else:
        subprocess.run(["python3", str(HERE.parent / "board_pair/build.py"), "--call-cost", "--output", str(out)], check=True)
    inputs, logs = out / "inputs", out / "checks"
    logs.mkdir()
    linux = inputs / "sdk/software/llama/platform/linux"
    llama = inputs / "llama"
    sdk = inputs / "sdk"
    pins = json.loads((out / "source-pins.json").read_text())
    commands = []
    result = {"state": "FAIL", "board_tested": False, "hardware_speedup_measured": False}

    def run(name, argv, timeout=180, cwd=None):
        argv = list(map(str, argv))
        with (logs / (name + ".log")).open("x") as log:
            rc = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout).returncode
        commands.append(dict(name=name, argv=argv, returncode=rc))
        if rc:
            raise RuntimeError(name + " failed; see " + str(logs / (name + ".log")))
        return (logs / (name + ".log")).read_text()

    try:
        inc = ["-I" + str(llama / d) for d in ("ggml/include", "ggml/src", "ggml/src/ggml-cpu")]
        for mode, cc, cxx, sanitizer in (("host", "gcc", "g++", []),
                ("asan-ubsan", "clang", "clang++", ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"])):
            flags = ["-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", *sanitizer]
            obj = logs / (mode + "-client.o")
            exe = logs / (mode + "-portal")
            run(mode + "-client", [cc, *flags, "-DARA_RESIDENT_CLIENT_TEST=1", "-I" + str(linux), "-c", linux / "client_v2.c", "-o", obj])
            run(mode + "-portal-build", [cxx, *flags, "-std=c++17", "-DGGML_RISCV_ACCEL_AUTO=1", *inc,
                "-I" + str(linux), llama / "tests/test-ara-linux-resident-v2.cpp", obj, "-o", exe])
            run(mode + "-portal", [exe])
            exe = logs / (mode + "-pool")
            run(mode + "-pool-build", [cc, *flags, "-I" + str(linux), inputs / "test_pool.c", "-o", exe])
            run(mode + "-pool", [exe])
        exe = logs / "prepare-test"
        run("prepare-build", ["gcc", "-O2", "-ffp-contract=off", "-fno-tree-vectorize",
            "-ffunction-sections", "-fdata-sections", "-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1",
            "-I" + str(sdk), "-I" + str(sdk / "software/akv/include"), "-I" + str(linux / "sdk"),
            inputs / "test_prepare.c", linux / "sdk/kernel_entry.c", sdk / "software/akv/src/akv_runtime.c",
            "-Wl,--gc-sections", "-lm", "-o", exe])
        run("prepare-test", [exe])
        audit_path = llama / "tests/test-ara-linux-resident-v2.py"
        audit = load_module(audit_path, "cost_entry_audit")
        obj = build_root / "ggml/src/CMakeFiles/ggml-cpu.dir/ggml-cpu/arch/riscv/akv.cpp.o"
        dis = run("portal-disassembly", [str(GNU) + "objdump", "-dr", obj])
        symbols = run("portal-symbols", [str(GNU) + "nm", "-S", "--defined-only", obj])
        entry = audit.preguard_audit(dis, symbols)
        (logs / "preguard-audit.json").write_text(json.dumps(entry, indent=2) + "\n")
        flags = ["-O2", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-mcmodel=medany", "-mno-relax",
                 "-msmall-data-limit=0", "-fno-stack-protector", "-fno-tree-vectorize", "-fno-builtin", "-ffreestanding"]
        elf = logs / "finite.elf"
        run("finite-build", [str(GNU) + "gcc", *flags, "-nostdlib", "-static", "-I" + str(linux),
            "-T" + str(inputs / "client.ld"), inputs / "client_start.S", inputs / "test_finite_rvv.c", "-lgcc", "-o", elf])
        symbols = run("finite-symbols", [str(GNU) + "nm", "-n", elf])
        exit_pc = re.findall(r"^([0-9a-f]+) T test_exit$", symbols, re.M)
        assert len(exit_pc) == 1
        debug = logs / "spike.cmd"
        debug.write_text("until pc 0 " + exit_pc[0] + "\nreg 0 a0\nquit\n")
        text = run("finite-spike", [SPIKE, "-d", "--debug-cmd=" + str(debug), "--isa=rv64gcv_zfh_zvfh_zvl1024b", "-m2", elf])
        assert re.findall(r"^0x[0-9a-f]+$", text, re.M) == ["0x0000000000000000"], text
        module = out / "module"
        shutil.copytree(linux, module)
        for f in (".config", "Module.symvers", "include/generated/utsrelease.h"):
            pins[str(KERNEL / f)] = sha(KERNEL / f)
        run("kbuild", ["make", "-C", KERNEL, "ARCH=riscv", "CROSS_COMPILE=" + str(GNU),
            "M=" + str(module), "ARA_RESIDENT_SDK=" + str(sdk), "-j4", "modules"], timeout=300)
        ko = module / "ara_resident.ko"
        reloc = run("module-relocations", [str(GNU) + "readelf", "-rW", ko])
        assert "R_RISCV_ALIGN" not in reloc and "R_RISCV_RELAX" not in reloc
        dis = run("broker-disassembly", [str(GNU) + "objdump", "-d", module / "ara_resident_broker.o"])
        ops = re.findall(r"^\s*[0-9a-f]+:\s+[0-9a-f]+\s+([a-z][a-z0-9_.]*)", dis, re.M)
        assert ops and not any(op.startswith(("v", "f")) and op != "fence" for op in ops)
        run("core-disassembly", [str(GNU) + "objdump", "-dr", module / "sdk/ara_resident_compute_core.o"])
        # Linux negative tests use a model that intentionally lacks Resident INFO4.
        # They validate ownership/lifecycle and pool reuse, not custom arithmetic.
        prior = json.loads((SMOKE / "result.json").read_text())
        assert prior["state"] == "QEMU_LINUX_MODULE_NEGATIVE_LIFECYCLE_PASS"
        helper_path = HERE.parent / "linux_smoke/run_minor_successor_v2.py"
        helper = load_module(helper_path, "cost_cpio")
        pins[str(helper_path)] = sha(helper_path)
        prior_commands = json.loads((SMOKE / "commands.json").read_text())
        init = logs / "init.elf"
        build = next(c["argv"] for c in prior_commands if c["name"] == "init-device-number-build")
        source = SMOKE / "inputs"
        for name in ("start.S",):
            shutil.copyfile(source / name, inputs / name)
            pins[str(inputs / name)] = sha(inputs / name)
        for name in ("client_v2.c", "client_rv64.S", "client.h", "job_layout.h", "ara_resident_uapi.h"):
            shutil.copyfile(linux / name, inputs / name)
            pins[str(inputs / name)] = sha(inputs / name)
        build = [word.replace(str(source / "init.elf"), str(init)).replace(str(source), str(inputs)) for word in build]
        run("linux-init-build", build)
        entries = helper.unpack((SMOKE / "initramfs.cpio").read_bytes())
        cpio = logs / "initramfs.cpio"
        cpio.write_bytes(helper.pack([(n, f, ko.read_bytes() if n == b"ara_resident.ko\0" else
                     init.read_bytes() if n == b"init\0" else data) for n, f, data in entries]))
        linux_results = []
        for cpus in (1, 2):
            cmd = next(c["argv"].copy() for c in prior_commands if c["name"] == "guest-" + str(cpus))
            cmd[cmd.index("-initrd") + 1] = str(cpio)
            trace = logs / ("linux-" + str(cpus) + ".trace")
            cmd[cmd.index("-trace") + 1] = "enable=akv_arch_*,file=" + str(trace)
            for field in ("-kernel", "-bios", "-dtb"):
                pins[cmd[cmd.index(field) + 1]] = sha(cmd[cmd.index(field) + 1])
            text = run("linux-" + str(cpus), cmd, timeout=180)
            assert f"RESIDENT_LINUX_SMOKE_PASS cpus={cpus} " in text and " errors=0" in text
            assert not re.search(r"CHECK .* FAIL|Kernel panic|Oops:|Unknown symbol", text)
            assert "akv_arch_begin" not in trace.read_text()
            linux_results.append({"cpus": cpus, "status": "PASS", "resident_arithmetic": False})
        assert all(sha(path) == value for path, value in pins.items()), "source identity drift"
        board = out / "board"
        shutil.copyfile(ko, board / "ara_resident.ko")
        shutil.copyfile(inputs / "CALL_COST.md", board / "CALL_COST.md")
        manifest = json.loads((board / "manifest.json").read_text())
        manifest.update(call_cost_candidate=True, rtl_changed=False, module_sha256=sha(ko),
                        module_profile_default=False, frozen_overlay=pins,
                        board_tested=False, performance_claim=False)
        (board / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        result.update(state="HOST_SPIKE_LINUX_CHECKED_BOARD_PENDING", linux=linux_results,
                      finite_encodings=65536, finite_lengths=10, finite_edge_checks=150,
                      module_sha256=sha(ko), elf_sha256=sha(board / "resident-ggml-pair"),
                      rtl_changed=False, ordinary_akv_assembly_from_pinned_git=True)
        (board / "qualification.json").write_text(json.dumps(result, indent=2) + "\n")
        (board / "SHA256SUMS").write_text("".join(f"{sha(f)}  {f.name}\n" for f in sorted(board.iterdir()) if f.is_file() and f.name != "SHA256SUMS"))
        run("board-check", ["sha256sum", "-c", "SHA256SUMS"], cwd=board)
        run("package", ["tar", "-czf", out / "resident-call-cost.tar.gz", "-C", out, "board"])
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        (out / "qualification.json").write_text(json.dumps(result, indent=2) + "\n")
        (out / "check-commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        (out / "check-source-pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
