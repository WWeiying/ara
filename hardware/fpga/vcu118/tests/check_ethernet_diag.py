#!/usr/bin/env python3
"""Bounded diagnostic RTL regression using hash-verified vendor example FIFOs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from check_ethernet_example_ctrl import EVIDENCE_COMMIT, verify_bundle
from host_ethernet_build import HERE, SOURCE, VENDOR
from host_ethernet_preflight import digest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="New directory only")
    args = parser.parse_args(argv)
    try:
        iverilog, vvp = shutil.which("iverilog"), shutil.which("vvp")
        if not iverilog or not vvp:
            raise ValueError("Put iverilog and vvp on PATH; no Vivado or hardware required")
        archive = subprocess.check_output(["git", "show", EVIDENCE_COMMIT + ":evidence.zip"], cwd=HERE, timeout=30)
        manifest = json.loads(subprocess.check_output(
            ["git", "show", EVIDENCE_COMMIT + ":manifest.json"], cwd=HERE, timeout=30))
        files = verify_bundle(archive, manifest)
        if args.out:
            output = args.out.resolve()
            output.mkdir(parents=True, exist_ok=False)
        else:
            output = Path(tempfile.mkdtemp(prefix="ara_eth_diag_sim_"))
        print("EVIDENCE", output, flush=True)
        sources = [HERE / "ethernet_diag_tb.sv", SOURCE / "rtl/eth_diag_echo.sv", SOURCE / "rtl/eth_diag_reset.sv"]
        for name, expected in VENDOR.items():
            path = output / name
            path.write_bytes(files["example/imports/" + name])
            if digest(path) != expected:
                raise ValueError("Unreviewed vendor source: " + name)
            if name not in ("eth_j10_support.v", "eth_j10_clocks_resets.v"):
                sources.append(path)
        commands = [[iverilog, "-g2012", "-s", "ethernet_diag_tb", "-o", str(output / "sim"), *map(str, sources)],
                    [vvp, str(output / "sim")]]
        for stage, command in zip(("compile", "simulation"), commands):
            result = subprocess.run(command, cwd=output, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, timeout=30)
            (output / (stage + ".log")).write_text(result.stdout, encoding="utf-8")
            if result.returncode:
                raise RuntimeError(stage + " failed: " + result.stdout)
        if "PASS: PHY timer" not in result.stdout:
            raise RuntimeError("Missing final testbench assertions")
        record = {"state": "diagnostic_rtl_tests_passed_not_hardware_verification", "hardware_verified": False,
                  "evidence_commit": EVIDENCE_COMMIT, "commands": commands,
                  "sources_sha256": {str(p): digest(p) for p in sources},
                  "scope": "Reviewed RX/TX FIFOs, diagnostic echo and reset timer; behavioral MAC stream/FDRE. "
                           "Not encrypted MAC/PCS, MDIO, JTAG IP, analog PHY, top clocking or timing verification."}
        (output / "report.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(result.stdout, end="")
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        print("FAILED:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
