#!/usr/bin/env python3
"""Emit a separate static/build review for the completed v4 entry guard."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def between(text, start, end):
    require(text.count(start) == 1 and text.count(end) == 1, "ambiguous function boundary")
    return text.split(start, 1)[1].split(end, 1)[0]


def review(out, write):
    result = json.loads((out / "result.json").read_text())
    require(result["status"] == "COMPILED_TEST_CANDIDATE_RUNTIME_PENDING", "Image build incomplete")
    tree = out / "linux"
    image = tree / "arch/riscv/boot/Image"
    require(sha(image) == result["image_sha256"], "Image identity mismatch")
    names = ["arch/riscv/kernel/akv_direct.c", "arch/riscv/kernel/traps.c",
             "arch/riscv/include/asm/entry-common.h", "arch/riscv/include/asm/switch_to.h"]
    sources = {name: (tree / name).read_text() for name in names}
    driver, traps, entry, switch = (sources[name] for name in names)
    guard = between(driver, "void noinstr riscv_akv_direct_user_enter(struct pt_regs *regs)",
                    "/* A switch must not drop an outstanding grant")
    acquire = between(driver, "static int akv_acquire(", "static long akv_ioctl(")
    ret = between(driver, "void riscv_akv_direct_return(void)", "static int akv_invalidate(")
    ecall = between(traps, "void do_trap_ecall_u(struct pt_regs *regs)", "void do_page_fault(")
    early = ecall.find("riscv_akv_direct_user_enter(regs);")
    discard = ecall.find("riscv_v_vstate_discard(regs);")
    require(0 <= early < discard, "missing pre-discard entry guard")
    require("riscv_akv_direct_user_enter(regs);" in entry, "generic user-entry guard missing")
    require("riscv_akv_direct_enter();" in switch and
            "riscv_akv_direct_user_enter(task_pt_regs(current));" in driver,
            "switch path can bypass guard")
    require("if (!READ_ONCE(akv_user_granted))\n\t\treturn;" in guard,
            "missing once-per-grant guard")
    require(driver.count("WRITE_ONCE(akv_user_granted, true)") == 1 and
            "WRITE_ONCE(akv_user_granted, true)" in ret, "grant publication not confined to return")
    order = [guard.find(x) for x in ["ARA_AKV_GATE_STRICT", "akv_user_granted, false",
              "csr_read_set(CSR_STATUS, SR_VS)", "csrr zero, vl", "fence rw, rw",
              "csr_clear(CSR_STATUS, SR_VS)", "csr_set(CSR_STATUS, status & SR_VS)",
              "regs->status |= SR_VS_DIRTY"]]
    require(all(x >= 0 for x in order) and order == sorted(order), "entry drain/restore order incorrect")
    for state in ("VS", "FS"):
        require("if (regs->status & SR_%s)\n\t\tregs->status |= SR_%s_DIRTY;" % (state, state) in guard,
                "saved %s OFF could be promoted" % state)
    conditions = ["!current->thread.vstate.datap", "!(task_pt_regs(current)->status & SR_VS)",
                  "!(task_pt_regs(current)->status & SR_FS)", "!riscv_v_vstate_ctrl_user_allowed()"]
    require(all(x in acquire for x in conditions), "initialized-state admission incomplete")
    reject = ret.find("victim = akv_revoke_locked(f, true);")
    grant = ret.find("WRITE_ONCE(akv_user_granted, true)")
    require(all(0 <= ret.find(x) < reject < grant for x in conditions),
            "return-state revalidation missing or after grant")
    pins = json.loads((out / "source-pins.json").read_text())
    for path, expected in pins.items():
        require(Path(path).is_file() and sha(Path(path)) == expected, "pin drift: " + path)
    for name in names:
        require(pins.get(str(tree / name)) == sha(tree / name), "built source not pinned: " + name)
    require(sha(tree / ".config") == sha(out / "test.config"), "built configuration drift")
    checks = {}
    for compiler in ("gcc", "clang"):
        match = re.fullmatch(r"AKV_DIRECT_HOST_POLICY_PASS checks=(\d+)\n",
                             (out / ("host-test-" + compiler + ".log")).read_text())
        require(match is not None and int(match[1]) == 17394, "host test report missing")
        checks[compiler] = {"status": "PASS", "checks": int(match[1]),
                            "sanitizers": ["ASan", "UBSan"] if compiler == "clang" else []}
    objdump = Path("/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-objdump")
    require(pins.get(str(objdump)) == sha(objdump), "objdump not pinned")
    obj = tree / "arch/riscv/kernel/akv_direct.o"
    disassembly = subprocess.check_output([str(objdump), "-dr", "--disassemble=riscv_akv_direct_user_enter",
                                          str(obj)], text=True)
    require(disassembly.count("c2002073") == 1 and "fence\trw,rw" in disassembly,
            "compiled owner-entry vl drain/fence missing")
    require(".noinstr.text" in disassembly and "vstart" not in disassembly,
            "unexpected owner-entry code section or VSTART modification")
    record = {
        "status": "ENTRY_GUARD_STATIC_REVIEW_PASS_RUNTIME_PENDING",
        "image": str(image), "image_sha256": sha(image), "linux_tree": str(tree),
        "built_source_sha256": {name: sha(tree / name) for name in names},
        "driver_object_sha256": sha(obj), "config_sha256": sha(tree / ".config"),
        "early_pre_discard_drain": True, "initialized_state_admission": True,
        "saved_off_not_promoted": True, "return_state_revalidated": True,
        "generic_user_entry_guard": True, "switch_cannot_bypass_guard": True,
        "single_drain_per_return_grant": True,
        "tests": {"host": checks, "kernel_objects": "COMPILED", "kernel_image": "COMPILED",
                  "source_pins": "MATCH", "entry_guard_object": "CSR vl/fence in noinstr section"},
        "runtime_pending": True, "runtime_validated": False, "hardware_validated": False,
        "board_validated": False, "custom_arithmetic_validated": False,
        "review_scope": "Static source/order checks and compiled-object inspection; no lifecycle execution proof",
        "review_tool": str(Path(__file__).resolve()), "review_tool_sha256": sha(Path(__file__).resolve()),
    }
    if write:
        target = out / "entry-guard-review.json"
        require(not target.exists(), "review already exists; preserve it")
        (out / "entry-guard-disassembly.txt").write_text(disassembly)
        target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        answer = review(args.out.resolve(), not args.check_only)
        print(json.dumps(answer, sort_keys=True))
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, "ENTRY_GUARD_REVIEW_REJECT: %s\n" % error)
