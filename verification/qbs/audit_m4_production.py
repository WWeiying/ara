#!/usr/bin/env python3
"""Strict successor audit of sealed canonical M4 native/graph evidence."""
import argparse
import importlib.util
import json
from pathlib import Path
import re

from run_half_scale_soc import digest, hashes

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "ggml_m4_prepare_production/check.py"
spec = importlib.util.spec_from_file_location("m4_production_sealed_check", CHECKER)
sealed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sealed)

MARKERS = tuple(re.compile(pattern) for pattern in (
    r"M4_PRODUCTION_NATIVE_BEGIN",
    r"M4_PRODUCTION_BYTES_PASS checks=3420 vector=594 fallback=2826 bytes=exact fcsr=exact vcsr=exact",
    r"M4_PRODUCTION_NATIVE_END exit=0",
    r"M4_PRODUCTION_NATIVE_GUEST_EXIT=0",
    r"M4_PRODUCTION_GRAPH_BEGIN prepare=[01]",
    r"M4_PRODUCTION_GRAPH_END prepare=[01] exit=0",
    r"M4_PRODUCTION_GUEST_EXIT=0",
))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_log(text, vlen):
    require(vlen in (128, 1024), "Unexpected VLEN")
    for line in text.splitlines():
        if "M4_PRODUCTION_" in line:
            require(any(pattern.fullmatch(line.strip()) for pattern in MARKERS),
                    "Unknown, embedded or malformed production marker: " + line)
    return (sealed.check_native_output if vlen == 128 else sealed.check_output)(text)


def audit(directory):
    directory = directory.resolve(strict=True)
    state = json.loads((directory / "status.json").read_text())
    require(state.get("state") == "PASS" and state.get("child_pid") is None and
            state.get("manifest_unchanged") is True, "Worker is not completed PASS")
    manifest = directory / "manifest.json"
    config = directory / "configuration.json"
    require(digest(manifest) == state["manifest_sha256"] and
            digest(config) == state["configuration_sha256"], "Manifest/configuration changed")
    pins = json.loads(manifest.read_text())
    require(pins and pins == json.loads((directory / "pins-after.json").read_text()) ==
            hashes(map(Path, pins)), "Source/image/binary drift")
    require(str(CHECKER) in pins and pins[str(CHECKER)] == digest(CHECKER),
            "Unpinned legacy checker")
    require([case["vlen"] for case in state["cases"]] == [128, 1024],
            "Missing/extra native configurations")
    reports = []
    for case in state["cases"]:
        log = directory / f"qemu-{case['vlen']}.log"
        require(digest(log) == case["log_sha256"], "Raw log changed")
        report = check_log(log.read_text(errors="strict"), case["vlen"])
        require(report == case["report"], "Worker result differs from strict recheck")
        reports.append(dict(vlen=case["vlen"], log_sha256=digest(log), report=report))
    return dict(state="PASS", worker=str(directory), cases=reports,
                native_helper_checks=6840, production_graphs=384,
                evidence_sha256=hashes([manifest, config, directory / "status.json",
                                       directory / "pins-after.json", Path(__file__), CHECKER]),
                scope=["Canonical helper bytes/FCSR/VCSR checked in the native test translation unit",
                       "Actual GGML preparation selection and graph outputs checked OFF versus ON",
                       "No direct production repack translation-unit CSR equivalence claim",
                       "Native QEMU functional evidence, not RTL or model performance"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.worker)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in
                      ("state", "native_helper_checks", "production_graphs")}))


if __name__ == "__main__":
    main()
