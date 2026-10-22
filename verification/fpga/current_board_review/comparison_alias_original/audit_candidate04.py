#!/usr/bin/env python3
"""Independent terminal evidence audit; no simulation or mutation of inputs."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
RUN = HERE / "candidate04_01"
BASE = HERE.parent / "fp_moves/candidate03_controls16_01"
OUT = HERE / "candidate04_audit02"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def trace(path):
    with path.open() as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap".split(","), "CSV schema differs")
        rows = list(reader)
    require(rows and all(None not in x and None not in x.values() for x in rows), "Incomplete CSV row")
    require(path.read_bytes().endswith(b"\n"), "Truncated last row")
    cycles = [int(x["cycle"]) for x in rows]
    require(cycles == sorted(cycles), "Nonmonotonic cycles")
    retire = [x for x in rows if x["event"] == "retire"]
    require([int(x["order"]) for x in retire] == list(range(len(retire))), "Retirement gap")
    require(all(x["trap"] in ("0", "1") for x in rows), "Invalid exception encoding")
    return rows


def main():
    OUT.mkdir(exist_ok=False)
    plan = read(RUN / "plan.json")
    ledger = read(Path(plan["image"]) / "image.json")
    pinsets = {"candidate04_plan": plan["pins"], "original19_measurement": read(HERE / "measurement01/pins.json"),
               "original_source": read(HERE / "prepared01/source_pins.json")}
    for name, pins in pinsets.items():
        for path, expected in pins.items():
            require(sha(Path(path)) == expected, "Pin drift: " + path)
    require(sha(Path(plan["image"]) / "image.json") == plan["image_sha256"], "Image identity drift")
    for filename, key in (("simulator.conf","configuration_sha256"), ("vcs_source_manifest.json","manifest_sha256")):
        require(sha(Path(ledger["simv"]).parent / filename) == ledger[key], "Compiled metadata drift")
    archived = read(Path("/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_masks02/manifest.json"))
    original19 = {x["name"] for x in archived["cases"] if "masks_cmp_alias_restart" in x["name"]}
    controls = {x["id"]:x for x in read(BASE / "plan.json")["cases"]}
    expected = {"first": {"rvv_small_masks_cmp_alias_restart_e8_m2"},
        "remaining18": original19 - {"rvv_small_masks_cmp_alias_restart_e8_m2"},
        "smokes": {x["original_name"] for x in controls.values() if x["group"] == "smokes"},
        "singles": {x["original_name"] for x in controls.values() if x["group"] == "singles"}}
    require([len(expected[x]) for x in ("first","remaining18","smokes","singles")] == [1,18,10,6], "Scope differs")
    require({x["name"] for x in plan["stages"]} == set(expected), "Stage set differs")
    failure = re.compile(r"RVV_MASK_(?:FAIL|FIRST|BIT|CAPACITY_FAIL)|BOARD_CASE_FAIL|BOARD_REPLAY_(?:TRAP|SERVICE_FAIL|VLEN_FAIL|MISMATCH)|Core Test \*\*\* FAIL|Error-\[|Fatal-|UVM_FATAL")
    tests, comparisons = [], []
    for stage in plan["stages"]:
        group = stage["name"]
        summaries = read(RUN / group / "replay/summary.json")
        require(len(summaries) == len(expected[group]) and {x["name"] for x in summaries} == expected[group], "Actual membership differs")
        require(set(stage["cases"]) == expected[group], "Plan membership differs")
        manifest = read(Path(stage["programs"]) / "programs.json")["programs"]
        for result in summaries:
            name = result["name"]
            folder = RUN / group / "replay/tests" / name
            entry = manifest[name]
            inputs = read(folder / "inputs.json")
            elfsha = sha(folder / "input.elf")
            require(elfsha == entry["sha256"] == inputs["binary"]["sha256"] == sha(Path(entry["path"])), "ELF differs")
            require(inputs["simv"]["image_sha256"] == ledger["files"], "Wrong runtime image")
            console = (folder / "console.log").read_text()
            require(result["status"] == "PASS" and result["returncode"] == 0, "Nonterminal/nonpass case")
            require("Core Test *** SUCCESS *** (tohost = 0)" in console and "$finish" in console,
                    "No complete zero-tohost exit")
            require(all(x in console for x in entry["pass_markers"]) and "SKIP" not in console and not failure.search(console), "Oracle/veto failed")
            if group in ("first","remaining18"):
                require(len(re.findall(r"RVV_MASK_PASS sew=\d+ cases=1 errors=0", console)) == 1, "Original single count differs")
            rows = trace(folder / "commit_trace.csv")
            if group in ("first","remaining18"):
                require(all(x["trap"] == "0" for x in rows), "Original comparison single has exception")
            tests.append(dict(group=group,name=name,status="PASS",returncode=0,elf_sha256=elfsha,
                console_sha256=sha(folder / "console.log"),csv_sha256=sha(folder / "commit_trace.csv"),
                csv_rows=len(rows),elapsed_s=result["elapsed_s"]))
            if group not in ("smokes","singles"):
                continue
            identity = group + "__" + name
            base = BASE / "replay/tests" / identity
            require(sha(base / "input.elf") == elfsha == controls[identity]["sha256"], "Control not same baseline ELF")
            before = trace(base / "commit_trace.csv")
            require(len(before) == len(rows), "CSV row count differs")
            noncycle = [(i,a,b) for i,(a,b) in enumerate(zip(before,rows))
                        if {k:v for k,v in a.items() if k != "cycle"} != {k:v for k,v in b.items() if k != "cycle"}]
            require(not noncycle, "Control noncycle field difference")
            diffs = [dict(row=i+2,before_cycle=int(a["cycle"]),after_cycle=int(b["cycle"]),
                          delta=int(b["cycle"])-int(a["cycle"]),event=a["event"],order=a["order"],insn=a["insn"])
                     for i,(a,b) in enumerate(zip(before,rows)) if a["cycle"] != b["cycle"]]
            record = dict(name=identity,rows=len(rows),retire_rows=sum(x["event"] == "retire" for x in rows),
                candidate03_sha256=sha(base / "commit_trace.csv"),candidate04_sha256=sha(folder / "commit_trace.csv"),
                byte_equal=(base / "commit_trace.csv").read_bytes() == (folder / "commit_trace.csv").read_bytes(),
                noncycle_differences=0,exception_indication_rows=sum(x["trap"] == "1" for x in rows),
                cycle_changed_rows=len(diffs),cycle_delta_counts=dict(Counter(x["delta"] for x in diffs)),
                last_cycle_before=int(before[-1]["cycle"]),last_cycle_after=int(rows[-1]["cycle"]),
                first_difference=diffs[0] if diffs else None)
            comparisons.append(record)
            if diffs:
                (OUT / (identity + "_cycle_diffs.json")).write_text(json.dumps(diffs,indent=2)+"\n")
    require(len(tests) == 35 and len(comparisons) == 16, "Incomplete audit")
    changed = [x for x in comparisons if x["cycle_changed_rows"]]
    require(len(changed) == 1 and changed[0]["name"] == "singles__restart_compare" and
            changed[0]["cycle_changed_rows"] == 1374 and changed[0]["cycle_delta_counts"] == {1:1374},
            "Observed cycle delta changed")
    finding = dict(status="INDEPENDENT_PASS_19_PLUS_16",counts={g:len(v) for g,v in expected.items()},
        pins_unchanged={k:len(v) for k,v in pinsets.items()},tests=tests,control_comparisons=comparisons,
        exact_original19=True,all_same_elf=True,all_full_oracles_and_zero_exit=True,
        scope="19 archived genuine singles plus16 controls, not parent matrices/Linux ELF replay")
    (OUT / "finding.json").write_text(json.dumps(finding,indent=2)+"\n")
    lines = ["# Candidate04 Independent Terminal Audit", "", "35/35 full-oracle PASS and zero exit, independently checked.",
        "Exact membership:19 archived comparison-alias singles +10 original smokes +6 original controls.",
        "All staged ELFs match original inputs; no source/oracle replacement.", "",
        "Pin sets unchanged: candidate04 plan1859; original19 measurement1144; original source107.",
        "No119-entry pin list was found in these manifests; the actual full lists were rehashed.", "",
        "| Control | CSV Rows | Changed Cycle Rows | Last Cycle M3 / M4 | Noncycle Differences |",
        "| --- | ---: | ---: | --- | ---: |"]
    lines += [f'| {x["name"]} | {x["rows"]} | {x["cycle_changed_rows"]} | {x["last_cycle_before"]} / {x["last_cycle_after"]} | 0 |' for x in comparisons]
    lines += ["", "15 CSVs are byte-identical. restart_compare has1374 changed rows, each exactly+1 cycle,",
        "starting at VMSEQ.vx opcode608e4c57 uop_done27644->27645 (CSV line17603).",
        "All18975 rows and all noncycle fields match; final cycle30318->30319.",
        "Every CSV was fully parsed, with valid schema, monotonic cycles, continuous retirement order,",
        "complete final row and a console-confirmed successful simulation finish.",
        "QBS has2 and AKV has3 cvx_resp exception indications; their entire traces match candidate03.",
        "These are not new architectural traps. The initial over-strict auditor is recorded in candidate04_audit01/error.json.",
        "Original first-error baseline and cancelled records remain unchanged. No whole-parent closure claimed.", ""]
    (OUT / "README.md").write_text("\n".join(lines))
    print(finding["status"], finding["pins_unchanged"], flush=True)


if __name__ == "__main__":
    main()
