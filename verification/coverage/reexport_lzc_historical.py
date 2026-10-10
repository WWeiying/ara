#!/usr/bin/env python3
"""Independent DVE-only second-pass diagnostic; no modification of old outputs."""
import argparse
import json
import os
from pathlib import Path
import shutil

import apply_lzc_historical as original

SCRIPT = Path(__file__).resolve()
HOOK = SCRIPT.with_suffix(".tcl")
BASE = original.OUT/"lzc-historical-689-20261006-01"
EXPECTED = "bb4bfae5bac62dcb4d08e4407b3c349204a288245ddb1a3a5bc893d7532de6f8"


def prepare(output):
    output = output.absolute()
    original.require(not output.exists() and output.parent == original.OUT,"Fresh diagnostic directory required")
    seal = original.seals.FileSeal()
    manifest = seal.read(BASE/"manifest.json",EXPECTED)
    status = seal.read(BASE/"status.json")
    original.require(status["status"] == "RAW_WAIVED_COMPLETE_HISTORICAL_ONLY"
                     and status["exact_exclusions"] == 180 and status["final_reset"] is True,
                     "Original exact application incomplete")
    seal.hashes(seal.read(BASE/"evidence-pins.json")["artifact_sha256"])
    for name in ("inputs.txt","groups.tcl","capture-helpers.tcl","points.el"):
        seal.pin(BASE/name,manifest["evidence_sha256"][str(BASE/name)])
    frozen_hook = original.TCL
    seal.pin(frozen_hook,manifest["sourcepins"][str(frozen_hook)])
    for path in (SCRIPT,HOOK):seal.pin(path)
    seal.finish()
    output.mkdir()
    for name in ("inputs.txt","groups.tcl","capture-helpers.tcl","points.el"):
        shutil.copyfile(BASE/name,output/name)
    manifest["status"] = "PREPARED_NOT_RUN"
    manifest["diagnostic_origin"] = dict(path=str(BASE),manifest_sha256=EXPECTED,
        hypothesis="First traversal plus GUI idle/recalculate may refresh cached child text",
        official_denominator_verified=False,official_denominator_delta=None)
    manifest["evidence_sha256"].update(seal.files)
    manifest["sourcepins"][str(HOOK)] = seal.files[str(HOOK)]
    for name in ("inputs.txt","groups.tcl","capture-helpers.tcl","points.el"):
        path = output/name
        manifest["evidence_sha256"][str(path)] = original.seals.sha_bytes(path.read_bytes())
    original.save(output/"manifest.json",manifest)
    return original.seals.sha_bytes((output/"manifest.json").read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("prepare","run"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(dict(manifest_sha256=prepare(args.output))),flush=True)
    else:
        os.environ["LZC_FROZEN_HOOK"] = str(original.TCL)
        original.TCL = HOOK
        print(json.dumps(original.run(args.output,args.manifest_sha256),indent=2),flush=True)
