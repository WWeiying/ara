"""738 CSR counter-freeze matrix: clang/Spike only, no EDA or admission."""
import argparse
import json
from pathlib import Path
import subprocess

import build_gap98_preflight as shared
import inventory_csr_707 as inventory

ROOT, OUT, sha, save, require = shared.ROOT, shared.OUT, shared.sha, shared.save, shared.require
BASE = OUT / "clip17-offline-admitted-738-parent-20261006-01"
BUILD = inventory.BUILD
APP = ROOT / "apps/riscv-tests/isa/rv64uv/vcsr_frozen_counter_matrix.c"
SPIKE_ISA = "rv64gv_zfh_zvfh_zvl1024b_zicntr_zihpm"
SEED = 0x1234567811223344
INPUT = 0x00ff00ff00ff00ff
GUARDS = [0x13579bdf2468ace0, 0xfedcba9876543210]
SPIKE_SOURCE = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart")


def expected():
    new = [0xfedcba9876543210, SEED | INPUT, SEED & ~INPUT,
           17, SEED | 3, SEED & ~5, SEED, SEED]
    return [5, 5, 5] + [v for _ in range(2) for n in new for v in (SEED, n, n)] + [5]


def target_evidence(pins):
    def pin(path, digest=None):
        path = Path(path).absolute()
        actual = sha(path)
        require(digest is None or actual == digest, "Frozen input drift: " + str(path))
        require(str(path) not in pins or pins[str(path)] == actual, "Conflicting pin")
        pins[str(path)] = actual
        return path
    state = json.loads(pin(BASE / "status.json").read_bytes())
    bits = json.loads(pin(BASE / "combined-bits.json").read_bytes())
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 738
            and len(bits["tests"]) == len(set(bits["tests"])) == 738, "Not formal738")
    require(pin(BASE / "combined-inputs.txt").read_text().splitlines() ==
            [str(BUILD / "sim/simv.vdb"), *bits["tests"]], "Wrong exact738 membership")
    pin(BASE / "admission-manifest.json")
    source_pins = json.loads(pin(BUILD / "build-source-pins.json").read_bytes())
    for path in (inventory.SOURCE, inventory.CONFIG, ROOT / "hardware/src/ara_soc.sv"):
        pin(path, source_pins[str(path)])
    source = inventory.SOURCE.read_text()
    cfg = inventory.CONFIG.read_text()
    require("CVA6ConfigPerfCounterEn = 1;" in cfg and "CVA6ConfigHExtEn = 0;" in cfg,
            "Wrong frozen counter/config implementation")
    for fragment in ("!mcountinhibit_q[0]", "!mcountinhibit_q[2]", "cycle_d = cycle_q;",
                     "cycle_d[CVA6Cfg.XLEN-1:0] = csr_wdata;",
                     "instret_d[CVA6Cfg.XLEN-1:0] = csr_wdata;",
                     "mcountinhibit_d = {csr_wdata[MHPMCounterNum+2:2], 1'b0, csr_wdata[0]};"):
        require(fragment in source, "Counter source predicate drift")
    design = inventory.Design(BUILD / "sim/simv.vdb")
    require(design.source(inventory.SCOPE)["resolved_path"] == str(inventory.SOURCE), "Wrong compiled source")
    for relative, digest in bits["design"].items():
        pin(design.db / relative, digest)
    for relative in ("auxiliary/verilog.sourceinfo.xml", "shape/line.verilog.shape.xml",
                     "shape/branch.verilog.shape.xml", "shape/cond.verilog.shape.xml",
                     "shape/cond.verilog.info.xml"):
        pin(design.db / relative)
    cond = inventory.read_xml(design.db / "shape/cond.verilog.shape.xml")
    rows, held = [], []
    for metric in ("line", "cond", "branch"):
        rec = bits["metrics"][metric][inventory.SCOPE]
        if metric == "cond":
            defs = [n for n in cond if n.get("id") == design.hierarchy[inventory.SCOPE].get("id")
                    and n.get("chksum") == rec["checksum"]]
            require(len(defs) == 1, "Ambiguous condition shape")
            definition = defs[0]
        else:
            definition = design.definition(inventory.SCOPE, metric)
        require(definition.get("chksum") == rec["checksum"], "Compiled checksum mismatch")
        points, _ = inventory.mapped_points(metric, definition, rec)
        for p in points:
            chosen = ((metric == "cond" and p["raw_index"] in (90, 92)) or
                      (metric == "line" and int(p["line"]) in (1038, 1732, 1745, 1749)) or
                      (metric == "branch" and p["raw_index"] == 202))
            if not chosen:
                continue
            hit = bool(int(rec["bits"], 16) & (1 << (rec["width"] - 1 - p["raw_index"])))
            row = dict(metric=metric, scope=inventory.SCOPE, raw_index=p["raw_index"],
                       source_line=p["line"], width=rec["width"], checksum=rec["checksum"], hit=hit,
                       expression=p.get("expression", ""), vector=p.get("vector", ""),
                       source_text=source.splitlines()[int(p["line"]) - 1])
            (held if hit else rows).append(row)
    require({r["raw_index"] for r in rows if r["metric"] == "cond"} == {90, 92},
            "CY inhibition targets no longer fresh")
    require(any(r["metric"] == "line" and r["raw_index"] == 275 for r in rows), "Cycle hold not fresh")
    return dict(baseline=738, status="STATIC_REACHABLE_CSR_TARGETS_NOT_NATIVE_QUALIFICATION",
                targets=rows, already_hit=held, exclusions_generated=False,
                predicate="PerfCounterEn=1, normal M-mode, CY/IR held1, legal writes to 0x320/b00/b02",
                duplicate_review="gap37_csr_counters rejected at Spike preflight; absent from formal738",
                expected_increment_is_not_measured=True)


def validate(commits, symbols):
    require(not any(c.vector_writes or c.pc == symbols["trap_fail"] for c in commits), "Unexpected vector/trap")
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    terminal = [v for c in commits for a, v in c.memory_accesses if a == symbols["tohost"] and v is not None]
    observed = [writes.get(symbols["counter_observed"] + 8 * i) for i in range(52)]
    require(observed == expected(), "Independent frozen counter oracle mismatch")
    require(terminal == [1] and writes.get(symbols["g75_result"]) == 54 and
            writes.get(symbols["g75_result"] + 4) == writes.get(symbols["num_failed"]) == 0 and
            all(writes.get(symbols["g75_trap"] + off) == 0 for off in (0, 8, 16)), "Exact signature/trap failed")
    require(not any(a in (symbols["counter_guards"], symbols["counter_guards"] + 8)
                    for c in commits for a, v in c.memory_accesses if v is not None), "Guard overwritten")
    counters = {0xb00, 0xb02}
    regs = {0: 0}
    primed, counts, aliases = set(), {a: 0 for a in counters}, {a: 0 for a in (0xc00, 0xc02)}
    inhibit = 0
    for c in commits:
        insn = c.instruction
        csr, funct, rs, rd = insn >> 20, (insn >> 12) & 7, (insn >> 15) & 31, (insn >> 7) & 31
        if insn & 127 == 0x73 and funct in (1, 2, 3, 5, 6, 7):
            value = rs if funct >= 5 else regs.get(rs)
            if csr == 0x320:
                require(value is not None, "Unknown inhibit source")
                require(funct in (1, 2), "Unexpected inhibit operation")
                inhibit = (value if funct == 1 else inhibit | value) & ~2
                require(inhibit in (0, 5), "Counter unexpectedly enabled mid-matrix")
            if csr in counters:
                if rd != 0:
                    require(inhibit == 5 and csr in primed, "Observed unprimed/running counter")
                    counts[csr] += 1
                elif funct == 1:
                    require(inhibit == 5 and value in (SEED, 0), "Wrong independent counter prime/reset")
                    primed.add(csr)
            if csr in aliases:
                require(inhibit == 5 and csr - 0x100 in primed and funct == 2 and rs == 0,
                        "Unexpected alias access")
                aliases[csr] += 1
        regs.update(c.gpr_writes)
    require(counts == {0xb00: 16, 0xb02: 16} and aliases == {0xc00: 8, 0xc02: 8} and inhibit == 0,
            "Wrong counter CSR population/final inhibit")
    return dict(status="SPIKE_COUNTER_MATRIX_PASS_NOT_NATIVE_DUT", checks=54, observed_bytes=416,
                counter_cells=16, traps=0, vector_destination_instructions=0,
                platform_running_counter_values_compared=False, native_oracle_qualified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    pins = {}
    targets = target_evidence(pins)
    paths = [APP, Path(__file__).resolve(), Path(__file__).with_name("test_build_csr_frozen_counter_preflight.py"),
             ROOT / "verification/tests/gap75_start.S", ROOT / "verification/tests/gap75.ld",
             shared.LLVM / "clang", shared.LLVM / "llvm-readelf", shared.SPIKE,
             Path(shared.__file__).resolve(), Path(inventory.__file__).resolve(),
             SPIKE_SOURCE / "riscv/csr_init.cc", SPIKE_SOURCE / "riscv/csrs.cc", SPIKE_SOURCE / "riscv/execute.cc"]
    paths += list((ROOT / "verification/ara_verify").glob("*.py"))
    paths += [p for p in (ROOT / "apps/riscv-tests/isa/macros").rglob("*") if p.is_file()]
    for path in paths:
        pins = shared.merge_pins(pins, {str(path): sha(path)})
    shared.check(pins)
    out.mkdir()
    save(out / "target-before.json", targets)
    save(out / "independent-gold.json", dict(observed=expected(), guards=GUARDS, checks=54,
         counter_final_state="MCYCLE=MINSTRET=0 while inhibited; then inhibit=0; no time restoration claim"))
    command = [str(shared.LLVM / "clang"), "--target=riscv64-unknown-elf", "-march=rv64gv_zfh_zvfh",
               "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-O2",
               "-fno-vectorize", "-fno-slp-vectorize", "-ffreestanding", "-DG75_NO_PRINT", "-D__SPIKE__",
               "-DVLEN=1024", "-DNR_LANES=4", "-I" + str(ROOT / "apps/riscv-tests/isa/macros/vector"),
               "-I" + str(ROOT / "apps/riscv-tests/env"), "-I" + str(ROOT / "apps/common"),
               "-fuse-ld=lld", "-nostdlib", "-T" + str(ROOT / "verification/tests/gap75.ld"),
               str(ROOT / "verification/tests/gap75_start.S"), str(APP), "-o", str(out / "input.elf")]
    save(out / "compile-command.json", command)
    try:
        with (out / "compile.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        symbols = {k: shared._elf_symbol(out / "input.elf", shared.LLVM / "llvm-readelf", k) for k in
                   ("tohost", "g75_result", "g75_trap", "num_failed", "trap_fail", "counter_observed", "counter_guards")}
        command = [str(shared.SPIKE), "--isa=" + SPIKE_ISA, "--priv=msu", "--pmpregions=0", "-l",
                   "--log-commits", str(out / "input.elf")]
        save(out / "spike-command.json", command)
        with (out / "spike.stdout").open("x") as stdout, (out / "spike.trace").open("x") as trace:
            subprocess.run(command, stdout=stdout, stderr=trace, check=True, timeout=60)
        validation = validate(shared.parse_spike_commits(out / "spike.trace"), symbols)
        save(out / "spike-validation.json", validation)
        shared.check(pins)
        outputs = {str(p): sha(p) for p in out.iterdir() if p.is_file()}
        save(out / "preflight-manifest.json", dict(status="CSR_COUNTER_MATRIX_PREFLIGHT_PASS_NOT_VCS",
             baseline_tests=738, input_elf=str(out / "input.elf"), input_spike_trace=str(out / "spike.trace"),
             symbols=symbols, pins=pins, output_pins=outputs, validation=validation,
             target_before=str(out / "target-before.json"), measured_raw_increment=None,
             rtl_changed=False, VCS_authorized=False, coverage_admitted=False,
             reference_scope="Explicit Zicntr/Zihpm matches frozen implemented counter CSR capability; no image change"))
        print(json.dumps(dict(output=str(out), seal=sha(out / "preflight-manifest.json"), validation=validation)))
    except Exception as error:
        save(out / "failure.json", dict(status="CSR_COUNTER_MATRIX_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()
