#!/usr/bin/env python3
"""Validate recovered old-image source bytes, without bypassing admission."""
import argparse
import hashlib
import json
from pathlib import Path

ALLOWED = {
    "hardware/src/ara_dispatcher.sv": "ara_dispatcher.sv",
    "hardware/src/lane/lane_sequencer.sv": "lane_sequencer.sv",
    "hardware/src/sldu/sldu.sv": "sldu.sv",
}
COMPILE_PINS_SHA256 = "6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b"
RECEIPT_SHA256 = "5057d845a6d75d070fcef33f92a106719b9b361fdfa6bdeecfda39af35f95209"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root, snapshot):
    root, snapshot = root.resolve(strict=True), snapshot.absolute()
    identities, topologies = {}, {}

    def identity(path):
        stat = path.stat()
        return (str(path.resolve(strict=True)), stat.st_dev, stat.st_ino,
                stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    def read_bound(path):
        if path.is_symlink() or not path.is_file():
            raise ValueError("evidence must be a regular, non-symlink file")
        for parent in path.parents:
            stat = parent.lstat()
            topology = (str(parent.resolve(strict=True)), stat.st_dev, stat.st_ino, stat.st_mode)
            if str(parent) in topologies and topologies[str(parent)] != topology:
                raise ValueError("evidence directory topology changed")
            topologies[str(parent)] = topology
        before = identity(path)
        raw = path.read_bytes()
        if identity(path) != before:
            raise ValueError("evidence identity changed during read")
        identities[str(path)] = before
        return raw

    if snapshot.resolve(strict=True) != snapshot or not snapshot.is_dir():
        raise ValueError("snapshot must be a direct, existing directory")
    manifest = snapshot / "manifest.json"
    if manifest.is_symlink():
        raise ValueError("manifest symlink forbidden")
    manifest_raw = read_bound(manifest)
    manifest_hash = hashlib.sha256(manifest_raw).hexdigest()
    data = json.loads(manifest_raw)
    if (data.get("status") != "SOURCE_BYTES_RECOVERED_NOT_ADMISSION_APPROVAL"
            or data.get("processor_rtl_modified") is not False):
        raise ValueError("not a recovered-source manifest")
    build = root / "verification/out/repaired-aligned-build-20260930-01/build-source-pins.json"
    receipt = root / "verification/out/gap65-report-only-recovery-20261005-01/reports/completion.json"
    if (data.get("build_pins") != str(build.relative_to(root))
            or data.get("receipt") != str(receipt.relative_to(root))):
        raise ValueError("foreign build or receipt")
    build_raw, receipt_raw = read_bound(build), read_bound(receipt)
    pins = {str(manifest): manifest_hash, str(build): hashlib.sha256(build_raw).hexdigest(),
            str(receipt): hashlib.sha256(receipt_raw).hexdigest()}
    if pins[str(build)] != COMPILE_PINS_SHA256 or pins[str(receipt)] != RECEIPT_SHA256:
        raise ValueError("historical compile or receipt seal changed")
    compiled, historical = json.loads(build_raw), json.loads(receipt_raw)["files"]
    files = data.get("files", [])
    if len(files) != len(ALLOWED) or {f["original_relative_path"] for f in files} != set(ALLOWED):
        raise ValueError("source whitelist differs")
    aliases = {}
    for entry in files:
        relative = entry["original_relative_path"]
        if entry["snapshot_file"] != ALLOWED[relative]:
            raise ValueError("snapshot leaf differs")
        path = snapshot / entry["snapshot_file"]
        if path.is_symlink() or not path.is_file():
            raise ValueError("snapshot source is not a regular file")
        expected = compiled[str(root / relative)]
        if not (hashlib.sha256(read_bound(path)).hexdigest() == expected
                == historical[str(root / relative)] == entry["sha256"]):
            raise ValueError("snapshot does not match both historical pins")
        pins[str(path)] = expected
        aliases[str(root / relative)] = dict(snapshot=str(path), sha256=expected)
    if any(digest(Path(p)) != h for p, h in pins.items()) or digest(manifest) != manifest_hash:
        raise ValueError("source evidence changed during validation")
    if any(identity(Path(p)) != value for p, value in identities.items()):
        raise ValueError("evidence file replaced during validation")
    for name, value in topologies.items():
        parent = Path(name)
        stat = parent.lstat()
        if (str(parent.resolve(strict=True)), stat.st_dev, stat.st_ino, stat.st_mode) != value:
            raise ValueError("evidence directory replaced during validation")
    return dict(status="SOURCE_SNAPSHOT_VERIFIED_NOT_ADMISSION_APPROVAL",
                source_aliases=aliases, evidence_pins=pins,
                processor_rtl_modified=False, admission_approved=False,
                exclusions_applied=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(validate(args.root, args.snapshot), indent=2))


if __name__ == "__main__":
    main()
