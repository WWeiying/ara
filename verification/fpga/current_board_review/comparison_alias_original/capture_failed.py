#!/usr/bin/env python3
"""One unchanged failing ELF, existing runner, bounded non-forcing UCLI capture."""
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
import replay19 as r

NAME = "rvv_small_masks_cmp_alias_restart_e8_m2"
OUT = r.HERE / "failure_capture01"


def profile():
    names = r.profile()
    names += [r.MASK + "." + n for n in (
        "vrf_pnt_q", "vrf_pnt_d", "delta_elm_q", "masku_operand_alu", "masku_operand_alu_seq",
        "masku_operand_m_valid", "masku_operand_m_ready", "result_queue_q", "result_queue_read_pnt_q",
        "in_ready_cnt_q", "out_valid_cnt_q", "issue_cnt_q", "commit_cnt_q")]
    for i in range(4):
        lane = r.ARA + f".gen_lanes[{i}].i_lane"
        names += [lane + "." + n for n in ("operand_queue_input", "operand_queue_input_valid",
            "vrf_operand", "vrf_operand_valid", "source_snapshot_replay_valid")]
        req = lane + ".i_operand_requester"
        names += [req + "." + n for n in ("source_snapshot_replay_valid_o", "vrf_req_o", "vrf_wen_o",
            "vrf_addr_o", "vrf_wdata_o", "vrf_be_o", "vrf_tgt_opqueue_o", "masku_result_final_gnt_o",
            "masku_result_req", "masku_result_gnt", "masku_result_addr", "masku_result_wdata", "masku_result_be")]
        for q in (0, 1):
            names += [req + "." + n + f"[{q}]" for n in ("operand_request_i", "requester_metadata_q",
                "operand_requester_gnt", "operand_payload", "operand_queue_cmd_o", "state_q")]
        valu = lane + ".i_vfus.i_valu"
        names += [valu + "." + n for n in ("vfu_operation_i", "vfu_operation_valid_i", "alu_ready_o",
            "vinsn_issue_q", "vinsn_issue_valid", "issue_cnt_q", "issue_cnt_d", "alu_operand_i",
            "alu_operand_valid_i", "alu_operand_ready_o", "alu_operand_a", "alu_operand_b", "valu_valid",
            "valu_result", "result_write", "result_queue_q", "result_queue_valid_q", "result_queue_read_pnt_q",
            "result_queue_write_pnt_q", "mask_operand_o", "mask_operand_valid_o", "mask_operand_ready_i")]
    return list(dict.fromkeys(names))


def main():
    OUT.mkdir(exist_ok=False)
    pins = r.p.read(r.HERE / "measurement01/pins.json")
    pins[str(Path(__file__).resolve())] = r.p.prepare.sha(Path(__file__))
    r.verify(pins)
    r.p.prepare.save(OUT / "pins.json", pins)
    r.p.prepare.save(OUT / "resources.json", r.resources(OUT, 1))
    signals = profile()
    r.p.prepare.save(OUT / "plan.json", dict(case=NAME, image=str(r.IMAGE), timeout_s=180, jobs=1,
        window_ns=[18000, 20500], baseline_target_pc="0x80000508", baseline_alloc_cycle=19203,
        baseline_done_cycle=19217, signals=signals, force=False, failure_marker_veto=True,
        hypothesis="AluA/B source origin64 while VALU/MASKU output origin0; bit84 compares source148",
        alternatives=["queue payload displacement", "comparison/compaction error", "alias write corruption"]))
    tcl = OUT / "capture.tcl"
    tcl.write_text("\n".join(["onerror {quit}", "run -absolute 18000ns",
        "set fid [dump -file failed.fsdb -type FSDB]",
        *["dump -add {" + n + "} -aggregates -fid $fid" for n in signals],
        "run -absolute 20500ns", "dump -disable -fid $fid", "dump -flush $fid", "run", "quit"]) + "\n")
    r.shared.oracle_complete = r.p.oracle
    ledger = r.p.read(r.IMAGE / "image.json")
    r.shared.framework(Path(ledger["snapshot"]) / "sources")
    import ara_verify.runner as engine
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern + "|" + r.p.FAIL.pattern, engine.FAIL_RE.flags)
    original = engine._run_monitored

    def capture(command, cwd, console, timeout, cancel):
        r.p.prepare.save(OUT / "launch_resources.json", r.resources(OUT, 1))
        command = [*command, "-ucli", "-do", str(tcl)]
        r.p.prepare.save(console.parent / "command.json", dict(command=command, cwd=str(cwd)))
        return original(command, cwd, console, timeout, cancel)

    engine._run_monitored = capture
    start = time.time()
    rc = r.shared.run_programs(SimpleNamespace(image=r.IMAGE, programs=r.HERE / "prepared01/soc",
        out=OUT / "replay", case=[NAME], jobs=1, timeout=180, execute=True))
    r.verify(pins)
    r.p.prepare.save(OUT / "status.json", dict(runner_returncode=rc,
        results=r.p.read(OUT / "replay/summary.json"), pins_unchanged=True, elapsed_s=time.time()-start,
        interpretation="Architectural failure is expected baseline evidence; not a passing regression"))
    return rc


if __name__ == "__main__":
    env = r.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    sys.exit(main())
