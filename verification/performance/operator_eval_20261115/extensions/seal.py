#!/usr/bin/env python3
"""Seal already cross-compiled extensions into one parent-runner manifest."""
import argparse
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from contract import HERE, OUT, require, read, save, sha, verify


def seal(output, builds):
    output = Path(output).absolute()
    require(output == output.resolve() and output.parent == OUT.resolve() and
            re.fullmatch(r"operator_extensions_prepare_20261115_[A-Za-z0-9_.-]+",output.name) and
            not output.exists(), "Fresh owned seal directory required")
    pins, cases = {}, []
    for build in builds:
        build = Path(build).resolve(strict=True)
        report = read(build/"build.json")
        require(report["state"] == "BUILT_NOT_EXECUTED" and report["post_pins_match"], "Unready firmware")
        source = build/"source-pins.json"
        require(sha(source) == report["source_pins_sha256"], "Source receipt drift")
        inherited = read(source)
        verify(inherited)
        inherited.update({str(p):sha(p) for p in (source,build/"build.json",build/"cases.json",Path(report["elf"]))})
        for path,digest in inherited.items():
            require(path not in pins or pins[path] == digest, "Conflicting pin: "+path)
            pins[path] = digest
        cases.extend(read(build/"cases.json")["cases"])
    require(cases and len({c["id"] for c in cases}) == len(cases), "Empty/duplicate cases")
    output.mkdir()
    for path in (HERE/"seal.py",HERE/"contract.py"):
        pins[str(path)] = sha(path)
    verify(pins)
    save(output/"source-pins.json",pins)
    for case in cases:
        case["source_pins"] = str(output/"source-pins.json")
    save(output/"cases.json",dict(cases=cases))
    save(output/"release.json",dict(state="PREPARED_NOT_EXECUTED",rtl_executed=False,
        primary_image="operator_soc_20261115_activity_02",cases=[c["id"] for c in cases],
        manifest_sha256=sha(output/"cases.json"),source_pins_sha256=sha(output/"source-pins.json"),
        note="Parent owns image/protocol/telemetry collection; no performance accepted here"))
    print(output/"cases.json")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument("--build",type=Path,action="append",required=True)
    p.add_argument("--output",type=Path,required=True)
    a = p.parse_args()
    seal(a.output,a.build)
