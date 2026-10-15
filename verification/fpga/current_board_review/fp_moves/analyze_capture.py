#!/usr/bin/env python3
"""Decode the pinned scalar-move capture at pre-rising-edge values."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from focused import ALU, ARA, LANE, SYSTEM, HERE, inside, prepare, checked
sys.path.insert(0, str(HERE.parent / "comparison"))
from decode_cycle import vcd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    capture, out = inside(args.capture), inside(args.out)
    out.mkdir(parents=True, exist_ok=False)
    source = out / "selected.vcd"
    command = [str(checked.VERDI / "platform/linux64/bin/fsdb2vcd"),
               str(capture / "selected.fsdb"), "-o", str(source),
               "-bt", "0ns", "-et", "50000ns", "-compacttree"]
    env = dict(checked.environment(), LD_LIBRARY_PATH=str(checked.VERDI / "etc/lib/libstdc++/linux64"))
    with (out / "conversion.log").open("w") as f:
        subprocess.run(command, env=env, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=60)
    prepare.save(out / "conversion.json", dict(command=command,
        source_sha256=prepare.sha(capture / "selected.fsdb")))
    assert "100fs" in source.read_text()[:256]
    events = iter(vcd(source))
    tag, declarations = next(events)
    assert tag == "declarations"
    fields = {"clk": "ara_tb.clk", "cycle": SYSTEM + ".i_ara_commit_monitor.cycle_q"}
    fields.update({"d_" + n: ARA + ".i_dispatcher." + n for n in (
        "csr_vl_q", "csr_vstart_q", "acc_req_i.req_valid", "acc_req_i.insn", "acc_resp_o.req_ready",
        "ara_req_valid_o", "ara_req_ready_i", "ara_req_o.op", "ara_req_o.vstart",
        "ara_req_o.vl", "ara_req_o.vd", "ara_req_o.scalar_op", "ara_req_o.verify_arch_insn")})
    fields.update({"l_" + n: LANE + ".i_lane_sequencer." + n for n in (
        "pe_req_valid", "pe_req_ready", "pe_req.id", "pe_req.op", "pe_req.vstart", "pe_req.vl",
        "vfu_operation_valid_d", "vfu_operation_d.vstart", "vfu_operation_d.vl")})
    fields.update({"a_" + n: ALU + "." + n for n in (
        "vfu_operation_valid_i", "alu_ready_o", "vfu_operation_i.id", "vfu_operation_i.op",
        "vfu_operation_i.vstart", "vfu_operation_i.vl", "vinsn_issue_valid", "vinsn_issue_q.id",
        "vinsn_issue_q.op", "vinsn_issue_q.vstart", "vinsn_issue_q.vl", "issue_cnt_q",
        "valu_valid", "valu_result", "result_write.id", "result_write.addr", "result_write.wdata",
        "result_write.be", "alu_result_req_o", "alu_result_gnt_i", "alu_result_id_o",
        "alu_result_addr_o", "alu_result_be_o", "alu_result_wdata_o", "alu_vinsn_done_o")})
    missing = set(fields.values()) - declarations.keys()
    assert not missing, sorted(missing)
    codes = {k: declarations[p]["code"] for k, p in fields.items()}
    rows = []
    for timestamp, before, after in events:
        if before.get(codes["clk"]) != "0" or after.get(codes["clk"]) != "1":
            continue
        row = {k: int(before[c], 2) if c in before and set(before[c]) <= set("01") else None
               for k, c in codes.items()}
        row["time_ns"] = timestamp / 10000
        rows.append(row)
    backend = [r for r in rows if r["d_ara_req_valid_o"] == r["d_ara_req_ready_i"] == 1
               and r["d_ara_req_o.verify_arch_insn"] == 0x42005c57]
    assert len(backend) == 1, backend
    first = backend[0]
    op = first["d_ara_req_o.op"]
    lane = [r for r in rows if r["cycle"] >= first["cycle"] and
            r["l_pe_req_valid"] == r["l_pe_req_ready"] == 1 and r["l_pe_req.op"] == op]
    assert len(lane) == 1
    vid = lane[0]["l_pe_req.id"]
    done = [r for r in rows if r["cycle"] >= lane[0]["cycle"] and
            r["a_alu_vinsn_done_o"] is not None and (r["a_alu_vinsn_done_o"] >> vid) & 1]
    assert done
    window = [r for r in rows if first["cycle"] - 3 <= r["cycle"] <= done[0]["cycle"] + 3]
    accepted = [r for r in window if r["a_vfu_operation_valid_i"] == r["a_alu_ready_o"] == 1
                and r["a_vfu_operation_i.op"] == op and r["a_vfu_operation_i.id"] == vid]
    issued = [r for r in window if r["a_vinsn_issue_valid"] == r["a_valu_valid"] == 1
              and r["a_vinsn_issue_q.op"] == op and r["a_vinsn_issue_q.id"] == vid]
    written = [r for r in window if r["a_alu_result_req_o"] == r["a_alu_result_gnt_i"] == 1
               and r["a_alu_result_id_o"] == vid]
    assert len(accepted) == len(issued) == len(written) == 1
    with (out / "cycles.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(window[0]))
        writer.writeheader()
        writer.writerows(window)
    with (capture / "commit_trace.csv").open() as f:
        trace = [r for r in csv.DictReader(f) if r["insn"] == "42005c57"]
    suppressed = (first["d_ara_req_o.vl"] == first["d_ara_req_o.vstart"] == 1 and
        accepted[0]["a_vfu_operation_i.vl"] == accepted[0]["a_vfu_operation_i.vstart"] == 1 and
        issued[0]["a_valu_result"] == issued[0]["a_result_write.wdata"] == 0 and
        issued[0]["a_result_write.be"] == written[0]["a_alu_result_be_o"] == 0)
    finding = dict(status="CYCLE_PROOF" if suppressed else "HYPOTHESIS_NOT_CONFIRMED",
        target_opcode="42005c57", vid=vid, backend=backend, lane_accept=lane,
        valu_accept=accepted, valu_issue=issued, vrf_handshake=written, done=done[:1],
        trace_target_events=trace, be_suppression_proved=suppressed,
        scope="One genuine source-derived VFMVSF; not VMVSX or full original partition",
        vcd_sha256=prepare.sha(source), analyzer_sha256=prepare.sha(Path(__file__)))
    prepare.save(out / "finding.json", finding)
    print(json.dumps({"status": finding["status"], "vid": vid,
        "backend_cycle": first["cycle"], "lane_cycle": lane[0]["cycle"],
        "valu_accept_cycle": accepted[0]["cycle"], "issue_cycle": issued[0]["cycle"],
        "issue_be": issued[0]["a_result_write.be"], "vrf_cycle": written[0]["cycle"],
        "vrf_be": written[0]["a_alu_result_be_o"], "done_cycle": done[0]["cycle"]}, indent=2))


if __name__ == "__main__":
    main()
