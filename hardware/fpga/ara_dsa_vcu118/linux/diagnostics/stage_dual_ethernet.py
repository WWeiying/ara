#!/usr/bin/env python3
"""Stage a separate dual-DDR/Ethernet build from a hash-verified working image."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

PROFILE = "dual_ddr_ethernet"
WRAPPER = "rtl/board/dram_wrapper_xilinx.sv"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Source drift: " + old[:100])
    return text.replace(old, new, 1)


def transform(name, data):
    if name == WRAPPER:
        text = data.decode()
        text = replace_once(text, "`ifdef ARA_FPGA_ETHERNET\n  axi_dw_iw_req_t loader_req;",
                            "`ifdef ARA_FPGA_ETHERNET\n  if (Channel == 0) begin : gen_ethernet\n  axi_dw_iw_req_t loader_req;")
        text = replace_once(text, "    .mem_req_o(cdc_cut_req), .mem_rsp_i(cdc_cut_rsp), .status_o(loader_status)\n  );\n`else",
                            "    .mem_req_o(cdc_cut_req), .mem_rsp_i(cdc_cut_rsp), .status_o(loader_status)\n  );\n"
                            "  end else begin : gen_no_ethernet\n"
                            "    assign cdc_cut_req = cdc_ara_req;\n"
                            "    assign cdc_ara_rsp = cdc_cut_rsp;\n"
                            "    assign {eth_txp, eth_txn, eth_mdc, eth_phy_reset_n} = '0;\n"
                            "    assign eth_mdio = 1'bz;\n  end\n`else")
        return text.encode()
    if name == "rtl/board/ara_dsa_vcu118.sv":
        return replace_once(data.decode(), "      .Channel(1),", "      .Channel(1),").replace(
            "      .sys_rst_i(sys_rst), .soc_resetn_i(rst_n), .soc_clk_i(soc_clk),",
            "`ifdef ARA_FPGA_ETHERNET\n"
            "      .eth_ref_p(1'b0), .eth_ref_n(1'b0), .eth_rxp(1'b0), .eth_rxn(1'b0),\n"
            "      .eth_txp(), .eth_txn(), .eth_mdc(), .eth_phy_reset_n(), .eth_mdio(),\n"
            "`endif\n"
            "      .sys_rst_i(sys_rst), .soc_resetn_i(rst_n), .soc_clk_i(soc_clk),", 1).encode()
    if name.startswith(("scripts/", "constraints/", "software/", "ethernet/")) and name.endswith((".tcl", ".ps1", ".py")):
        text = data.decode()
        text = text.replace('$fpga_profile eq "dual_ddr"', '$fpga_profile in {dual_ddr dual_ddr_ethernet}')
        text = text.replace('$::fpga_profile eq "dual_ddr"', '$::fpga_profile in {dual_ddr dual_ddr_ethernet}')
        text = text.replace('$fpga_profile eq "host_ethernet"', '$fpga_profile in {host_ethernet dual_ddr_ethernet}')
        text = text.replace("'dual_ddr', 'host_ethernet')", "'dual_ddr', 'host_ethernet', 'dual_ddr_ethernet')")
        text = text.replace('{baseline host dual_ddr host_ethernet}', '{baseline host dual_ddr host_ethernet dual_ddr_ethernet}')
        text = text.replace("i_dram_wrapper/i_eth_loader", "i_dram_wrapper/gen_ethernet.i_eth_loader")
        if name == "scripts/config.tcl":
            # Two large MIG OOC runs must not compete with loader OOC on a 32 GB host.
            text = replace_once(text, "set run_jobs 4", "set run_jobs 1")
        return text.encode()
    return data


def stage(source, target):
    source = source.resolve(strict=True)
    target = target.absolute()
    if target.exists() or source == target or source in target.parents:
        raise ValueError("New output outside baseline required")
    inventory = (source / "SHA256SUMS").read_bytes()
    files, changes = {}, {}
    for row in inventory.decode().splitlines():
        expected, name = row.split("  ", 1)
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or name in files:
            raise ValueError("Unsafe/duplicate inventory path")
        before = (source / name).read_bytes()
        if sha(before) != expected:
            raise ValueError("Baseline hash mismatch: " + name)
        after = transform(name, before)
        files[name] = after
        if before != after:
            changes[name] = {"before": sha(before), "after": sha(after)}
    if WRAPPER not in changes or "scripts/config.tcl" not in changes:
        raise ValueError("Missing combined integration sources")
    if "provenance/mmu_ppn_fix.json" not in files:
        raise ValueError("Requires the repaired MMU baseline")
    record = {"profile": PROFILE, "source": str(source), "baseline_inventory": sha(inventory),
              "changes": changes, "board_modified": False,
              "memory": [{"base": "0x80000000", "bytes": "0x80000000"},
                         {"base": "0x100000000", "bytes": "0x80000000"}],
              "ethernet_download_bank": "C1 only; C2 accessed by CPU/JTAG",
              "hardware_validated": False}
    files["provenance/dual_ethernet.json"] = (json.dumps(record, indent=2) + "\n").encode()
    target.mkdir(parents=True)
    for name, data in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (target / "SHA256SUMS").write_text("".join(f"{sha(data)}  {name}\n" for name, data in sorted(files.items())))
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    stage(args.source, args.target)
