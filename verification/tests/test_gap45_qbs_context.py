#!/usr/bin/env python3
"""Offline checker mutations and adapter composition tests; never launch a DUT."""
import copy
import json
from pathlib import Path
import sys
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification/coverage"))
sys.path.insert(0, str(ROOT / "verification"))
import gap45_qbs_context_admission as a
import run_gap45_qbs_checked_extension as adapter


def synthetic_perf_rows():
    rows = []
    # Test fixtures only. These are NOT simulator evidence.
    for i, (access, error) in enumerate(zip(a.ACCESS, a.ERRORS), 1):
        fault, fill = error != 0, access == 1
        reuse = not fault and access in (2, 3)
        rows.append(dict(seq=i, id=i % 8, m=1, n=1, vlen=1024, lanes=4,
            activation_access=access, success=int(not fault), fault=int(fault),
            validation_fault=int(fault), validation_error=error, read_fault=0,
            context_fill_count=int(fill), context_reuse_count=int(reuse),
            context_reuse_block_count=int(reuse), context_read_bytes=292 if reuse else 0,
            activation_axi_bytes_saved=292 if reuse else 0,
            context_validation_fault_count=int(fault),
            payload_bytes=16 if fault else 452 if fill else 160,
            read_ranges=1 if fault else 3 if fill else 2, busy_cycles=1,
            commit_groups=0 if fault else 1))
    return rows


def perf_text(rows):
    return "\n".join("[QBS_PERF] " + " ".join(f"{k}={v}" for k, v in r.items()) for r in rows)


def reject(label, action, rejected):
    try:
        action()
    except (ValueError, RuntimeError, KeyError, FileNotFoundError):
        rejected.append(label)
    else:
        raise AssertionError("accepted mutation: " + label)


def run(metadata, blob, host_log, scratch, targets, elf):
    rejected, positive = [], []
    a.validate_log(host_log, host=True)
    good = host_log.replace("checks=172", "checks=198").replace("flag_samples=0", "flag_samples=8")
    a.validate_log(good)
    for label, bad in (("log-count", good.replace("198", "197")),
                       ("log-duplicate", good + good), ("log-failure", good + "\nFAIL test\n"),
                       ("log-vrf-short", good.replace("8192", "8191")),
                       ("log-source-short", good.replace("1272", "1271")),
                       ("log-flags-short", good.replace("flag_samples=8", "flag_samples=7")),
                       ("log-host-is-not-dut", host_log)):
        reject(label, lambda: a.validate_log(bad), rejected)
    rows = synthetic_perf_rows()
    assert a.perf_records(perf_text(rows)) == rows
    positive.append("eight synthetic PERF rows accepted; not RTL evidence")
    for key in rows[0]:
        bad = copy.deepcopy(rows)
        del bad[3][key]
        reject("perf-missing-" + key, lambda: a.perf_records(perf_text(bad)), rejected)
    for index, key, value in ((1, "validation_error", 20), (3, "validation_error", 19),
            (5, "validation_error", 19), (1, "commit_groups", 1),
            (2, "payload_bytes", 452), (2, "activation_axi_bytes_saved", 0),
            (6, "seq", 1), (0, "m", 2), (0, "vlen", 512), (0, "lanes", 8),
            (7, "activation_access", 2), (4, "read_ranges", 3)):
        bad = copy.deepcopy(rows)
        bad[index][key] = value
        reject(f"perf-step{index + 1}-{key}", lambda: a.perf_records(perf_text(bad)), rejected)
    for label, text in (("perf-missing-command", perf_text(rows[:-1])),
                        ("perf-duplicate-command", perf_text(rows + rows[:1])),
                        ("perf-duplicate-key", perf_text(rows) + " seq=8"),
                        ("perf-unknown-bits", perf_text(rows).replace("n=1 ", "n=x ", 1))):
        reject(label, lambda: a.perf_records(text), rejected)
    proof = a.elf_audit(metadata, blob)
    symbols = {r["Symbol"]["Name"]["Name"]: r["Symbol"] for r in metadata["Symbols"]}
    pc = symbols["qbs_gap45_site"]["Value"]
    sec = next(r["Section"] for r in metadata["Sections"]
               if r["Section"]["Address"] <= pc < r["Section"]["Address"] + r["Section"]["Size"])
    offset = pc - sec["Address"] + sec["Offset"]
    for label, delta in (("elf-custom-opcode", 0), ("elf-early-fflags", 4), ("elf-early-vstart", 12)):
        bad = bytearray(blob)
        bad[offset + delta] ^= 0x10
        reject(label, lambda: a.elf_audit(metadata, bad), rejected)
    bad = copy.deepcopy(metadata)
    next(r["Symbol"] for r in bad["Symbols"] if r["Symbol"]["Name"]["Name"] == "rvtest_init")["Value"] += 4
    reject("elf-wrong-hook", lambda: a.elf_audit(bad, blob), rejected)
    positive.append("linked opcode, immediate flags, all VRF groups and pre-MRET hook audited")
    assert json.loads(json.dumps(proof)) == proof
    command = ["never-execute", "+TESTCASE=" + a.NAME, "+NO_FSDB"]
    assert adapter.perf_command(command) == command + ["+QBS_PERF"]
    assert command[-1] == "+NO_FSDB"
    reject("perf-wrong-case", lambda: adapter.perf_command(["+TESTCASE=other"]), rejected)
    reject("perf-duplicate-option", lambda: adapter.perf_command(command + ["+QBS_PERF"]), rejected)

    # Substitute every launcher. Test the same directed hook without starting tools.
    checked, full = adapter.checked, adapter.full
    from ara_verify import runner
    launch = Mock(return_value=(0, 1.0, False, False))
    previous = Mock(return_value="delegated")
    summary = Mock(return_value="summary-delegated")
    precheck = Mock(return_value="precheck-delegated")
    def directed(output, name):
        if name != a.NAME:
            return "directed-delegated"
        return runner._run_monitored(command, output, output / "synthetic-console.log", 600, None)
    script = checked.SCRIPT
    with patch.object(adapter, "_installed", False), \
         patch.object(checked.evidence, "precheck", precheck), \
         patch.object(full, "worker", previous), patch.object(checked, "summarize", summary), \
         patch.object(full.batch, "directed", directed), patch.object(runner, "_run_monitored", launch):
        adapter.install_hooks()
        handlers = (checked.evidence.precheck, full.worker, checked.summarize, full.batch.directed)
        adapter.install_hooks()
        assert handlers == (checked.evidence.precheck, full.worker, checked.summarize, full.batch.directed)
        assert checked.SCRIPT == script
        assert checked.evidence.precheck({"name": "app:other"}, None) == "precheck-delegated"
        assert full.worker(scratch, "other") == "delegated"
        assert checked.summarize(scratch, {"cases": [{"name": "other"}]}) == "summary-delegated"
        assert full.batch.directed(scratch, "other") == "directed-delegated"
        assert full.batch.directed(scratch, a.NAME) == (0, 1.0, False, False)
        assert launch.call_args.args[0] == command + ["+QBS_PERF"]
        assert runner._run_monitored is launch
        with patch.object(a, "precheck", return_value={"status": "synthetic"}) as own:
            pin = Mock()
            assert checked.evidence.precheck({"name": "app:" + a.NAME}, pin) == {"status": "synthetic"}
            own.assert_called_once()
            assert pin.pin.call_count == 2
    positive.append("precheck/worker/summarize/directed delegate, idempotence, SCRIPT unchanged, local PERF injection")
    runtime_tests(scratch, good, rows, targets, elf, proof, rejected, positive)
    return dict(status="PASS", rejected=rejected, positive=positive,
                scope="offline checker tests and synthetic fixtures only; no DUT PASS", vcs_launched=False)


def runtime_tests(scratch, log, rows, targets, elf, audit, rejected, positive):
    full = a.full
    output = scratch / "synthetic-runtime"
    artifact = output / "results" / a.NAME / "tests/synthetic"
    work = artifact / "work"
    work.mkdir(parents=True)
    source = output / "synthetic-input.txt"
    source.write_text("SYNTHETIC CHECKER FIXTURE, NOT A SIMULATION\n")
    record_path, selection_path = output / "record.json", output / "selection.json"
    record = dict(source_hashes=full.pins([source]), rtl_pins=full.pins([source]),
                  binary_sha256=full.pins([elf])[str(elf)], targets=targets, elf_audit=audit)
    full.save(record_path, record)
    full.save(selection_path, {"cases": [dict(name="app:" + a.NAME, precheck=dict(record=str(record_path)))]})
    summary = output / "results" / a.NAME / "summary.json"
    full.save(summary, [dict(status="PASS", artifact_dir=str(artifact))])
    log_path = work / "run.vcs.log"
    log_path.write_text(log + perf_text(rows) + "\n")
    command = work / "coverage.command.json"
    full.save(command, {"command": ["synthetic-simv-NOT-EXECUTABLE", "+QBS_PERF", "+TESTCASE=" + a.NAME]})
    vdb = work / "synthetic.vdb"
    vdb.mkdir()
    paths = []
    for metric in ("line", "branch"):
        from xml.etree.ElementTree import Element, SubElement, tostring
        root = Element("synthetic-only")
        for scope in sorted({p["scope"] for p in targets if p["metric"] == metric}):
            points = [p for p in targets if p["metric"] == metric and p["scope"] == scope]
            definition = points[0]["definition"]
            bits = ["0"] * definition["width"]
            for p in points:
                bits[p["raw_index"]] = "1"
            SubElement(root, "instance_data", name=scope, chksum=definition["checksum"], value="".join(bits))
        path = vdb / (metric + ".verilog.data.xml")
        path.write_bytes(tostring(root))
        paths.append(path)
    plan = dict(cases=[dict(name=a.NAME, timeout_s=600, frozen_elf=str(elf))],
                source_selection=dict(selection=str(selection_path)),
                files=full.pins([record_path, a.SCRIPT]), simv="synthetic-simv-NOT-EXECUTABLE")
    row = dict(files=full.pins([summary, log_path, command]), vdb=str(vdb), vdb_files=full.pins(paths))
    result = a.runtime_proof(output, plan, row)
    assert json.loads(json.dumps(result)) == result and len(result["hit_points"]) == 8
    assert a.runtime_proof(output, plan, row) == result
    positive.append("runtime proof synthetic fixture JSON roundtrip/replay and exact eight raw targets")
    outcome = output / "outcomes" / (a.NAME + ".json")
    outcome.parent.mkdir()
    full.save(outcome, dict(row, status="PASS", passed_only=True))
    checked = adapter.checked
    with patch.object(adapter, "_installed", False), \
         patch.object(checked.evidence, "precheck", Mock()), \
         patch.object(full, "worker", Mock(return_value=0)), \
         patch.object(checked, "summarize", Mock(return_value="summary-delegated")), \
         patch.object(full.batch, "directed", Mock()), \
         patch.object(checked, "frozen", return_value=plan), \
         patch.object(full.batch, "publish", Mock()):
        adapter.install_hooks()
        assert full.worker(output, a.NAME) == 0
        assert checked.summarize(output, plan) == "summary-delegated"
        report = output / "results" / a.NAME / "gap45_runtime_audit.json"
        saved = full.read(report)
        saved["uart"]["checks"] = 197
        full.save(report, saved)
        changed = full.read(outcome)
        changed["files"].update(full.pins([report]))
        full.save(outcome, changed)
        reject("summarize-runtime-replay", lambda: checked.summarize(output, plan), rejected)
        with patch.object(a, "runtime_proof", side_effect=ValueError("synthetic rejection")):
            assert full.worker(output, a.NAME) == 1
            failed = full.read(outcome)
            assert failed["status"] == "INFRASTRUCTURE_ERROR" and failed["passed_only"] is False
    positive.append("own worker and summarize replay; altered JSON rejected; runtime rejection demotes PASS")
    for key, path in (("files", log_path), ("files", command), ("files", summary), ("vdb_files", paths[0])):
        bad = copy.deepcopy(row)
        del bad[key][str(path)]
        reject("runtime-unbound-" + path.name, lambda: a.runtime_proof(output, plan, bad), rejected)
    bad = copy.deepcopy(plan)
    bad["simv"] = "foreign-simv"
    reject("runtime-foreign-image", lambda: a.runtime_proof(output, bad, row), rejected)
    data = paths[0].read_text()
    paths[0].write_text(data.replace('value="', 'value="0', 1))
    changed = copy.deepcopy(row)
    changed["vdb_files"].update(full.pins([paths[0]]))
    reject("runtime-raw-width", lambda: a.runtime_proof(output, plan, changed), rejected)
    paths[0].write_text(data)
    from xml.etree import ElementTree as ET
    for label, change in (("runtime-zero-target", "zero"), ("runtime-wrong-checksum", "checksum"),
                           ("runtime-duplicate-instance", "duplicate")):
        root = ET.fromstring(data)
        first = next(root.iter("instance_data"))
        if change == "zero":
            first.set("value", "0" * len(first.get("value")))
        elif change == "checksum":
            first.set("chksum", "0")
        else:
            root.append(copy.deepcopy(first))
        paths[0].write_bytes(ET.tostring(root))
        changed = copy.deepcopy(row)
        changed["vdb_files"].update(full.pins([paths[0]]))
        reject(label, lambda: a.runtime_proof(output, plan, changed), rejected)
    paths[0].write_text(data)
    source.write_text("mutated synthetic fixture\n")
    reject("runtime-source-drift", lambda: a.runtime_proof(output, plan, row), rejected)


def sealed_tests(item, path):
    rejected = []
    for key, value in (("timeout_s", 601), ("source_audit", "changed"),
                       ("sources", item["sources"] + [str(Path(__file__))]),
                       ("evidence", item["evidence"] + [str(path)])):
        bad = copy.deepcopy(item)
        bad[key] = value
        reject("seal-exact-" + key, lambda: a.precheck(bad, a.evidence.Evidence()), rejected)
    return dict(status="PASS", rejected=rejected,
                composer_binding="Parent batch only; this exact case must remain unchanged")
