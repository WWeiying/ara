"""Compiled-source justification for bare-mode translation-counter semantics."""
import csv
import json
from pathlib import Path

import akv_historical_budget_oracle_717 as oracle
from audit_historical_nonpass_717 import Audit, OUT, ROOT, sha

BUILD_PINS = OUT / "repaired-aligned-build-20260930-01/build-source-pins.json"
BUILD_SHA = "6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b"
TRANSLATION_CSRS = {0x180, 0x280, 0x680}
ANCHORS = {
    "hardware/deps/cva6/core/csr_regfile.sv": [
        "satp_q <= {CVA6Cfg.XLEN{1'b0}};", "vsatp_q <= {CVA6Cfg.XLEN{1'b0}};",
        "assign en_translation_o = (CVA6Cfg.RVS && config_pkg::vm_mode_t'(satp_q.mode) == CVA6Cfg.MODE_SV &&"],
    "hardware/deps/cva6/core/cva6.sv": [
        ".en_translation_o (enable_translation_csr_ex),", ".acc_mmu_en_i (enable_translation_csr_ex),"],
    "hardware/deps/cva6/core/acc_dispatcher.sv": ["assign acc_req_o.acc_mmu_en = acc_mmu_en_i;"],
    "hardware/src/ara.sv": [
        "assign acc_mmu_en = acc_req_i.acc_mmu_en;", "assign acc_mmu_en = '0;",
        "`FF(acc_mmu_en_q, acc_mmu_en, '0, clk_i, rst_ni);",
        ".en_ld_st_translation_i (acc_mmu_en_q"],
    "hardware/src/vlsu/vlsu.sv": [
        ".read_translation_count_o (akv_read_translation_count),",
        "akv_read_range_count, akv_read_translation_count,"],
    "hardware/src/vlsu/akv/akv_engine.sv": [
        ".counters_clear_i (command_fire),", ".translation_count_o (read_translation_count_o),"],
    "hardware/src/vlsu/qbs/qbs_read_engine.sv": [
        "assign translation_complete = plan_state_q == QBS_PLAN_TRANSLATE && en_ld_st_translation_i && (mmu_exception_valid_i || mmu_valid_i);",
        "translation_count_o <= '0;", "if (translation_complete) translation_count_o <= translation_count_o + 1'b1;",
        "if (en_ld_st_translation_i) translated_addr = AxiAddrWidth'(mmu_paddr_i); else translated_addr = AxiAddrWidth'(planner_cursor_q);"]}


def writes_translation_csr(word):
    if word & 127 != 0x73 or word >> 20 not in TRANSLATION_CSRS:
        return False
    funct3, source = (word >> 12) & 7, (word >> 15) & 31
    return funct3 in (1, 5) or (funct3 in (2, 3, 6, 7) and source != 0)


def elf_no_translation_writes(blob):
    layout, code = oracle.elf_layout(blob, 2097152)
    scanned = 0
    for segment in layout["segments"]:
        if not segment["flags"] & 1:
            continue
        pc, end = segment["vaddr"], segment["vaddr"] + segment["file_bytes"]
        while pc < end:
            half = int.from_bytes(code(pc, 2), "little")
            size = 4 if half & 3 == 3 else 2
            word = int.from_bytes(code(pc, size), "little")
            oracle.require(not writes_translation_csr(word), "ELF changes SATP/VSATP/HGATP at " + hex(pc))
            scanned += 1
            pc += size
    return dict(status="PASS", scanned_instructions=scanned, translation_csr_writes=0,
                scope="All executable bytes of this exact ELF; reset SATP/VSATP remain bare")


def source_proof(elf_path):
    a = Audit()
    a.pin(BUILD_PINS, BUILD_SHA)
    build = a.load(BUILD_PINS)
    bindings = []
    for relative, anchors in ANCHORS.items():
        path = ROOT / relative
        a.pin(path, build[str(path)])
        raw = path.read_text()
        compact = " ".join(raw.split())
        for anchor in anchors:
            oracle.require(anchor in compact, "Compiled source anchor missing: " + anchor)
        bindings.append(dict(path=str(path), compiled_source_sha256=build[str(path)], anchors=anchors))
    elf_path = a.pin(elf_path)
    no_writes = elf_no_translation_writes(elf_path.read_bytes())
    differences = []
    for index in range(12):
        old = oracle.skew.expected_perf(index)
        new = oracle.bare_perf.expected_perf(index)
        if index in (0, 7):
            oracle.require("translations" not in old and new["translations"] == 0, "FULL delta changed")
            without = dict(new)
            del without["translations"]
            oracle.require(old == without, "Nontranslation PERF expectations changed")
            differences.append(dict(phase=index + 1, old="FULL translations>=4", new="FULL translations==0"))
        else:
            oracle.require(old == new, "Non-FULL PERF expectations changed")
    for path in (Path(__file__).resolve(), Path(oracle.__file__).resolve(),
                 Path(oracle.skew.__file__).resolve(), Path(oracle.bare_perf.__file__).resolve()):
        a.pin(path)
    proof = dict(status="COMPILED_SOURCE_BOUND_BARE_COUNTER_PROOF_NOT_DUT_PASS", bindings=bindings,
        build_source_manifest_sha256=BUILD_SHA, elf_no_translation_writes=no_writes,
        causal_chain=["SATP/VSATP reset to0; exact ELF has no writes to translation CSRs.",
                      "CVA6 en_translation_o needs SATP.mode==MODE_SV (or VSATP in virtualization); bare modes disable it.",
                      "CVA6 -> acc_dispatcher.acc_req_o.acc_mmu_en -> Ara registered acc_mmu_en_q -> VLSU/AKV/read_engine.en_ld_st_translation_i; OSSupport=false instead forces0.",
                      "Read counter resets at reset/command_fire and increments only translation_complete, which explicitly requires translation enable.",
                      "Bare path uses planner_cursor_q as physical address, still requires physical-range checking and AXI reads; translation counter stays0.",
                      "AKV_PERF translations prints that read_engine translation counter, not range count or successful read count."],
        old_new_differences=differences, unchanged="12 PERF records, schema/field uniqueness, all other expected fields; FULL ar>=4/r_beats>=28/outstanding_max>0; full original3237 checks/trap/CSR/phase/trace remain.",
        measured_zero_used_as_only_justification=False,
        applicability="Only these exact original bare-mode ELFs and compiled image; no translated-mode waiver",
        fresh_runtime_gate="Reject any retired write to SATP/VSATP/HGATP in the new complete trace before original full oracle verification")
    return proof, a.pins


def verify(case, output, blob, ram_bytes):
    elf_no_translation_writes(blob)
    with (Path(output) / "commit_trace.csv").open() as stream:
        for row in csv.DictReader(stream):
            if row["event"] == "retire":
                oracle.require(not writes_translation_csr(int(row["insn"], 16)), "Runtime translation CSR write")
    proof = oracle.verify(case, output, blob, ram_bytes)
    proof["runtime_translation_csr_writes"] = 0
    proof["translation_counter_gate"] = "Source-qualified bare-mode translations==0, not a measured-value relaxation"
    return proof
