#!/usr/bin/env python3
"""Resolve scalar/cache/MMU observations from frozen netlist inventories."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from plan_stall_observation import resolve


def members(names, base):
    return sorted(n for n in names if n == base or
                  re.fullmatch(re.escape(base) + r"(?:\[\d+\])+", n))


def build(pins, registers, modules, previous):
    pins = [dict(row) for row in pins]
    registers = [dict(row) for row in registers]
    ports, regs = {}, {}
    for row in pins:
        row["object"] = row["pin"]
    for row in registers:
        row["net"] = row["q_net"]
    by_kind = {}
    for row in pins:
        by_kind.setdefault(row["kind"], []).append(
            row["pin"].removeprefix(row["cell"] + "/"))

    def select(kind, *groups):
        for group in groups:
            found = members(by_kind.get(kind, []), group)
            if not found:
                raise ValueError(f"Missing required port group {kind}/{group}")
            ports.setdefault(kind, []).extend(found)

    select("lsu", "clk_i", "rst_ni", "lsu_valid_i", "lsu_ready_o",
           "commit_tran_id_i", "commit_i", "commit_ready_o", "flush_i",
           "dcache_wbuffer_empty_i", "dcache_wbuffer_not_ni_i",
           "acc_mmu_req_i[acc_mmu_req]", "acc_mmu_resp_o[acc_mmu_valid]",
           "acc_mmu_resp_o[acc_mmu_dtlb_hit]", "acc_mmu_resp_o[acc_mmu_exception][valid]")
    select("bypass", "lsu_ctrl_o[valid]", "lsu_ctrl_o[vaddr]", "lsu_ctrl_o[fu]",
           "lsu_ctrl_o[operation]", "lsu_ctrl_o[trans_id]", "lsu_req_valid_i",
           "pop_ld_i", "pop_st_i")
    select("load", "valid_i", "valid_o", "trans_id_o", "translation_req_o",
           "dtlb_hit_i", "dtlb_ppn_i", "paddr_i", "ex_i[valid]", "ex_i[cause]",
           "page_offset_matches_i", "store_buffer_empty_i")
    select("store", "valid_i", "valid_o", "translation_req_o", "dtlb_hit_i",
           "ex_i[valid]", "store_buffer_empty_o", "stall_st_pending_i")
    for kind in ("load", "store"):
        select(kind, "req_port_o[data_req]", "req_port_o[data_id]",
               "req_port_o[kill_req]", "req_port_o[tag_valid]",
               "req_port_i[data_gnt]", "req_port_i[data_rvalid]", "req_port_i[data_rid]")

    classes = set()
    for module in modules:
        kind, ref = module["kind"], module["ref"]
        if ref.startswith("wt_dcache_ctrl"):
            classes.add("cache_ctrl")
            select(kind, "req_port_i[data_req]", "req_port_i[data_id]",
                   "req_port_i[kill_req]", "req_port_i[tag_valid]",
                   "req_port_o[data_gnt]", "req_port_o[data_rvalid]", "req_port_o[data_rid]",
                   "miss_req_o", "miss_ack_i", "miss_replay_i", "miss_rtrn_vld_i",
                   "rd_req_o", "rd_ack_i")
        elif ref.startswith("wt_dcache_missunit"):
            classes.add("missunit")
            select(kind, "miss_req_i", "miss_ack_o", "miss_replay_o", "miss_rtrn_vld_o",
                   "mem_data_req_o", "mem_data_ack_i", "mem_rtrn_vld_i",
                   "busy_o", "wbuffer_empty_i", "tx_vld_i")
        elif ref.startswith(("ptw", "cva6_ptw")):
            classes.add("ptw")
            # All scalar control ports; omit address and PTE payload arrays here.
            for name in by_kind[kind]:
                if "[" not in name and name not in {"clk_i", "rst_ni"}:
                    ports.setdefault(kind, []).append(name)
            select(kind, "req_port_o[data_req]", "req_port_o[kill_req]",
                   "req_port_o[tag_valid]", "req_port_o[address_index]",
                   "req_port_o[address_tag]", "req_port_i[data_gnt]",
                   "req_port_i[data_rvalid]", "req_port_i[data_rdata]", "shared_tlb_update_o[valid]")
    if classes != {"cache_ctrl", "missunit", "ptw"}:
        raise ValueError(f"Missing downstream modules: {classes}")

    for row in registers:
        name = row["register"].removeprefix(row["cell"] + "/")
        if re.fullmatch(r"(?:FSM_sequential_)?(?:state_q|mmu_state_q|status_cnt_q|ldbuf_valid_q|ldbuf_last_id_q)_reg(?:\[\d+\])*", name):
            regs.setdefault(row["kind"], []).append(name)
        elif re.fullmatch(r"(?:commit|speculative)_status_cnt_q_reg\[\d+\]", name):
            regs.setdefault(row["kind"], []).append(name)
        elif re.fullmatch(r"(?:commit|speculative)_queue_q_reg\[\d+\]\[valid\]", name):
            regs.setdefault(row["kind"], []).append(name)
    for kind in ("lsu", "bypass", "load", "store"):
        if not regs.get(kind):
            raise ValueError(f"Missing state registers: {kind}")
    for module in modules:
        if module["ref"].startswith(("wt_dcache_ctrl", "wt_dcache_missunit", "ptw", "cva6_ptw")):
            if not regs.get(module["kind"]):
                raise ValueError(f"Missing downstream FSM: {module['cell']}")

    wanted = {
        "ara_dispatcher": {"acc_req_i[req_valid]", "acc_resp_o[req_ready]", "acc_req_i[insn]"},
        "addrgen": {"mmu_req_o", "mmu_valid_i", "mmu_exception_i[valid]", "axi_ar_valid_o", "axi_ar_ready_i"},
        "vlsu": {"mmu_dtlb_hit_i"},
    }
    for row in previous["selected"]:
        if row["source"] != "pin":
            continue
        if any(members([row["name"]], group) for group in wanted.get(row["kind"], set())):
            pins.append(dict(row, object=row["cell"] + "/" + row["name"]))
            ports.setdefault(row["kind"], []).append(row["name"])
    for kind in wanted:
        if not ports.get(kind):
            raise ValueError(f"Missing vector anchor: {kind}")
    # These exact unused/optimized boundary pins have no net. Never invent zeros.
    allowed = {
        ("lsu", "acc_mmu_resp_o[acc_mmu_dtlb_hit]"),
        ("bypass", "lsu_ctrl_o[operation][7]"),
        ("store", "req_port_o[data_id][0]"),
        ("store", "req_port_o[kill_req]"), ("store", "req_port_o[tag_valid]"),
    }
    for module in modules:
        kind, ref, cell = module["kind"], module["ref"], module["cell"]
        if ref.startswith(("ptw", "cva6_ptw")):
            allowed.update((kind, n) for n in (
                "ptw_err_at_g_int_st_o", "ptw_error_at_g_st_o", "req_port_o[kill_req]",
                "req_port_o[address_index][0]", "req_port_o[address_index][1]", "req_port_o[address_index][2]"))
        if cell.endswith("gen_rd_ports[0].i_wt_dcache_ctrl"):
            allowed.add((kind, "req_port_o[data_rid][0]"))
        if cell.endswith("gen_rd_ports[2].i_wt_dcache_ctrl"):
            allowed.update((kind, n) for n in ("req_port_o[data_gnt]", "req_port_o[data_rvalid]", "req_port_o[data_rid][0]"))
        if ref.startswith("wt_dcache_missunit"):
            allowed.add((kind, "miss_replay_o[3]"))
    unavailable = []
    for row in pins:
        name = row["object"].removeprefix(row["cell"] + "/")
        if not row["net"] and (row["kind"], name) in allowed:
            if name in ports.get(row["kind"], []):
                ports[row["kind"]].remove(name)
                unavailable.append(dict(kind=row["kind"], name=name, reason="unconnected_not_sampled_not_zero"))
    result = resolve(pins, [], ports, {}, registers, regs)
    if result["missing"] or len(result["physical_nets"]) > 1024:
        raise ValueError(f"Invalid profile: missing={result['missing']} width={len(result['physical_nets'])}")
    result["profile"] = "scalar_cache_mmu_stall"
    result["unavailable"] = unavailable
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("previous_bindings", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    paths = [args.inventory / n for n in ("pins.tsv", "registers.tsv", "modules.tsv")]
    tables = []
    for path in paths:
        with path.open(newline="") as stream:
            tables.append(list(csv.DictReader(stream, delimiter="\t")))
    result = build(*tables, json.loads(args.previous_bindings.read_text()))
    result["inventory_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in paths + [args.previous_bindings]}
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "bindings.json").write_text(json.dumps(result, indent=2) + "\n")
    columns = ["source", "kind", "name", "cell", "net", "role", "probe_bit", "register_ref"]
    with (args.output / "connections.tsv").open("w", newline="") as stream:
        for row in result["selected"]:
            if any(any(c in str(row.get(key, "")) for c in '\t\r\n"') for key in columns):
                raise ValueError("Invalid Tcl table field")
        writer = csv.DictWriter(stream, columns, delimiter="\t", extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(result["selected"])
    print(f"CANDIDATE width={len(result['physical_nets'])} not_implemented_not_captured")


if __name__ == "__main__":
    main()
