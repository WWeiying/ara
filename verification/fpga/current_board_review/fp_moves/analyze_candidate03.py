#!/usr/bin/env python3
"""Read actual scalar insertion and destination-layout handshakes from FSDB."""
import argparse
import csv
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from focused import ARA, ALU, LANE, SYSTEM, HERE, checked, prepare, inside
sys.path.insert(0, str(HERE.parent / "comparison"))
from decode_cycle import vcd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--opcode", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    capture, out = inside(args.capture), inside(args.out)
    opcode = int(args.opcode, 16)
    out.mkdir(parents=True, exist_ok=False)
    source = out / "selected.vcd"
    command = [str(checked.VERDI / "platform/linux64/bin/fsdb2vcd"), str(capture / "selected.fsdb"),
               "-o", str(source), "-bt", "0ns", "-et", "50000ns", "-compacttree"]
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
        "ara_req_valid_o", "ara_req_ready_i", "ara_req_o.op", "ara_req_o.vstart", "ara_req_o.vl",
        "ara_req_o.vd", "ara_req_o.scalar_op", "ara_req_o.verify_arch_insn", "ara_req_o.use_scalar_op",
        "ara_req_o.use_vs2", "ara_req_o.vtype.vsew", "ara_req_o.vs2", "ara_req_o.eew_vs2",
        "state_q", "state_d", "decode_blocked", "ara_req.vstart", "ara_req.vl",
        "layout_req.vstart", "layout_req.vl", "eew_q[24]", "eew_d[24]",
        "reshuffle_req_q", "reshuffle_req_d", "eew_old_buffer_q", "eew_new_buffer_q",
        "vs_buffer_q", "rs_lmul_cnt_q", "rs_lmul_cnt_limit_q")})
    fields.update({"l_" + n: LANE + ".i_lane_sequencer." + n for n in (
        "pe_req_valid", "pe_req_ready", "pe_req.id", "pe_req.op", "pe_req.vstart", "pe_req.vl")})
    fields.update({"a_" + n: ALU + "." + n for n in (
        "vfu_operation_valid_i", "alu_ready_o", "vfu_operation_i.id", "vfu_operation_i.op",
        "vfu_operation_i.vstart", "vfu_operation_i.vl", "vinsn_issue_valid", "vinsn_issue_q.id",
        "vinsn_issue_q.op", "vinsn_issue_q.vstart", "vinsn_issue_q.vl", "issue_cnt_q",
        "valu_valid", "valu_result", "result_write.wdata", "result_write.be", "alu_result_req_o",
        "alu_result_gnt_i", "alu_result_id_o", "alu_result_addr_o", "alu_result_be_o",
        "alu_result_wdata_o", "alu_vinsn_done_o")})
    assert not set(fields.values()) - declarations.keys(), sorted(set(fields.values()) - declarations.keys())
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
               and r["d_ara_req_o.verify_arch_insn"] == opcode]
    scalar = [r for r in backend if r["d_ara_req_o.use_scalar_op"] == 1 and r["d_ara_req_o.use_vs2"] == 0]
    assert len(scalar) == 1, scalar
    first, op = scalar[0], scalar[0]["d_ara_req_o.op"]
    lane = [r for r in rows if r["cycle"] >= first["cycle"] and
            r["l_pe_req_valid"] == r["l_pe_req_ready"] == 1 and r["l_pe_req.op"] == op]
    assert len(lane) == 1
    vid = lane[0]["l_pe_req.id"]
    done = [r for r in rows if r["cycle"] >= lane[0]["cycle"] and
            r["a_alu_vinsn_done_o"] is not None and (r["a_alu_vinsn_done_o"] >> vid) & 1]
    assert done
    decoded = [r for r in rows if r["d_acc_req_i.req_valid"] == 1 and r["d_acc_req_i.insn"] == opcode]
    window = [r for r in rows if decoded[0]["cycle"] - 2 <= r["cycle"] <= done[0]["cycle"] + 3]
    accept = [r for r in window if r["a_vfu_operation_valid_i"] == r["a_alu_ready_o"] == 1
              and r["a_vfu_operation_i.op"] == op and r["a_vfu_operation_i.id"] == vid]
    issue = [r for r in window if r["a_vinsn_issue_valid"] == r["a_valu_valid"] == 1
             and r["a_vinsn_issue_q.op"] == op and r["a_vinsn_issue_q.id"] == vid]
    writes = [r for r in window if r["a_alu_result_req_o"] == r["a_alu_result_gnt_i"] == 1
              and r["a_alu_result_id_o"] == vid and r["cycle"] >= first["cycle"]]
    assert len(accept) == len(issue) == len(writes) == 1
    suppressed = (accept[0]["a_vfu_operation_i.vstart"] >= accept[0]["a_vfu_operation_i.vl"] and
                  issue[0]["a_valu_result"] == 0 and issue[0]["a_result_write.be"] == writes[0]["a_alu_result_be_o"] == 0)
    with (out / "cycles.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(window[0]))
        writer.writeheader()
        writer.writerows(window)
    with (capture / "commit_trace.csv").open() as f:
        trace = [r for r in csv.DictReader(f) if int(r["insn"], 16) == opcode]
    result = dict(status="MEASURED", target_opcode=f"{opcode:08x}", vid=vid,
        first_decode=decoded[:1], scalar_backend=scalar, all_owner_backend=backend,
        maintenance_backend=[r for r in backend if r not in scalar], lane_accept=lane,
        valu_accept=accept, valu_issue=issue, vrf_handshake=writes, done=done[:1],
        be_suppression_proved=suppressed, trace_target_events=trace,
        final_eew24=window[-1]["d_eew_q[24]"],
        eew_changes=[r for r in window if r["d_eew_q[24]"] != r["d_eew_d[24]"]],
        vcd_sha256=prepare.sha(source), analyzer_sha256=prepare.sha(Path(__file__)))
    prepare.save(out / "finding.json", result)
    print(dict(be_suppression_proved=suppressed, backend=first["cycle"], issue=issue[0]["cycle"],
               be=issue[0]["a_result_write.be"], write=writes[0]["cycle"],
               old_eew=decoded[0]["d_eew_q[24]"], final_eew=result["final_eew24"],
               maintenance=len(result["maintenance_backend"])))


if __name__ == "__main__":
    main()
