#!/usr/bin/env python3
"""Strict numerical/work adapter for the parent current-RTL campaign."""
import argparse
import math
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
from contract import ORDER, require, read, save, sha, verify, module


def native_sequence(fixture):
    seq = []
    prefixes = fixture["visible_prefixes"]
    for start in range(0, max(prefixes), 64):
        seq += [4 if start == 0 else 5]
        for prefix in prefixes:
            count = min(64, max(0, prefix-start))
            if count:
                seq += [6]*32 + [2]*count
    return seq + [3]


def fields(line, prefix):
    pairs = line[len(prefix):].split()
    require(pairs and all(re.fullmatch(r"[a-z0-9_]+=[0-9]+", p) for p in pairs), "Malformed raw activity")
    result = dict(p.split("=") for p in pairs)
    require(len(result) == len(pairs), "Duplicate activity field")
    return {k:int(v) for k,v in result.items()}


def activity(text, fixture):
    f16 = fixture["kind"] == "f16"
    begin = "EXT_PREFILL_BEGIN" if f16 else "PREFILL_BEGIN"
    end = "EXT_PREFILL_RESULT" if f16 else "PREFILL_RESULT"
    active, trial, records, counts = False, 0, [], []
    sequence = native_sequence(fixture) if f16 else None
    sequence_number = 0
    for line in text.splitlines():
        if line.startswith(begin+" "):
            require(not active and trial < 4, "Nested/extra activity trial")
            require(line == (f"{begin} trial={trial} mode={ORDER[trial]}" if f16 else
                             f"{begin} trial={trial} shared={ORDER[trial]}"), "Activity trial order")
            active, records = True, []
        if line.startswith(("[AKV_PERF] ", "[QBS_PERF] ")):
            require(active, "Native command outside full call")
            prefix = "[AKV_PERF] " if f16 else "[QBS_PERF] "
            require(line.startswith(prefix), "Unrelated engine work")
            row = fields(line,prefix)
            sequence_number += 1
            require(row.get("seq") == sequence_number and row.get("success") == 1 and
                    all(row.get(k) == 0 for k in ("fault","validation_fault","validation_error","read_fault")) and
                    row.get("busy_cycles",0) > 0, "Native command identity/fault/cycles")
            if f16:
                expected = sequence if ORDER[trial] else []
                require(len(records) < len(expected) and row.get("command") == expected[len(records)],
                        "Native FULL/Panel4/PV/REFILL/RELEASE schedule")
                require(row.get("v2_rejected") == 0, "AKV rejection")
            else:
                require(len(records) < 4 and (row.get("m"),row.get("n"),row.get("vlen"),row.get("lanes")) ==
                        (2,17+len(records),1024,4),
                        "Native QBS query/prefix geometry")
            records.append(row)
        if line.startswith(end+" "):
            expected_count = len(sequence) if f16 and ORDER[trial] else 0 if f16 else 4
            require(active and len(records) == expected_count, "Missing/extra native commands")
            counts.append(len(records)); trial += 1; active = False
    require(not active and trial == 4, "Incomplete native work")
    return counts


def check_f16(text, golden, fixture):
    q, first, outputs = fixture["queries"], fixture["first_query"], fixture["outputs"]
    cap = f"EXT_PREFILL_CAP queries={q} first={first} heads=2 kvheads=1 d=128 capacity=256 trials=4 pair_pv=1"
    lines = text.splitlines()
    require(lines.count(cap) == 1 and lines.count("EXT_PREFILL_SUITE_PASS") == 1, "Capability/completion")
    require(len(golden) == outputs*4, "Golden extent")
    expected = struct.unpack("<"+"f"*outputs,golden)
    rows, pending, complete = [], None, False
    for line in lines:
        if line.startswith("EXT_PREFILL_BEGIN "):
            require(pending is None and not complete, "Nested/post-completion trial")
            pending = line
        elif line.startswith("EXT_PREFILL_RESULT "):
            m = re.fullmatch(r"EXT_PREFILL_RESULT trial=([0-3]) mode=([01]) cycles=([1-9][0-9]*) "
                r"fcsr=([0-9]+) vcsr=5 vstart=0 guards=128 inputs=1 errors=0 hex=([0-9a-f]+)",line)
            require(m is not None and len(rows) < 4, "Malformed result")
            trial, mode, cycles, fc = map(int,m.groups()[:4])
            require((trial,mode) == (len(rows),ORDER[len(rows)]) and fc <= 31 and
                    pending == f"EXT_PREFILL_BEGIN trial={trial} mode={mode}", "Trial order/scope/flags")
            pending = None
            require(len(m[5]) == outputs*8, "Complete output hex")
            words = tuple(int(m[5][i:i+8],16) for i in range(0,len(m[5]),8))
            values = struct.unpack("<"+"f"*outputs,struct.pack("<"+"I"*outputs,*words))
            maximum = 0.0
            for y,g in zip(values,expected):
                require(math.isfinite(y) and math.isfinite(g) and abs(y-g) <= .004+.002*abs(g), "Golden mismatch")
                maximum = max(maximum,abs(y-g))
            previous = next((r for r in rows if r["mode"] == mode),None)
            require(previous is None or (words,fc) == (previous["words"],previous["fcsr"]), "Repeat output/flags changed")
            rows.append(dict(trial=trial,mode=mode,cycles=cycles,fcsr=fc,max_abs=maximum,words=words))
        elif line == "EXT_PREFILL_SUITE_PASS":
            require(len(rows) == 4 and pending is None and not complete, "Early completion")
            complete = True
        elif line.startswith("EXT_PREFILL_") and line != cap:
            raise ValueError("Unknown Prefill evidence")
    require(len(rows) == 4 and pending is None and complete, "Incomplete Prefill")
    means = [sum(r["cycles"] for r in rows if r["mode"] == mode)/2 for mode in (0,1)]
    return dict(baseline_cycles=means[0],native_cycles=means[1],speedup=means[0]/means[1],
        outputs_per_trial=outputs,trials=[{k:v for k,v in r.items() if k != "words"} for r in rows],
        scope="Existing Q64/KV64 tiled RVV vs canonical native Prefill; pair PV explicitly enabled; exact captured slice")


def check_quant(text, golden, q4, checker):
    result = checker.check_log(text,golden,q4)
    states = re.findall(r"^EXT_QUANT_STATE trial=([0-3]) vstart=0 inputs=1$",text,re.M)
    require(states == ["0","1","2","3"] and len(re.findall(r"^EXT_QUANT_STATE",text,re.M)) == 4,
            "Missing/invalid quant input or VSTART evidence")
    return result


def successful_log(text):
    terminal = "Core Test *** SUCCESS *** (tohost = 0)"
    require(text.splitlines().count(terminal) == 1 and text.count("Core Test") == 1, "Unique RTL terminal required")
    require(not re.search(r"Fatal:|Error:|Error-|\b(?:FAIL|FAILED|TIMEOUT)\b",text,re.I), "Failure text")
    for line in text.splitlines():
        if re.match(r"\s*UVM_(ERROR|FATAL)\b",line):
            require(re.fullmatch(r"\s*UVM_(ERROR|FATAL)\s*:\s*0\s*",line), "UVM failure")


def main():
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument("--build",type=Path,required=True)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--log",type=Path,required=True)
    p.add_argument("--result",type=Path,required=True)
    a = p.parse_args()
    result = dict(state="FAIL")
    try:
        build = a.build.resolve(strict=True)
        report = read(build/"build.json")
        require(report["state"] == "BUILT_NOT_EXECUTED" and report["sdk_overlays"] == {} and
                report["sdk_commit"] == "dbe2b78817ef45b912444afcb85ad6e01a2be135", "Current archived SDK required")
        require(sha(build/"source-pins.json") == report["source_pins_sha256"], "Pin receipt identity")
        verify(read(build/"source-pins.json")); verify({report["elf"]:report["elf_sha256"]})
        require(a.log.resolve().is_relative_to(a.run.resolve(strict=True)), "Log not inside parent run")
        text = a.log.read_text(errors="strict")
        successful_log(text)
        f = read(build/"inputs/fixture.json")
        completion = "EXT_PREFILL_SUITE_PASS" if f["kind"] == "f16" else "PREFILL_SUITE_PASS"
        require(text.index(completion) < text.index("Core Test"), "Early RTL terminal")
        golden = (build/"inputs/golden.bin").read_bytes()
        if f["kind"] == "f16":
            metrics = check_f16(text,golden,f)
        else:
            old = module(build/"inputs/sdk/verification/akv/quantized_kv/prefill/check_native.py","extensions_checked_quant")
            metrics = check_quant(text,golden,int(f["kind"] == "q4_0"),old)
        metrics["native_records_per_trial"] = activity(text,f)
        metrics["raw_monitor_records"] = [line for line in text.splitlines() if line.startswith(("[PERF]","[LLM_PERF]"))]
        require(metrics["raw_monitor_records"], "Missing full-call monitor records")
        metrics.update(whole_model=False,actual_ggml_dispatch=False,protocol_gate="parent runner separately required",
                       llm_perf_files="Parent collects llm_perf_report_* separately; raw records here are from the log")
        result = dict(state="PASS",metrics=metrics,log_sha256=sha(a.log),elf_sha256=report["elf_sha256"])
    except Exception as exc:
        result["error"] = str(exc)
    save(a.result,result)
    return result["state"] != "PASS"


if __name__ == "__main__":
    raise SystemExit(main())
