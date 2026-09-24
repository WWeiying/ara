#!/usr/bin/env python3
"""Characterize the reviewed vendor example controller; NOT a hardware pass."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


HERE = Path(__file__).resolve().parent
EVIDENCE_COMMIT = "2dfc00c4cbac63fd9a724b435771d091bb981a92"
SOURCES = {
    "eth_j10_axi_lite_ctrl.v": "b8c0566ae9739ef86ade4e2df628c71762b333a66301d2fb81ade67093599199",
    "eth_j10_bit_sync.v": "612a06980fabcddede8fa1c4e5aee523eb7b98fd52b3699cc0e948305d447e87",
}


def verify_bundle(archive_data, manifest):
    if hashlib.sha256(archive_data).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("Archive SHA256 mismatch")
    entries = manifest["files"]
    expected = {row["path"]: row for row in entries}
    if len(entries) != len(expected) or len(entries) > 96:
        raise ValueError("Duplicate or excessive manifest entries")
    result = {}
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        if len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(expected):
            raise ValueError("Archive members differ from manifest")
        if sum(info.file_size for info in archive.infolist()) > 16 * 1024 * 1024:
            raise ValueError("Review archive exceeds 16 MiB")
        for name, row in expected.items():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise ValueError("Unsafe archive member")
            if archive.getinfo(name).file_size > 4 * 1024 * 1024:
                raise ValueError("Review member exceeds 4 MiB")
            data = archive.read(name)
            if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("Member SHA256/length mismatch: " + name)
            result[name] = data
    for name, digest in SOURCES.items():
        if hashlib.sha256(result["example/imports/" + name]).hexdigest() != digest:
            raise ValueError("Unreviewed controller source: " + name)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default=EVIDENCE_COMMIT, help="Already fetched evidence commit (40 hex digits)")
    parser.add_argument("--out", type=Path, help="New result directory; default is a temporary directory")
    args = parser.parse_args(argv)
    output = None
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
            raise ValueError("Expected a full Git commit hash")
        iverilog, vvp = shutil.which("iverilog"), shutil.which("vvp")
        if not iverilog or not vvp:
            raise ValueError("Icarus Verilog (iverilog and vvp) is required; Vivado is not used")
        blobs = {}
        for name in ("evidence.zip", "manifest.json"):
            blobs[name] = subprocess.check_output(["git", "show", args.commit + ":" + name], cwd=HERE, timeout=30)
        manifest = json.loads(blobs["manifest.json"])
        files = verify_bundle(blobs["evidence.zip"], manifest)
        if args.out is None:
            output = Path(tempfile.mkdtemp(prefix="ara_eth_ctrl_check_"))
        else:
            output = args.out.resolve()
            output.mkdir(parents=True, exist_ok=False)
        print("EVIDENCE", output, flush=True)
        source_paths = []
        for name in SOURCES:
            path = output / name
            path.write_bytes(files["example/imports/" + name])
            source_paths.append(str(path))
        commands = [
            [iverilog, "-g2012", "-s", "ethernet_example_ctrl_tb", "-o", str(output / "sim"),
             str(HERE / "ethernet_example_ctrl_tb.sv"), *source_paths],
            [vvp, str(output / "sim")],
        ]
        for name, command in zip(("compile", "simulation"), commands):
            run = subprocess.run(command, cwd=output, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, timeout=30)
            (output / (name + ".log")).write_text(run.stdout, encoding="utf-8")
            if run.returncode:
                raise RuntimeError(f"{name} failed; inspect {output / (name + '.log')}")
        if "CHARACTERIZED:" not in run.stdout:
            raise RuntimeError("Simulation did not reach its final assertions")
        cases = [line for line in run.stdout.splitlines() if line.startswith("CASE ")]
        report = {
            "state": "example_limitations_reproduced_not_hardware_pass",
            "evidence_commit": args.commit, "archive_sha256": manifest["archive_sha256"],
            "sources_sha256": SOURCES,
            "testbench_sha256": hashlib.sha256((HERE / "ethernet_example_ctrl_tb.sv").read_bytes()).hexdigest(),
            "commands": commands, "cases": cases,
            "hardware_verified": False, "build_ready": False, "rtl_modified": False,
            "scope": "Unmodified example controller, behavioral AXI-Lite subordinate and FDRE only. "
                     "MDIO-ready bit is modeled; no actual MDIO, MAC, PCS/PMA, PHY or packet simulation. "
                     "start_config intentionally starts configuration without waiting for the startup timer.",
        }
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("\n".join(cases))
        print(report["state"])
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print("FAILED:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
