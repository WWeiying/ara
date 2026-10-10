"""Scalar-only CSR SATP/MPRV Spike preflight; old-image707 target pins, no EDA."""
import argparse
import json
from pathlib import Path
import subprocess

import build_gap98_preflight as shared
import inventory_csr_707 as inventory

ROOT, OUT, sha, save, require = shared.ROOT, shared.OUT, shared.sha, shared.save, shared.require
NAME = "vgap99_csr_satp_mprv"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
INVENTORY = OUT / "csr-functional-inventory-707-20261006-02.json"
INVENTORY_SEAL = "bb033cb005704f064463070855c8cf1f9b5d5239aadd04da9bc3e6f44a2c12e0"


def expected_observations(status_mask):
    return [value for priv in (0, 0x800) for value in
            (0, 0, 0x20000 | priv, 0x13579bdf2468ace0, 0x13579bdf2468ace0, status_mask)]


def validate(commits, symbols):
    require(not any(c.vector_writes or c.pc == symbols["trap_fail"] for c in commits), "Unexpected vector/trap")
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    terminal = [v for c in commits for a, v in c.memory_accesses if a == symbols["tohost"] and v is not None]
    require(terminal == [1] and writes.get(symbols["g75_result"]) == 14 and
            writes.get(symbols["g75_result"] + 4) == writes.get(symbols["num_failed"]) == 0 and
            all(writes.get(symbols["g75_trap"] + off) == 0 for off in (0, 8, 16)), "Wrong exact software signature")
    # Startup sets FS/VS only; the independent status contract masks MPRV/MPP.
    require([writes.get(symbols["g99_observed"] + 8 * i) for i in range(12)] == expected_observations(0),
            "Wrong96-byte independent CSR/memory oracle")
    satp = [c for c in commits if c.instruction & 127 == 0x73 and c.instruction >> 20 == 0x180]
    changes = [c for c in satp if (c.instruction >> 12) & 7 == 1]
    require(len(satp) == 6 and len(changes) == 2, "Wrong SATP probe population")
    registers = {0: 0}
    inputs, outputs, mprv = [], [], []
    for c in commits:
        insn = c.instruction
        if c in changes:
            value = registers.get((insn >> 15) & 31)
            require(value in ((1 << 60) | 0x12345, (1 << 60) | 0x12346), "Wrong reserved MODE1 write input")
            rd = (insn >> 7) & 31
            require(rd != 0 and c.gpr_writes.get(rd) == 0, "Wrong SATP old-value return")
            inputs.append(value)
        if insn & 127 == 0x73 and insn >> 20 == 0x300 and (insn >> 12) & 7 == 1:
            value = registers.get((insn >> 15) & 31)
            require(value is not None, "Unknown mstatus input")
            if value & 0x20000:
                mprv.append(value & 0x21800)
        registers.update(c.gpr_writes)
    require(inputs == [(1 << 60) | 0x12345, (1 << 60) | 0x12346] and mprv == [0x20000, 0x20800],
            "Missing/reordered SATP or MPRV phases")
    return dict(status="SPIKE_SCALAR_CSR_PREFLIGHT_PASS_NOT_DUT", checks=14, exact_observed_bytes=96,
                satp_writes=2, mprv_phases=2, vector_destination_instructions=0, vector_bytes=0,
                traps=0, measured_raw_increment=None, coverage_admitted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    require(sha(INVENTORY) == INVENTORY_SEAL, "Inventory drift")
    inv = json.loads(INVENTORY.read_bytes())
    require(inv["baseline_tests"] == 707 and inv["condition_branch_mapping_complete"] and
            not inv["native_qualified"], "Wrong diagnostic inventory")
    targets = [r for values in inv["case_targets"].values() for r in values]
    require(len(targets) == 2 and {r["point"]["raw_index"] for r in targets} == {155, 334} and
            all(not r["hit"] and r["metric"] == "cond" for r in targets), "Wrong two zero condition targets")
    pins = shared.merge_pins(inv["pins"], {str(INVENTORY): INVENTORY_SEAL})
    paths = [APP, Path(__file__).resolve(), Path(__file__).with_name("test_build_gap99_preflight.py"),
             ROOT / "verification/tests/gap75_start.S", ROOT / "verification/tests/gap75.ld",
             shared.LLVM / "clang", shared.LLVM / "llvm-readelf", shared.SPIKE,
             Path(shared.__file__).resolve()]
    paths += [p for p in (ROOT / "apps/riscv-tests/isa/macros").rglob("*") if p.is_file()]
    paths += list((ROOT / "verification/ara_verify").glob("*.py"))
    for path in paths:
        pins = shared.merge_pins(pins, {str(path): sha(path)})
    shared.check(pins)
    out.mkdir()
    save(out / "target-before.json", dict(baseline_tests=707, targets=targets, pins=inv["pins"],
                                         measured_raw_increment=None, exclusions_generated=False))
    elf = out / "input.elf"
    command = [str(shared.LLVM / "clang"), "--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh",
               "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-O2",
               "-fno-vectorize", "-fno-slp-vectorize", "-ffreestanding", "-DG75_NO_PRINT", "-D__SPIKE__",
               "-DVLEN=1024", "-DNR_LANES=4", "-I" + str(ROOT / "apps/riscv-tests/isa/macros/vector"),
               "-I" + str(ROOT / "apps/riscv-tests/env"), "-I" + str(ROOT / "apps/common"),
               "-fuse-ld=lld", "-nostdlib", "-T" + str(ROOT / "verification/tests/gap75.ld"),
               str(ROOT / "verification/tests/gap75_start.S"), str(APP), "-o", str(elf)]
    save(out / "compile-command.json", command)
    try:
        with (out / "compile.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        symbols = {key: shared._elf_symbol(elf, shared.LLVM / "llvm-readelf", key) for key in
                   ("tohost", "g75_result", "g75_trap", "num_failed", "trap_fail", "g99_observed")}
        command = [str(shared.SPIKE), "--isa=rv64gcv_zfh_zvfh_zvl1024b", "--priv=msu", "--pmpregions=0",
                   "-l", "--log-commits", str(elf)]
        save(out / "spike-command.json", command)
        with (out / "spike.stdout").open("x") as stdout, (out / "spike.trace").open("x") as trace:
            subprocess.run(command, stdout=stdout, stderr=trace, check=True, timeout=120)
        validation = validate(shared.parse_spike_commits(out / "spike.trace"), symbols)
        save(out / "spike-validation.json", validation)
        shared.check(pins)
        for path in out.iterdir():
            if path.is_file():
                pins = shared.merge_pins(pins, {str(path): sha(path)})
        shared.check(pins)
        save(out / "preflight-manifest.json", dict(status="GAP99_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME,
             baseline_tests=707, checks=14, exact_observed_bytes=96, symbols=symbols, spike_validation=validation,
             pins=pins, input_elf=str(elf), input_spike_trace=str(out / "spike.trace"), target_unhit_count=2,
             target_before=str(out / "target-before.json"), measured_raw_increment=None,
             coverage_admitted=False, rtl_changed=False, new_RTL_signoff=False, exclusions_generated=False))
        print(json.dumps(dict(output=str(out), seal=sha(out / "preflight-manifest.json"), checks=14, targets=2)))
    except Exception as error:
        save(out / "failure.json", dict(status="GAP99_PREFLIGHT_FAILED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()
