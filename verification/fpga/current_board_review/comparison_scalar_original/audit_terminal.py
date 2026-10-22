#!/usr/bin/env python3
"""Independently accept actual scalar19 inputs, consoles and complete traces."""
import csv
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
RUN = HERE / "vcs_candidate04_01"
PREP = HERE / "prepared01"
OUT = HERE / "terminal_audit01"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    OUT.mkdir(exist_ok=False)
    plan = read(RUN / "plan.json")
    source_pins = read(PREP / "source_pins.json")
    for pins in (plan["pins"], source_pins):
        for name,digest in pins.items():
            require(sha(Path(name)) == digest, "Pinned input changed: " + name)
    archive = Path("/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_masks02")
    originals = {x["name"]:x for x in read(archive / "manifest.json")["cases"] if "masks_scalar_restart" in x["name"]}
    programs = read(PREP / "soc/programs.json")["programs"]
    addresses = read(PREP / "address_map.json")
    require(len(originals) == 19 and set(originals) == set(programs), "Original19 membership differs")
    image = Path(plan["image"])
    ledger = read(image / "image.json")
    require(sha(image / "image.json") == plan["image_sha256"] ==
        "e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673", "Wrong candidate04 image")
    snapshot = read(Path(ledger["snapshot"]) / "snapshot.json")
    require(len(snapshot["files"]) == 539, "Snapshot membership differs")
    for name,digest in snapshot["files"].items():
        require(sha(Path(snapshot["root"]) / name) == digest, "Snapshot drift")
    failure = re.compile(r"RVV_MASK_(?:BIT|FIRST|FAIL|CAPACITY_FAIL)|BOARD_CASE_FAIL|BOARD_REPLAY_(?:TRAP|MISMATCH|SERVICE_FAIL|VLEN_FAIL)|Core Test \*\*\* FAIL|Error-\[|Fatal[-:]|UVM_FATAL")
    tests = []
    for stage in ("first", "remaining18"):
        directory = RUN / stage / "replay"
        metadata = read(directory / "run.json")
        require(metadata["status"] == "COMPLETE" and metadata["simv"] == ledger["simv"], "Run incomplete/wrong simv")
        summary = read(directory / "summary.json")
        require(len(summary) == (1 if stage == "first" else 18), "Stage length differs")
        for result in summary:
            name = result["name"]
            require(name in originals and result["status"] == "PASS" and result["returncode"] == 0, "Case failed/incomplete")
            entry, record = programs[name], originals[name]
            dest = directory / "tests" / name
            inputs = read(dest / "inputs.json")
            require(sha(dest / "input.elf") == entry["sha256"] == inputs["binary"]["sha256"] == sha(Path(entry["path"])), "Not same ELF")
            require(inputs["simv"]["image_sha256"] == ledger["files"], "Actual runtime image differs")
            console = (dest / "console.log").read_text()
            require(not failure.search(console) and "SKIP" not in console and
                    "Core Test *** SUCCESS *** (tohost = 0)" in console and "$finish" in console,
                    "Failure veto/incomplete finish")
            for marker in entry["pass_markers"]:
                require(console.count(marker) == 1, "Missing/duplicate original oracle marker")
            stimulus = record["measured_stimulus"]
            require(console.count(f'RVV_MASK_TRIAL vl={stimulus["vl"]} vstart={stimulus["vstart"]}') == 1, "Wrong original tuple")
            for filename,digest in record["scenario_sources"].items():
                require(sha(PREP / "prepared" / name / "original" / filename) == digest == sha(archive / name / filename), "Original source differs")
            trace = dest / "commit_trace.csv"
            with trace.open() as stream:
                reader = csv.DictReader(stream)
                require(reader.fieldnames == "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap".split(","), "CSV schema differs")
                rows = list(reader)
            require(rows and all(None not in x and None not in x.values() for x in rows) and trace.read_bytes().endswith(b"\n"), "Incomplete CSV")
            cycles = [int(x["cycle"]) for x in rows]
            require(cycles == sorted(cycles) and all(x["trap"] == "0" for x in rows), "Unexpected trace chronology/exception")
            retires = [x for x in rows if x["event"] == "retire"]
            require([int(x["order"]) for x in retires] == list(range(len(retires))), "Retirement gap")
            target = [x for x in retires if int(x["pc"],16) == int(addresses[name]["soc"]["target_pc"],16)]
            require(len(target) == 1 and target[0]["insn"] == "608e4c57", "Wrong/duplicated target retirement")
            alloc = [x for x in rows if x["event"] == "uop_alloc" and x["insn"] == "608e4c57"]
            done = [x for x in rows if x["event"] == "uop_done" and x["insn"] == "608e4c57"]
            require(len(alloc) == len(done) == 1 and alloc[0]["order"] == done[0]["order"], "Target execution incomplete")
            tests.append(dict(name=name,status="PASS",returncode=0,elapsed_s=result["elapsed_s"],
                elf_sha256=entry["sha256"],original_linux_sha256=record["original_elf_sha256"],
                archived_single_sha256=record["sha256"],console_sha256=sha(dest / "console.log"),
                csv_sha256=sha(trace),csv_rows=len(rows),retire_rows=len(retires),last_cycle=cycles[-1],
                target_pc=addresses[name]["soc"]["target_pc"],target_retire_cycle=int(target[0]["cycle"]),
                target_alloc_cycle=int(alloc[0]["cycle"]),target_done_cycle=int(done[0]["cycle"]),
                sew=record["sew"],lmul=record["lmul"],vl=stimulus["vl"],vstart=stimulus["vstart"]))
    require(len(tests) == len({x["name"] for x in tests}) == 19 and {x["name"] for x in tests} == set(originals), "Incomplete/duplicate19")
    for x in read(PREP / "reference.json")["results"]:
        require(x["status"] == "PASS" and sha(PREP / "spike" / (x["name"]+".spike.log")) == x["log_sha256"], "Reference drift")
    for token in ("RVV_MASK_BIT", "RVV_MASK_FIRST", "RVV_MASK_FAIL", "BOARD_CASE_FAIL", "BOARD_REPLAY_TRAP"):
        require(failure.search("Core Test *** SUCCESS *** (tohost = 0)\n$finish\n"+token), "Veto broken")
    finding = dict(status="INDEPENDENT_PASS_19_SCALAR_SINGLES",exact_original19=True,full_original_oracle=True,
        same_elf=True,pins_unchanged=True,plan_pin_count=len(plan["pins"]),source_pin_count=len(source_pins),
        snapshot_files=len(snapshot["files"]),image_sha256=plan["image_sha256"],tests=tests,
        scope="19 archived source singles only; not original Linux ELF execution, other scalar operations or parent matrices")
    (OUT / "finding.json").write_text(json.dumps(finding,indent=2)+"\n")
    lines = ["# Scalar19 Independent Terminal Acceptance", "", "Candidate04:19/19 original single-source ports PASS.",
        f'All{len(plan["pins"])} plan pins, all{len(source_pins)} source pins and539 frozen snapshot files were rehashed unchanged.',
        "Exact archive membership, same staged ELF, actual image, full original oracle, zero exit and failure veto checked.",
        "Each complete CSV has continuous retirement order and exactly one target VMSEQ.vx allocation/retirement/completion.","",
        "| Shape | VL/Start | Seconds | CSV Rows | Target Alloc/Done |",
        "| --- | --- | ---: | ---: | --- |"]
    lines += [f'| {x["sew"]}/{x["lmul"]} | {x["vl"]}/{x["vstart"]} | {x["elapsed_s"]:.2f} | {x["csv_rows"]} | {x["target_alloc_cycle"]}/{x["target_done_cycle"]} |' for x in tests]
    lines += ["", "Acceptance is limited to19 archived genuine singles. Host/Spike checks remain reference evidence,",
        "and no complete parent matrix, original Linux ELF execution or common historical root cause is claimed.", ""]
    (OUT / "README.md").write_text("\n".join(lines))
    print(finding["status"],finding["plan_pin_count"],finding["source_pin_count"],flush=True)


if __name__ == "__main__":
    main()
