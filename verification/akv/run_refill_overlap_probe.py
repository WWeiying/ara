#!/usr/bin/env python3
"""Bounded existing-image baseline; no build, RTL change, or overlap speedup claim.

Run this foreground worker under systemd (KillMode=control-group). It waits for
its simulator, kills the process group on timeout, and never detaches a worker.
Monitor semantics: arch_start.order is arch_seq at FIRST PRESENTATION, not
command fire; uop events use that arch_seq. retire.order is a separate namespace.
An architectural instruction may allocate multiple backend uops (reshuffles).
The final completion is max(uop_done) for that order, not a reused VID lookup.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_SIMV = ROOT / "verification/out/qbs-context-projection-soc-20261023-01/build/sim/simv"
DEFAULT_BUILD = HERE / "refill_overlap_probe/build-gnu-02"
SEALED_ELF = "9f95541228e9c158059acba2bc516c49d59e6f824fd19023a3eee46ff372281f"
FMA, REFILL, FULL, LOAD, RELEASE, INFO = (
    0xb3481457, 0x02a0605b, 0x00b5605b, 0x0205345b, 0x0000505b, 0x0005455b)
MODES = ("immediate", "serial")
COMMANDS = [4] + [2] * 7 + [5] + [2] * 17 + [3]
OPCODES = {4: FULL, 2: LOAD, 5: REFILL, 3: RELEASE}
EXPECTED = dict(commands=54, v2_full=2, v2_refill=2, load=48, v2_row_load=48,
                release=2, q_external_bytes=512, kv_external_bytes=73728,
                replay_bytes=12288, read_ranges=292, read_payload_bytes=74368)
COUNTERS = ("busy_cycles full refill load release v2_full v2_refill v2_row_load "
            "v2_column_load v2_column_panel v2_logical_column v2_k_view_bank_cycles "
            "v2_bank_conflict_cycles v2_rejected q_external_bytes kv_external_bytes "
            "replay_bytes replay_backpressure_cycles read_ranges translations ar "
            "r_beats read_payload_bytes store_wait_cycles read_backpressure_cycles "
            "read_outstanding_occ_sum read_outstanding_max read_outstanding_full_cycles").split()
PERF_FIELDS = ("seq id command success fault validation_fault validation_error "
               "read_fault context_ready").split() + COUNTERS
SUMMARY_FIELDS = ("records success_records fault_records validation_fault_records").split() + COUNTERS
COMMIT_HEADER = ("cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,"
                 "mem_rmask,mem_wmask,mem_wdata,trap").split(",")
VECTOR_HEADER = ("cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,"
                 "addr,be,wdata,nr_lanes,vlen_bits").split(",")
HEX_FIELDS = {"pc", "insn", "rd_wdata", "mem_addr", "mem_rmask", "mem_wmask",
              "mem_wdata", "be", "wdata"}
PC = {"immediate": dict(first=0x8000022c, refill=0x8000026c),
      "serial": dict(first=0x800002ec, refill=0x80000330)}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fields(text, expected):
    result = {}
    for token in text.split():
        require(token.count("=") == 1, "malformed key/value token")
        key, value = token.split("=")
        require(key not in result and value != "", "duplicate/empty field: " + key)
        result[key] = value
    require(set(result) == set(expected),
            f"missing/extra fields: {set(result) ^ set(expected)}")
    return result


def decimal(value):
    require(re.fullmatch(r"[0-9]+", value) is not None, "unknown/non-decimal field: " + value)
    return int(value)


def numeric_fields(text, expected):
    return {k: decimal(v) for k, v in fields(text, expected).items()}


def check_perf(record, command, seq):
    expected = dict(seq=seq, command=command, success=1, fault=0, validation_fault=0,
                    validation_error=0, read_fault=0, context_ready=int(command != 3),
                    full=0, refill=0, load=int(command == 2), release=int(command == 3),
                    v2_full=int(command == 4), v2_refill=int(command == 5),
                    v2_row_load=int(command == 2), v2_column_load=0, v2_column_panel=0,
                    v2_logical_column=0, v2_k_view_bank_cycles=0,
                    v2_bank_conflict_cycles=0, v2_rejected=0,
                    q_external_bytes=256 if command == 4 else 0,
                    kv_external_bytes={4: 32768, 5: 4096}.get(command, 0),
                    replay_bytes=256 if command == 2 else 0,
                    read_ranges={4: 130, 5: 16}.get(command, 0),
                    read_payload_bytes={4: 33088, 5: 4096}.get(command, 0))
    require(all(record[k] == v for k, v in expected.items()),
            f"AKV command {seq} geometry/count/outcome mismatch")
    require(record["id"] < 8 and record["busy_cycles"] > 0, "invalid VID/busy_cycles")
    require(record["read_outstanding_max"] <= 2, "reader outstanding bound")
    if command in (4, 5):
        require(record["ar"] >= record["read_ranges"] and
                record["r_beats"] >= record["ar"] and
                record["read_outstanding_max"] > 0, "missing fill read traffic")
    else:
        require(all(record[k] == 0 for k in ("ar", "r_beats", "translations",
                    "read_outstanding_max", "read_outstanding_occ_sum")),
                "local command performed external reads")


def check_log(text):
    require(text.count("Core Test *** SUCCESS") == 1, "missing/duplicate core success")
    require(not re.search(r"Fatal:|Error:|\bUVM_(?:ERROR|FATAL)\b(?!\s*:\s*0\s*$)",
                          text, re.M), "simulator error/fatal")
    require("[QBS_PERF]" not in text, "unexpected QBS execution")
    expected_tags = ["CAPS", "EXPECT", "BEGIN", "CYCLES", "PASS",
                     "BEGIN", "CYCLES", "PASS", "SUITE_PASS"]
    seen, perf, summaries, cycles = [], [], [], {}
    mode = None
    mode_commands = 0
    for line in text.splitlines():
        if "[AKV_PERF]" in line:
            require(line.startswith("[AKV_PERF] "), "malformed PERF line")
            require(mode is not None and seen[-1] == "BEGIN" and mode_commands < 27,
                    "command outside mode or excess command")
            record = numeric_fields(line[len("[AKV_PERF] "):], PERF_FIELDS)
            check_perf(record, COMMANDS[mode_commands], len(perf) + 1)
            mode_commands += 1
            perf.append(record)
        elif "[AKV_PERF_SUMMARY]" in line:
            require(line.startswith("[AKV_PERF_SUMMARY] "), "malformed summary")
            summaries.append(numeric_fields(line[len("[AKV_PERF_SUMMARY] "):], SUMMARY_FIELDS))
        elif "AKV_REFILL_PROBE_" in line:
            require(line.startswith("AKV_REFILL_PROBE_"), "embedded program marker")
            marker, sep, body = line.partition(" ")
            tag = marker.removeprefix("AKV_REFILL_PROBE_")
            require(sep and len(seen) < len(expected_tags) and
                    tag == expected_tags[len(seen)], "unexpected/missing/duplicate program marker")
            if tag == "CAPS":
                caps = fields(body, ("word0", "word1", "word2", "word3"))
                require(all(re.fullmatch(r"[0-9a-f]{16}", v) for v in caps.values()),
                        "unknown capability bits")
                caps = {k: int(v, 16) for k, v in caps.items()}
                require(caps["word0"] == (1 | 1 << 8 | 64 << 16 | 8 << 24 |
                        8 << 32 | 1 << 40 | 15 << 48) and
                        caps["word1"] == (0x5b | 2 << 8 | 3 << 11 | 4 << 14 | 5 << 17 | 6 << 20)
                        and caps["word2"] & ((1 << 38) - 1) ==
                        (2 | 64 << 8 | 8 << 16 | 6 << 24 | 63 << 32) and
                        caps["word3"] == (0x5b | 6 << 8 | 7 << 11 | 128 << 16 | 1 << 24),
                        "capability mismatch")
            elif tag == "EXPECT":
                require(numeric_fields(body, EXPECTED) == EXPECTED, "program expectation mismatch")
            elif tag == "BEGIN":
                mode = MODES[len(cycles)]
                expected = dict(mode=mode, d="128", q_rows="1", kv_length="72",
                                tile_start="64", tile_count="8", fmas="16", elements="128")
                require(fields(body, expected) == expected, "mode/shape mismatch")
                mode_commands = 0
            elif tag == "CYCLES":
                require(mode_commands == 27, "incomplete mode command sequence")
                record = fields(body, ("mode", "start", "returned", "drained", "to_return", "to_drain"))
                require(record.pop("mode") == mode, "cycle mode mismatch")
                values = {k: decimal(v) for k, v in record.items()}
                require(0 < values["start"] < values["returned"] < values["drained"] and
                        values["to_return"] == values["returned"] - values["start"] and
                        values["to_drain"] == values["drained"] - values["start"],
                        "invalid cycle markers/deltas")
                if cycles:
                    require(values["start"] > cycles["immediate"]["drained"], "mode cycle regression")
                cycles[mode] = values
            elif tag == "PASS":
                expected = dict(mode=mode, arithmetic="128", fflags="8", vstart="0",
                                q_rows="2", k_rows="11", v_rows="11", canaries="2", traps="0")
                require(fields(body, expected) == expected, "data/state checks did not pass")
                mode = None
            else:
                require(fields(body, ("modes", "traps")) == dict(modes="2", traps="0"),
                        "bad suite summary")
            seen.append(tag)
    require(seen == expected_tags and len(perf) == 54 and len(summaries) == 1,
            "incomplete/extra program or hardware records")
    totals = {k: (max(r[k] for r in perf) if k == "read_outstanding_max" else
                  sum(r[k] for r in perf)) for k in COUNTERS}
    totals.update(records=54, success_records=54, fault_records=0, validation_fault_records=0)
    require(summaries[0] == totals, "PERF summary disagrees with per-command accounting")
    require(all(totals[k] == v for k, v in EXPECTED.items() if k != "commands"),
            "wrong aggregate work")
    return dict(software_cycles=cycles, hardware_totals=totals)


def csv_records(stream, header, allowed):
    reader = csv.DictReader(stream)
    require(reader.fieldnames == header, "missing/extra/reordered CSV columns")
    last_cycle = -1
    for row in reader:
        require(set(row) == set(header) and all(v is not None for v in row.values()),
                "malformed CSV row width")
        require(row["event"] in allowed, "unknown CSV event: " + row["event"])
        result = {"event": row["event"]}
        for key, value in row.items():
            if key == "event":
                continue
            pattern = r"[0-9a-fA-F]+" if key in HEX_FIELDS else r"-?[0-9]+"
            require(re.fullmatch(pattern, value) is not None, "unknown CSV field: " + key)
            result[key] = int(value, 16 if key in HEX_FIELDS else 10)
            require(result[key] >= ( -1 if key in ("order", "port", "trans_id") else 0),
                    "negative CSV field: " + key)
        require(result["cycle"] >= last_cycle, "CSV cycle regression/reset")
        last_cycle = result["cycle"]
        yield result


def check_traces(commit_stream, vector_stream):
    starts, groups, live, events, retired = {}, {}, {}, [], []
    front = None
    retired_order = -1
    for r in csv_records(commit_stream, COMMIT_HEADER,
                         {"arch_start", "uop_alloc", "uop_done", "retire", "cvx_req", "cvx_resp"}):
        event, order, vid = r["event"], r["order"], r["port"]
        require(r["trap"] == 0, "commit trace exception")
        if event == "arch_start":
            require(front is None and order == len(starts) and r["trans_id"] >= 0,
                    "duplicate/missing arch order or frontend overlap")
            starts[order] = r
            groups[order] = []
            front = r
        elif event == "cvx_req":
            require(front is not None and r["trans_id"] == front["trans_id"] and
                    r["insn"] == front["insn"], "request without matching arch_start")
            front = None
        elif event in ("uop_alloc", "uop_done"):
            require(order in starts and r["insn"] == starts[order]["insn"] and
                    r["trans_id"] == starts[order]["trans_id"] and 0 <= vid < 8,
                    "uop arch metadata mismatch")
            if event == "uop_alloc":
                require(vid not in live, "VID reused before completion")
                live[vid] = r
            else:
                require(vid in live and live[vid]["order"] == order and
                        r["cycle"] >= live[vid]["cycle"], "orphan/misjoined uop completion")
                groups[order].append((live.pop(vid)["cycle"], r["cycle"]))
            events.append((r["cycle"], event.removeprefix("uop_"), order, vid, r["insn"]))
        elif event == "retire":
            require(order == retired_order + 1, "missing/duplicate retire order")
            retired_order = order
            if r["insn"] in (FMA, REFILL):
                retired.append((r["insn"], r["pc"]))
    require(front is None and not live, "unfinished frontend/backend trace")
    vector_events, configs = [], 0
    for r in csv_records(vector_stream, VECTOR_HEADER, {"config", "alloc", "done", "write"}):
        require(r["nr_lanes"] == 4 and r["vlen_bits"] == 1024, "vector trace geometry")
        if r["event"] == "config":
            configs += 1
            require(r["cycle"] == 0 and configs == 1 and not vector_events,
                    "duplicate/misplaced vector config")
        else:
            require(configs == 1 and r["vid"] < 8 and r["arch_seq"] in starts and
                    r["insn"] == starts[r["arch_seq"]]["insn"], "vector metadata mismatch")
            if r["event"] in ("alloc", "done"):
                vector_events.append((r["cycle"], r["event"], r["arch_seq"], r["vid"], r["insn"]))
    require(configs == 1 and events and vector_events == events, "commit/vector uop trace mismatch")
    ordered = list(starts.values())
    custom = [r["insn"] for r in ordered if r["insn"] & 0x7f == 0x5b]
    require(custom == [INFO] * 4 + [OPCODES[c] for c in COMMANDS * 2],
            "trace custom command sequence differs from program")
    require(all(groups[r["order"]] for r in ordered if r["insn"] in OPCODES.values()),
            "AKV command has no backend completion")
    require(sum(r["insn"] == FMA for r in ordered) == 32, "missing/extra FMA architecture starts")
    expected_retired = []
    for mode in MODES:
        expected_retired.extend((FMA, PC[mode]["first"] + i * 4) for i in range(16))
        expected_retired.append((REFILL, PC[mode]["refill"]))
    require(retired == expected_retired, "retired PC sequence differs from sealed assembly")
    refills = [r for r in ordered if r["insn"] == REFILL]
    results = {}
    for mode, refill in zip(MODES, refills):
        stop = refill["order"]
        if mode == "serial":
            require(ordered[stop - 1]["insn"] == 0x0c82f057, "serial LMUL drain missing")
            stop -= 1
        chain = ordered[stop - 16:stop]
        require(len(chain) == 16 and all(r["insn"] == FMA for r in chain),
                "FMA/refill adjacency window differs")
        require(all(groups[r["order"]] for r in chain + [refill]), "missing measured uop completion")
        done = [max(end for _, end in groups[r["order"]]) for r in chain]
        last_done = max(done)
        present = refill["cycle"]
        results[mode] = dict(refill_arch_order=refill["order"],
            refill_present_cycle=present, arithmetic_last_done_cycle=last_done,
            remaining_arithmetic_cycles=max(0, last_done - present),
            arithmetic_instructions_remaining=sum(cycle > present for cycle in done),
            refill_backend_first_alloc_cycle=min(a for a, _ in groups[refill["order"]]),
            refill_backend_last_done_cycle=max(b for _, b in groups[refill["order"]]),
            fma_arch_orders=[r["order"] for r in chain],
            fma_uop_counts=[len(groups[r["order"]]) for r in chain])
    return dict(modes=results, backend_events=len(events),
                interpretation="arch_start is first presentation, NOT command_fire; "
                "remaining arithmetic is an opportunity bound, NOT measured overlap or speedup")


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def hashes(paths):
    return {str(p): digest(p) for p in sorted(set(Path(p).resolve(strict=True) for p in paths))}


def write_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


def validate_build(build):
    report = json.loads((build / "build.json").read_text())
    elf = build / "akv_refill_overlap_probe.elf"
    require(digest(elf) == report["elf_sha256"] == SEALED_ELF, "not the sealed build-gnu-02 ELF")
    require(report["expected_akv_commands"] == 54 and report["simulation_l2_mb"] == 16 and
            report["required_vlen"] == 1024 and report["disassembly_checks"] == "PASS",
            "build receipt geometry/check mismatch")
    require(report["input_hashes"] == json.loads((build / "inputs-before.json").read_text()) ==
            json.loads((build / "inputs-after.json").read_text()) == hashes(report["input_hashes"]),
            "build input/provenance drift")
    require(digest(Path(report["compiler"])) == report["compiler_sha256"], "compiler provenance drift")
    for mode in MODES:
        require(report["marker_pcs"][mode]["fma_first"] == PC[mode]["first"] and
                report["marker_pcs"][mode]["refill"] == PC[mode]["refill"], "marker PC provenance")
    return elf, report


def inventory(simv, build):
    libraries = sorted(Path(str(simv) + ".daidir").rglob("*.so"))
    require(os.access(simv, os.X_OK) and libraries, "incomplete executable image")
    config = {}
    for line in (simv.parent / "simulator.conf").read_text().splitlines():
        key, value = line.split("=", 1)
        require(key not in config, "duplicate image config key")
        config[key] = value
    require(all(config.get(k) == v for k, v in dict(nr_lanes="4", vlen="1024",
            akv_enabled="1", akv_v2_enabled="1", sim_l2_mb="16",
            sim_l2_bytes="16777216", verify_axi_delay="0").items()), "image configuration mismatch")
    manifest_path = simv.parent / "vcs_source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    require(manifest["schema_version"] == 1, "manifest version")
    elf, report = validate_build(build)
    paths = [simv, simv.parent / "simulator.conf", manifest_path, *libraries,
             *[Path(r["path"]) for r in manifest["files"]],
             *map(Path, report["input_hashes"]), Path(report["compiler"]),
             *[p for p in build.rglob("*") if p.is_file()], Path(__file__),
             HERE / "test_refill_overlap_probe.py",
             *sorted((ROOT / "verification/ara_verify").glob("*.py"))]
    return hashes(paths), elf


def run(args):
    require(1 <= args.timeout <= 2700, "timeout must be 1..2700 seconds")
    simv, build = args.simv.resolve(strict=True), args.build.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    work = out / "work"
    work.mkdir()
    state = dict(state="preflight", pid=os.getpid(), simv=str(simv), build=str(build),
                 timeout_seconds=args.timeout, started=datetime.now(timezone.utc).isoformat())
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "verification"))
    pins = None
    def save():
        write_json(out / "status.json", state)
    def manifest_check(stage):
        command = [sys.executable, "-B", "-m", "ara_verify.vcs_source_manifest", "--output",
                   str(simv.parent / "vcs_source_manifest.json"), "--check"]
        with (out / ("manifest-" + stage + ".log")).open("x") as log:
            subprocess.run(command, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=120)
    save()
    try:
        manifest_check("before")
        pins, elf = inventory(simv, build)
        shutil.copytree(build, out / "build-provenance")
        for source in (Path(__file__), HERE / "test_refill_overlap_probe.py",
                       HERE / "refill_overlap_probe/main.c", HERE / "refill_overlap_probe/probe.S",
                       HERE / "refill_overlap_probe/build.py"):
            shutil.copy2(source, out / source.name)
        shutil.copy2(elf, work / "input.elf")
        snapshots = hashes(p for p in out.rglob("*") if p.is_file() and
                           p.name not in ("status.json", "manifest-before.log"))
        pins.update(snapshots)
        write_json(out / "pins-before.json", pins)
        args_list = [str(simv), "-no_save", "-l", str(work / "run.vcs.log"),
                     "+PRELOAD=" + str(work / "input.elf"), "+TESTCASE=akv_refill_overlap_probe",
                     "+NO_FSDB", "+AKV_PERF", "+AKV_SUMMARY",
                     "+COMMIT_TRACE=" + str(work / "commit_trace.csv"),
                     "+VECTOR_TRACE=" + str(work / "vector_trace.csv"),
                     "+ARA_CONTRACT_TRACE_LIMIT=100000", "+ARA_UVM_TRACE_LIMIT=100000"]
        write_json(out / "command.json", dict(argv=args_list, cwd=str(work)))
        require(hashes(pins) == pins, "pre-launch pin drift")
        with (work / "console.log").open("x") as console:
            process = subprocess.Popen(args_list, cwd=work, env=env, stdout=console,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            state.update(state="running", child_pid=process.pid)
            save()
            try:
                rc = process.wait(timeout=args.timeout)
            except BaseException:
                # Process group is for bounded cleanup, not escape from systemd.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=10)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass
                finally:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                raise
        state.update(state="checking", child_pid=None, simulator_exit_code=rc)
        save()
        require(rc == 0, f"simulator exit {rc}")
        result = check_log((work / "run.vcs.log").read_text())
        with (work / "commit_trace.csv").open(newline="") as commit, \
                (work / "vector_trace.csv").open(newline="") as vector:
            result["trace"] = check_traces(commit, vector)
        command = [sys.executable, "-B", "-m", "ara_verify.uvm_dut", "--require-events",
                   "--require-backend", "--require-axi", "--require-axi-write", "--vector-trace",
                   str(work / "vector_trace.csv"), "--log", str(work / "run.vcs.log"),
                   "--simv", str(simv), "--elf", str(work / "input.elf"),
                   "--output", str(out / "uvm_result.json")]
        with (out / "uvm-check.log").open("x") as log:
            subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=120)
        require(json.loads((out / "uvm_result.json").read_text())["status"] == "PASS",
                "UVM checker did not pass")
        write_json(out / "result.json", dict(state="CHECKED_PENDING_PINS", **result))
        state["state"] = "checked"
    except BaseException as error:
        state.update(state="FAIL", error=repr(error))
    finally:
        if pins is not None:
            try:
                manifest_check("after")
                fresh, _ = inventory(simv, build)
                require(set(fresh) == set(pins) - set(snapshots), "input inventory changed")
                after = hashes(pins)
                write_json(out / "pins-after.json", after)
                require(after == pins, "source/image/ELF/checker drift")
                require(json.loads((out / "pins-before.json").read_text()) == pins,
                        "pin receipt changed")
                if state["state"] == "checked":
                    result = json.loads((out / "result.json").read_text())
                    result["state"] = "PASS"
                    write_json(out / "result.json", result)
                    state["state"] = "PASS"
            except BaseException as error:
                state.update(state="FAIL", pin_error=repr(error))
        state["finished"] = datetime.now(timezone.utc).isoformat()
        save()
        write_json(out / "artifact-hashes.json", hashes(p for p in out.rglob("*") if
                   p.is_file() and p.name != "artifact-hashes.json"))
    print(json.dumps(state, sort_keys=True), flush=True)
    return 0 if state["state"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simv", type=Path, default=DEFAULT_SIMV)
    parser.add_argument("--build", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=2700)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
