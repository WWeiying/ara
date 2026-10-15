#!/usr/bin/env python3
"""Bind original RNG bytes to measured source words and packed output coordinates."""
import sys
sys.dont_write_bytecode = True
import analyze_failure as f
r = f.r
rows = r.p.read(f.OUT / "raw_cycles.json")
A, M = r.ARA, r.MASK
# Exact NrLanes=4/EW8 shuffle_index table in the frozen ara_pkg.sv.
SHUFFLE = [0,8,16,24,4,12,20,28,2,10,18,26,6,14,22,30,
           1,9,17,25,5,13,21,29,3,11,19,27,7,15,23,31]
s, srca, srcb = 0xc274caf34727a125, [], []
for i in range(256):
    s ^= (s << 13) & ((1 << 64)-1)
    s ^= s >> 7
    s ^= (s << 17) & ((1 << 64)-1)
    srca.append(s & 255)
    srcb.append(srca[-1] if i % 8 == 0 else (s >> 19) & 255)


def word(source, first, lane):
    return sum(source[first+i] << (8*(SHUFFLE[i] % 8)) for i in range(32) if SHUFFLE[i] // 8 == lane)


lanes, all_issue, all_write = [], [], []
for lane in range(4):
    L = A + f".gen_lanes[{lane}].i_lane"
    Q, V = L + ".i_operand_requester", L + ".i_vfus.i_valu"
    commands, grants, inputs, issues, writes = [], [], [], [], []
    for x in rows:
        cycle = x["cycle"]
        if not 19203 <= cycle <= 19217:
            continue
        for q in (0,1,5):
            if x[Q+".operand_request_valid_i"] & x[Q+".operand_request_ready_o"] & (1 << q):
                commands.append(dict(cycle=cycle, q=q, **{n:x[Q+f".operand_request_i[{q}]."+n]
                    for n in ("id","vs","eew","vl","vstart")}))
            if x[Q+f".operand_requester_gnt[{q}]"]:
                grants.append(dict(cycle=cycle, q=q, address=x[Q+f".requester_metadata_q[{q}].addr"],
                    bank_bitmap=x[Q+f".operand_requester_gnt[{q}]"], bank_row=x[Q+f".operand_payload[{q}].addr"]))
            if q < 2 and x[L+".operand_queue_input_valid"] & (1 << q):
                ordinal = sum(v["q"] == q for v in inputs)
                actual = x[L+f".operand_queue_input[{q}]"]
                expected = word(srcb if q == 0 else srca, 64+32*ordinal, lane)
                r.p.require(actual == expected, "Queue input differs from source64+ordinal")
                inputs.append(dict(cycle=cycle, q=q, ordinal=ordinal, value_hex=f"{actual:016x}", source_first=64+32*ordinal))
        if x[V+".valu_valid"] and x[V+".alu_operand_valid_i"] == x[V+".alu_operand_ready_o"] == 3:
            ordinal = len(issues)
            aa, bb, result = (x[V+"."+n] for n in ("alu_operand_a","alu_operand_b","valu_result"))
            r.p.require(aa == word(srcb,64+32*ordinal,lane) and bb == word(srca,64+32*ordinal,lane), "VALU payload differs")
            for byte in range(8):
                r.p.require((result >> (8*byte)) & 1 == int(((aa >> (8*byte)) & 255) == ((bb >> (8*byte)) & 255)), "Wrong comparison bit")
            issues.append(dict(cycle=cycle, ordinal=ordinal, issue_cnt=x[V+".issue_cnt_q"],
                a_hex=f"{aa:016x}", b_hex=f"{bb:016x}", result_hex=f"{result:016x}"))
            all_issue.append(cycle)
        if x[Q+".masku_result_req"] and x[Q+".masku_result_gnt"]:
            writes.append(dict(cycle=cycle, address=x[Q+".masku_result_addr"],
                value=x[Q+".masku_result_wdata"], be=x[Q+".masku_result_be"]))
            all_write.append(cycle)
    r.p.require(len(issues) == 4 and len(writes) == 1 and len(inputs) == 8, "Unexpected stream length")
    r.p.require([g["address"] for g in grants if g["q"] == 0] == [66,67,68,69], "AluA origin mismatch")
    r.p.require([g["address"] for g in grants if g["q"] == 1] == [34,35,36,37], "AluB origin mismatch")
    lanes.append(dict(lane=lane, commands=commands, grants=grants, queue_inputs=inputs, valu_accepts=issues, final_writes=writes))
slices = []
for x in rows:
    if x[M+".in_ready_cnt_en"] and x[M+".masku_operand_alu_valid"] == x[M+".masku_operand_alu_ready"] == 15:
        first = x[M+".vrf_pnt_q"]
        compressed = x[M+".alu_result_compressed_seq"]
        for i in range(32):
            r.p.require((compressed >> (first+i)) & 1 == int(srca[64+first+i] == srcb[64+first+i]), "Compaction mismatch")
        slices.append(dict(cycle=x["cycle"], output_first=first, source_first=64+first,
            compressed_hex=f"{compressed:064x}", active_hex=f'{x[M+".result_queue_active_mask_seq"]:064x}'))
r.p.require([x["output_first"] for x in slices] == [0,32,64,96], "Bad slice coordinates")
result = bytes((lanes[SHUFFLE[i]//8]["final_writes"][0]["value"] >> (8*(SHUFFLE[i]%8))) & 255 for i in range(32))
wrong = [i for i in range(64,128) if ((result[i//8] >> (i%8)) & 1) != int(srca[i] == srcb[i])]
r.p.require(wrong and wrong[0] == 84 and max(all_issue) < min(all_write), "Failure/write timing differs")
finding = dict(status="MEASURED_SOURCE_ORIGIN64_OUTPUT_ORIGIN0", target_pc="0x80000508", target_vid=0,
    baseline_image_sha256=r.IMAGE_SHA, elf_sha256=r.p.prepare.sha(r.HERE / "prepared01/soc" / (f.c.NAME+".elf")),
    oracle84=dict(a=srca[84],b=srcb[84],expected=0), observed_source148=dict(a=srca[148],b=srcb[148],equal=1),
    first_active_wrong_bit=wrong[0], measured_active_wrong_bits=wrong, lanes=lanes, masku_slices=slices,
    first_misaligned_stream_coordinate=dict(output_ordinal=0, actual_source_element=64),
    bit84_coordinate=dict(valu_cycle=19211, lane=0, byte=5, zero_based_slice=2, masku_cycle=19213,
        vrf_pnt=64, source_element=148, final_write_cycle=19216, final_lane=2, final_byte=2, final_bit_in_byte=4),
    final_result_hex=result.hex(), queue_payload_matches_vrf_source=True, comparison_bits_correct_for_received_values=True,
    compaction_matches_received_bits=True, last_source_accept=max(all_issue), first_final_write=min(all_write),
    alias_early_write_excluded_for_this_case=True, raw_sha256=r.p.prepare.sha(f.OUT / "raw_cycles.json"),
    limitation="One unchanged genuine e8/m2 single. Does not prove all19 historical symptoms share a cause.")
r.p.prepare.save(f.OUT / "finding.json", finding)
print(finding["status"], "wrong", wrong, flush=True)
