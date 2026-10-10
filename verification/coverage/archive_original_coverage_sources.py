#!/usr/bin/env python3
"""Archive exact original build inputs without restoring or changing live RTL."""
import hashlib
from pathlib import Path

import run_vcs_dve_checkpoint as base

DISPATCHER = base.ROOT / "hardware/src/ara_dispatcher.sv"
REPAIR_BLOCK = b"""      // Empty segments never enter the sequencer. Do not leave a reservation
      // that lets the next segment bypass draining older memory completions.
      // Whole-register no-ops also need no segment reservation.
      if ((is_vload || is_vstore) && ara_req.nf != 3'b000) begin
        pending_seg_mem_op_d = 1'b0;
        is_segment_mem_op = 1'b0;
        if (state_d == WAIT_IDLE) state_d = NORMAL_OPERATION;
      end
"""


def snapshot(manifest_path, destination, image):
    destination.mkdir(parents=True, exist_ok=False)
    manifest = base.read(manifest_path)
    records = []
    for index, row in enumerate(manifest["files"]):
        source = Path(row["path"])
        data = source.read_bytes()
        current_hash = hashlib.sha256(data).hexdigest()
        method = "EXACT_COPY"
        if current_hash != row["sha256"]:
            if source != DISPATCHER or data.count(REPAIR_BLOCK) != 1:
                raise RuntimeError(f"no exact original source available: {source}")
            data = data.replace(REPAIR_BLOCK, b"", 1)
            method = "RECONSTRUCTED_PRE_FIX_BYTES_VERIFIED_AGAINST_ORIGINAL_BUILD_MANIFEST"
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise RuntimeError(f"original source reconstruction hash mismatch: {source}")
        target = destination / f"{index:04d}-{source.name}"
        target.write_bytes(data)
        records.append(dict(row, archive=str(target), method=method, live_sha256_at_capture=current_hash))
    record = {"scope": "ORIGINAL_PRE_REPAIR_BUILD_SOURCES_NOT_CURRENT_RTL",
              "manifest": str(manifest_path), "manifest_sha256": base.sha256(manifest_path),
              "image": image, "files": records}
    base.save(destination / "archive.json", record)
    base.save(destination / "archive.sha256.json", base.pins([destination / "archive.json"]))
    validate(destination, manifest_path)
    return record


def validate(destination, manifest_path):
    base.check(base.read(destination / "archive.sha256.json"))
    record = base.read(destination / "archive.json")
    if Path(record["manifest"]) != manifest_path:
        raise RuntimeError("archive belongs to another original manifest")
    base.check({str(manifest_path): record["manifest_sha256"], **record["image"]})
    manifest = base.read(manifest_path)
    original = [{"path": r["path"], "sha256": r["sha256"]} for r in record["files"]]
    if original != manifest["files"]:
        raise RuntimeError("archived source inventory differs from original build")
    base.check({r["archive"]: r["sha256"] for r in record["files"]})
    return manifest


def archived_pins(files, record):
    replacements = {r["path"]: r for r in record["files"]}
    result = {}
    for path, digest in files.items():
        if path in replacements:
            row = replacements[path]
            if digest != row["sha256"]:
                raise RuntimeError(f"historical pin disagrees with original build: {path}")
            result[row["archive"]] = digest
        else:
            result[path] = digest
    return result
