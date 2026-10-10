#!/usr/bin/env python3
"""Frozen AXI64/reg32 side-effect bridge regression. No CPU/SoC/PLIC signoff.

Only two RTL overrides come from --mmio-dir (export-relative paths); everything
else comes from the current FPGA export. Point --mmio-dir at the export itself
for a baseline negative diagnostic: semantic failures remain FAIL/exit 1.
--prepare-only snapshots and audits inputs without invoking any EDA tool.
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

from run_plic_contract import EXPORT, EXPORT_SOURCES, HEADERS, INCLUDES, ROOT
from run_qbs_read_contract import changed_sources, command_run, now, prepare_output, save_json, sha256


TB = ROOT / "verification/fpga/mmio_read_contract_tb.sv"
OVERRIDES = ("axi/src/axi_to_detailed_mem.sv", "register_interface/src/axi_to_reg_v2.sv")
UNUSED = {"common_cells/src/sync.sv", "common_cells/src/addr_decode.sv",
          "common_cells/src/addr_decode_dync.sv", "register_interface/src/reg_intf.sv",
          "register_interface/src/reg_err_slv.sv"}
SOURCES = tuple(s for s in EXPORT_SOURCES if s not in UNUSED and
                "/vendor/" not in s and not s.startswith("opentitan_peripherals/"))
CASES = ("size_lanes", "queued_reads", "mixed_channels", "incr_bursts", "error_mapping")
TOTALS = dict(ar=65, r=74, aw=6, w=6, b=6, regs=91)
MAX_CYCLES = 4096
BASE = 0x04000000
ERROR = re.compile(r"(?:^|\n)\s*(?:Fatal\b|Error\b|UVM_FATAL\b|UVM_ERROR\b|MMIO_FAIL\b)|"
                   r"\bassert(?:ion)?\b[^\n]*(?:fail|error)|\$fatal", re.I)
PROBE_PLAN = {
    "sample": "posedge pre-edge (#1step), all cycles including reset, max4096",
    "ownership": "AXI handshake sequence + beat index, never reg_id (bank0 forwarding is not reg-mux ownership)",
    "request_mask": "accepted AR byte interval -> expected 32-bit bank addresses/strobes; no extra reg accesses",
    "metadata": "queued/held AR and independent AW/W -> selected meta -> meta buffer -> m2s -> banks -> cuts -> reg",
    "error_mask": "selected invalid bank => SLVERR; invalid suppressed neighbor => OKAY; offsets0/4/8/12/48/52/56/60",
    "side_effects": "independent per-word read counters and byte-writable storage versus AXI-derived shadow",
    "responses": "ID, RLAST, valid data bytes, RRESP/BRESP and stable held responses",
    "recovery": "semantic mismatches accumulate FAIL; drain/reset per group; X/timeout/identity/protocol are fatal",
    "queue_scope": "BufDepth1; require subsequent AR presented while prior R stalls, not unsupported >=2 accepted ARs",
    "excludes": "CPU, full SoC, PLIC, board, atomics, WRAP/FIXED bursts, write bursts and default non-MMIO mode",
}
FIELDS = set((
    "cycle rst case awv awr awaddr awid awsize awlen wv wr wd ws wl bv br bid bresp "
    "arv arr araddr arid arsize arlen rv rr rid rresp rd rl arbv arbr meta_addr meta_size "
    "meta_strb meta_write meta_id meta_last metav metar bufv bufr buf_addr buf_size buf_strb "
    "buf_write buf_id buf_last memv memr mem_addr mem_strb mem_write mem_id mempv mempr "
    "bankv bankr bank_addr bank_strb bank_write bank_id bankpv bankerr bankrd cutv cutr "
    "cut_addr cut_strb cut_write active0 active1 zero0 zero1 regv regr regaddr regw regbe "
    "regwd regerr regrd regid rleft wleft busy model_reads model_writes response_banks error_profile"
).split())


def fields(text):
    pairs = [s.split("=", 1) for s in text.split()]
    if any(len(p) != 2 for p in pairs) or len({p[0] for p in pairs}) != len(pairs):
        raise ValueError("malformed/duplicate fields")
    return dict(pairs)


def read_beats(address, size, length):
    """Independent byte-address enumeration, not the RTL shift-based mask."""
    if size not in range(4) or length not in range(256):
        raise ValueError("unsupported AXI read shape")
    width = 2 ** size
    aligned = address - address % width
    result = []
    for beat in range(length + 1):
        start = address if beat == 0 else aligned + beat * width
        stop = aligned + (beat + 1) * width
        lanes = sum(1 << (byte % 8) for byte in range(start, stop))
        banks = [(start - start % 8 + 4 * b, (lanes >> (4 * b)) & 15)
                 for b in range(2) if lanes & (15 << (4 * b))]
        result.append(dict(address=start, lanes=lanes, banks=banks, last=int(beat == length)))
    return result


def mapped(address, profile):
    bad = {BASE + 0x34, BASE + 0x38}
    if profile == 1:
        bad.update((BASE + 4, BASE + 12))
    elif profile == 2:
        bad.add(BASE + 8)
    return BASE <= address < BASE + 512 and address not in bad


def snapshot(mmio_dir, output, export=EXPORT, tb=TB):
    entries = [(f"rtl/{s}", (mmio_dir if s in OVERRIDES else export) / s) for s in SOURCES + HEADERS]
    entries += [("tb/mmio_read_contract_tb.sv", tb)]
    entries += [(f"host/{s}", ROOT / "verification" / s) for s in
                ("run_mmio_read_contract.py", "run_plic_contract.py", "run_qbs_read_contract.py")]
    records = {}
    for name, source in entries:
        content = source.read_bytes()
        target = output / "inputs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        records[name] = dict(path=str(source.resolve()), frozen=str(target),
                             sha256=hashlib.sha256(content).hexdigest())
    return records


def compile_command(output, vcs):
    return [str(vcs), "-full64", "-sverilog", "-timescale=1ns/1ps", "+lint=TFIPC-L",
            *[f"+incdir+{output / 'inputs/rtl' / s}" for s in INCLUDES],
            *[str(output / "inputs/rtl" / s) for s in SOURCES],
            str(output / "inputs/tb/mmio_read_contract_tb.sv"),
            "-top", "mmio_read_contract_tb", "-o", str(output / "build/simv"), "-l", "compile.log"]


def analyze(console, probe):
    report = dict(errors=[], mismatches=[], counts={}, complete=False)
    errors = report["errors"]
    try:
        if ERROR.search(console):
            errors.append("simulator error/fatal/assertion failure")
        markers = defaultdict(list)
        known = {"CONFIG", "AR", "AW", "W", "EXPECT_R", "EXPECT_B", "MATCH", "EXTRA",
                 "R", "B", "MISMATCH", "FAIL", "CASE", "RESET", "RESULT"}
        for line in console.splitlines():
            if line.startswith("MMIO_"):
                tag, _, text = line.partition(" ")
                tag = tag[5:]
                if tag not in known:
                    raise ValueError(f"unknown marker {tag}")
                markers[tag].append(fields(text))
        report["mismatches"] = markers["MISMATCH"] + markers["FAIL"]
        if report["mismatches"]:
            errors.append(f"TB reported {len(report['mismatches'])} mismatches/failures")
        if markers["CONFIG"] != [dict(axi_data="64", axi_addr="48", axi_id="4", axi_user="2", reg_data="32", cut="1")]:
            errors.append("missing/duplicate/wrong config")
        if [v.get("name") for v in markers["CASE"]] != list(CASES):
            errors.append("missing/duplicate/out-of-order case")
        if any(v.get("status") != "PASS" or v.get("failures") != "0" for v in markers["CASE"]):
            errors.append("nonpassing case")
        if [v.get("case") for v in markers["RESET"]] != list(CASES):
            errors.append("missing/duplicate reset boundary")
        lines = probe.splitlines()
        if (not lines or lines[0] != f"# MMIO_PROBE schema=1 sample=pre_edge max_cycles={MAX_CYCLES}" or
                not lines[-1].startswith("# END ")):
            raise ValueError("probe header/trailer missing")
        trailer = fields(lines[-1][6:])
        rows = [fields(line) for line in lines[1:-1]]
        if not rows or len(rows) > MAX_CYCLES or int(trailer["rows"]) != len(rows):
            raise ValueError("probe bounds/count")
        counts = Counter()
        requests, responses, aw, wd, bs = [], [], [], [], []
        expected_regs, actual_regs = Counter(), Counter()
        stalled = Counter()
        last_held = {}
        for index, row in enumerate(rows):
            if set(row) != FIELDS or int(row["cycle"]) != index:
                raise ValueError(f"probe schema/cycle gap at {index}")
            if row["rst"] == "0":
                last_held = {}
                continue
            controls = "rst awv awr wv wr bv br arv arr rv rr regv regr".split()
            if any(row[k] not in ("0", "1") for k in controls):
                raise ValueError(f"X control at {index}")
            for channel, valid, ready, payload in (
                    ("r", "rv", "rr", ("rid", "rresp", "rd", "rl")),
                    ("b", "bv", "br", ("bid", "bresp"))):
                value = tuple(row[k] for k in payload)
                if channel in last_held and (row[valid] != "1" or value != last_held[channel]):
                    errors.append(f"unstable {channel} cycle={index}")
                last_held.pop(channel, None)
                if row[valid] == "1" and row[ready] == "0":
                    last_held[channel] = value
                    stalled[channel] += 1
            stalled["reg"] += row["regv"] == "1" and row["regr"] == "0"
            stalled["queued_ar"] += row["arv"] == "1" and row["arr"] == "0" and row["rv"] == "1" and row["rr"] == "0"
            stalled["held_w_reads"] += row["wv"] == "1" and row["wr"] == "0" and row["arv"] == "1" and row["arr"] == "1"
            if row["arv"] == row["arr"] == "1":
                counts["ar"] += 1
                for beat in read_beats(int(row["araddr"], 16), int(row["arsize"], 16), int(row["arlen"], 16)):
                    response = 0 if all(mapped(a, int(row["error_profile"])) for a, _ in beat["banks"]) else 2
                    requests.append((int(row["arid"], 16), beat["last"], response, beat))
                    expected_regs.update((row["case"], 0, a, be) for a, be in beat["banks"])
            if row["awv"] == row["awr"] == "1":
                counts["aw"] += 1
                aw.append((int(row["awaddr"], 16), int(row["awid"], 16), row["case"], int(row["error_profile"])))
            if row["wv"] == row["wr"] == "1":
                counts["w"] += 1
                wd.append(int(row["ws"], 16))
            if row["rv"] == row["rr"] == "1":
                counts["r"] += 1
                responses.append((int(row["rid"], 16), int(row["rl"], 2), int(row["rresp"], 2)))
            if row["bv"] == row["br"] == "1":
                counts["b"] += 1
                bs.append((int(row["bid"], 16), int(row["bresp"], 2)))
            if row["regv"] == row["regr"] == "1":
                counts["regs"] += 1
                actual_regs[(row["case"], int(row["regw"], 2), int(row["regaddr"], 16), int(row["regbe"], 16))] += 1
        expected_bs = []
        for (address, id_, case, profile), strobes in zip(aw, wd):
            banks = [(address-address % 8 + b*4, (strobes >> (4*b)) & 15)
                     for b in range(2) if strobes & (15 << (4*b))]
            expected_regs.update((case, 1, a, be) for a, be in banks)
            expected_bs.append((id_, 0 if all(mapped(a, profile) for a, _ in banks) else 2))
        if responses != [r[:3] for r in requests] or bs != expected_bs:
            errors.append("AXI ID/RLAST/response sequence differs from accepted requests")
        if actual_regs != expected_regs:
            errors.append("register address/mask multiset differs from accepted AXI requests")
            report["extra_registers"] = [list(k) + [v] for k, v in (actual_regs-expected_regs).items()]
            report["missing_registers"] = [list(k) + [v] for k, v in (expected_regs-actual_regs).items()]
        for tag, key in (("AR", "ar"), ("AW", "aw"), ("W", "w"), ("R", "r"), ("B", "b")):
            label = "beat" if tag in ("R", "B") else "seq"
            if [int(v[label]) for v in markers[tag]] != list(range(counts[key])):
                errors.append(f"{tag} marker/raw count or sequence mismatch")
        if len(markers["EXPECT_R"]) != len(requests) or len(markers["EXPECT_B"]) != len(aw):
            errors.append("expected-beat marker count")
        for index, (mark, request) in enumerate(zip(markers["EXPECT_R"], requests)):
            id_, last, response, beat = request
            if (int(mark["beat"]) != index or int(mark["id"], 16) != id_ or
                    int(mark["addr"], 16) != beat["address"] or int(mark["lanes"], 16) != beat["lanes"] or
                    int(mark["last"], 2) != last or int(mark["resp"], 2) != response):
                errors.append(f"TB read oracle marker mismatch beat={index}")
        report["counts"] = dict(counts)
        if dict(counts) != TOTALS:
            errors.append(f"suite totals differ: {dict(counts)}")
        results = markers["RESULT"]
        if len(results) != 1:
            errors.append("missing/duplicate result")
        else:
            result = results[0]
            report["complete"] = trailer["completed"] == "1" and int(result["cycles"]) == len(rows)
            if result["status"] != "PASS" or result["failures"] != "0" or result["cases"] != "5":
                errors.append("nonpassing result")
            if not report["complete"] or int(result["checks"]) <= 0 or trailer["checks"] != result["checks"]:
                errors.append("incomplete/inconsistent trailer")
            if any(int(result[k]) != counts[k] or int(trailer[k]) != counts[k] for k in TOTALS):
                errors.append("result/trailer/raw count mismatch")
            for label, key in (("r_stalls", "r"), ("b_stalls", "b"), ("reg_stalls", "reg"),
                               ("queued_ar", "queued_ar"), ("held_w_reads", "held_w_reads")):
                if int(result[label]) != stalled[key] or stalled[key] <= 0:
                    errors.append(f"missing/inconsistent traffic coverage {label}")
            if result["bursts"] != "4" or result["unaligned"] != "18":
                errors.append("burst/unaligned coverage")
    except (ValueError, KeyError, IndexError) as error:
        errors.append(f"malformed/incomplete evidence: {error}")
    return report


def run(mmio_dir, output, vcs="vcs", *, prepare_only=False):
    if any(output.resolve().is_relative_to(p.resolve()) for p in (mmio_dir, EXPORT)):
        raise ValueError("output must not be inside an input source directory")
    output = prepare_output(output)
    report = dict(schema_version=1, status="FAIL", started_at=now(), scope=__doc__,
                  probe_plan=PROBE_PLAN, expected_totals=TOTALS, errors=[])
    save_json(output / "summary.json", report)
    records, interrupted = {}, None
    try:
        records = snapshot(mmio_dir.resolve(), output)
        report["sources"] = records
        save_json(output / "sources.json", records)
        save_json(output / "probe_plan.json", PROBE_PLAN)
        command = compile_command(output, vcs)
        save_json(output / "compile_command.json", command)
        if prepare_only:
            report["status"] = "NOT_RUN"
        else:
            executable = shutil.which(str(vcs))
            if not executable:
                raise ValueError(f"VCS executable not found: {vcs}")
            command[0] = executable
            build = output / "build"
            report["compile"] = command_run(command, build, 240)
            text = (build / "console.log").read_text(errors="replace")
            report["compile_warnings"] = re.findall(r"^Warning-\[([^]]+)\]", text, re.M)
            if report["compile"]["status"] != "PASS" or ERROR.search(text):
                raise ValueError("compile failed; no simulation launched")
            report["simv_sha256"] = sha256(build / "simv")
            directory = output / "run"
            report["simulation"] = command_run([str(build / "simv"), "-l", "run.log"], directory, 60)
            if report["simulation"]["status"] != "PASS":
                report["errors"].append(f"simulation status {report['simulation']['status']}")
            probe = directory / "mmio_signals.log"
            if probe.stat().st_size > 32*1024*1024:
                raise ValueError("probe exceeds size bound")
            report["probe_sha256"] = sha256(probe)
            report["analysis"] = analyze((directory / "console.log").read_text(errors="replace"), probe.read_text())
            report["errors"].extend(report["analysis"]["errors"])
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
                frozen_drift = [k for k, v in records.items() if sha256(v["frozen"]) != v["sha256"]]
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
    parser.add_argument("--mmio-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vcs", default="vcs")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    def terminate(signum, _frame):
        raise SystemExit(128 + signum)

    old_term = signal.signal(signal.SIGTERM, terminate)
    try:
        try:
            report = run(args.mmio_dir, args.output, args.vcs, prepare_only=args.prepare_only)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    finally:
        signal.signal(signal.SIGTERM, old_term)
    print(json.dumps({"status": report["status"], "output": str(args.output.resolve()), "errors": report["errors"]}, indent=2))
    return int(report["status"] not in ("PASS", "NOT_RUN"))


if __name__ == "__main__":
    raise SystemExit(main())
