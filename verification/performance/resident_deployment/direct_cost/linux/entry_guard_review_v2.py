#!/usr/bin/env python3
"""Validate final built files, then emit the fixed packaging review schema."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import entry_guard_review_v1 as prior


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    checked = prior.review(out, write=False)
    record = {
        "image_sha256": checked["image_sha256"],
        "built_files": {str(Path(checked["linux_tree"]) / name): digest
                        for name, digest in checked["built_source_sha256"].items()},
        "early_pre_discard_drain": checked["early_pre_discard_drain"],
        "initialized_state_admission": checked["initialized_state_admission"],
        "saved_off_not_promoted": checked["saved_off_not_promoted"],
        "return_state_revalidated": checked["return_state_revalidated"],
        "scope": "static-and-compiled-runtime-pending",
        "tests": checked["tests"],
        "runtime_pending": True,
        "runtime_validated": False,
    }
    target = out / "entry-guard-review.json"
    if target.exists():
        old_bytes = target.read_bytes()
        old = json.loads(old_bytes)
        prior.require(old.get("image_sha256") == record["image_sha256"],
                      "existing review belongs to a different Image")
        prior.require("built_files" not in old, "fixed-schema review already exists; preserve it")
        with (out / "entry-guard-review.schema-v1.json").open("xb") as archive:
            archive.write(old_bytes)
    temp = out / "entry-guard-review.schema-v2.tmp"
    with temp.open("x") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temp, target)
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
