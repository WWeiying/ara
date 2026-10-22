#!/usr/bin/env python3
"""One frozen AXI64/reg32/PLIC integration build/run, or --prepare-only (no VCS).

Scope: exported bridge/decode/demux/error slave and selected generated PLIC.
No CPU, AXI interconnect/atomics, UART, Linux, FPGA timing, or board signoff.
AXI 64/48/2 and request cut=1 match board DefaultCfg; ID width=4 is TB-local.
PLIC oracle: https://raw.githubusercontent.com/riscv/riscv-plic-spec/master/riscv-plic.adoc
Errors/holes and WARL masks additionally follow the generated register contract.
Expected legacy failure is evidence only: status remains FAIL and exit code 1.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import signal

from run_qbs_read_contract import (
    changed_sources, command_run, now, prepare_output, save_json, sha256,
)


ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "hardware/fpga/ara_dsa_vcu118/rtl"
TB = ROOT / "verification/fpga/plic_contract_tb.sv"
MAX_CYCLES = 8192
BASE = 0x04000000
SOURCE_IDS = (1, 31, 32, 51, 52, 57)
CASES = (
    "physical_decode", "word_lanes", "reserved_holes", "source_context_matrix",
    "priority_threshold", "competition_completion", "read_side_effect",
)
EXPECTS = (
    "ie_zero_context0", "ie_zero_context1", "disabled_context_completion",
    "threshold_read_claimed", "threshold_read_pending",
)
EXPECTED_VALUES = dict(zip(EXPECTS, (0xfffffffe, 0xfffffffe, 1, 0, 6)))
SHAPE = dict(src=58, targets=2, prio_width=3, block_aw=26)
LEGACY_SHAPE = dict(src=32, targets=1, prio_width=3, block_aw=27)
MMIO_OVERRIDES = ("axi/src/axi_to_detailed_mem.sv", "register_interface/src/axi_to_reg_v2.sv")
# Each row specifies the discriminating observation, not a DUT-derived oracle.
PROBE_PLAN = {
    "sampling": "every rising edge, clocking input #1step; all cycles including reset",
    "bound": MAX_CYCLES,
    "physical_decode": "txn0 AW=04000004 -> regaddr unchanged -> paddr4/hit -> OKAY; legacy miss/SLVERR",
    "word_lanes": "AW/AR size, W strb/data -> reg address/byte enables -> stable B/R under >=4 stalls",
    "reserved_holes": "IE bit0=0, upper IE mask03ffffff; invalid/partial writes error without state change",
    "source_context_matrix": "2 contexts x 6 IDs: synced source/IP -> IRQ/claim -> IA -> complete -> repend",
    "priority_threshold": "priority strictly above threshold gates IRQ, not claim; tied priority chooses lower ID",
    "competition_completion": "S IE57=0, M claimed held57: S complete must leave IA57=1/IP57=0/IRQ=0",
    "read_side_effect": "AR=04200000 size2: no claim_re and IP1/IRQ remain set; extra CC reg read proves over-read",
    "recovery": "IE violations clear enables; reset after reserved, completion and final read-side-effect groups",
}

# Explicit dependency closure. Never compile dependency worktrees or regenerate IP.
EXPORT_SOURCES = (
    "common_cells/src/cf_math_pkg.sv", "axi/src/axi_pkg.sv", "axi/src/axi_intf.sv",
    "register_interface/src/reg_intf.sv",
    *[f"common_cells/src/{name}.sv" for name in (
        "sync", "lzc", "rr_arb_tree", "stream_arbiter_flushable", "stream_arbiter",
        "fifo_v3", "stream_fifo", "stream_mux", "stream_fork", "stream_fork_dynamic",
        "stream_join_dynamic", "stream_join", "spill_register_flushable", "spill_register",
        "addr_decode_dync", "addr_decode",
    )],
    *[f"register_interface/src/{name}.sv" for name in (
        "reg_demux", "reg_mux", "reg_err_slv", "periph_to_reg",
    )],
    "axi/src/axi_to_detailed_mem.sv", "register_interface/src/axi_to_reg_v2.sv",
    *[f"register_interface/vendor/lowrisc_opentitan/src/{name}.sv" for name in (
        "prim_subreg_arb", "prim_subreg", "prim_subreg_ext",
    )],
    "opentitan_peripherals/src/prim/prim_pulp_platform/prim_flop_2sync.sv",
    "opentitan_peripherals/src/prim/rtl/prim_max_tree.sv",
)
PLIC_SOURCES = tuple(f"rtl/{name}.sv" for name in (
    "rv_plic_reg_pkg", "rv_plic_reg_top", "rv_plic_gateway", "rv_plic_target", "rv_plic",
))
INCLUDES = ("common_cells/include", "axi/include", "register_interface/include")
HEADERS = (
    "common_cells/include/common_cells/assertions.svh",
    "common_cells/include/common_cells/registers.svh",
    "axi/include/axi/typedef.svh", "axi/include/axi/assign.svh",
    "register_interface/include/register_interface/typedef.svh",
    "register_interface/include/register_interface/assign.svh",
)
ERROR = re.compile(
    r"(?:^|\n)\s*(?:Fatal\b|Error\b|UVM_FATAL\b|UVM_ERROR\b|PLIC_FAIL\b)|"
    r"\bassert(?:ion)?\b[^\n]*(?:fail|error)|\$fatal", re.I,
)
FIELDS = set((
    "cycle time_ns rst txn case awv awr awaddr awid awsize wv wr wd ws wl bv br bid bresp "
    "arv arr araddr arid arsize rv rr rid rresp rd rl regv regr regw regaddr regwd regbe "
    "regrd regerr sel decvalid decerr pvalid paddr hit miss wrerr src synced ip ia ie prio "
    "threshold claim_re claim_id claim complete_we complete_id complete irq irq_id msip"
).split())


def fields(text):
    pairs = [part.split("=", 1) for part in text.split()]
    if any(len(pair) != 2 for pair in pairs) or len({p[0] for p in pairs}) != len(pairs):
        raise ValueError("malformed/duplicate log fields")
    return dict(pairs)


def package_shape(text):
    result = {}
    for key, param in (("src", "NumSrc"), ("targets", "NumTarget"),
                       ("prio_width", "PrioWidth"), ("block_aw", "BlockAw")):
        values = re.findall(rf"\bparameter\s+int\s+(?:unsigned\s+)?{param}\s*=\s*(\d+)\s*;", text)
        if len(values) != 1:
            raise ValueError(f"missing/ambiguous literal package parameter {param}")
        result[key] = int(values[0])
    return result


def snapshot(plic_dir, output, export=EXPORT, tb=TB, mmio_dir=None):
    entries = [(f"export/{name}",
                (mmio_dir if mmio_dir is not None and name in MMIO_OVERRIDES else export) / name)
               for name in EXPORT_SOURCES + HEADERS]
    entries += [(f"plic/{name}", plic_dir / name) for name in PLIC_SOURCES]
    entries += [("tb/plic_contract_tb.sv", tb), ("host/run_plic_contract.py", Path(__file__)),
                ("host/run_qbs_read_contract.py", ROOT / "verification/run_qbs_read_contract.py")]
    records = {}
    for name, source in entries:
        content = source.read_bytes()
        frozen = output / "inputs" / name
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_bytes(content)
        records[name] = dict(path=str(source.resolve()), frozen=str(frozen),
                             sha256=hashlib.sha256(content).hexdigest())
    return records


def compile_command(output, vcs):
    inputs = output / "inputs"
    sources = [inputs / "export" / name for name in EXPORT_SOURCES]
    sources += [inputs / "plic" / name for name in PLIC_SOURCES]
    sources += [inputs / "tb/plic_contract_tb.sv"]
    return [str(vcs), "-full64", "-sverilog", "-timescale=1ns/1ps", "+lint=TFIPC-L",
            *[f"+incdir+{inputs / 'export' / name}" for name in INCLUDES],
            *map(str, sources), "-top", "plic_contract_tb", "-o",
            str(output / "build/simv"), "-l", "compile.log"]


def parse_console(text, shape):
    errors, records = [], defaultdict(list)
    if ERROR.search(text):
        errors.append("simulator error/fatal/assertion failure")
    for line in text.splitlines():
        if line.startswith("PLIC_"):
            tag, _, payload = line.partition(" ")
            if tag not in {"PLIC_CONFIG", "PLIC_TX_BEGIN", "PLIC_TX_END", "PLIC_CASE",
                           "PLIC_SOURCE", "PLIC_EXPECT", "PLIC_RESET", "PLIC_RESULT", "PLIC_FAIL"}:
                raise ValueError(f"unknown marker {tag}")
            records[tag].append(fields(payload))
    config = {**shape, "axi_data": 64, "axi_addr": 48, "cut": 1}
    if records["PLIC_CONFIG"] != [{k: str(v) for k, v in config.items()}]:
        errors.append("missing/duplicate/wrong config")
    if [v.get("name") for v in records["PLIC_CASE"]] != list(CASES):
        errors.append("missing/duplicate/out-of-order case")
    if any(v.get("status") != "PASS" or v.get("failures") != "0" for v in records["PLIC_CASE"]):
        errors.append("functional case failure")
    matrix = Counter((v.get("id"), v.get("context"), v.get("status")) for v in records["PLIC_SOURCE"])
    if matrix != Counter((str(s), str(t), "PASS") for t in range(2) for s in SOURCE_IDS):
        errors.append("source/context matrix incomplete or duplicated")
    observations = records["PLIC_EXPECT"]
    if Counter(v.get("code") for v in observations) != Counter(EXPECTS):
        errors.append("missing/duplicate functional observation")
    for v in observations:
        if (v.get("status") != "PASS" or int(v["actual"], 16) != int(v["expected"], 16) or
                int(v["expected"], 16) != EXPECTED_VALUES.get(v["code"])):
            errors.append(f"contract violation: {v['code']} cycle={v['cycle']} actual={v['actual']} expected={v['expected']}")
    if [v.get("case") for v in records["PLIC_RESET"]] != [
            "reserved_holes", "competition_completion", "read_side_effect"]:
        errors.append("missing/duplicate recovery boundary")
    starts, ends = records["PLIC_TX_BEGIN"], records["PLIC_TX_END"]
    if not starts or [int(v["txn"]) for v in starts] != list(range(len(starts))):
        errors.append("transaction begin sequence")
    if [int(v["txn"]) for v in ends] != list(range(len(starts))):
        errors.append("incomplete/duplicate transaction end sequence")
    if starts and (int(starts[0]["addr"], 16) != BASE + 4 or starts[0]["write"] != "1"):
        errors.append("first access is not physical priority1 write")
    for begin, end in zip(starts, ends):
        if end["resp"] != begin["expected"]:
            errors.append(f"wrong response txn={begin['txn']}")
    results = records["PLIC_RESULT"]
    if len(results) != 1:
        errors.append("missing/duplicate result")
    else:
        v = results[0]
        if (v.get("status") != "PASS" or v.get("failures") != "0" or
                int(v["cases"]) != len(CASES) or int(v["transactions"]) != len(ends) or
                len(ends) < 300 or int(v["checks"]) < len(ends) * 8 or
                not 0 < int(v["cycles"]) < MAX_CYCLES):
            errors.append("invalid/nonpassing suite totals")
    return records, errors


def check_probe(text, records):
    lines = text.splitlines()
    header = f"# PLIC_PROBE schema=1 sample=pre_edge max_cycles={MAX_CYCLES}"
    if not lines or lines[0] != header or not lines[-1].startswith("# END "):
        raise ValueError("missing probe header/end")
    end = fields(lines[-1][6:])
    rows = [fields(line) for line in lines[1:-1]]
    if not rows or len(rows) > MAX_CYCLES or int(end["rows"]) != len(rows):
        raise ValueError("invalid probe row count/bound")
    errors, events, stalls = [], defaultdict(Counter), defaultdict(Counter)
    starts = records["PLIC_TX_BEGIN"]
    ends = records["PLIC_TX_END"]
    controls = "rst awv awr wv wr wl bv br arv arr rv rr rl regv regr regw regerr sel decvalid decerr pvalid miss wrerr".split()
    for index, row in enumerate(rows):
        if set(row) != FIELDS or int(row["cycle"]) != index:
            raise ValueError(f"probe schema/cycle gap at row {index}")
        if abs(float(row["time_ns"]) - (5 + 10 * index)) > 0.001:
            raise ValueError(f"probe time mismatch at row {index}")
        if row["rst"] == "0":
            continue
        if any(row[k] not in ("0", "1") for k in controls):
            raise ValueError(f"unknown control at cycle {index}")
        if int(row["ip"], 16) & 1 or int(row["src"], 16) & 1 or int(row["msip"], 16):
            errors.append(f"source0/MSIP invariant at cycle {index}")
        int(row["irq"], 16)  # Reject X on active IRQ even if no AXI handshake.
        txn = int(row["txn"])
        for channel, valid, ready in (("aw", "awv", "awr"), ("w", "wv", "wr"),
                                      ("b", "bv", "br"), ("ar", "arv", "arr"), ("r", "rv", "rr")):
            if row[valid] != "1":
                continue
            if txn < 0 or txn >= len(starts):
                raise ValueError(f"unowned AXI valid cycle={index}")
            if row[ready] == "0":
                stalls[txn][channel] += 1
                continue
            events[txn][channel] += 1
            begin = starts[txn]
            if channel in ("aw", "ar"):
                if (int(row[channel + "addr"], 16) != int(begin["addr"], 16) or
                        int(row[channel + "size"], 16) != int(begin["size"]) or
                        int(row[channel + "id"], 16) != txn % 16):
                    errors.append(f"AXI request mismatch cycle={index}")
            elif channel == "w":
                if (int(row["wd"], 16) != int(begin["data"], 16) or
                        int(row["ws"], 16) != int(begin["strb"], 16) or row["wl"] != "1"):
                    errors.append(f"W payload mismatch cycle={index}")
            else:
                if row[channel + "resp"] != begin["expected"] or int(row[channel + "id"], 16) != txn % 16:
                    errors.append(f"AXI response mismatch cycle={index}")
                if channel == "r" and (row["rl"] != "1" or txn >= len(ends) or
                                       int(row["rd"], 16) != int(ends[txn]["data"], 16)):
                    errors.append(f"R payload mismatch cycle={index}")
    for txn, begin in enumerate(starts):
        write = begin["write"] == "1"
        if events[txn] != Counter({"aw": 1, "w": 1, "b": 1} if write else {"ar": 1, "r": 1}):
            errors.append(f"handshake count txn={txn}: {dict(events[txn])}")
        if stalls[txn]["b" if write else "r"] < 4:
            errors.append(f"backpressure missing txn={txn}")
    result = records["PLIC_RESULT"]
    if (end["completed"] != "1" or len(result) != 1 or
            any(end[k] != result[0][k] for k in ("transactions", "checks")) or
            len(result) == 1 and int(result[0]["cycles"]) != len(rows)):
        errors.append("incomplete/inconsistent probe trailer")
    legacy_first = any(row["txn"] == "0" and row["regv"] == "1" and
                       row["regw"] == "1" and int(row["regaddr"], 16) == BASE + 4 and
                       row["pvalid"] == "1" and row["miss"] == "1" and row["regerr"] == "1"
                       for row in rows)
    return dict(rows=len(rows), transactions=len(starts), legacy_first_address_miss=legacy_first), errors


def analyze(console, probe, shape):
    report = {"errors": [], "probe": {}, "observations": [], "first_failure": None}
    try:
        records, errors = parse_console(console, shape)
        report["errors"].extend(errors)
        report["observations"] = records["PLIC_EXPECT"]
        failures = records["PLIC_FAIL"] + [r for r in records["PLIC_EXPECT"] if r["status"] != "PASS"]
        report["first_failure"] = min(failures, key=lambda v: int(v["cycle"])) if failures else None
        report["probe"], errors = check_probe(probe, records)
        report["errors"].extend(errors)
    except (ValueError, KeyError, IndexError) as error:
        report["errors"].append(f"malformed/incomplete evidence: {error}")
    return report


def run(plic_dir, output, vcs="vcs", *, prepare_only=False, expect_legacy_failure=False,
        compile_timeout=240, run_timeout=60, mmio_dir=None):
    if any(output.resolve().is_relative_to(source.resolve()) for source in (plic_dir, EXPORT)):
        raise ValueError("output must not be inside a source IP/export directory")
    output = prepare_output(output)
    report = dict(schema_version=1, status="FAIL", started_at=now(), errors=[],
                  scope=__doc__, expected_legacy_failure=expect_legacy_failure, probe_plan=PROBE_PLAN)
    save_json(output / "summary.json", report)
    records, interrupted = {}, None
    try:
        records = snapshot(plic_dir.resolve(), output, mmio_dir=mmio_dir)
        report["sources"] = records
        save_json(output / "sources.json", records)
        shape = package_shape((output / "inputs/plic/rtl/rv_plic_reg_pkg.sv").read_text())
        report["shape"] = shape
        if shape != (LEGACY_SHAPE if expect_legacy_failure else SHAPE):
            raise ValueError(f"unexpected PLIC shape {shape}")
        command = compile_command(output, vcs)
        save_json(output / "compile_command.json", command)
        save_json(output / "probe_plan.json", PROBE_PLAN)
        if prepare_only:
            report["status"] = "NOT_RUN"
        else:
            executable = shutil.which(str(vcs))
            if not executable:
                raise ValueError(f"VCS executable not found: {vcs}")
            command[0] = executable
            build = output / "build"
            report["compile"] = command_run(command, build, compile_timeout)
            compile_text = (build / "console.log").read_text(errors="replace")
            report["compile_warnings"] = re.findall(r"^Warning-\[([^]]+)\]", compile_text, re.M)
            if report["compile"]["status"] != "PASS" or ERROR.search(compile_text):
                raise ValueError("compile failed; no simulation started")
            binary = build / "simv"
            report["simv_sha256"] = sha256(binary)
            directory = output / "run"
            report["simulation"] = command_run([str(binary), "-l", "run.log"], directory, run_timeout)
            if report["simulation"]["status"] != "PASS":
                report["errors"].append(f"simulation status {report['simulation']['status']}")
            probe = directory / "plic_signals.log"
            if probe.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("probe exceeds bounded log size")
            report["probe_sha256"] = sha256(probe)
            report["analysis"] = analyze((directory / "console.log").read_text(errors="replace"),
                                         probe.read_text(errors="replace"), shape)
            report["errors"].extend(report["analysis"]["errors"])
            if expect_legacy_failure:
                failure = report["analysis"]["first_failure"] or {}
                report["legacy_failure_observed"] = (
                    report["analysis"]["probe"].get("legacy_first_address_miss", False) and
                    failure.get("code") == "axi_response" and failure.get("txn") == "0")
                report["errors"].append("legacy negative control is not a passing DUT")
            report["status"] = "FAIL" if report["errors"] else "PASS"
    except (OSError, ValueError) as error:
        report["errors"].append(str(error))
    except (KeyboardInterrupt, SystemExit) as error:
        interrupted = error
        report["errors"].append(f"interrupted: {type(error).__name__}")
    finally:
        if records:
            try:
                drift = changed_sources(records)
                frozen_drift = [name for name, entry in records.items()
                                if sha256(entry["frozen"]) != entry["sha256"]]
                if drift or frozen_drift:
                    report["errors"].append(f"source drift: live={drift}, frozen={frozen_drift}")
            except OSError as error:
                report["errors"].append(str(error))
        if report["errors"]:
            report["status"] = "FAIL"
        report["completed_at"] = now()
        save_json(output / "summary.json", report)
    if interrupted is not None:
        raise interrupted
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plic-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vcs", default="vcs")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--expect-legacy-failure", action="store_true")
    parser.add_argument("--mmio-dir", type=Path,
                        help="isolated overrides for the two AXI/MMIO source files; others use export")
    args = parser.parse_args()

    def terminate(signum, _frame):
        raise SystemExit(128 + signum)

    old_term = signal.signal(signal.SIGTERM, terminate)
    try:
        try:
            report = run(args.plic_dir, args.output, args.vcs, prepare_only=args.prepare_only,
                         expect_legacy_failure=args.expect_legacy_failure, mmio_dir=args.mmio_dir)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    finally:
        signal.signal(signal.SIGTERM, old_term)
    print(json.dumps({"status": report["status"], "output": str(args.output.resolve()),
                      "errors": report["errors"]}, indent=2))
    return int(report["status"] not in ("PASS", "NOT_RUN"))


if __name__ == "__main__":
    raise SystemExit(main())
