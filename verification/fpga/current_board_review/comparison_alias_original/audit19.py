#!/usr/bin/env python3
"""Independent exact membership, staged input and failure-veto checks."""
from collections import Counter
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import replay19 as r

p = r.p
prepared = r.HERE / "prepared01"
out = r.HERE / "audit01"
out.mkdir(exist_ok=False)
pins = p.read(r.HERE / "measurement01/pins.json")
r.verify(pins)
archive = p.read(p.ARCH / "manifest.json")
names = {x["name"] for x in archive["cases"] if "masks_cmp_alias_restart" in x["name"]}
programs = p.read(prepared / "soc/programs.json")["programs"]
reference = p.read(prepared / "reference.json")["results"]
results = sum((p.read(r.HERE / "measurement01" / (s + ".json"))["results"] for s in ("selected", "remaining")), [])
p.require(len(names) == len(results) == 19 and names == set(programs) == {x["name"] for x in reference}
          == {x["name"] for x in results}, "Membership differs")
checks = []
for entry in reference:
    name = entry["name"]
    log = prepared / "spike" / (name + ".spike.log")
    p.require(entry["status"] == "PASS" and p.prepare.sha(log) == entry["log_sha256"], "Reference drift")
    p.require(p.oracle(programs[name], log.read_text()), "Reference oracle incomplete")
for entry in results:
    name = entry["name"]
    source = prepared / "prepared" / name
    p.require((source / "case.c").read_text() == p.adapt((source / "original/scenario.c").read_text(), name), "Port drift")
    for fname in ("scenario.c", "scenario.S", "operations.h"):
        p.require((source / "original" / fname).read_bytes() == (p.ARCH / name / fname).read_bytes(), "Archived source drift")
    folder = Path(entry["artifact_dir"])
    item = dict(name=name, status=entry["status"], elapsed_s=entry["elapsed_s"])
    if (folder / "inputs.json").exists():
        inputs = p.read(folder / "inputs.json")
        binary = inputs["binary"]
        p.require(p.prepare.sha(Path(binary["path"])) == binary["sha256"] == p.prepare.sha(Path(binary["source"])), "ELF mismatch")
        r.verify(inputs["simv"]["image_sha256"])
        text = (folder / "console.log").read_text()
        if entry["status"] == "PASS":
            p.require(entry["returncode"] == 0 and p.oracle(programs[name], text), "False PASS")
        if entry["status"] == "FAIL":
            p.require(bool(p.FAIL.search(text)) and not p.oracle(programs[name], text), "Failure veto missing")
        item.update(input_sha256=binary["sha256"], staged_input_verified=True,
                    console_sha256=p.prepare.sha(folder / "console.log"))
    checks.append(item)
entry = programs[p.SELECTED]
passing = "\n".join(entry["pass_markers"])
p.require(p.oracle(entry, passing), "PASS test broken")
veto = ["RVV_MASK_BIT", "RVV_MASK_FAIL", "RVV_MASK_FIRST", "RVV_MASK_CAPACITY_FAIL", "BOARD_CASE_FAIL", "BOARD_REPLAY_TRAP"]
for token in veto:
    p.require(not p.oracle(entry, passing + "\n" + token), "Veto failed: " + token)
p.prepare.save(out / "finding.json", dict(status="AUDIT_PASS_DUT_HAS_FAILURE", exact_original19=True,
    reference_pass=19, dut_status_counts=dict(Counter(x["status"] for x in results)),
    pins_verified=len(pins), pins_unchanged=True, negative_veto_tests=veto, results=checks,
    limitation="First-error veto stops failing program before final oracle summary; cancelled cases are not passes"))
print("AUDIT_PASS", Counter(x["status"] for x in results), len(pins), flush=True)
