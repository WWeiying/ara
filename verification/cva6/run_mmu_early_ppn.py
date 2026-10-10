#!/usr/bin/env python3
"""Bounded actual-CVA6-MMU early PPN/registered PA/NI-consumer experiment.

Archive baseline directly from CVA6 HEAD, never rewrite a live source. Inject
only the DTLB refill interface. This is functional, not code coverage.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from cva6.run_contract import execute, validate_output
from cva6.run_load_contract import freeze_bytes

CORE = "hardware/deps/cva6/core/"
COMMON = "hardware/deps/common_cells/"
MMU = CORE + "cva6_mmu/cva6_mmu.sv"
BASELINE_SHA = "4859d957d56541c27928e347cee7ef800486cf3b1ad91aa53a9e3e044344c480"
SOURCES = (
    COMMON + "src/cf_math_pkg.sv",
    CORE + "include/config_pkg.sv",
    CORE + "include/cv64a6_imafdcv_sv39_config_pkg.sv",
    CORE + "include/riscv_pkg.sv", CORE + "include/ariane_pkg.sv",
    CORE + "include/build_config_pkg.sv",
    COMMON + "src/lzc.sv", COMMON + "src/lfsr.sv",
    CORE + "pmp/src/pmp.sv", CORE + "pmp/src/pmp_entry.sv",
    CORE + "cva6_mmu/cva6_tlb.sv", CORE + "cva6_mmu/cva6_shared_tlb.sv",
    CORE + "cva6_mmu/cva6_ptw.sv", MMU, CORE + "load_unit.sv",
    "verification/cva6/mmu_early_ppn_tb.sv",
)
EXTRA = (CORE + "cva6.sv", COMMON + "include/common_cells/assertions.svh",
         COMMON + "include/common_cells/registers.svh",
         "verification/cva6/run_mmu_early_ppn.py",
         "verification/cva6/test_run_mmu_early_ppn.py",
         "verification/cva6/run_contract.py", "verification/cva6/run_load_contract.py")
TYPE_NAMES = ("exception_t", "icache_areq_t", "icache_arsp_t", "icache_dreq_t",
              "icache_drsp_t", "dcache_req_i_t", "dcache_req_o_t", "lsu_ctrl_t")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def oracle(mode, va, ppn):
    if mode not in (-1, 0, 1, 2) or not 0 <= ppn < 2**44:
        raise ValueError("invalid Sv39 fixture input")
    if mode == -1:
        return va % 2**56
    page = 4096 * 512**mode
    if ppn * 4096 % page:
        raise ValueError("illegal unaligned superpage PPN")
    return ppn * 4096 + va % page


def ni(addr):
    return int(any(base <= addr < base + 4096 for base in (0xC0000000, 0xD0000000)))


def stale_page_mutant(candidate):
    old = b"if (dtlb_is_page[CVA6Cfg.PtLevels-1-level]) begin"
    new = b"if (dtlb_is_page_q[CVA6Cfg.PtLevels-1-level]) begin"
    if candidate.count(old) != 1:
        raise ValueError("cannot uniquely construct stale-page-only negative control")
    return candidate.replace(old, new)


def cases():
    rows = []
    def add(prev, mode, va, ppn, family, bit=-1):
        oracle(mode, va, ppn)
        rows.append(dict(id=len(rows), prev=prev, mode=mode, va=va, ppn=ppn,
                         family=family, bit=bit))
    # Device and next normal pages first: deterministic, directly useful failures.
    for mode in (1, 2):
        page = 4096 * 512**mode
        for base in (0xC0000000, 0xD0000000):
            for delta in (0, 4096, 8192):
                physical = base + delta
                add(0, mode, physical % page + 0x88,
                    physical // page * page // 4096, "device")
    for prev in (-1, 0, 1, 2):
        for mode in (-1, 0, 1, 2):
            page = 4096 * 512**max(mode, 0)
            for offset in (0, 1, 0xFFF, page // 2, page - 1):
                add(prev, mode, 0x40000000 + offset, 0x88000000000, "transition")
    for mode in (0, 1, 2):
        for bit in range(27):
            va = (1 << (12 + bit)) | 0x3C
            if va & 2**38:
                va |= (2**64 - 2**39)
            add((mode + 1) % 3, mode, va, 0x80000000000, "vpn_walk", bit)
        for bit in range(9 * mode, 44):
            add((mode + 2) % 3, mode, 0x23456128, 1 << bit, "ppn_walk", bit)
    return rows


def types(source):
    result = ["// Verbatim packed interfaces extracted from archived actual cva6.sv."]
    for name in TYPE_NAMES:
        found = re.findall(r"(?:localparam|parameter)\s+type\s+" + name +
                           r"\s*=\s*(struct\s+packed\s*\{[^{}]*\})\s*,", source)
        if len(found) != 1:
            raise ValueError(f"ambiguous interface {name}")
        result.append(f"typedef {found[0]} {name};")
    return "\n".join(result) + "\n"


def audit_trace(trace, console, planned):
    if not planned or [r["id"] for r in planned] != list(range(len(planned))):
        raise ValueError("empty or noncontiguous planned cases")
    lines = trace.splitlines()
    header = "id prev mode va ppn old_page current_page hit early ni valid pa exception prev_pa prev_valid prev_exception"
    if not lines or lines[0] != header or len(lines) != len(planned) + 1:
        raise ValueError("missing, malformed or incomplete observed trace")
    failures = []
    counts = Counter()
    for line, item in zip(lines[1:], planned):
        fields = line.split()
        if len(fields) != len(header.split()):
            raise ValueError("trace width mismatch")
        try:
            vals = [int(f, 10 if i < 3 else 16) for i, f in enumerate(fields)]
        except ValueError as exc:
            raise ValueError("unknown/X or malformed observed value") from exc
        obs = dict(zip(header.split(), vals))
        if any(obs[k] != item[k] for k in ("id", "prev", "mode", "va", "ppn")):
            raise ValueError("observed input differs from archived stimulus")
        wanted = oracle(item["mode"], item["va"], item["ppn"])
        prev_wanted = oracle(item["prev"], 0x1552345080, 0x80000)
        def page_bits(mode):
            return {-1: 0, 0: 0, 1: 2, 2: 1}[mode]
        expected = dict(hit=1, early=wanted // 4096, ni=ni(wanted), valid=1,
                        pa=wanted, exception=0, prev_pa=prev_wanted,
                        prev_valid=1, prev_exception=0,
                        old_page=page_bits(item["prev"]), current_page=page_bits(item["mode"]))
        bad = False
        for key, value in expected.items():
            if obs[key] != value:
                bad = True
                failures.append(dict(id=item["id"], field=key, got=obs[key], expected=value,
                                     va=item["va"], ppn=item["ppn"], prev=item["prev"], mode=item["mode"]))
        counts["observed_cases"] += 1
        if not bad:
            counts["passing_cases"] += 1
            counts[f"mode_{item['mode']}"] += 1
            counts[f"pair_{item['prev']}_{item['mode']}"] += 1
            counts[item["family"]] += 1
            counts[f"offset_{item['va'] % 4096:x}"] += 1
            if item["family"] in ("vpn_walk", "ppn_walk"):
                counts[f"{item['family']}_mode{item['mode']}_bit{item['bit']}"] += 1
    complete = re.findall(r"MMU_EARLY_PPN_COMPLETE cases=(\d+) checks=(\d+) errors=(\d+)", console)
    if len(complete) != 1:
        raise ValueError("missing or duplicate normal test completion")
    n, checks, errors = map(int, complete[0])
    if n != len(planned) or checks != n * 11 + 2:
        raise ValueError("incorrect test/check count")
    # SV and host independently check the same output mismatches; page flags
    # additionally checked by the host must never be wrong.
    if any(f["field"] in ("old_page", "current_page") for f in failures):
        raise ValueError("DTLB installation/page-transition observation invalid")
    if errors != len(failures):
        raise ValueError("unaccounted SV failure (including idle/drain checks)")
    if re.search(r"UVM_(?:ERROR|FATAL)|Error-\[|^\s*Error:|assertion.*fail|\$stop", console, re.I | re.M):
        raise ValueError("unexpected simulator error")
    if failures:
        if "EARLY_PPN_TEST_FAILED" not in console:
            raise ValueError("missing expected bounded test failure")
    elif "$finish called" not in console or "Fatal:" in console:
        raise ValueError("simulator did not finish cleanly")
    return dict(checks=checks, failures=failures, functional_coverage=dict(counts),
                status="FAIL" if failures else "PASS")


def run(output, variant, execute_now):
    output = validate_output(output)
    output.mkdir(parents=True)
    dep = ROOT / "hardware/deps/cva6"
    original = subprocess.check_output(["git", "-C", str(dep), "show", "HEAD:core/cva6_mmu/cva6_mmu.sv"])
    if sha(original) != BASELINE_SHA:
        raise ValueError("CVA6 HEAD baseline differs from independently identified original")
    head = subprocess.check_output(["git", "-C", str(dep), "rev-parse", "HEAD"], text=True).strip()
    current = (ROOT / MMU).read_bytes()
    selected = original if variant == "baseline" else current
    if variant == "stale-page-mutant":
        selected = stale_page_mutant(current)
    freeze_bytes(output / "original_cva6_mmu.sv", original)
    freeze_bytes(output / "candidate_cva6_mmu.sv", current)
    records = []
    for path in SOURCES + EXTRA:
        data = (ROOT / path).read_bytes()
        if path == MMU:
            data = selected
        record = freeze_bytes(output / "frozen" / path, data)
        record["relative"] = path
        record["live_sha256"] = sha((ROOT / path).read_bytes())
        records.append(record)
    rows = cases()
    freeze_bytes(output / "cases.txt", "".join(
        f"{r['id']} {r['prev']} {r['mode']} {r['va']:016x} {r['ppn']:016x}\n"
        for r in rows).encode())
    save(output / "cases.json", rows)
    generated = output / "generated"
    freeze_bytes(generated / "mmu_early_ppn_types.svh",
                 types((output / "frozen" / CORE / "cva6.sv").read_text()).encode())
    manifest = dict(variant=variant, cva6_head=head, baseline_sha256=sha(original),
                    candidate_sha256=sha(current), dut_sha256=sha(selected), sources=records, cases=len(rows),
                    scope="RVH=0 Sv39; actual MMU+TLB+load_unit NI; refill-only injection",
                    exclusions=["PTW memory walk", "fault-to-normal overlap", "RVH/Sv32",
                                "cache request timing", "full SoC", "code coverage"])
    save(output / "manifest.json", manifest)
    if not execute_now:
        return dict(status="PREPARED", output=str(output))
    vcs = shutil.which("vcs") or "/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs"
    build = output / "build"
    cmd = [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "-assert", "svaext",
           "+define+ARIANE_ACCELERATOR_PORT=1", "-top", "mmu_early_ppn_tb",
           "-o", str(build / "simv"), "-Mdir=" + str(build / "csrc"),
           "+incdir+" + str(output / "frozen" / COMMON / "include"),
           "+incdir+" + str(output / "frozen" / CORE / "include"),
           "+incdir+" + str(generated)]
    cmd += [str(output / "frozen" / p) for p in SOURCES]
    compiled = execute(cmd, build, 180)
    if compiled["returncode"] or not (build / "simv").is_file():
        raise ValueError("VCS build failed; see build/console.log")
    sim = execute([str(build / "simv"), "+CASES=" + str(output / "cases.txt")], output / "sim", 30)
    result = audit_trace((output / "sim/observed.tsv").read_text(),
                         (output / "sim/console.log").read_text(), rows)
    if sim.get("timeout"):
        raise ValueError("simulation timeout is not a functional verdict")
    if variant in ("baseline", "stale-page-mutant"):
        if not any(f["field"] == "early" for f in result["failures"]):
            raise ValueError("original did not reproduce exact early PPN failure")
        if any(f["field"] not in ("early", "ni") for f in result["failures"]):
            raise ValueError("original has unexpected non-early-path failures")
        result["status"] = ("BASELINE_REJECTED_EARLY_PPN" if variant == "baseline"
                            else "STALE_PAGE_MUTANT_REJECTED_EARLY_PPN")
    elif result["status"] != "PASS" or sim["returncode"]:
        save(output / "audit.json", result)
        raise ValueError("candidate failed strict directed checks")
    for record in records:
        if sha(Path(record["frozen"]).read_bytes()) != record["sha256"]:
            raise ValueError("archived source drift")
        if sha((ROOT / record["relative"]).read_bytes()) != record["live_sha256"]:
            raise ValueError("live input changed during experiment")
    result.update(output=str(output), manifest_sha256=sha((output / "manifest.json").read_bytes()),
                  baseline_sha256=sha(original), candidate_sha256=sha(current), dut_sha256=sha(selected),
                  compile_seconds=compiled["elapsed_s"], simulation_seconds=sim["elapsed_s"])
    save(output / "audit.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=("baseline", "candidate", "stale-page-mutant"), required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = run(args.output, args.variant, args.execute)
    print(json.dumps({k: v for k, v in result.items() if k != "failures"}, indent=2))


if __name__ == "__main__":
    main()
