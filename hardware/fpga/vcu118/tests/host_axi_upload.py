#!/usr/bin/env python3
"""Package existing AXI evidence; optionally push an isolated evidence branch."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
import zipfile


NETLIST_FILES = (
    "inspection.json", "axi_netlist.rpt", "vivado.log",
    "i_read_unit.v", "i_write_unit.v", "i_ar_splitter.v", "i_aw_splitter.v",
)
MAP_FILES = ("map.json", "transport/vivado.log", "transport/transport.jsonl")
MAX_INPUT_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_BYTES = 48 * 1024 * 1024


def git(directory, *args):
    result = subprocess.run(["git", "-C", str(directory), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode:
        raise RuntimeError(f"git {args[0]} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def latest(parent, marker):
    candidates = list(parent.glob(marker))
    if not candidates:
        raise ValueError(f"No existing evidence under {parent}")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, str(path))).parent


def evidence_files(netlist, mapping):
    inspection = json.loads((netlist / "inspection.json").read_text(encoding="utf-8-sig"))
    if inspection.get("collected") is not True:
        raise ValueError("Latest inspection is incomplete; specify --netlist for the intended run")
    report = (netlist / "axi_netlist.rpt").read_text(encoding="utf-8-sig")
    if "INSPECTION_COMPLETE" not in report.splitlines():
        raise ValueError("Netlist report has no INSPECTION_COMPLETE marker")
    files = [(netlist / name, "netlist/" + name) for name in NETLIST_FILES]
    if inspection.get("full_export") is True:
        files.append((netlist / "full_design.v", "netlist/full_design.v"))
    if mapping is not None:
        files.append((mapping / "map.json", "burst_map/map.json"))
        files.extend((mapping / name, "burst_map/" + name) for name in MAP_FILES[1:]
                     if (mapping / name).is_file())
    for source, _ in files:
        if source.is_symlink() or not source.is_file() or source.stat().st_size == 0:
            raise ValueError(f"Required evidence missing, empty or symlink: {source}")
    if sum(source.stat().st_size for source, _ in files) > MAX_INPUT_BYTES:
        raise ValueError("Selected evidence exceeds 512 MiB; nothing uploaded")
    return files


def package(files, output, metadata):
    records = []
    total = 0
    archive = output / "evidence.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for source, name in files:
            checksum = hashlib.sha256()
            size = 0
            with source.open("rb") as stream, bundle.open(name, "w") as target:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    size += len(block)
                    total += len(block)
                    if total > MAX_INPUT_BYTES:
                        raise ValueError("Evidence grew beyond 512 MiB; nothing uploaded")
                    checksum.update(block)
                    target.write(block)
            records.append({"path": name, "bytes": size, "sha256": checksum.hexdigest()})
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Compressed evidence exceeds 48 MiB; nothing uploaded")
    metadata = dict(metadata, files=records,
                    archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    (output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def publish(output, remote, branch):
    # A fresh repository keeps the user's branch, index, hooks and files untouched.
    git(output, "init", "-q")
    git(output, "symbolic-ref", "HEAD", "refs/heads/" + branch)
    git(output, "add", "--", "evidence.zip", "manifest.json")
    git(output, "-c", "user.name=FPGA Evidence", "-c", "user.email=fpga-evidence@localhost",
        "-c", "commit.gpgsign=false", "commit", "-q", "-m", "Collect existing FPGA AXI evidence")
    git(output, "push", remote, "HEAD:refs/heads/" + branch)
    return git(output, "rev-parse", "HEAD")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--software", type=Path,
                        default=Path(__file__).resolve().parents[2] / "ara_dsa_vcu118/software")
    parser.add_argument("--netlist", type=Path, help="Existing netlist directory (default: latest)")
    parser.add_argument("--map", type=Path, help="Existing directory containing map.json")
    parser.add_argument("--push", action="store_true", help="Upload selected evidence to origin")
    args = parser.parse_args(argv)
    output = None
    try:
        software = args.software.resolve(strict=True)
        netlist = (args.netlist.resolve(strict=True) if args.netlist else
                   latest(software / "axi_netlists", "*/inspection.json"))
        mapping = args.map.resolve(strict=True) if args.map else None
        if mapping is None and list((software / "burst_maps").glob("*/run/map.json")):
            mapping = latest(software / "burst_maps", "*/run/map.json")
        files = evidence_files(netlist, mapping)
        root = Path(git(software, "rev-parse", "--show-toplevel"))
        checkout = git(root, "rev-parse", "HEAD")
        remote = git(root, "remote", "get-url", "--push", "origin") if args.push else None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        branch = f"fpga-evidence/axi-{stamp}-{uuid.uuid4().hex[:8]}"
        output = Path(tempfile.mkdtemp(prefix="ara_axi_evidence_"))
        print(f"NETLIST {netlist}", flush=True)
        print(f"BURST_MAP {mapping or 'not available'}", flush=True)
        print(f"BUNDLE {output}", flush=True)
        metadata = {"diagnostic_only": True, "hardware_access": False,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "collection_checkout_commit": checkout,
                    "netlist_source": str(netlist), "map_source": str(mapping) if mapping else None,
                    "note": "Independently collected runs; checkout commit is not bitstream provenance.",
                    "evidence_branch": branch}
        package(files, output, metadata)
        print(f"FILES {len(files)} ZIP_BYTES {(output / 'evidence.zip').stat().st_size}", flush=True)
        if args.push:
            print("Uploading only evidence.zip and manifest.json to an isolated origin branch...", flush=True)
            commit = publish(output, remote, branch)
            print(f"UPLOADED_BRANCH {branch}\nUPLOADED_COMMIT {commit}", flush=True)
        else:
            print("PACKAGED_ONLY: no upload. Use --push to authorize upload to origin.")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        if output:
            print(f"Local evidence retained: {output}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
