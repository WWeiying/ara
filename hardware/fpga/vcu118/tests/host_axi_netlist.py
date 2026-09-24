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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probes", type=Path, help="Matching .ltx with adjacent bitstream.json")
    parser.add_argument("--vivado", default="vivado")
    args = parser.parse_args(argv)
    output = None
    try:
        probes = args.probes.resolve(strict=True)
        checkpoint, metadata = checkpoint_for(probes)
        vivado = shutil.which(args.vivado)
        if not vivado:
            raise ValueError("Vivado not found; use a Vivado-enabled shell or --vivado PATH")
        parent = Path.cwd() / "axi_netlists"
        parent.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix=datetime.now().strftime("%Y%m%d_%H%M%S_"), dir=parent))
        script = Path(__file__).with_suffix(".tcl").resolve()
        command = [vivado, "-mode", "batch", "-notrace", "-nojournal", "-nolog",
                   "-source", str(script), "-tclargs", str(checkpoint), str(output)]
        record = {"diagnostic_only": True, "hardware_access": False,
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
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
