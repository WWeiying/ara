#!/usr/bin/env python3
"""Resolve a bounded observation profile from a read-only Vivado inventory.

This produces a candidate connection map, not an ILA, a capture, or a diagnosis.
Every source must be revalidated in the synthesized checkpoint before insertion.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def bus(name, width):
    return [f"{name}[{bit}]" for bit in range(width)]


# Ordered low bit first. Keep request, response and final completion separate.
PORTS = {
    "ara_dispatcher": (
        ["clk_i", "rst_ni", "acc_req_i[req_valid]", "acc_resp_o[req_ready]",
         "acc_resp_o[resp_valid]", "acc_resp_o[exception][valid]",
         "ara_req_valid_o", "ara_req_ready_i", "ara_idle_i", "sldu_idle_i",
         "sldu_drain_o", "load_complete_i", "acc_resp_o[load_complete]"]
        + bus("acc_req_i[insn]", 32) + bus("acc_req_i[rs1]", 64)
        + bus("acc_req_i[trans_id]", 3) + bus("acc_resp_o[trans_id]", 3)
        + bus("ara_req_o[op]", 8) + bus("ara_req_o[vd]", 5)
        + bus("ara_req_o[vl]", 11) + bus("ara_req_o[vstart]", 11)
        + ["ara_req_o[token]"]
    ),
    "ara_sequencer": (
        ["pe_req_valid_o", "addrgen_ack_i", "ara_resp_valid_o"]
        + bus("pe_req_o[id]", 3) + bus("pe_req_o[op]", 8)
        + bus("pe_vinsn_running_o", 8)
    ),
    "addrgen": (
        ["mmu_req_o", "mmu_valid_i",
         "mmu_exception_i[valid]", "en_ld_st_translation_i", "core_st_pending_i",
         "axi_ar_valid_o", "axi_ar_ready_i", "axi_addrgen_req_valid_o",
         "ldu_axi_addrgen_req_ready_i", "idle_o"]
        # Only these low bits survived at this boundary; no invented upper bits.
        + bus("mmu_vaddr_o", 48) + bus("axi_ar_o[addr]", 48)
    ),
    "vldu": (
        ["axi_r_valid_i", "axi_r_ready_o",
         "load_complete_o", "idle_o", "ldu_current_burst_exception_o"]
        + bus("ldu_result_req_o", 4)
        + bus("ldu_result_gnt_i", 4) + bus("ldu_result_final_gnt_i", 4)
        + bus("pe_resp_o[vinsn_done]", 8)
    ),
    "load_store_unit": ["lsu_valid_i", "lsu_ready_o", "no_st_pending_o"],
    "lsu_bypass": ["lsu_ctrl_o[valid]", "pop_ld_i", "pop_st_i"],
    # The optimized VLDU/AddrGen consumer pins do not carry these signals.
    "vlsu": ["mmu_dtlb_hit_i", "axi_resp_i[r][last]"] + bus("axi_resp_i[r][resp]", 2),
    "ara_fpga_debug": bus("head_pc_i", 64) + bus("retire_count_i", 8) + ["soc_rst_ni"],
}
REGISTERS = {
    "ara_sequencer": [f"pe_vinsn_running_q_reg[{pe}][{vid}]"
                      for pe in range(8) for vid in range(8)],
    "addrgen": bus("state_q_reg", 3) + bus("axi_addrgen_state_q_reg", 2),
}
NETS = {
    "acc_dispatcher": bus("insn_pending_q", 8) + bus("insn_ready_q", 8),
    "ara_dispatcher": bus("state_q", 4),
    "ara_sequencer": (
        ["state_q", "addrgen_acked_q", "vinsn_running_full"]
        + [f"insn_queue_cnt_q[{fu}][{bit}]" for fu in range(6) for bit in range(3)]
        + [f"global_hazard_table_o[{row}][{bit}]" for row in range(8) for bit in range(8)]
    ),
    "vldu": (
        bus("vinsn_queue_q_reg[commit_cnt_n_0_]", 3)
        + bus("vinsn_queue_q_reg[issue_cnt_n_0_]", 3)
        + bus("commit_cnt_bytes_q", 11) + bus("issue_cnt_bytes_q", 11)
        + bus("result_queue_cnt_q", 2) + bus("result_final_gnt_q_reg_n_0_", 4)
        + [f"result_queue_valid_q_reg_n_0_[{slot}][{lane}]"
           for slot in range(2) for lane in range(4)]
    ),
    "load_store_unit": ["mmu_state_q"],
    "lsu_bypass": bus("status_cnt_q", 2),
}


def resolve(pin_rows, net_rows, ports=PORTS, nets=NETS,
            register_rows=(), registers=None):
    index = {}
    for source, rows in (("pin", pin_rows), ("net", net_rows), ("register", register_rows)):
        for row in rows:
            obj = row[{"pin": "object", "net": "net", "register": "register"}[source]]
            prefix = row["cell"] + "/"
            if not obj.startswith(prefix):
                raise ValueError(f"Object is outside its declared cell: {obj}")
            key = (source, row["kind"], obj[len(prefix):])
            index.setdefault(key, []).append(row)
    selected, missing = [], []
    for source, groups in (("pin", ports), ("net", nets), ("register", registers or {})):
        for kind, names in groups.items():
            for name in names:
                key = (source, kind, name)
                found = index.get(key, [])
                if len(found) != 1 or not found[0]["net"]:
                    missing.append({"source": source, "kind": kind, "name": name,
                                    "reason": "unconnected" if len(found) == 1
                                    else f"matched {len(found)} objects"})
                    continue
                selected.append({"source": source, "kind": kind, "name": name,
                                 "cell": found[0]["cell"], "net": found[0]["net"],
                                 "register_ref": found[0].get("ref") if source == "register" else None})
    # Net aliases (e.g. sign-extended PC bits) must not silently shorten a bus.
    # Store one physical probe bit and an explicit logical-bit mapping instead.
    physical_nets = []
    clock_nets = []
    bit_indices = {}
    for entry in selected:
        if entry["source"] == "pin" and entry["name"] == "clk_i":
            entry["role"] = "clock"
            clock_nets.append(entry["net"])
        else:
            entry["role"] = "data"
            if entry["net"] not in bit_indices:
                bit_indices[entry["net"]] = len(physical_nets)
                physical_nets.append(entry["net"])
            entry["probe_bit"] = bit_indices[entry["net"]]
    return {"schema": 2, "candidate_sources_resolved": not missing,
            "hardware_capture": False, "insertion_ready": False,
            "selected": selected, "missing": missing,
            "physical_nets": physical_nets, "clock_nets": clock_nets,
            "remaining_checks": [
                "Validate synthesized-checkpoint sources, register semantics and clock domains",
                "Insert observation only; implement and pass existing release gates",
                "Reproduce Linux stall and collect request/response/completion together"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--connections", type=Path,
                        help="Also emit a strictly delimited connection table for Vivado validation")
    args = parser.parse_args()
    paths = [args.inventory / name for name in ("inventory.tsv", "state_nets.tsv", "registers.tsv")]
    tables = []
    for path in paths:
        with path.open(newline="") as stream:
            tables.append(list(csv.DictReader(stream, delimiter="\t")))
    result = resolve(*tables[:2], register_rows=tables[2], registers=REGISTERS)
    result["inventory_sha256"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    if args.connections:
        if result["missing"]:
            parser.error("Refusing a connection table with unresolved sources")
        columns = ["source", "kind", "name", "cell", "net", "role", "probe_bit", "register_ref"]
        # Tcl consumes tab-separated fields without CSV quote interpretation.
        for row in result["selected"]:
            if any(any(c in str(row.get(key, "")) for c in '\t\r\n"') for key in columns):
                parser.error("Unsupported delimiter/quote in connection metadata")
        with args.connections.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, columns, delimiter="\t", extrasaction="ignore",
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(result["selected"])
    print(f"CANDIDATE_BITS {len(result['selected'])} MISSING {len(result['missing'])}")
    print(f"UNIQUE_DATA_NETS {len(result['physical_nets'])}")
    print("NOT_INSERTION_READY: no hardware state captured")
    return 0 if result["candidate_sources_resolved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
