#!/usr/bin/env python3
"""Build and check the client-session successor without running the board."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
from audit import preguard

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
BASE = OUT / "resident_board_pair_cost_20261113_03"
GNU = "/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-built", type=Path, help="Reuse a frozen ELF after an audit-only failure")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != OUT or not out.name.startswith("resident_board_pair_session_") or out.exists():
        parser.error("use a fresh signoff verification/out/resident_board_pair_session_* directory")
    build_root = out / "build"
    if args.reuse_built:
        old = args.reuse_built.resolve()
        assert old.parent == OUT and old.name.startswith("resident_board_pair_session_")
        old_pins = json.loads((old / "source-pins.json").read_text())
        for path, expected in old_pins.items():
            if Path(path) != Path(__file__).resolve():
                assert sha(path) == expected, "reuse source drift: " + path
        assert sha(old / "board/resident-ggml-pair") == json.loads((old / "result.json").read_text())["elf_sha256"]
        out.mkdir()
        shutil.copytree(old / "inputs", out / "inputs")
        shutil.copytree(old / "board", out / "board")
        old_pins[str(Path(__file__).resolve())] = sha(__file__)
        old_pins.update({str(p): sha(p) for p in (out / "inputs").rglob("*") if p.is_file()})
        save(out / "source-pins.json", old_pins)
        save(out / "reuse.json", dict(build=str(old), original_failure=json.loads((old / "session-qualification.json").read_text()),
                                     scope="Unchanged ELF; multi-guard audit replaces the one-guard assumption; original failure retained"))
        build_root = old / "build"
    else:
        subprocess.run(["python3", str(HERE.parent / "board_pair/build.py"), "--session-cost", "--output", str(out)], check=True)
    inputs = out / "inputs"
    sdk, llama = inputs / "sdk", inputs / "llama"
    linux = sdk / "software/llama/platform/linux"
    checks = out / "checks"
    checks.mkdir()
    pins = json.loads((out / "source-pins.json").read_text())
    for name in ("audit.py", "test_audit.py"):
        shutil.copyfile(HERE / name, inputs / name)
        pins[str(HERE / name)] = sha(HERE / name)
        pins[str(inputs / name)] = sha(inputs / name)
    commands = []
    result = dict(state="FAIL", rtl_changed=False, board_tested=False, performance_claim=False)

    def run(name, argv):
        argv = list(map(str, argv))
        with (checks / (name + ".log")).open("x") as log:
            rc = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=180).returncode
        commands.append(dict(name=name, argv=argv, returncode=rc))
        if rc:
            raise RuntimeError(name + " failed: " + str(checks / (name + ".log")))
        return (checks / (name + ".log")).read_text()

    try:
        run("audit-tests", ["python3", "-m", "unittest", "discover", "-s", inputs, "-p", "test_audit.py", "-v"])
        includes = ["-I" + str(llama / d) for d in ("ggml/include", "ggml/src", "ggml/src/ggml-cpu")]
        for mode, cc, cxx, sanitizer in (("host", "gcc", "g++", []),
                ("asan-ubsan", "clang", "clang++", ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"])):
            flags = ["-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", *sanitizer]
            obj, exe = checks / (mode + ".o"), checks / (mode + "-test")
            run(mode + "-client", [cc, *flags, "-DARA_RESIDENT_CLIENT_TEST=1", "-I" + str(linux),
                                    "-c", linux / "client_v2.c", "-o", obj])
            run(mode + "-build", [cxx, *flags, "-std=c++17", "-DGGML_RISCV_ACCEL_AUTO=1", *includes,
                    "-I" + str(linux), llama / "tests/test-ara-linux-resident-session.cpp", obj, "-pthread", "-o", exe])
            text = run(mode + "-test", [exe])
            for marker in ("PASS: canonical ioctl", "PASS storage:", "PASS v2:", "PASS session:"):
                assert marker in text, marker

        audit_file = llama / "tests/test-ara-linux-resident-v2.py"
        spec = importlib.util.spec_from_file_location("session_entry_audit", audit_file)
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        obj = build_root / "ggml/src/CMakeFiles/ggml-cpu.dir/ggml-cpu/arch/riscv/akv.cpp.o"
        dis = run("portal-disassembly", [GNU + "objdump", "-dr", obj])
        syms = run("portal-symbols", [GNU + "nm", "-S", "--defined-only", obj])
        guard = preguard(dis, syms)
        save(checks / "preguard.json", guard)

        client = checks / "scalar-client.o"
        run("scalar-build", [GNU + "gcc", "-O3", "-march=rv64gc", "-mabi=lp64d", "-fno-tree-vectorize",
                "-fno-tree-slp-vectorize", "-ffreestanding", "-fno-builtin", "-I" + str(linux),
                "-c", linux / "client_v2.c", "-o", client])
        dis = run("scalar-disassembly", [GNU + "objdump", "-dr", client])
        ops = audit.instructions(dis)
        assert ops and not any(op.startswith(("v", "f", "csr")) for op, _ in ops.values())
        assert "<ara_resident_linux_admit>:" in dis and "ecall" in dis

        # Reuse the unchanged, previously checked module, not a current dirty build.
        prior = json.loads((BASE / "qualification.json").read_text())
        assert prior["state"] == "HOST_SPIKE_LINUX_CHECKED_BOARD_PENDING"
        module = BASE / "board/ara_resident.ko"
        assert sha(module) == prior["module_sha256"]
        old = BASE / "inputs/sdk"
        relatives = [Path("software/llama/platform/linux") / name for name in
                ("ara_resident_broker.c", "ara_resident_uapi.h", "job_layout.h", "buffer_pool.h", "Makefile")]
        for prefix in ("software/akv", "software/llama/platform/linux/sdk"):
            relatives += [p.relative_to(old) for p in (old / prefix).rglob("*") if p.is_file()]
        for relative in relatives:
            assert sha(old / relative) == sha(sdk / relative), "module source drift: " + str(relative)
            pins[str(old / relative)] = sha(old / relative)
        pins[str(module)] = sha(module)
        pins[str(BASE / "qualification.json")] = sha(BASE / "qualification.json")
        assert all(sha(path) == value for path, value in pins.items()), "source drift"

        board = out / "board"
        shutil.copyfile(module, board / "ara_resident.ko")
        shutil.copyfile(inputs / "SESSION.md", board / "SESSION.md")
        result.update(state="SESSION_HOST_SANITIZER_RV64_CHECKED_BOARD_PENDING", source_pins_match=True,
                module_reused=str(module), module_sha256=sha(module), unchanged_module_sources=len(relatives),
                elf_sha256=sha(board / "resident-ggml-pair"), kernel_and_rtl_retest=False,
                fresh_admission_per_call=True, warm_syscalls_removed=["openat", "GET_INFO", "close"],
                prior_module_evidence=str(BASE / "qualification.json"))
        save(board / "session-qualification.json", result)
        manifest = json.loads((board / "manifest.json").read_text())
        manifest.update(session_candidate=True, module_sha256=sha(module), module_reused_from=str(BASE),
                        session_option="GGML_RISCV_AKV_LINUX_SESSION", session_default=False,
                        full_copy_io=True, zero_copy=False, board_tested=False, performance_claim=False)
        save(board / "manifest.json", manifest)
        (board / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(board.iterdir())
                                                if p.is_file() and p.name != "SHA256SUMS"))
        run("package", ["tar", "-czf", out / "resident-session-checked.tar.gz", "-C", out, "board"])
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        save(out / "session-qualification.json", result)
        save(out / "session-commands.json", commands)
        save(out / "session-source-pins.json", pins)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
