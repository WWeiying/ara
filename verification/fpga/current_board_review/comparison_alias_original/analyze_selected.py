#!/usr/bin/env python3
"""Inspect actual pre-edge MaskB/old-vd handshakes; never force DUT state."""
import argparse
import csv
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
import replay19 as r
sys.path.insert(0, str(r.HERE.parent / "comparison"))
from decode_cycle import vcd


def convert(measurement, out):
    out.mkdir(parents=True, exist_ok=False)
    fsdb = measurement / "selected/tests" / r.p.SELECTED / "work/selected.fsdb"
    command = [str(r.shared.VERDI / "platform/linux64/bin/fsdb2vcd"), str(fsdb),
               "-o", str(out / "selected.vcd"), "-bt", "0ns", "-et", "100000ns", "-compacttree"]
    env = dict(r.shared.environment(), LD_LIBRARY_PATH=str(r.shared.VERDI / "etc/lib/libstdc++/linux64"))
    with (out / "conversion.log").open("x") as stream:
        subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=90)
    r.p.prepare.save(out / "conversion.json", dict(command=command, fsdb_sha256=r.p.prepare.sha(fsdb)))


def analyze(out):
    path = out / "selected.vcd"
    r.p.require("100fs" in path.read_text()[:256], "Unexpected timescale")
    events = iter(vcd(normalize(path)))
    tag, decl = next(events)
    r.p.require(tag == "declarations", "Missing VCD header")
    r.p.prepare.save(out / "declarations.json", decl)
    fields = {"clk": "ara_tb.clk", "cycle": r.SYSTEM + ".i_ara_commit_monitor.cycle_q"}
    for prefix, scope, names in (
        ("d_", r.ARA + ".i_dispatcher", ("ara_req_valid_o", "ara_req_ready_i", "ara_req_o.verify_arch_insn",
         "ara_req_o.op", "ara_req_o.vl", "ara_req_o.vstart", "ara_req_o.eew_vd_op", "eew_q[8]", "eew_q[16]")),
        ("m_", r.MASK, ("pe_req_valid_i", "pe_req_ready_o", "pe_req_i.id", "pe_req_i.op", "vinsn_issue_valid",
         "vinsn_issue.id", "vinsn_issue.op", "masku_operand_vd_valid", "masku_operand_vd_ready",
         "masku_operand_vd_seq", "masku_operand_alu_valid", "masku_operand_alu_ready", "in_ready_cnt_en",
         "result_queue_active_mask_seq", "background_data_init_seq", "alu_result_vm_m", "out_vrf_word_valid",
         "pe_resp.vinsn_done"))):
        fields.update({prefix + n: scope + "." + n for n in names})
    for lane in range(4):
        scope = r.ARA + f".gen_lanes[{lane}].i_lane.i_operand_requester"
        names = ("operand_request_valid_i", "operand_request_ready_o", "operand_request_i[5].id",
            "operand_request_i[5].vs", "operand_request_i[5].vstart", "operand_request_i[5].vl",
            "operand_request_i[5].eew", "requester_metadata_q[5].id", "requester_metadata_q[5].addr",
            "operand_issued_o", "lane_operand_req_transposed[5]", "operand_requester_gnt[5]",
            "operand_payload[5].addr", "masku_result_req_i", "masku_result_gnt_o", "masku_result_id_i",
            "masku_result_addr_i", "masku_result_wdata_i", "masku_result_be_i")
        fields.update({f"l{lane}_" + n: scope + "." + n for n in names})
    missing = set(fields.values()) - set(decl)
    r.p.require(not missing, "Missing fields: " + str(sorted(missing)))
    codes = {n: decl[path]["code"] for n, path in fields.items()}
    rows, first, vid, done = [], None, None, None
    for timestamp, before, after in events:
        if before.get(codes["clk"]) != "0" or after.get(codes["clk"]) != "1":
            continue
        row = {n: int(before[c], 2) if c in before and set(before[c]) <= set("01") else None for n, c in codes.items()}
        row["time_ns"] = timestamp / 10000
        if row["d_ara_req_valid_o"] == row["d_ara_req_ready_i"] == 1 and row["d_ara_req_o.verify_arch_insn"] == 0x60880457:
            r.p.require(first is None, "More than one target acceptance")
            first = row
        if first is None:
            continue
        if done is not None and row["cycle"] > done + 3:
            continue
        rows.append(row)
        if row["m_pe_req_valid_i"] == row["m_pe_req_ready_o"] == 1 and row["m_pe_req_i.op"] == first["d_ara_req_o.op"]:
            vid = row["m_pe_req_i.id"]
        if vid is not None and row["m_pe_resp.vinsn_done"] is not None and (row["m_pe_resp.vinsn_done"] >> vid) & 1:
            done = row["cycle"]
    r.p.require(first is not None and vid is not None and done is not None, "Target acceptance/completion missing")
    lanes = []
    for lane in range(4):
        key = f"l{lane}_"
        commands = [x for x in rows if x[key + "operand_request_valid_i"] is not None and x[key + "operand_request_ready_o"] is not None
                    and (x[key + "operand_request_valid_i"] & x[key + "operand_request_ready_o"] & (1 << 5))
                    and x[key + "operand_request_i[5].id"] == vid and x[key + "operand_request_i[5].vs"] == 8]
        grants = [x for x in rows if x[key + "requester_metadata_q[5].id"] == vid and
                  x[key + "operand_issued_o"] is not None and x[key + "operand_issued_o"] & (1 << 5)]
        writes = [x for x in rows if x[key + "masku_result_req_i"] == x[key + "masku_result_gnt_o"] == 1
                  and x[key + "masku_result_id_i"] == vid]
        lanes.append(dict(lane=lane, commands=[{n: x[key + "operand_request_i[5]." + n] for n in ("vs", "vstart", "vl", "eew")}
            | dict(cycle=x["cycle"]) for x in commands],
            grants=[dict(cycle=x["cycle"], addr=x[key + "operand_payload[5].addr"],
                         metadata_addr=x[key + "requester_metadata_q[5].addr"],
                         grant_bitmap=x[key + "operand_requester_gnt[5]"]) for x in grants],
            writes=[dict(cycle=x["cycle"], addr=x[key + "masku_result_addr_i"],
                         data=x[key + "masku_result_wdata_i"], be=x[key + "masku_result_be_i"]) for x in writes]))
    old = [x for x in rows if x["m_vinsn_issue_valid"] == 1 and x["m_vinsn_issue.id"] == vid and
           x["m_vinsn_issue.op"] == first["d_ara_req_o.op"] and x["m_masku_operand_vd_valid"] == 15]
    # Source C uses uint64 xorshift and truncates each generated value to EW16.
    rng, data, limit = 0xc274caf34727a125, bytearray(), (1 << 64) - 1
    for _ in range(16):
        rng ^= (rng << 13) & limit
        rng ^= rng >> 7
        rng ^= (rng << 17) & limit
        data.extend((rng & 0xffff).to_bytes(2, "little"))
    expected_old = int.from_bytes(data, "little")
    origin = all(len(x["commands"]) == len(x["grants"]) == 1 and
                 x["commands"][0]["vstart"] == 0 and x["commands"][0]["vl"] == 1 and
                 x["commands"][0]["eew"] == 3 and x["grants"][0]["metadata_addr"] == 32 and
                 x["grants"][0]["addr"] == 4 and x["grants"][0]["grant_bitmap"] == 1 for x in lanes)
    old_correct = bool(old) and all(x["m_masku_operand_vd_seq"] == expected_old for x in old)
    with (out / "cycles.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    finding = dict(status="CURRENT_ORIGIN_AND_OLD_DATA_CONFIRMED" if origin and old_correct else "CHECK_REQUIRED",
        backend_cycle=first["cycle"], vid=vid, masku_done_cycle=done, lanes=lanes,
        backend_vl=first["d_ara_req_o.vl"], backend_vstart=first["d_ara_req_o.vstart"],
        eew_vd_op=first["d_ara_req_o.eew_vd_op"], stored_eew8=first["d_eew_q[8]"],
        origin_zero_all_lanes=origin, correct_old_vd=old_correct, expected_old_hex=f"{expected_old:064x}",
        old_samples=[dict(cycle=x["cycle"], old_hex=f'{x["m_masku_operand_vd_seq"]:064x}',
                         ready=x["m_masku_operand_vd_ready"], active=x["m_result_queue_active_mask_seq"],
                         accepted_slice=x["m_in_ready_cnt_en"]) for x in old],
        scope="Current selected single only; no measured archived-RTL A/B or all19 common-cause claim",
        vcd_sha256=r.p.prepare.sha(path), analyzer_sha256=r.p.prepare.sha(Path(__file__)))
    r.p.prepare.save(out / "finding.json", finding)
    print(finding["status"], first["cycle"], done, flush=True)


def normalize(path):
    dest = path.with_name("normalized.vcd")
    scopes, seen, duplicates = [], {}, []
    body = False
    with path.open() as src, dest.open("w") as dst:
        for raw in src:
            line = raw.strip()
            if not body:
                if line.startswith("$scope "):
                    scopes.append(line.split()[2].replace("\\sv_", ""))
                elif line.startswith("$upscope"):
                    scopes.pop()
                elif line.startswith("$var "):
                    p = line.split()
                    name = p[4]
                    for suffix in p[5:-1]:
                        if suffix.startswith("[") and "][" in suffix:
                            name += suffix[:suffix.rfind("[")]
                        elif suffix.startswith("[") and ":" not in suffix:
                            name += suffix
                    name = ".".join(scopes + [name])
                    identity = (p[2], p[3])
                    if name in seen:
                        r.p.require(seen[name] == identity, "Conflicting declaration " + name)
                        duplicates.append(name)
                        continue
                    seen[name] = identity
                elif line.startswith("$enddefinitions"):
                    body = True
            dst.write(raw)
    r.p.prepare.save(path.with_name("normalization.json"), dict(raw_sha256=r.p.prepare.sha(path),
        normalized_sha256=r.p.prepare.sha(dest), removed_identical_declarations=duplicates,
        value_body_unchanged=True))
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("convert", "analyze"))
    parser.add_argument("--measurement", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    measurement, out = args.measurement.resolve(), args.out.resolve()
    r.p.require(measurement.is_relative_to(r.HERE) and out.is_relative_to(r.HERE), "Owned output only")
    if args.mode == "convert":
        convert(measurement, out)
    else:
        analyze(out)
