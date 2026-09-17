#!/usr/bin/env python3
"""Static FPGA hierarchy check; proprietary Xilinx IP is not modeled here."""
import argparse
import json
from pathlib import Path
import sys

from pyslang.driver import Driver
from pyslang import Diags, DiagnosticSeverity
from collections import Counter

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("package", type=Path)
parser.add_argument("--allow-vendor-ip", action="store_true",
                    help="Allow only the exact expected unelaborated Vivado IP/primitives")
args = parser.parse_args()
root = args.package.resolve()
manifest = json.loads((root / "manifest.json").read_text())
driver = Driver()
driver.addStandardArgs()
driver.setTerminalColorsEnabled(False)
argv = ["slang", "--top", manifest["top"], "--single-unit", "-DSYNTHESIS", "--error-limit=100",
        "--translate-off-format=pragma,translate_off,translate_on",
        "--translate-off-format=synopsys,translate_off,translate_on",
        "--translate-off-format=synthesis,translate_off,translate_on",
        "--allow-use-before-declare", "--relax-enum-conversions",
        "-Wno-range-width-oob"]
for name, value in manifest["defines"].items():
    argv.append("-D" + name + ("" if value is None else "=" + str(value)))
argv.extend("-I" + str(root / path) for path in manifest["include_dirs"])
argv.extend(str(root / path) for path in manifest["files"])
command = " ".join('"' + arg + '"' for arg in argv)
if not driver.parseCommandLine(command) or not driver.processOptions():
    sys.exit(2)
if not driver.parseAllSources():
    driver.reportParseDiags()
    sys.exit(2)
compilation = driver.createCompilation()
driver.reportCompilation(compilation, True)
instances = Counter()
prefix = "ara_dsa_vcu118.i_cheshire_soc.gen_cva6_cores[0]."
paths = [prefix + "i_core_cva6", prefix + "gen_ara.i_ara"]
paths += [prefix + f"gen_ara.i_ara.gen_lanes[{i}].i_lane" for i in range(4)]
paths += [prefix + "gen_ara.i_ara.i_vlsu." + name for name in ("i_qbs_engine", "i_akv_engine")]
payload_rams = []
payload_widths = {}
for bank in range(2):
    payload = (prefix + "gen_ara.i_ara.i_vlsu.i_qbs_engine.i_compute_engine."
               + f"i_block_adapter_bank{bank}.i_payload_buffer")
    paths.append(payload)
    for plane in range(3):
        for row in range(4):
            ram = payload + f".gen_plane[{plane}].gen_row[{row}].i_payload"
            paths.append(ram)
            payload_rams.append(ram)
            payload_widths[ram] = 256 if plane == 2 else 128
for path in paths:
    symbol = compilation.getRoot().lookupName(path)
    if symbol is None:
        raise RuntimeError(f"Missing required hardware instance {path}")
    instances[symbol.definition.name] += 1
required = {"cva6": 1, "ara": 1, "lane": 4, "qbs_engine": 1, "akv_engine": 1,
            "qbs_payload_buffer": 2, "qbs_payload_sram": 24}
for name, count in required.items():
    if instances[name] != count:
        raise RuntimeError(f"Expected {count} {name} instances, got {instances[name]}")
for ram in payload_rams:
    wrapper = compilation.getRoot().lookupName(ram + ".i_sram")
    if wrapper is None or wrapper.definition.name != "tc_sram":
        raise RuntimeError(f"QBS payload must use FPGA tc_sram, not an ASIC macro: {ram}")
    for port in ("wdata_i", "rdata_o"):
        symbol = compilation.getRoot().lookupName(ram + "." + port)
        if symbol is None or symbol.type.bitWidth != payload_widths[ram]:
            raise RuntimeError(f"Unexpected QBS payload width: {ram}.{port}")
print("Required hierarchy: " + json.dumps({k: instances[k] for k in required}, sort_keys=True))
print("QBS payload: 16 weight SRAMs x 128 bits, 8 activation SRAMs x 256 bits")
# Keep the focused synthesis/simulation probe tied to real elaborated AXI types,
# not to endpoint counts after Vivado constant propagation.
cdc = "ara_dsa_vcu118.i_dram_wrapper.gen_cdc.i_axi_cdc_mig"
for channel, side, width in (("w", "src", 579), ("r", "dst", 525)):
    path = f"{cdc}.i_axi_cdc_{side}.i_cdc_fifo_gray_src_{channel}.src_data_i"
    symbol = compilation.getRoot().lookupName(path)
    if symbol is None or symbol.type.bitWidth != width:
        raise RuntimeError(f"DDR FIFO {channel} payload changed; update/review the probe: {path}")
    print(f"DDR FIFO {channel}: {width} bits (packed AXI struct)")
vendor = {"BUFGMUX", "LUT5", "xpm_memory_spram", "xpm_memory_tdpram", "ddr4", "IBUFDS",
          "clkwiz", "vio", "STARTUPE3"}
errors, external = [], set()
for diag in compilation.getAllDiagnostics():
    severity = driver.diagEngine.getSeverity(diag.code, diag.location)
    if severity not in (DiagnosticSeverity.Error, DiagnosticSeverity.Fatal):
        continue
    if diag.code == Diags.UnknownModule and str(diag.args[0]) in vendor:
        external.add(str(diag.args[0]))
    else:
        errors.append(str(diag.code))
okay = driver.reportDiagnostics(True)
if args.allow_vendor_ip and not errors:
    print("STATIC RTL CHECK: no non-vendor elaboration errors")
    print("NOT ELABORATED (Vivado required): " + ", ".join(sorted(external)))
    sys.exit(0)
sys.exit(0 if okay else 1)
