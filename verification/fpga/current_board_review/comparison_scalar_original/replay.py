#!/usr/bin/env python3
"""Original RVV12 scalar19, existing image: one representative then18 jobs2."""
import argparse
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent / "comparison_alias_original"))
import replay19 as r
p = r.p
PREPARED = HERE / "prepared01"
SELECTED = "rvv_small_masks_scalar_restart_e8_m2"
IMAGE_SHA = "e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673"


def main(args):
    out, image = args.out.resolve(), args.image.resolve()
    p.require(out.is_relative_to(HERE) and out != HERE and not out.exists(),"Fresh owned output required")
    p.require(p.prepare.sha(image / "image.json") == IMAGE_SHA,"Wrong candidate04 image")
    reference = p.read(PREPARED / "reference.json")
    host = p.read(PREPARED / "host.json")
    p.require(reference["status"] == "SPIKE_19_PASS_NOT_DUT" and len(reference["results"]) == 19,"Reference gate")
    p.require(host["status"] == "PASS_19_HOST_PLUS_4_ORACLE_REJECTIONS" and len(host["results"]) == 23,"Host gate")
    records = p.read(p.ARCH / "manifest.json")["cases"]
    names = {x["name"] for x in records if "masks_scalar_restart" in x["name"]}
    programs = p.read(PREPARED / "soc/programs.json")["programs"]
    p.require(len(names) == 19 and names == set(programs) == {x["name"] for x in reference["results"]},"Exact19 membership differs")
    for entry in reference["results"]:
        log = PREPARED / "spike" / (entry["name"]+".spike.log")
        p.require(entry["status"] == "PASS" and p.prepare.sha(log) == entry["log_sha256"] and
                  p.oracle(programs[entry["name"]],log.read_text()),"Reference evidence drift")
    ledger = p.read(image / "image.json")
    snapshot = Path(ledger["snapshot"])
    pins = p.read(PREPARED / "source_pins.json")
    pins.update(ledger["files"])
    pins.update({str(snapshot / "sources" / name):digest for name,digest in p.read(snapshot / "snapshot.json")["files"].items()})
    for file in [*filter(Path.is_file,PREPARED.rglob("*")),Path(__file__),Path(r.__file__),image / "image.json",
                 snapshot / "snapshot.json",Path(ledger["simv"]).parent / "simulator.conf",
                 Path(ledger["simv"]).parent / "vcs_source_manifest.json"]:
        pins[str(file.resolve())] = p.prepare.sha(file)
    r.verify(pins)
    out.mkdir()
    stages = [dict(name="first",cases=[SELECTED],jobs=1),
              dict(name="remaining18",cases=[n for n in programs if n != SELECTED],jobs=2)]
    p.prepare.save(out / "plan.json",dict(image=str(image),image_sha256=IMAGE_SHA,pins=pins,stages=stages,
        timeout_s=180,stop_first_fail=True,scope="19 archived scalar singles, not full parent matrices",
        global_cap=24,mem_floor_gib=32,no_build=True,no_rtl_edits=True))
    framework = r.shared.framework
    def admitted(repo):
        base, options, case, identity = framework(repo)
        class Runner(base):
            def _run_test(self,test,simv):
                if not self.cancel_event.is_set():
                    p.prepare.save(out / ("admission_"+test.name+".json"),r.resources(out,2))
                return super()._run_test(test,simv)
        return Runner,options,case,identity
    r.shared.framework = admitted
    r.shared.framework(snapshot / "sources")
    import ara_verify.runner as engine
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern + "|" + p.FAIL.pattern,engine.FAIL_RE.flags)
    r.shared.oracle_complete = p.oracle
    observations, start = [], time.time()
    for stage in stages:
        r.verify(pins)
        dest = out / stage["name"]
        dest.mkdir()
        p.prepare.save(dest / "resources.json",r.resources(out,stage["jobs"]))
        rc = r.shared.run_programs(SimpleNamespace(image=image,programs=PREPARED / "soc",out=dest / "replay",
            case=stage["cases"],jobs=stage["jobs"],timeout=180,execute=True))
        results = p.read(dest / "replay/summary.json")
        passed = rc == 0 and len(results) == len(stage["cases"]) and all(x["status"] == "PASS" and x["returncode"] == 0 for x in results)
        observations.append(dict(stage=stage["name"],passed=passed,results=results))
        p.prepare.save(dest / "status.json",observations[-1])
        if not passed:
            break
    r.verify(pins)
    passed = len(observations) == 2 and all(x["passed"] for x in observations)
    p.prepare.save(out / "complete.json",dict(status="PASS_19_SCALAR_SINGLES" if passed else "NOT_PASS",
        stages=observations,pins_unchanged=True,pin_count=len(pins),elapsed_s=time.time()-start,
        image_sha256=IMAGE_SHA,scope="Original selected singles only; no parent-matrix or Linux-board closure"))
    print("PASS_19_SCALAR_SINGLES" if passed else "NOT_PASS",flush=True)
    return int(not passed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Refuse existing output")
    os.environ.update(r.shared.environment())
    try:
        sys.exit(main(args))
    except Exception as error:
        if args.out.is_dir():
            p.prepare.save(args.out / "error.json",dict(error=str(error),finished=time.time()))
        raise
