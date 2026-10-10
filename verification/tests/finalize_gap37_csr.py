#!/usr/bin/env python3
"""Finalize one strictly passing candidate; preserve the counter preflight failure."""
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("gap37_build", Path(__file__).with_name("build_gap37_csr.py"))
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def main():
    out = build.OUT
    preflight = out / "preflight-01"
    old = json.loads((preflight / "source-hashes.json").read_text())
    assert all(build.digest(Path(p)) == h for p, h in old.items()), "Executed inputs changed"
    native = json.loads((out / "native-points.json").read_text())
    assert all(build.digest(Path(p)) == h for p, h in native["provenance"].items())
    assert all(build.digest(Path(p["path"])) == p["sha256"] for p in native["source_pins"])
    audit = json.loads((out / "source-audit.json").read_text())
    name = "gap37_csr_alias_tvm"
    evidence_path = preflight / (name + ".evidence.json")
    evidence = json.loads(evidence_path.read_text())
    elf = preflight / (name + ".elf")
    spike = preflight / (name + ".spike")
    log = preflight / (name + ".spike.log")
    assert build.digest(elf) == evidence["elf_sha256"]
    assert build.digest(spike) == evidence["spike_elf_sha256"]
    assert build.digest(log) == evidence["log_sha256"]
    symbols = (preflight / (name + ".nm")).read_text()
    stub = re.findall(r"^([0-9a-f]+) [bB] csr_gap35_stub$", symbols, re.MULTILINE)
    assert len(stub) == 1
    checked = build.validate_log(name, log.read_text(), int(stub[0], 16))
    assert all(evidence[k] == v for k, v in checked.items())
    failed_log = preflight / "gap37_csr_counters.spike.log"
    failed_text = failed_log.read_text()
    assert "cy-ir-implemented got=0 want=5" in failed_text
    assert "phases=22 checks=245 illegal=0 legal=22 failures=62" in failed_text
    assert "FAIL: gap37_csr_counters" in failed_text
    try:
        build.validate_log("gap37_csr_counters", failed_text, 0x800038c0)
    except ValueError:
        pass
    else:
        raise AssertionError("Counter failure admitted")
    selection = dict(baseline=str(build.BASE), baseline_bits=str(build.BASE / "combined-bits.json"),
        status="DRAFT_SPIKE_ONLY_NOT_SUBMITTED", measured_new_dut_coverage=None,
        cases=[dict(name="rvv:" + name, binary=str(elf), binary_sha256=build.digest(elf),
            timeout_s=600, preflight_status="PASS", phases=52, checks=626, illegal=7,
            sources=[str(build.DEST / (name + ".c")), str(build.DEST / "gap37_csr_ops.h"),
                     str(build.DEST / "csr_gap35_body.h"), str(Path(__file__).with_name("build_gap37_csr.py"))],
            evidence=[str(log), str(evidence_path), str(preflight / "source-hashes.json"),
                      str(out / "source-audit.json"), str(out / "analysis.md")],
            targets=[native["scope"]], source_audit=str(out / "source-audit.json"),
            rationale=audit["cases"][name]["rationale"],
            predicted_missing_native_branches=[dict(native=p["native"], raw_index=p["raw_index"], current_hit=p["hit"])
                                              for p in audit["cases"][name]["branches"]])],
        rejected=[dict(name="rvv:gap37_csr_counters", reason="Strict Spike precheck FAIL: MCOUNTINHIBIT readback is zero; 62 failures. Do not submit.",
                       evidence=str(failed_log), source_unchanged=True)],
        admission="No VCS launched. Parent owns frozen-image admission, strict terminal/trace checking, and measured coverage delta. No lower standard or checker bypass authorized.")
    build.save(out / "selection-draft.json", selection)
    build.save(out / "finalization.json", dict(readonly_hashes_verified=True,
        accepted=name, rejected="gap37_csr_counters", no_simulator_invoked=True,
        counter_log_sha256=build.digest(failed_log),
        note="Installed Spike observation does not imply an RTL failure or frozen-image unreachability."))
    print("Selection draft: one Spike PASS, one preserved FAIL excluded; no VCS")


if __name__ == "__main__":
    main()
