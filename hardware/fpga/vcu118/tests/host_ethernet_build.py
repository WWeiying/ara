#!/usr/bin/env python3
"""Build an isolated J10 diagnostic image; never connect to/program the board."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

import host_ethernet_preflight as preflight
from host_ethernet_review import collect


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "ethernet"
STAGES = ("project", "ip", "sources", "synthesis", "implementation", "reports", "gates", "bitstream")
# Exact reviewed integration files, copied locally with notices intact. No vendor
# implementation HDL, unsafe demo controller or example location XDC is imported.
VENDOR = {
    "eth_j10_support.v": "0ad02b835aedcdb3eabe45cf82d7d3dafc97901ce1d760fbd6567977779c0072",
    "eth_j10_clocks_resets.v": "4513fa5f359e774324da3e5c3f6dc160dcdf603fd29e73cbc3e8a4e5c336b451",
    "eth_j10_ten_100_1g_eth_fifo.v": "cf337af68d893cfb8aee6cfd8b7e110f3a97a86ab604f6d58803b9f9c945a247",
    "eth_j10_rx_client_fifo.v": "b438ff3acff186ca0eb2bd426febee2bda0e22872e6a40b531b18eb1df3b4389",
    "eth_j10_tx_client_fifo.v": "5d3dc97ef0bc6e275dcb2c2e01370ec726b6eef491d0b95818862764d3cb81b1",
    "eth_j10_bram_tdp.v": "84452205021536b2d547445e169263d3572473482e3dd9c0343cffbc6f556eb8",
    "eth_j10_bit_sync.v": "612a06980fabcddede8fa1c4e5aee523eb7b98fd52b3699cc0e948305d447e87",
    "eth_j10_reset_sync.v": "b8985ab8157c52e21356dc88f7eaf0742ad4280036a96349cfb34d78737db5d7",
}
REPORTS = (
    "build.json", "build.rpt", "build_stages.tsv", "vivado.log", "ip_status.rpt",
    "compile_order.rpt", "route_status.rpt", "io.rpt", "clocks.rpt", "clock_interaction.rpt",
    "utilization.rpt", "timing.rpt", "check_timing.rpt", "cdc.rpt", "bus_skew.rpt",
    "exceptions.rpt", "methodology.rpt", "drc.rpt",
)


def snapshot_sources(output):
    destination = output / "inputs/ethernet"
    shutil.copytree(SOURCE, destination)
    helpers = output / "inputs/tests"
    helpers.mkdir()
    shutil.copyfile(HERE / "host_ethernet_preflight.tcl", helpers / "host_ethernet_preflight.tcl")
    board_repo = output / "inputs/board_files"
    shutil.copytree(preflight.BOARD, board_repo / "vcu118/2.4")
    fingerprints = {p.relative_to(output / "inputs").as_posix(): preflight.digest(p)
                    for p in (output / "inputs").rglob("*") if p.is_file()}
    if preflight.board_contract(board_repo / "vcu118/2.4") != preflight.board_contract(preflight.BOARD):
        raise ValueError("Board files changed during snapshot")
    return destination, board_repo, fingerprints


def prepare(source, output):
    files, review = collect(source)
    selected = {Path(member).name: path for path, member in files if member.startswith("example/imports/")}
    for name, expected in VENDOR.items():
        if preflight.digest(selected[name]) != expected:
            raise ValueError("Unreviewed integration source: " + name)
    vendor = output / "vendor"
    vendor.mkdir()
    for name in VENDOR:
        shutil.copyfile(selected[name], vendor / name)
        if preflight.digest(vendor / name) != VENDOR[name]:
            raise ValueError("Integration file changed during copy: " + name)
    return review["board"]


def read_stages(output):
    path = output / "build_stages.tsv"
    result = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        row = line.split("\t")
        if len(row) != 2 or row[0] not in STAGES or row[1] not in ("PASS", "FAIL") or row[0] in result:
            raise ValueError("Malformed build stage: " + line)
        if row[0] != STAGES[len(result)]:
            raise ValueError("Out-of-order build stage: " + line)
        result[row[0]] = row[1]
    return result


def classify(output, code):
    stages = read_stages(output)
    license_path = output / "ip_status.rpt"
    license_status = preflight.assess_mac_license(
        license_path.read_text(encoding="utf-8-sig", errors="replace") if license_path.is_file() else "")
    artifacts = {}
    complete = code == 0 and stages == dict.fromkeys(STAGES, "PASS")
    for name in ("eth_diag.bit", "eth_diag.ltx", "eth_diag_routed.dcp"):
        path = output / name
        if path.is_file() and not path.is_symlink() and path.stat().st_size:
            artifacts[name] = {"bytes": path.stat().st_size, "sha256": preflight.digest(path)}
        else:
            complete = False
    full = license_status["state"] == "full_reported_not_bitstream_verified"
    built = complete and full
    return {"stages": stages, "temac_license": license_status, "artifacts": artifacts,
            "state": "built_needs_manual_review_and_board_test" if built else "failed_or_incomplete",
            "bitstream_generated": complete, "full_license_bitstream_generated": built,
            "hardware_verified": False, "programming_approved": False}


def upload(output):
    from host_axi_upload import git, package, publish
    files = [(output / name, name) for name in REPORTS if (output / name).is_file()]
    # Include failing OOC/synthesis logs, not any generated IP source or license file.
    files.extend((p, "run_logs/" + p.relative_to(output / "project").as_posix())
                 for p in sorted((output / "project").glob("**/runme.log")))
    if any(p.is_symlink() for p, _ in files):
        raise ValueError("Refusing linked diagnostic input")
    root = Path(git(HERE, "rev-parse", "--show-toplevel"))
    remote = git(root, "remote", "get-url", "--push", "origin")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    branch = f"fpga-evidence/ethernet-build-{stamp}-{uuid.uuid4().hex[:8]}"
    bundle = Path(tempfile.mkdtemp(prefix="ara_eth_build_evidence_"))
    package(files, bundle, {"hardware_access": False, "hardware_verified": False,
                           "source": str(output), "evidence_branch": branch,
                           "collection_checkout_commit": git(root, "rev-parse", "HEAD")})
    print("Uploading build diagnostics only; no bitstream, checkpoint, IP HDL or license files.", flush=True)
    commit = publish(bundle, remote, branch, message="Collect isolated VCU118 Ethernet build diagnostics")
    print(f"UPLOADED_BRANCH {branch}\nUPLOADED_COMMIT {commit}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", default=Path("D:/fpga_runs/ara_eth_zr9jsk58"),
                        help="Existing successful, reviewed preflight directory (read-only)")
    parser.add_argument("--vivado")
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--out", type=Path, help="New directory only")
    parser.add_argument("--prepare-only", action="store_true", help="Check/copy inputs only; no Vivado")
    parser.add_argument("--upload", action="store_true", help="Upload diagnostics, including failures, to origin")
    args = parser.parse_args(argv)
    output = None
    code = 1
    record = {"state": "incomplete", "hardware_access": False, "hardware_verified": False,
              "programming_approved": False, "started_utc": datetime.now(timezone.utc).isoformat()}
    try:
        if args.out:
            candidate = args.out.resolve()
            candidate.mkdir(parents=True, exist_ok=False)
            output = candidate
        else:
            parent = Path("D:/fpga_runs") if os.name == "nt" and Path("D:/").is_dir() else Path(tempfile.gettempdir())
            parent.mkdir(parents=True, exist_ok=True)
            output = Path(tempfile.mkdtemp(prefix="ara_eth_build_", dir=parent))
        print("EVIDENCE", output, flush=True)
        record["source"] = str(args.source.resolve())
        record["board"] = prepare(args.source.resolve(strict=True), output)
        record["vendor_sha256"] = VENDOR
        source, board_repo, record["source_sha256"] = snapshot_sources(output)
        record["runner_sha256"] = preflight.digest(Path(__file__))
        if args.prepare_only:
            record["state"] = "inputs_prepared_not_built"
            code = 0
        else:
            command = [preflight.find_vivado(args.vivado), "-mode", "batch", "-notrace", "-nojournal",
                       "-log", (output / "vivado.log").as_posix(), "-source", (source / "build.tcl").as_posix(),
                       "-tclargs", output.as_posix(), source.as_posix(), board_repo.as_posix(), str(args.jobs)]
            record["command"] = command
            print("Isolated synthesis/route/bitgen; no Ara project or board access. Keep this console open.", flush=True)
            # Windows Vivado example generation needed inherited console handles.
            run = subprocess.run(command, cwd=output, check=False)
            record["vivado_exit_code"] = run.returncode
            record.update(classify(output, run.returncode))
            for stage in STAGES:
                print(f"{stage}: {record['stages'].get(stage, 'SKIP')}", flush=True)
            code = 0 if record["state"] == "built_needs_manual_review_and_board_test" else 1
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        record.update(state="failed_or_interrupted", error=str(exc) or type(exc).__name__)
        print("FAILED:", record["error"], file=sys.stderr)
    finally:
        # Never overwrite evidence when an explicitly supplied directory exists.
        if output is not None and not (output / "build.json").exists():
            (output / "build.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print("STATE", record["state"], flush=True)
    if args.upload and output is not None and (output / "build.json").is_file():
        try:
            upload(output)
        except (OSError, ValueError, RuntimeError) as exc:
            print("UPLOAD_FAILED:", exc, file=sys.stderr)
            return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
