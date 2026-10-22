#!/usr/bin/env python3
"""Short actual-module upstream repair experiments; no full-SoC claim."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from cva6.run_contract import execute, validate_output
from cva6.run_load_contract import freeze_bytes

CORE = "hardware/deps/cva6/core/"
COMMON = "hardware/deps/common_cells/"
ORIGINAL = ROOT / "verification/out/upstream_20261009-original-01"
TARGETS = {"load": CORE + "load_unit.sv", "csr": CORE + "csr_regfile.sv",
           "mmu": CORE + "cva6_mmu/cva6_mmu.sv", "ptw": CORE + "cva6_mmu/cva6_ptw.sv"}
ORIGINAL_SHA = {
    "load": "042db6cbcfdba16f6810a49de010eeb52105829e444a348df5fc7ec89f3ac7dd",
    "csr": "635466f3c536e290b6cdf208c12cef762ed394fbf701e03c89ecf770420d12f4",
    "mmu": "369c791bb6723741e9e15f0b9bb7f0e1d9a55e0277b2bef8a00cd7202a8ec2fc",
    "ptw": "82dab3584098056cff37c18e3070875b0b71ba185e90fd878151fc197c0d9505"}
PACKAGES = [COMMON + "src/cf_math_pkg.sv", CORE + "include/config_pkg.sv",
            CORE + "include/cv64a6_imafdcv_sv39_config_pkg.sv",
            CORE + "include/riscv_pkg.sv", CORE + "include/ariane_pkg.sv",
            CORE + "include/build_config_pkg.sv"]
MMU_SUPPORT = [COMMON + "src/lzc.sv", COMMON + "src/lfsr.sv",
               CORE + "pmp/src/pmp.sv", CORE + "pmp/src/pmp_entry.sv",
               CORE + "cva6_mmu/cva6_tlb.sv", CORE + "cva6_mmu/cva6_shared_tlb.sv",
               TARGETS["ptw"]]
TYPES = ("branchpredict_sbe_t", "exception_t", "jvt_t", "scoreboard_entry_t",
         "irq_ctrl_t", "icache_areq_t", "icache_arsp_t", "icache_dreq_t",
         "icache_drsp_t", "dcache_req_i_t", "dcache_req_o_t", "lsu_ctrl_t")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def types(text):
    parts = []
    for name in TYPES:
        matches = re.findall(r"(?:localparam|parameter)\s+type\s+" + name +
                             r"\s*=\s*(struct\s+packed\s*\{[^{}]*\})\s*,", text)
        if len(matches) != 1:
            raise ValueError(f"ambiguous actual interface: {name}")
        parts.append(f"typedef {matches[0]} {name};")
    parts.append("""
typedef struct packed {
  logic [9:0] reserved;
  logic [CVA6Cfg.PPNW-1:0] ppn;
  logic [1:0] rsw;
  logic d, a, g, u, x, w, r, v;
} refill_pte_t;
typedef struct packed {
  logic valid;
  logic [CVA6Cfg.PtLevels-2:0][0:0] is_page;
  logic [CVA6Cfg.VpnLen-1:0] vpn;
  logic [CVA6Cfg.ASID_WIDTH-1:0] asid;
  logic [CVA6Cfg.VMID_WIDTH-1:0] vmid;
  logic [0:0] v_st_enbl;
  refill_pte_t content, g_content;
} refill_t;
""")
    return "\n".join(parts)


def cases(suite):
    if suite == "load":
        return list(itertools.product(range(2), range(2), (3, 4, 9, 17), (0, 3)))
    if suite == "csr":
        return ([(0, d, m, p, 0) for d, m, p in itertools.product((0, 1, 3), range(2), range(2))] +
                [(1, d, m, p, 0) for d, m, p in itertools.product(range(2), range(2), range(2))] +
                [(1, d, 0, p, 1) for d, p in itertools.product(range(2), range(2))])
    if suite == "mmu":
        return list(itertools.product(*([range(2)] * 6), range(3)))
    if suite == "ptw":
        rows = [(k, level, bits, 2, 0, delay) for k, level, bits, delay in
                itertools.product(range(3), range(2), range(1, 8), (0, 2))]
        rows += [(k, -1, 0, level, fault, delay) for k, level, fault, delay in
                 itertools.product(range(3), range(3), range(6), (0, 2))]
        return rows
    raise ValueError("unknown suite")


def expected(suite, row):
    if suite == "load":
        cancel, wait_grant, delay, tid = row
        return dict(allocation_fire=1, flushed_slot=cancel, old_reply_valid=1-cancel,
                    old_reply_id=tid, old_reply_data=0x1234567887654321, old_reply_exception=0,
                    reuse_fire=1, reuse_reply_valid=1, reuse_reply_id=tid,
                    reuse_reply_data=0xfedcba9876543210, reuse_reply_exception=0, drained=1)
    if suite == "csr":
        sret, dest, mprv, pie, start_s = row
        after_mprv = mprv if not sret and dest == 3 else 0
        return dict(before_priv=1 if start_s else 3, before_mprv=mprv,
                    eret=1, target_epc=0x80003000 if sret else 0x80002000,
                    after_priv=dest, after_mprv=after_mprv,
                    effective_ld_priv=0 if after_mprv else dest,
                    previous_priv=0, ie=pie, pie=1, fs=3, vs=3, sd=1)
    if suite == "mmu":
        ar, br, ab, bb, store, negative, mode = row
        base = 0xffffffc012345088 if negative else 0x12345088
        a = base ^ (ab << 39)
        b = (base + 8) ^ (bb << 39)
        page = 4096 * 512**mode
        af, bf = ar * ab, br * bb
        return dict(a_hit=1, a_valid=ar, a_pa=0x80000000 + a % page,
                    a_exception=af, a_cause=(15 if store else 13) if af else 0,
                    a_tval=a if af else 0, b_hit=1,
                    b_early_ppn=(0x80000000 + b % page) >> 12,
                    b_valid=br, b_pa=0x80000000 + b % page, b_exception=bf,
                    b_cause=(13 if store else 15) if bf else 0, b_tval=b if bf else 0,
                    drain_valid=0, drain_exception=0)
    if suite == "ptw":
        kind, bad_level, bits, level, fault, delay = row
        nonleaf_bad = bad_level >= 0 and bits != 0
        failed = nonleaf_bad or fault in (1, 3, 4) or (fault == 2 and kind == 2) or (fault == 5 and level < 2)
        return dict(terminal=1, requests=(bad_level if nonleaf_bad else level)+1,
                    updates=int(not failed), faults=int(failed), pmp_faults=0,
                    address_errors=0, walking_instr=int(kind == 0),
                    update_ppn=(0x80001 if fault == 5 else 0x80000) if not failed else 0,
                    update_va=0x12345088 if not failed else 0,
                    update_asid=5 if not failed else 0,
                    update_page=(1, 2, 0)[level] if not failed else 0, idle=1)
    raise ValueError("unknown suite")


def audit(trace, console, suite, rows):
    if not rows:
        raise ValueError("empty plan")
    wanted = {(i, key): value for i, row in enumerate(rows) for key, value in expected(suite, row).items()}
    observed = {}
    for line in trace.splitlines():
        match = re.fullmatch(r"(\d+) ([a-z_]+) ([0-9a-fA-F]{16})", line)
        if not match:
            raise ValueError("malformed or X/Z observation")
        i, key, value = match.groups()
        pair = (int(i), key)
        if pair not in wanted or pair in observed:
            raise ValueError("duplicate/unplanned observation")
        observed[pair] = int(value, 16)
    if observed.keys() != wanted.keys():
        raise ValueError("missing observations")
    if re.findall(r"UPSTREAM_COMPLETE cases=(\d+)", console) != [str(len(rows))]:
        raise ValueError("missing/duplicate/mismatched completion")
    if "$finish called" not in console or re.search(r"Fatal:|Error-\[|UVM_(ERROR|FATAL)|assertion.*fail|\$stop", console, re.I):
        raise ValueError("abnormal simulation")
    failures = [dict(id=i, field=key, got=observed[i, key], expected=value)
                for (i, key), value in wanted.items() if observed[i, key] != value]
    return dict(status="FAIL" if failures else "PASS", cases=len(rows), checks=len(wanted),
                passing_cases=len(rows)-len({f["id"] for f in failures}), failures=failures)


def baseline_gate(result, suite, rows):
    # Require the exact predicted old behavior, not merely any failed check.
    predicted = []
    for i, row in enumerate(rows):
        good = expected(suite, row)
        old = dict(good)
        if suite == "load" and row[0]:
            old.update(flushed_slot=0, old_reply_valid=1)
        elif suite == "csr":
            sret, dest, mprv, pie, start_s = row
            old["after_mprv"] = mprv
            old["effective_ld_priv"] = (3 if sret else 0) if mprv else dest
        elif suite == "mmu":
            ar, br, ab, bb, store, neg, mode = row
            bad = ar and br and bb
            va = (0xffffffc012345088 if neg else 0x12345088) ^ (ab << 39)
            old.update(a_exception=int(bad), a_cause=(15 if store else 13) if bad else 0,
                       a_tval=va if bad else 0)
        elif suite == "ptw" and row[1] >= 0 and row[2]:
            old.update(requests=3, updates=1, faults=0, update_ppn=0x80000,
                       update_va=0x12345088, update_asid=5, update_page=0)
        predicted += [dict(id=i, field=k, got=old[k], expected=v)
                      for k, v in good.items() if old[k] != v]
    if not predicted or result["failures"] != predicted:
        raise ValueError("baseline differs from exact predicted bug signature")


def run(suite, variant, output):
    output = validate_output(output)
    output.mkdir(parents=True)
    support = (MMU_SUPPORT if suite == "mmu" else
               MMU_SUPPORT[:4] if suite == "ptw" else
               [COMMON + "src/lzc.sv"] if suite == "load" else [])
    tb = f"verification/cva6/upstream_20261009_{suite}_tb.sv"
    sources = PACKAGES + support + [TARGETS[suite], tb]
    extra = [CORE+"cva6.sv", CORE+"include/rvfi_types.svh",
             COMMON+"include/common_cells/assertions.svh", COMMON+"include/common_cells/registers.svh",
             "verification/cva6/upstream_20261009_common.svh",
             "verification/cva6/upstream_20261009_run.py", "verification/cva6/upstream_20261009_test.py",
             "verification/cva6/run_contract.py", "verification/cva6/run_load_contract.py"]
    records = []
    for rel in sources + extra:
        data = (ROOT / rel).read_bytes()
        live_sha = sha(data)
        if rel == TARGETS[suite] and variant == "baseline":
            data = (ORIGINAL / Path(rel).relative_to("hardware/deps/cva6")).read_bytes()
            if sha(data) != ORIGINAL_SHA[suite]:
                raise ValueError("original snapshot identity mismatch")
        record = freeze_bytes(output / "frozen" / rel, data)
        record.update(relative=rel, live_sha256=live_sha)
        records.append(record)
    generated = output / "generated"
    freeze_bytes(generated / "upstream_20261009_types.svh", types((output / "frozen" / CORE / "cva6.sv").read_text()).encode())
    rows = cases(suite)
    freeze_bytes(output / "cases.txt", "".join(" ".join(map(str, (i, *r))) + "\n" for i, r in enumerate(rows)).encode())
    save(output / "cases.json", rows)
    save(output / "manifest.json", dict(suite=suite, variant=variant, sources=records,
         cases_sha256=sha((output / "cases.txt").read_bytes()), scope="actual module RV64 Sv39 RVH=0 PMP=0; no full-SoC signoff"))
    build = output / "build"
    vcs = shutil.which("vcs") or "/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs"
    cmd = [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "-assert", "svaext",
           "+define+ARIANE_ACCELERATOR_PORT=1", "-top", f"upstream_20261009_{suite}_tb",
           "-o", str(build / "simv"), "-Mdir=" + str(build / "csrc")]
    cmd += ["+incdir+" + str(output / "frozen" / x) for x in
            (COMMON+"include", CORE+"include", "verification/cva6")]
    cmd += ["+incdir+" + str(generated)]
    cmd += [str(output / "frozen" / p) for p in sources]
    compiled = execute(cmd, build, 180)
    if compiled["returncode"] or compiled.get("timeout") or not (build / "simv").exists():
        raise ValueError("VCS compile failed; inspect build/console.log")
    sim = execute([str(build / "simv"), "+CASES=" + str(output / "cases.txt")], output / "sim", 60)
    if sim["returncode"] or sim.get("timeout"):
        raise ValueError("VCS simulation did not complete normally")
    result = audit((output / "sim/observed.txt").read_text(), (output / "sim/console.log").read_text(), suite, rows)
    result.update(compile=compiled, simulation=sim, variant=variant,
                  image_sha256=sha((build / "simv").read_bytes()),
                  trace_sha256=sha((output / "sim/observed.txt").read_bytes()))
    for rec in records:
        if sha(Path(rec["frozen"]).read_bytes()) != rec["sha256"] or sha((ROOT / rec["relative"]).read_bytes()) != rec["live_sha256"]:
            raise ValueError("source drift during module experiment")
    if variant == "baseline":
        save(output / "observations-audit.json", result)
        baseline_gate(result, suite, rows)
        result["status"] = "BASELINE_REJECTED"
    save(output / "audit.json", result)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suite", choices=TARGETS, required=True)
    ap.add_argument("--variant", choices=("baseline", "candidate"), required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    try:
        result = run(args.suite, args.variant, args.output)
        print(json.dumps({k: result[k] for k in ("status", "cases", "checks", "passing_cases")}, indent=2))
        sys.exit(0 if result["status"] in ("PASS", "BASELINE_REJECTED") else 1)
    except (ValueError, OSError) as exc:
        if args.output.is_dir():
            save(args.output / "rejection.json", dict(error=str(exc)))
        print(str(exc), file=sys.stderr)
        sys.exit(1)
