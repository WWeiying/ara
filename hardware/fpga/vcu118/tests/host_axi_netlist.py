#!/usr/bin/env python3
"""Inspect the bitstream's archived AXI netlist without accessing hardware."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def checkpoint_for(probes):
    metadata_path = probes.with_name("bitstream.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    if metadata.get("Profile") not in ("host", "dual_ddr"):
        raise ValueError("bitstream.json is not a host-capable profile")
    checkpoint = Path(metadata["Checkpoint"])
    if not checkpoint.is_absolute():
        checkpoint = metadata_path.parent / checkpoint
    if not checkpoint.is_file() or checkpoint.stat().st_size == 0:
        raise ValueError(f"Archived checkpoint not found: {checkpoint}")
    if digest(checkpoint) != metadata["CheckpointSHA256"].lower():
        raise ValueError("Checkpoint SHA256 differs from bitstream.json; refusing inspection")
    outputs = metadata["Outputs"]
    if isinstance(outputs, dict):
        outputs = [outputs]
    hashes = {item["Hash"].lower() for item in outputs
              if item.get("Algorithm", "").upper() == "SHA256"}
    if digest(probes) not in hashes:
        raise ValueError("Probes SHA256 is not recorded in bitstream.json")
    return checkpoint.resolve(), metadata


def probes_from_last(software):
    from host_axi_upload import latest
    previous = latest(software / "axi_netlists", "*/inspection.json")
    record = json.loads((previous / "inspection.json").read_text(encoding="utf-8-sig"))
    outputs = record["bitstream_metadata"]["Outputs"]
    if isinstance(outputs, dict):
        outputs = [outputs]
    probes = [Path(item["Path"]) for item in outputs
              if Path(item.get("Path", "")).suffix.lower() == ".ltx"]
    if len(probes) != 1:
        raise ValueError("Latest inspection must record exactly one .ltx path; supply probes explicitly")
    return probes[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probes", type=Path, nargs="?",
                        help="Matching .ltx (default: path from the latest inspection)")
    parser.add_argument("--vivado", default="vivado")
    parser.add_argument("--full", action="store_true", help="Also export the entire functional netlist")
    parser.add_argument("--upload", action="store_true", help="Upload completed evidence to origin")
    args = parser.parse_args(argv)
    output = None
    try:
        software = Path(__file__).resolve().parents[2] / "ara_dsa_vcu118/software"
        probes = (args.probes or probes_from_last(software)).resolve(strict=True)
        checkpoint, metadata = checkpoint_for(probes)
        vivado = shutil.which(args.vivado)
        if not vivado:
            raise ValueError("Vivado not found; use a Vivado-enabled shell or --vivado PATH")
        parent = software / "axi_netlists" if args.probes is None else Path.cwd() / "axi_netlists"
        parent.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix=datetime.now().strftime("%Y%m%d_%H%M%S_"), dir=parent))
        script = Path(__file__).with_suffix(".tcl").resolve()
        command = [vivado, "-mode", "batch", "-notrace", "-nojournal", "-nolog",
                   "-source", str(script), "-tclargs", str(checkpoint), str(output)]
        if args.full:
            command.append("1")
        record = {"diagnostic_only": True, "hardware_access": False,
                  "full_export": args.full,
                  "checkpoint": str(checkpoint), "bitstream_metadata": metadata,
                  "script_sha256": digest(script), "runner_sha256": digest(Path(__file__)),
                  "command": command, "collected": False}
        print(f"CHECKPOINT {checkpoint}", flush=True)
        print(f"EVIDENCE {output}", flush=True)
        print("Opening archived netlist; no synthesis, routing, programming or board connection.", flush=True)
        try:
            with (output / "vivado.log").open("wb") as log:
                process = subprocess.run(command, cwd=output, stdout=log,
                                         stderr=subprocess.STDOUT, check=False)
            if process.returncode:
                raise RuntimeError(f"Vivado exited {process.returncode}; inspect {output / 'vivado.log'}")
            if digest(checkpoint) != metadata["CheckpointSHA256"].lower():
                raise RuntimeError("Checkpoint changed during inspection")
            report = (output / "axi_netlist.rpt").read_text(encoding="utf-8")
            if "INSPECTION_COMPLETE" not in report.splitlines():
                raise RuntimeError("Incomplete netlist report; inspect vivado.log")
            if args.full:
                full = output / "full_design.v"
                if not full.is_file() or full.stat().st_size == 0:
                    raise RuntimeError("Full netlist was not exported; nothing uploaded")
            record["collected"] = True
            for line in report.splitlines():
                if line.startswith(("JTAG_CELL", "WIDTH", "SIZE", "LLC_BLOCK", "NETLIST")):
                    print(line)
            print(f"Full report: {output / 'axi_netlist.rpt'}")
        except BaseException as exc:
            record["error"] = str(exc)
            raise
        finally:
            (output / "inspection.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"EVIDENCE {output}")
        if args.upload:
            from host_axi_upload import main as upload
            return upload(["--software", str(software), "--netlist", str(output), "--push"])
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
