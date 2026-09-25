#!/usr/bin/env python3
"""Program the isolated J10 diagnostic image or restore the archived Ara image."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


DEFAULT_BUILD = Path("D:/fpga_runs/ara_eth_build_nc1cwrm8")
DEFAULT_RESTORE = Path("D:/fpga_runs/ara_20260923_125216_228b9d4f9525/bitstream_host")
RESTORE_HASHES = {
    "ara_dsa_vcu118.bit": "bb3eee0dc3469097e39be7ab042049763250f9ef0357713290071c458cbfc2a9",
    "ara_dsa_vcu118.ltx": "201c121c270cb1c6be404a197a88bacb81abed5c8afaf4b5be3625eb1ca1c180",
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_files(directory, expected):
    for name, fingerprint in expected.items():
        path = directory / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or linked image file: {path}")
        if sha256(path) != fingerprint.lower():
            raise ValueError(f"Image SHA256 mismatch: {path}")


def checked_build(directory):
    record = json.loads((directory / "build.json").read_text(encoding="utf-8"))
    if record.get("state") != "built_needs_manual_review_and_board_test" or not record.get(
        "full_license_bitstream_generated"
    ):
        raise ValueError("Diagnostic build has not passed bitgen/license gates")
    expected = {}
    for name in ("eth_diag.bit", "eth_diag.ltx"):
        expected[name] = record["artifacts"][name]["sha256"]
    verify_files(directory, expected)
    return directory / "eth_diag.bit", directory / "eth_diag.ltx"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program-confirmed", action="store_true", help="Acknowledge that this replaces the running FPGA image")
    parser.add_argument("--restore", action="store_true", help="Restore the archived Ara host image")
    parser.add_argument("--check-only", action="store_true", help="Read the running diagnostic image without programming")
    parser.add_argument("--build", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--rollback", type=Path, default=DEFAULT_RESTORE)
    parser.add_argument("--vivado", default="D:/Xilinx/Vivado/2020.1/bin/vivado.bat")
    parser.add_argument("--server", default="localhost:3121")
    parser.add_argument("--out", type=Path, required=True, help="New evidence directory")
    args = parser.parse_args(argv)
    if args.restore and args.check_only:
        parser.error("--restore and --check-only are mutually exclusive")
    if not args.program_confirmed and not args.check_only:
        parser.error("--program-confirmed is required")
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"mode": "restore" if args.restore else ("check" if args.check_only else "diagnostic"),
              "started_utc": datetime.now(timezone.utc).isoformat(), "state": "not_programmed"}
    code = 1
    try:
        verify_files(args.rollback.resolve(), RESTORE_HASHES)
        if args.restore:
            bit = args.rollback.resolve() / "ara_dsa_vcu118.bit"
            probes = args.rollback.resolve() / "ara_dsa_vcu118.ltx"
        else:
            bit, probes = checked_build(args.build.resolve())
        report.update(bit=str(bit), bit_sha256=sha256(bit), probes=str(probes), probes_sha256=sha256(probes))
        script = Path(__file__).with_suffix(".tcl").resolve()
        command = [args.vivado, "-mode", "batch", "-notrace", "-nojournal", "-log", str(output / "vivado.log"), "-source", str(script), "-tclargs", str(bit), str(probes), report["mode"], args.server]
        report["command"] = command
        print("BOARD_ACTION", report["mode"], "EVIDENCE", output, flush=True)
        with (output / "console.log").open("w", encoding="utf-8") as log:
            run = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT,
                                 timeout=600, check=False)
        report["vivado_exit_code"] = run.returncode
        console = (output / "console.log").read_text(encoding="utf-8", errors="replace")
        for line in console.splitlines():
            if line.startswith(("TARGET ", "PROGRAMMED ", "CHECK_ONLY ", "STATUS_", "MANAGEMENT_AXI ", "DIAGNOSTIC_BASELINE_PASS", "RESTORE_PROGRAMMED", "ETH_BOARD_ERROR ")):
                print(line, flush=True)
        if run.returncode == 0 and ("RESTORE_PROGRAMMED" if args.restore else "DIAGNOSTIC_BASELINE_PASS") in console:
            report["state"] = "restored_not_software_verified" if args.restore else "diagnostic_baseline_pass_packet_test_pending"
            code = 0
        else:
            report["state"] = "read_only_check_failed" if args.check_only else (
                "programmed_but_check_failed" if f"PROGRAMMED {report['mode']}" in console else "programming_failed_or_unknown")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        report["error"] = str(exc)
        print("FAILED", exc, file=sys.stderr)
    finally:
        (output / "board_probe.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("STATE", report["state"], "EVIDENCE", output, flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
