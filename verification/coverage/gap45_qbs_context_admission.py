#!/usr/bin/env python3
"""Case-local QBS context admission. Host precheck is never a DUT PASS."""
import gzip
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import coverage_evidence as evidence

full = evidence.full
require = full.require
ROOT = full.ROOT
NAME = "qbs_gap45_context"
SCHEMA = "qbs-gap45-context-v1"
SCRIPT = Path(__file__).resolve()
NATIVE_PRECHECK = evidence.precheck
ACCESS = [1, 2, 2, 2, 3, 2, 1, 3]
ERRORS = [0, 19, 0, 20, 0, 18, 0, 0]


def validate_log(text, host=False):
    require(not re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b|Error:|Fatal:)", text), "failure in log")
    expected = f"PASSED: {NAME} checks={172 if host else 198} errors=0"
    require([s for s in text.splitlines() if s.startswith("PASSED:")] == [expected], "PASS/cardinality differs")
    summary = f"G45_CONTEXT operations=8 vrf_words=8192 source_words=1272 flag_samples={0 if host else 8}"
    require([s for s in text.splitlines() if s.startswith("G45_CONTEXT")] == [summary], "sample cardinality differs")
    return dict(checks=172 if host else 198, operations=8, vrf_words=8192, source_words=1272,
                flag_samples=0 if host else 8, host_reference_only=host)


def perf_records(text):
    rows = []
    for line in text.splitlines():
        if not line.startswith("[QBS_PERF]"):
            continue
        require(line.startswith("[QBS_PERF] "), "bad PERF prefix")
        row = {}
        for token in line[len("[QBS_PERF] "):].split():
            require(re.fullmatch(r"[a-z][a-z0-9_]*=[0-9]+", token), "malformed PERF field")
            key, value = token.split("=")
            require(key not in row, "duplicate PERF key")
            row[key] = int(value)
        rows.append(row)
    require(len(rows) == 8, "need exactly eight QBS_PERF terminal records")
    for i, (r, access, error) in enumerate(zip(rows, ACCESS, ERRORS), 1):
        fill, reuse, fault = access == 1, error == 0 and access in (2, 3), error != 0
        expected = dict(seq=i, m=1, n=1, vlen=1024, lanes=4, activation_access=access,
                        success=int(not fault), fault=int(fault), validation_fault=int(fault),
                        validation_error=error, read_fault=0,
                        context_fill_count=int(fill), context_reuse_count=int(reuse),
                        context_reuse_block_count=int(reuse), context_read_bytes=292 if reuse else 0,
                        activation_axi_bytes_saved=292 if reuse else 0,
                        context_validation_fault_count=int(fault),
                        payload_bytes=16 if fault else 452 if fill else 160,
                        read_ranges=1 if fault else 3 if fill else 2)
        require(all(r.get(k) == v for k, v in expected.items()), f"PERF identity/outcome differs at step {i}")
        require("id" in r and r.get("busy_cycles", 0) > 0, "missing command identity/cycles")
        require(r.get("commit_groups") == 0 if fault else r.get("commit_groups", 0) > 0,
                "fault committed or success has no commit")
    return rows


def elf_audit(metadata, blob):
    symbols = {r["Symbol"]["Name"]["Name"]: r["Symbol"] for r in metadata["Symbols"]}
    def code(address, size):
        for row in metadata["Sections"]:
            s = row["Section"]
            if s["Flags"]["Value"] & 4 and s["Address"] <= address and address + size <= s["Address"] + s["Size"]:
                start = s["Offset"] + address - s["Address"]
                return blob[start:start + size]
        raise ValueError("PC outside executable section")
    pc = symbols["qbs_gap45_site"]["Value"]
    expected = [0x00b5045b, 0x001022f3, 0x00573023, 0x008022f3, 0x00573423]
    require(code(pc, 20) == b"".join(w.to_bytes(4, "little") for w in expected), "opcode/early CSR capture differs")
    issue = symbols["issue"]
    body = code(issue["Value"], issue["Size"])
    require(issue["Value"] <= pc < issue["Value"] + issue["Size"], "foreign custom PC")
    require(sum(body[i:i + 4] == bytes.fromhex("5b04b500") for i in range(0, len(body) - 3, 2)) == 1, "ambiguous opcode")
    transfers = {"loads": [], "stores": []}
    cursor = 0
    while cursor < len(body):
        half = int.from_bytes(body[cursor:cursor + 2], "little")
        size = 4 if half & 3 == 3 else 2
        word = int.from_bytes(body[cursor:cursor + size], "little")
        if size == 4 and (word >> 12) & 7 == 6 and word & 0x7f in (7, 39):
            transfers["loads" if word & 0x7f == 7 else "stores"].append((word >> 7) & 31)
        cursor += size
    require(transfers == {"loads": [0, 8, 16, 24], "stores": [0, 8, 16, 24]}, "incomplete VRF capture")
    vector_setup = bytes.fromhex("9302001057f03201")
    require(body.count(vector_setup) == 2, "VRF capture is not VL256/e32/m8 twice")
    start = symbols["_start"]["Value"]
    reset = code(start, symbols["trap_vector"]["Value"] - start)
    mret = reset.find(bytes.fromhex("73002030"))
    require(mret >= 0, "CRT has no MRET")
    hook = symbols["rvtest_init"]["Value"]
    matches = []
    for pos in range(0, mret - 11, 2):
        a, b, c = [int.from_bytes(reset[pos + n:pos + n + 4], "little") for n in (0, 4, 8)]
        if a & 0xfff != 0x297 or b & 0xfffff != 0x28293:
            continue
        hi, lo = a & 0xfffff000, b >> 20
        hi -= (1 << 32) if hi & 0x80000000 else 0
        lo -= (1 << 12) if lo & 0x800 else 0
        if start + pos + hi + lo == hook:
            # Frozen CRT checks the weak symbol before its compressed call.
            require(c == 0x00028363 and reset[pos + 12:pos + 14] == bytes.fromhex("8292"),
                    "hook is not followed by BEQ t0,zero,+6 and C.JALR t0")
            require(pos + 14 <= mret, "hook call is not before MRET")
            matches.append(start + pos + 12)
    require(len(matches) == 1, "CRT M-mode hook binding differs")
    return dict(status="PASS", custom_pc=hex(pc), opcode="0x00b5045b", early_csr_capture=True,
                vrf_transfers=transfers, hook_pc=hex(hook), hook_call_pc=hex(matches[0]),
                hook_before_mret=True, runtime_instruction_executed=False)


def precheck(item, proof):
    require(item["name"] == "app:" + NAME and item["timeout_s"] == 600, "case/budget differs")
    path = Path(item["precheck"]["record"])
    record = proof.read(path)
    require(record["schema"] == SCHEMA and record["host_checks"] == 172 and record["dut_checks"] == 198, "contract schema differs")
    seal = proof.read(path.parent / "seal.json")
    required = {str(path.parent / n) for n in ("selection.json", "checked-precheck.json", "artifact-hashes.json")}
    require(set(seal) == required, "seal manifest set differs")
    proof.hashes(seal)
    selection = proof.read(path.parent / "selection.json")
    require(selection["cases"] == [item], "case differs from exact sealed selection")
    proof.hashes(proof.read(path.parent / "artifact-hashes.json"))
    replay = evidence.Evidence()
    result = NATIVE_PRECHECK(item, replay)
    saved = proof.read(path.parent / "checked-precheck.json")
    require(saved["result"] == result and saved["checked_files"] == replay.files,
            "native precheck replay differs")
    proof.hashes(replay.files)
    require(proof.read(path.parent / "negative-tests.json")["status"] == "PASS", "negative tests not passed")
    validate_log(proof.pin(record["host_log"]).read_text(), host=True)
    metadata = proof.read(record["metadata"])
    require(elf_audit(metadata, proof.pin(item["binary"]).read_bytes()) == record["elf_audit"], "linked ELF audit differs")
    proof.hashes(record["rtl_pins"])
    require(len(record["targets"]) == 8 and all(p["hit_638"] == p["hit_640"] == 0 for p in record["targets"]), "wrong context targets")
    for p in (SCRIPT, path.parent / "checked-precheck.json"):
        proof.pin(p)
    return dict(result, runtime_contract=SCHEMA)


def runtime_proof(output, plan, row):
    case = next(c for c in plan["cases"] if c["name"] == NAME)
    require(case["timeout_s"] == 600, "runtime budget differs")
    selection = full.read(Path(plan["source_selection"]["selection"]))
    item = next(c for c in selection["cases"] if c["name"] == "app:" + NAME)
    record_path = Path(item["precheck"]["record"])
    for path in (record_path, SCRIPT):
        require(str(path) in plan["files"], "unbound runtime checker/input")
        full.check({str(path): plan["files"][str(path)]})
    record = full.read(record_path)
    full.check(record["source_hashes"])
    full.check(record["rtl_pins"])
    full.check({case["frozen_elf"]: record["binary_sha256"]})
    target = output / "results" / NAME
    summary_path = target / "summary.json"
    require(str(summary_path) in row["files"], "unbound summary")
    full.check({str(summary_path): row["files"][str(summary_path)]})
    summary = full.read(summary_path)
    require(len(summary) == 1 and summary[0]["status"] == "PASS", "incomplete functional PASS")
    artifact = Path(summary[0]["artifact_dir"]).resolve(strict=True)
    require(artifact.is_relative_to(target.resolve()), "foreign runtime artifact")
    log = artifact / "work/run.vcs.log"
    require(str(log) in row["files"], "unbound original simulator log")
    full.check({str(log): row["files"][str(log)]})
    command_path = artifact / "work/coverage.command.json"
    require(str(command_path) in row["files"], "unbound actual command")
    full.check({str(command_path): row["files"][str(command_path)]})
    command = full.read(command_path)["command"]
    require(command.count("+QBS_PERF") == 1 and "+TESTCASE=" + NAME in command and command[0] == plan["simv"], "PERF/test/image command identity differs")
    text = log.read_text(errors="strict")
    uart, perf = validate_log(text), perf_records(text)
    hit_points, files = [], full.pins([log, command_path, summary_path, record_path, SCRIPT])
    for metric in ("line", "branch"):
        paths = [Path(p) for p in row["vdb_files"] if p.endswith(f"/{metric}.verilog.data.xml")]
        require(len(paths) == 1 and paths[0].is_relative_to(Path(row["vdb"])), "foreign/ambiguous raw test data")
        path = paths[0]
        full.check({str(path): row["vdb_files"][str(path)]})
        data = path.read_bytes()
        root = ET.fromstring(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)
        nodes = list(root.iter("instance_data"))
        rows = {n.get("name"): n for n in nodes}
        require(len(rows) == len(nodes), "duplicate raw coverage instance")
        for point in record["targets"]:
            if point["metric"] != metric:
                continue
            value = rows[point["scope"]]
            definition = point["definition"]
            bits = value.get("value")
            require(value.get("chksum") == definition["checksum"] and
                    len(bits) == definition["width"] and set(bits) <= {"0", "1"},
                    "coverage identity differs")
            require(bits[point["raw_index"]] == "1", "intended context path not covered")
            hit_points.append(dict(scope=point["scope"], coordinate=point["coordinate"], raw_index=point["raw_index"]))
        files[str(path)] = row["vdb_files"][str(path)]
    require(len(hit_points) == 8, "missing context points")
    return dict(status="PASS", schema=SCHEMA, uart=uart, perf=perf, hit_points=hit_points, files=files,
                exact_opcode_pc=record["elf_audit"]["custom_pc"], dynamic_pc_trace_required=False,
                identity_basis="sealed ELF + exact fault PC selfcheck + eight PERF sequence/shape/mode/error records")
