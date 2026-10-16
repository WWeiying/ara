#!/usr/bin/env python3
"""Check generated loader hardware metadata; not a timing or physical CDC signoff."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


PARAMETERS = {
    "mb": {"C_USE_ICACHE": "0", "C_USE_DCACHE": "0"},
    "cdma": {"C_M_AXI_DATA_WIDTH": "64", "C_INCLUDE_DRE": "1"},
    "mac": {"TXCSUM": "None", "RXCSUM": "None"},
}
PORTS = {
    "clock": {"clk_in1": "External_Ports_sys_clk", "reset": "External_Ports_sys_reset"},
    "mb": {"Clk": "clock_clk_out1", "Reset": "rst_clock_100M_mb_reset"},
    "rst_clock_100M": {"slowest_sync_clk": "clock_clk_out1",
                       "ext_reset_in": "External_Ports_sys_reset", "dcm_locked": "clock_locked"},
    "rst_ddr_300M": {"slowest_sync_clk": "External_Ports_ui_clk",
                     "ext_reset_in": "External_Ports_ui_reset"},
    "cdma": {"m_axi_aclk": "clock_clk_out1",
             "s_axi_lite_aresetn": "rst_clock_100M_peripheral_aresetn"},
    "dma": {"axi_resetn": "rst_clock_100M_peripheral_aresetn",
            "m_axi_sg_aclk": "External_Ports_ui_clk",
            "m_axi_mm2s_aclk": "External_Ports_ui_clk",
            "m_axi_s2mm_aclk": "External_Ports_ui_clk"},
    "ddr_fabric": {"aclk": "External_Ports_ui_clk", "aclk1": "clock_clk_out1",
                   "aresetn": "rst_ddr_300M_peripheral_aresetn"},
}


def check(root):
    modules = {m.get("INSTANCE"): m for m in root.findall(".//MODULE")}
    if any(m.get("MODTYPE", "").lower() == "ddr4" for m in modules.values()):
        raise ValueError("Loader XSA must not contain a private MIG")
    checks = 1
    for group, expectations, key in (("PARAMETERS/PARAMETER", PARAMETERS, "VALUE"),
                                      ("PORTS/PORT", PORTS, "SIGNAME")):
        for instance, expected in expectations.items():
            if instance not in modules:
                raise ValueError(f"Missing {instance}")
            actual = {p.get("NAME"): p.get(key) for p in modules[instance].findall(group)}
            for name, value in expected.items():
                if actual.get(name) != value:
                    raise ValueError(f"{instance}/{name}: {actual.get(name)!r} != {value!r}")
                checks += 1
    for instance, pin, frequency in (("clock", "clk_in1", "250000000"),
                                     ("mb", "Clk", "100000000"),
                                     ("ddr_fabric", "aclk", "300000000")):
        port = modules[instance].find(f"PORTS/PORT[@NAME='{pin}']")
        if port is None or port.get("CLKFREQUENCY") != frequency:
            raise ValueError(f"Unexpected {instance}/{pin} frequency")
        checks += 1
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xsa", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with zipfile.ZipFile(args.xsa) as archive:
        checks = check(ET.fromstring(archive.read("loader_bd.hwh")))
    report = {"state": "metadata_checked", "checks": checks,
              "xsa_sha256": hashlib.sha256(args.xsa.read_bytes()).hexdigest(),
              "physical_cdc_signoff": False, "board_validated": False}
    with args.out.open("x") as out:
        out.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
