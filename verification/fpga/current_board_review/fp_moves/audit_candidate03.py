#!/usr/bin/env python3
"""Independent terminal evidence and cycle-preservation audit for candidate03."""
import csv
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from focused import HERE, IMAGE, IMAGE_SHA, MARKER, prepare
from candidate03 import CANDIDATE, DISPATCHER


def read(path):
    return json.loads(path.read_text())


def main():
    out = HERE / "candidate03_audit01"
    out.mkdir(exist_ok=False)
    after = HERE / "candidate03_after01"
    terminal = read(after / "complete.json")
    assert terminal["status"] == "PASS" and terminal["all_planned_completed"]
    assert len(terminal["results"]) == 11 and terminal["pins_unchanged"]
    assert prepare.sha(IMAGE / "image.json") == IMAGE_SHA
    old_snapshot = read(Path(read(IMAGE / "image.json")["snapshot"]) / "snapshot.json")
    snapshot = read(CANDIDATE / "frozen/snapshot.json")
    assert snapshot["files"]["hardware/src/ara_dispatcher.sv"] == DISPATCHER
    changed = [n for n, digest in snapshot["files"].items() if old_snapshot["files"].get(n) != digest]
    assert sorted(changed) == ["frozen.filelist", "hardware/bender", "hardware/src/ara_dispatcher.sv"]
    checked = {}
    for directory in (HERE / "candidate02_before01", HERE / "candidate02_supplement01", after):
        for path, digest in read(directory / "pins.json").items():
            if path not in checked:
                checked[path] = prepare.sha(Path(path))
            assert checked[path] == digest, path
    for root, data in [(Path(snapshot["root"]), snapshot), (Path(old_snapshot["root"]), old_snapshot)]:
        for n, digest in data["files"].items():
            assert prepare.sha(root / n) == digest
    maps = {}
    for directory in (HERE / "port02", HERE / "supplement01"):
        maps.update(read(directory / "address_map.json")["programs"])
    controls, results = [], []
    for entry in terminal["results"]:
        name = entry["name"]
        directory = after / name
        before = HERE / ("candidate02_before01" if name.startswith("fp_move_") else "candidate02_supplement01") / name
        old = read(before / "status.json")
        assert entry["status"] == "PASS" and entry["returncode"] == 0
        assert prepare.sha(directory / "input.elf") == prepare.sha(before / "input.elf") == maps[name]["soc"]["elf_sha256"]
        for log_name in ("console.log", "run.vcs.log"):
            log = (directory / log_name).read_text()
            assert MARKER in log and "BOARD_REPLAY_PASS" in log
            assert "Core Test *** SUCCESS *** (tohost = 0)" in log
            assert "RVV_FP_MOVE_FAIL" not in log and "BOARD_REPLAY_TRAP" not in log
        with (directory / "commit_trace.csv").open() as f:
            rows = list(csv.DictReader(f))
        opcode = maps[name]["soc"].get("opcode", "42005c57")
        target = [r for r in rows if r["insn"] == opcode]
        assert len([r for r in target if r["event"] == "retire"]) == 1
        row = dict(name=name, before_status=old["status"], after_status="PASS", elapsed_s=entry["elapsed_s"],
            elf_sha256=entry["input_sha256"], target_events=target,
            after_trace_sha256=prepare.sha(directory / "commit_trace.csv"),
            before_trace_sha256=prepare.sha(before / "commit_trace.csv"))
        if old["status"] == "PASS":
            row["normal_trace_identical"] = row["before_trace_sha256"] == row["after_trace_sha256"]
            assert row["normal_trace_identical"], name
            controls.append(name)
        else:
            assert "first_bad_element=0 expected_bits=0 actual_bits=31743" in (before / "console.log").read_text()
        results.append(row)
    assert len(controls) == 7
    captures = {}
    for name in ("fp_move_original", "int_plain_restart", "fp_old64_restart", "int_old8_restart"):
        opcode = maps[name]["soc"].get("opcode", "42005c57")
        target = out / name
        command = [sys.executable, str(HERE / "analyze_candidate03.py"), str(after / name),
                   "--opcode", opcode, "--out", str(target)]
        subprocess.run(command, check=True, timeout=120)
        proof = read(target / "finding.json")
        assert not proof["be_suppression_proved"]
        scalar, issue, write = proof["scalar_backend"][0], proof["valu_issue"][0], proof["vrf_handshake"][0]
        assert scalar["d_ara_req_o.vstart"] == 0 and scalar["d_ara_req_o.vl"] == 1
        assert issue["a_result_write.be"] == write["a_alu_result_be_o"] == 3
        assert issue["a_valu_result"] == issue["a_result_write.wdata"] == write["a_alu_result_wdata_o"] == 0
        assert proof["final_eew24"] == 1
        mixed = name in ("fp_old64_restart", "int_old8_restart")
        assert len(proof["maintenance_backend"]) == int(mixed)
        if mixed:
            assert proof["first_decode"][0]["d_eew_q[24]"] == (3 if name == "fp_old64_restart" else 0)
            maintenance = proof["maintenance_backend"][0]
            assert maintenance["d_ara_req_o.vd"] == maintenance["d_ara_req_o.vs2"] == 24
            assert maintenance["d_ara_req_o.vl"] == 64 and maintenance["d_ara_req_o.vstart"] == 0
            assert maintenance["d_rs_lmul_cnt_limit_q"] == 0
            done = next(r for r in proof["trace_target_events"] if r["event"] == "uop_done")
            assert int(done["cycle"]) < scalar["cycle"]
        captures[name] = dict(finding_sha256=prepare.sha(target / "finding.json"),
            target_cycle=scalar["cycle"], issue_cycle=issue["cycle"], write_cycle=write["cycle"],
            be=write["a_alu_result_be_o"], maintenance_count=len(proof["maintenance_backend"]))
    image = CANDIDATE / "campaign/image/image.json"
    result = dict(status="CANDIDATE03_SCALAR_MOVE_11_PASS", scope="Original single-source four plus seven derivatives, not full Linux partition or whole arithmetic regression",
        dispatcher_sha256=DISPATCHER, snapshot_sha256=prepare.sha(CANDIDATE / "frozen/snapshot.json"),
        image_sha256=prepare.sha(image), baseline_image_sha256=IMAGE_SHA,
        changed_snapshot_files=changed, rechecked_distinct_pins=len(checked), pin_mismatches=0,
        normal_controls_full_trace_identical=controls, results=results, cycle_proofs=captures,
        runner_sha256=prepare.sha(HERE / "candidate03.py"), auditor_sha256=prepare.sha(Path(__file__)))
    prepare.save(out / "finding.json", result)
    print("CANDIDATE03_11_PASS SEVEN_FULL_TRACES_IDENTICAL FOUR_REAL_BE_PROOFS", flush=True)


if __name__ == "__main__":
    main()
