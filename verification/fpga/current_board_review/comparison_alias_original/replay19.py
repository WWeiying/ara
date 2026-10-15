#!/usr/bin/env python3
"""Reuse the sealed integration runner: selected capture, then gated18 jobs2."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
import prepare19 as p
import run as shared

HERE = p.HERE
IMAGE = Path("/home/wangwy/fpga_runs/current_board_memory_candidate03/campaign/image")
IMAGE_SHA = "e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6"
SYSTEM = "ara_tb.dut.i_ara_soc.i_system"
ARA = SYSTEM + ".i_ara"
MASK = ARA + ".i_masku"


def resources(out, jobs):
    process = subprocess.run(["/usr/bin/pgrep", "-a", "-x", "simv"], capture_output=True, text=True)
    p.require(process.returncode in (0, 1), "Process inventory failed")
    lines = process.stdout.splitlines()
    external = [line for line in lines if str(out) not in line]
    reserve = max(0, 2 - sum("indexed_review" in line for line in external))
    mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(mem["MemAvailable"].split()[0]) * 1024
    p.require(len(external) + reserve + jobs <= 24, "Capacity unavailable; no automatic retry")
    p.require(available >= 32 * 1024**3, "MemAvailable below32GiB")
    return dict(time=time.time(), processes=lines, external_simv=len(external), reserved_nf7=reserve,
                own_slots=jobs, available_bytes=available, alias_reservation=0)


def profile():
    names = ["ara_tb.clk", SYSTEM + ".i_ara_commit_monitor.cycle_q"]
    names += [ARA + ".i_dispatcher." + n for n in ("ara_req_o", "ara_req_valid_o", "ara_req_ready_i",
              "csr_vl_q", "csr_vstart_q", "eew_q[8]", "eew_q[16]", "reshuffle_req_q")]
    names += [MASK + "." + n for n in ("pe_req_i", "pe_req_valid_i", "pe_req_ready_o", "vinsn_issue",
        "vinsn_issue_valid", "masku_operand_vd_seq", "masku_operand_vd_valid", "masku_operand_vd_ready",
        "masku_operand_alu_valid", "masku_operand_alu_ready", "masku_operand_m_seq", "masku_operand_vd",
        "alu_result_compressed_seq", "result_queue_active_mask_seq", "background_data_init_seq",
        "alu_result_vm_m", "result_queue_d", "result_queue_cnt_q", "result_queue_write_pnt_q",
        "in_ready_cnt_en", "out_vrf_word_valid", "iteration_cnt_q", "pe_resp",
        "masku_result_req_o", "masku_result_gnt_i", "masku_result_final_gnt_i")]
    for i in range(4):
        lane = ARA + f".gen_lanes[{i}].i_lane"
        names += [lane + ".i_operand_requester." + n for n in (
            "operand_request_i[5]", "operand_request_valid_i", "operand_request_ready_o",
            "requester_metadata_q[5]", "lane_operand_req_transposed[5]", "operand_requester_gnt[5]",
            "operand_payload[5]", "operand_issued_o", "state_q[5]", "operand_queue_cmd_o[5]",
            "operand_queue_cmd_valid_o", "masku_result_req_i", "masku_result_gnt_o",
            "masku_result_id_i", "masku_result_addr_i", "masku_result_wdata_i", "masku_result_be_i")]
    return names


def verify(pins):
    for path, digest in pins.items():
        p.require(p.prepare.sha(Path(path)) == digest, "Pinned input changed: " + path)


def work(prepared, out, stage):
    p.require(p.read(prepared / "reference.json")["status"] == "SPIKE_19_PASS_NOT_DUT", "Reference gate not PASS")
    p.require(p.prepare.sha(IMAGE / "image.json") == IMAGE_SHA, "Wrong candidate03")
    ledger = p.read(IMAGE / "image.json")
    if stage == "selected":
        out.mkdir(parents=True, exist_ok=False)
        pins = dict(ledger["files"])
        pins.update(p.read(prepared / "source_pins.json"))
        for f in prepared.rglob("*"):
            if f.is_file():
                pins[str(f)] = p.prepare.sha(f)
        snapshot = Path(ledger["snapshot"])
        for n, h in p.read(snapshot / "snapshot.json")["files"].items():
            pins[str(snapshot / "sources" / n)] = h
        for f in (Path(__file__), IMAGE / "image.json", snapshot / "snapshot.json",
                  Path(ledger["simv"]).parent / "simulator.conf",
                  Path(ledger["simv"]).parent / "vcs_source_manifest.json"):
            pins[str(f)] = p.prepare.sha(f)
        p.prepare.save(out / "pins.json", pins)
    else:
        first = p.read(out / "selected.json")
        p.require(first["status"] == "PASS" and first["count"] == 1 and first["pins_unchanged"], "Selected target did not PASS")
    pins = p.read(out / "pins.json")
    verify(pins)
    programs = p.read(prepared / "soc/programs.json")["programs"]
    names = [p.SELECTED] if stage == "selected" else [n for n in programs if n != p.SELECTED]
    p.require(len(names) == (1 if stage == "selected" else 18), "Wrong exact membership")
    jobs = 1 if stage == "selected" else 2
    dest = out / stage
    p.require(not dest.exists(), "Never overwrite previous run")
    (out / (stage + "_admission")).mkdir()
    p.prepare.save(out / (stage + "_resources.json"), resources(out, jobs))
    framework = shared.framework

    def resource_framework(repo):
        base, options, case, image = framework(repo)
        class Admitted(base):
            def _run_test(self, test, simv):
                if not self.cancel_event.is_set():
                    p.prepare.save(out / (stage + "_admission") / (test.name + ".json"), resources(out, jobs))
                return super()._run_test(test, simv)
        return Admitted, options, case, image

    shared.framework = resource_framework
    shared.oracle_complete = p.oracle
    shared.framework(Path(ledger["snapshot"]) / "sources")
    import ara_verify.runner as engine
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern + "|" + p.FAIL.pattern, engine.FAIL_RE.flags)
    monitored = engine._run_monitored
    if stage == "selected":
        p.prepare.save(out / "profile.json", dict(signals=profile(), window_ns=[0, 100000],
            scope="Actual accepted MaskB/VRF and MASKU signals; no forced state"))
        tcl = out / "capture.tcl"
        tcl.write_text("\n".join(["onerror {quit}", "set fid [dump -file selected.fsdb -type FSDB]",
            *["dump -add {" + n + "} -aggregates -fid $fid" for n in profile()],
            "run -absolute 100000ns", "dump -disable -fid $fid", "dump -flush $fid", "run", "quit"]) + "\n")

        def capture(command, cwd, console, timeout, cancel):
            command = [*command, "-ucli", "-do", str(tcl)]
            p.prepare.save(console.parent / "command.json", dict(command=command, cwd=str(cwd),
                capture_hook="Only bounded UCLI arguments appended to existing frozen runner"))
            return monitored(command, cwd, console, timeout, cancel)
        engine._run_monitored = capture
    started = time.time()
    try:
        rc = shared.run_programs(SimpleNamespace(image=IMAGE, programs=prepared / "soc", out=dest,
            case=names, jobs=jobs, timeout=180, execute=True))
    finally:
        engine._run_monitored = monitored
    verify(pins)
    summary = p.read(dest / "summary.json")
    passed = rc == 0 and len(summary) == len(names) and all(r["status"] == "PASS" and r["returncode"] == 0 for r in summary)
    p.prepare.save(out / (stage + ".json"), dict(status="PASS" if passed else "NOT_PASS", count=len(summary),
        jobs=jobs, elapsed_s=time.time()-started, results=summary, pins_unchanged=True,
        image_sha256=IMAGE_SHA, full_original_oracle=True, explicit_failure_veto=True))
    print(stage.upper(), "PASS" if passed else "NOT_PASS", len(summary), flush=True)
    return int(not passed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("selected", "remaining"))
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out, prepared = args.out.resolve(), args.prepared.resolve()
    p.require(out.is_relative_to(HERE) and prepared.is_relative_to(HERE) and out != HERE, "Owned paths only")
    env = shared.environment()
    os.environ.clear()
    os.environ.update(env)
    sys.exit(work(prepared, out, args.stage))
