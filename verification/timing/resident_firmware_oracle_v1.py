#!/usr/bin/env python3
"""Additive UART oracle for one completed resident run; no simulator or trace replay.

Run in its own Python process for each image/kernel (the frozen checkers both
import modules named cases and generate). Existing pairing, simulator status,
cycle, image identity and any independent trace/protocol gates still apply.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


OUT = Path("/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out")
CONFIG = {
    "qk": ("resident_qk_boundary_build_20261110_01", "qk_boundary",
           "f660436c74629b8cc2055ea3387e362538b530f76a4884cec98dfbedda515af2",
           "stage3_qk_boundary_v2_20261110_01", "stage3_qk_boundary_v2_20261110_01",
           "3d346cfdc56d4a310db5d5b7e55cb66de078d522d76dc751837048526e6ce5fc"),
    "pv": ("resident_pv_soc_boundary_build_20261109_02", "soc_boundary",
           "7a6ba64e77c7fa4d6ce52602d992484d83c8b844d631dfd4cd9f2d8c41fb751c",
           "stage3_pv_boundary_20261110_01", "stage3_pv_boundary_audit_20261110_01",
           "8ed1845fa59bfe227cbd9e17ae49bda58cd68514c4406a92b079e789ef827fa9"),
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, expected):
    raw = path.read_bytes()
    need(sha(raw) == expected, f"Pin mismatch: {path}")
    return raw


def records(text):
    lines = [line for line in text.splitlines()
             if "QK_BOUNDARY_" in line or "PV_BOUNDARY_" in line]
    need(all(line.startswith(("QK_BOUNDARY_", "PV_BOUNDARY_")) for line in lines),
         "Malformed boundary prefix")
    return lines


def check_run(kind, elf_path, log):
    bdir, subdir, bpin, gdir, rdir, rpin = CONFIG[kind]
    build = OUT / bdir
    build_info = json.loads(pinned(build / "build.json", bpin))
    elf_path = elf_path.resolve(strict=True)
    raw_elf = pinned(elf_path, build_info["elf_sha256"])
    artifacts = build_info["artifacts"]
    vec = build / "vectors/vectors.json"
    vectors = json.loads(pinned(vec, artifacts[str(vec)]))
    src = build / "inputs" / subdir
    modules = ["check", "cases", "generate"] + (["elf"] if kind == "qk" else [])
    for name in modules:
        path = src / (name + ".py")
        pinned(path, artifacts[str(path)])
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(src))
    import check

    need(all(Path(sys.modules[name].__file__).resolve() == src / (name + ".py")
             for name in modules), "Incorrect checker import")
    raw = log.read_bytes()
    text = raw.decode("utf-8")
    loads = re.findall(r"(?m)^Loading ELF file (.+)$", text)
    need(len(loads) == 1 and Path(loads[0]).is_absolute() and
         Path(loads[0]).resolve(strict=True) == elf_path, "Preload path does not match ELF")
    if kind == "qk":
        specs, _ = check.numerical(text, vectors, check.elf.contract(raw_elf))
        attempts = len(specs)
    else:
        result = check.check_log(text, vectors, build_info["fault_pc"])
        attempts = result["successful_pv"] + result["rejected_pv"]

    report = json.loads(pinned(OUT / rdir / "report.json", rpin))
    need(report["state"] == "PASS" and report["numerical_checked"], "No golden numerical audit")
    if kind == "pv":
        need(report["original_state"] == "FAIL" and report["original_failure_preserved"],
             "PV gold must come from the scoped audit of the preserved worker failure")
    gold = OUT / gdir / "work/run.vcs.log"
    gold_sha = report["artifacts" if kind == "qk" else "evidence_sha256"][str(gold)]
    expected = records(pinned(gold, gold_sha).decode("utf-8"))
    observed = records(text)
    need(len(observed) == len(expected), "Golden boundary record count mismatch")
    for i, (actual, wanted) in enumerate(zip(observed, expected), 1):
        need(actual == wanted, f"Golden boundary record {i} differs: {wanted[:55]}")
    need(re.findall(r"(?m)^Core Test .*\*\*\*.*$", text) ==
         ["Core Test *** SUCCESS *** (tohost = 0)"], "Missing or duplicate clean tohost exit")
    need(not re.search(r"Fatal:|Error(?:-|:)|\*\*\* FAILED \*\*\*|UVM_(?:ERROR|FATAL)\s*:\s*[1-9]", text),
         "Simulator error")
    need(len(re.findall(r"(?m)^\$finish at simulation time\s+\d+$", text)) == 1,
         "Missing or duplicate finish timestamp")
    return dict(state="PASS", scope="resident_uart_oracle_only", kernel=kind, attempts=attempts,
                boundary_records=len(observed), numerical_checked=True, golden_uart_equal=True,
                trace_checked=False, protocol_checked=False, elf=str(elf_path), elf_sha256=sha(raw_elf),
                log=str(log.resolve()), log_sha256=sha(raw), gold_log_sha256=gold_sha,
                golden_audit_sha256=rpin, build_manifest_sha256=bpin)


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument("kernel", choices=CONFIG)
    p.add_argument("--elf", type=Path, required=True)
    p.add_argument("--log", type=Path, required=True)
    args = p.parse_args()
    try:
        result = check_run(args.kernel, args.elf, args.log)
    except (ValueError, OSError, KeyError, ImportError) as exc:
        print(json.dumps(dict(state="FAIL", kernel=args.kernel, error=str(exc))))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
