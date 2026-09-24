#!/usr/bin/env python3
"""Inspect VCU118 J10 IP support in an isolated Vivado 2020.1 project."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
BOARD = HERE.parents[1] / "ara_dsa_vcu118/board_files/vcu118/2.4"
PART = "xcvu9p-flga2104-2L-e"
BOARD_PART = "xilinx.com:vcu118:part0:2.4"
PIN_LOCS = {
    "SGMII_TX_P": "AU21", "SGMII_TX_N": "AV21",
    "SGMII_RX_P": "AU24", "SGMII_RX_N": "AV24",
    "SGMIICLK_P": "AT22", "SGMIICLK_N": "AU22",
    "mdio_i": "AR23", "mdc": "AV23", "phy_rst_out": "BA21",
}
PRESET = {
    "CONFIG.lvdsclkrate": "625",
    "CONFIG.tx_in_upper_nibble": "false",
    "CONFIG.rxnibblebitslice0used": "false",
    "CONFIG.txlane0_placement": "DIFF_PAIR_2",
    "CONFIG.rxlane0_placement": "DIFF_PAIR_0",
}
# PG138 parameter names plus the bundled VCU118 board preset. The installed
# AXI Ethernet 7.2 schema must accept and echo each property. This candidate
# non-processor-mode core is not the final Ara integration contract.
CONFIG = {
    "CONFIG.PHY_TYPE": "SGMII", "CONFIG.ENABLE_LVDS": "true",
    "CONFIG.speed_1_2p5": "1G", "CONFIG.SupportLevel": "1",
    "CONFIG.processor_mode": "false", "CONFIG.ENABLE_AVB": "false",
    "CONFIG.Enable_1588": "false", "CONFIG.USE_BOARD_FLOW": "true",
    "CONFIG.ETHERNET_BOARD_INTERFACE": "sgmii_lvds",
    "CONFIG.MDIO_BOARD_INTERFACE": "mdio_mdc",
    "CONFIG.PHYRST_BOARD_INTERFACE": "phy_reset_out",
    "CONFIG.DIFFCLK_BOARD_INTERFACE": "sgmii_phyclk",
    **PRESET,
}
STAGES = (
    "console", "version", "project", "catalog", "create_ip", "configure",
    "license_before", "generate", "license_after", "example", "example_inventory",
)
UPLOAD_FILES = (
    "preflight.json", "requested_config.tsv", "stages.tsv", "preflight.rpt",
    "ip_status_before.rpt", "ip_status_after.rpt", "vivado.log",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def board_contract(directory):
    board = ET.parse(directory / "board.xml").getroot()
    fpga = board.find("./components/component[@name='part0']")
    phy = board.find("./components/component[@name='phy_onboard']")
    if fpga is None or fpga.get("part_name") != PART:
        raise ValueError("Board FPGA part differs from VCU118 contract")
    if phy is None or phy.get("part_name") != "DP83867ISRGZ":
        raise ValueError("Board PHY differs from DP83867ISRGZ")
    name = f"{board.get('vendor')}:{board.get('name')}:part0:{board.findtext('file_version')}"
    if name != BOARD_PART:
        raise ValueError(f"Unexpected board part {name}")
    expected_maps = {
        "sgmii_lvds": {"TXP": "SGMII_TX_P", "TXN": "SGMII_TX_N",
                       "RXP": "SGMII_RX_P", "RXN": "SGMII_RX_N"},
        "sgmii_phyclk": {"CLK_P": "SGMIICLK_P", "CLK_N": "SGMIICLK_N"},
        "mdio_mdc": {"MDIO_I": "mdio_i", "MDIO_O": "mdio_i",
                     "MDIO_T": "mdio_i", "MDC": "mdc"},
        "phy_reset_out": {"RESET": "phy_rst_out"},
    }
    for interface, expected in expected_maps.items():
        node = fpga.find(f"./interfaces/interface[@name='{interface}']")
        if node is None:
            raise ValueError(f"Missing board interface {interface}")
        ports = node.findall("./port_maps/port_map")
        observed = {p.get("logical_port"): [m.get("component_pin") for m in p.findall("./pin_maps/pin_map")]
                    for p in ports}
        if observed != {k: [v] for k, v in expected.items()}:
            raise ValueError(f"Board port mapping changed: {interface}")
    clock = fpga.find("./interfaces/interface[@name='sgmii_phyclk']/parameters/parameter[@name='frequency']")
    if clock is None or clock.get("value") != "625000000":
        raise ValueError("Expected PHY-provided 625 MHz reference clock")
    pins = {p.get("name"): dict(p.attrib) for p in ET.parse(directory / "part0_pins.xml").iter("pin")}
    for pin, loc in PIN_LOCS.items():
        if pins.get(pin, {}).get("loc") != loc:
            raise ValueError(f"Board pin mismatch: {pin} expected {loc}")
    preset = ET.parse(directory / "preset.xml").getroot().find(
        "./ip_preset[@preset_proc_name='sgmii_over_lvds_preset']/ip[@name='axi_ethernet']")
    if preset is None:
        raise ValueError("Missing AXI Ethernet board preset")
    parameters = {p.get("name"): p.get("value") for p in preset.iter("user_parameter")}
    if parameters != PRESET:
        raise ValueError("SGMII LVDS preset changed; review before generating IP")
    return {"part": PART, "board_part": name, "phy": phy.get("part_name"),
            "reference_clock_hz": 625000000, "interface": "SGMII over LVDS",
            "pins": {pin: pins[pin] for pin in PIN_LOCS}, "preset": parameters,
            "files_sha256": {n: digest(directory / n) for n in ("board.xml", "preset.xml", "part0_pins.xml")}}


def find_vivado(explicit):
    if explicit:
        result = shutil.which(explicit)
        if not result:
            raise ValueError(f"Vivado not found: {explicit}")
        return result
    known = Path("D:/Xilinx/Vivado/2020.1/bin/vivado.bat")
    if os.name == "nt" and known.is_file():
        return str(known)
    result = shutil.which("vivado")
    if not result:
        raise ValueError("Vivado not found; supply --vivado PATH (or use --static-only)")
    return result


def read_stages(output):
    path = output / "stages.tsv"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream, delimiter="\t"))
    result = {}
    for row in rows:
        if len(row) != 2 or row[0] not in STAGES or row[1] not in ("PASS", "FAIL", "SKIP") or row[0] in result:
            raise ValueError(f"Malformed stage record: {row}")
        result[row[0]] = row[1]
    return result


def assess_mac_license(content):
    """Read the Vivado 2020.1 table, including blank continuation cells."""
    header = ["Instance Name", "Target", "Required License",
              "Generated License Level", "Available License Level"]
    in_table = False
    instance = target = ""
    rows = []
    for fields in csv.reader(content.splitlines(), delimiter="|"):
        if len(fields) != 7 or fields[0].strip() or fields[-1].strip():
            continue
        fields = [field.strip() for field in fields[1:-1]]
        if fields == header:
            in_table = True
            instance = target = ""
            continue
        if not in_table:
            continue
        if fields[0]:
            instance, target = fields[:2]
        elif fields[1]:
            target = fields[1]
        required, generated, available = fields[2:]
        # AVB is disabled in CONFIG. Its separate table entries must not be
        # mistaken for the required TEMAC feature's hardware license level.
        if instance == "eth_j10" and target == "Synthesis" and required.startswith("tri_mode_eth_mac@"):
            rows.append({"required": required, "generated": generated, "available": available})
    state = "unverified"
    if rows:
        generated = {row["generated"] for row in rows}
        available = {row["available"] for row in rows}
        if "Design_Linking" in generated | available:
            state = "blocked_design_linking"
        elif generated | available <= {"Full", "Bought", "Purchased"}:
            state = "full_reported_not_bitstream_verified"
        elif generated | available <= {"Full", "Bought", "Purchased", "Hardware_Evaluation"}:
            state = "evaluation_reported_not_bitstream_verified"
    return {"state": state, "synthesis_rows": rows, "bitstream_verified": False}


def diagnose_reports(output):
    license_path = output / "ip_status_after.rpt"
    log_path = output / "vivado.log"
    license_text = license_path.read_text(encoding="utf-8-sig", errors="replace") if license_path.is_file() else ""
    log = log_path.read_text(encoding="utf-8-sig", errors="replace") if log_path.is_file() else ""
    report_path = output / "preflight.rpt"
    report = report_path.read_text(encoding="utf-8-sig", errors="replace") if report_path.is_file() else ""
    return {
        "license_stage_pass_means_report_generated_only": True,
        "temac_license": assess_mac_license(license_text),
        "stdout_channel_error_observed": 'can not find channel named "stdout"' in log + report,
    }


def upload(output):
    from host_axi_upload import git, package, publish
    files = [(output / name, name) for name in UPLOAD_FILES if (output / name).is_file()]
    if any(source.is_symlink() for source, _ in files):
        raise ValueError("Refusing symlink in evidence")
    root = Path(git(HERE, "rev-parse", "--show-toplevel"))
    remote = git(root, "remote", "get-url", "--push", "origin")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    branch = f"fpga-evidence/ethernet-{stamp}-{uuid.uuid4().hex[:8]}"
    bundle = Path(tempfile.mkdtemp(prefix="ara_eth_evidence_"))
    metadata = {"diagnostic_only": True, "hardware_access": False,
                "collection_checkout_commit": git(root, "rev-parse", "HEAD"),
                "evidence_branch": branch, "source": str(output),
                "note": "IP preflight only, not an Ethernet or bitstream acceptance test."}
    package(files, bundle, metadata)
    print(f"BUNDLE {bundle}", flush=True)
    print("Uploading diagnostic reports/logs only, not generated IP or license files.", flush=True)
    commit = publish(bundle, remote, branch, message="Collect VCU118 Ethernet IP preflight")
    print(f"UPLOADED_BRANCH {branch}\nUPLOADED_COMMIT {commit}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado", help="Vivado executable (auto-detects D:/Xilinx/Vivado/2020.1)")
    parser.add_argument("--out", type=Path, help="New evidence directory, must not already exist")
    parser.add_argument("--static-only", action="store_true", help="Check bundled board XML only; do not run Vivado")
    parser.add_argument("--upload", action="store_true", help="Upload reports/logs, including failures, to isolated origin branch")
    args = parser.parse_args(argv)
    output = None
    record = {"diagnostic_only": True, "hardware_access": False, "hardware_verified": False,
              "bitstream_license_verified": False, "state": "incomplete", "stages": {},
              "started_utc": datetime.now(timezone.utc).isoformat(), "static_only": args.static_only}
    code = 1
    try:
        if args.out:
            path = args.out.resolve()
            path.mkdir(parents=True, exist_ok=False)
            output = path
        else:
            # Keep Windows IP paths short, outside the checkout and existing runs.
            parent = Path("D:/fpga_runs") if os.name == "nt" and Path("D:/").is_dir() else Path(tempfile.gettempdir())
            parent.mkdir(parents=True, exist_ok=True)
            output = Path(tempfile.mkdtemp(prefix="ara_eth_", dir=parent))
        print(f"EVIDENCE {output}", flush=True)
        record["board"] = board_contract(BOARD)
        record["requested_config"] = CONFIG
        script = HERE / "host_ethernet_preflight.tcl"
        record["tools_sha256"] = {p.name: digest(p) for p in (Path(__file__), script)}
        with (output / "requested_config.tsv").open("w", encoding="ascii", newline="") as stream:
            writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
            for key, value in CONFIG.items():
                if not all(re.fullmatch(r"[A-Za-z0-9_.]+", s) for s in (key, value)):
                    raise ValueError("Unsafe configuration token")
                writer.writerow((key, value))
        if args.static_only:
            record["state"] = "static_board_checked_not_ip_verified"
            code = 0
        else:
            # Vivado 2020.1's board repository parser rejected a Tcl list made
            # from Windows backslashes. Use native argv quoting, but Tcl paths.
            command = [find_vivado(args.vivado), "-mode", "batch", "-notrace", "-nojournal",
                       "-log", (output / "vivado.log").as_posix(),
                       "-source", script.as_posix(), "-tclargs", output.as_posix(), BOARD.parents[1].as_posix()]
            record["command"] = command
            record["logging_mode"] = "inherited_console_with_vivado_native_log"
            print("Generating isolated IP/example only; no Ara project, synthesis, routing or board access.", flush=True)
            print(f"Vivado log: {output / 'vivado.log'}", flush=True)
            # Keep Windows console handles intact; let Vivado own its log file.
            # Whether redirection caused the example's stdout error still needs
            # a real Windows run. Tcl records channel checks on both sides.
            print("Vivado output follows; keep this console open until completion.", flush=True)
            process = subprocess.run(command, cwd=output, check=False)
            record["vivado_exit_code"] = process.returncode
            record["diagnostics"] = diagnose_reports(output)
            record["stages"] = read_stages(output)
            report = (output / "preflight.rpt").read_text(encoding="utf-8", errors="replace")
            complete = "PREFLIGHT_COMPLETE" in report.splitlines()
            all_pass = record["stages"] == dict.fromkeys(STAGES, "PASS")
            if process.returncode or not complete or not all_pass:
                raise RuntimeError("IP preflight incomplete/failed; inspect stages.tsv, preflight.rpt and vivado.log")
            if record["diagnostics"]["stdout_channel_error_observed"]:
                raise RuntimeError("stdout channel error observed despite stage results; inspect Vivado and Tcl reports")
            for name in ("ip_status_before.rpt", "ip_status_after.rpt"):
                if not (output / name).is_file() or (output / name).stat().st_size == 0:
                    raise RuntimeError(f"Missing IP status report: {name}")
            if record["diagnostics"]["temac_license"]["state"] == "blocked_design_linking":
                raise RuntimeError("TEMAC is Design_Linking only in generated or available license level; "
                                   "IP generation is not hardware authorization")
            record["state"] = "ip_example_generated_needs_license_and_constraints_review"
            code = 0
    except (OSError, ValueError, RuntimeError, ET.ParseError) as exc:
        record.update(state="failed", error=str(exc))
        print(f"FAILED: {exc}", file=sys.stderr)
    finally:
        if output is not None:
            (output / "preflight.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if output is not None:
        for stage, state in record["stages"].items():
            print(f"{stage}: {state}")
        print(f"STATE {record['state']}\nEVIDENCE {output}", flush=True)
        if "diagnostics" in record:
            diagnostics = record["diagnostics"]
            print("License-stage PASS means report generation only, not hardware authorization.")
            print(f"TEMAC_LICENSE {diagnostics['temac_license']['state']}")
            if diagnostics["temac_license"]["state"] == "blocked_design_linking":
                print("HARDWARE BLOCKER: TEMAC Design_Linking is not a hardware license. "
                      "Do not proceed to board integration on this evidence.")
            if diagnostics["stdout_channel_error_observed"]:
                print("TOOL ERROR: stdout channel error observed; example generation is not validated. "
                      "This is separate from the license assessment.")
        print("No hardware validation or full bitstream license approval has been established.", flush=True)
        if args.upload:
            try:
                upload(output)
            except (OSError, ValueError, RuntimeError) as exc:
                print(f"UPLOAD FAILED: {exc}; local evidence retained at {output}", file=sys.stderr)
                return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
