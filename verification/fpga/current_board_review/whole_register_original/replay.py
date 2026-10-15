#!/usr/bin/env python3
"""Replay all1134 archived whole-register configurations in20 fixed partitions."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "integration"
sys.path.insert(0,str(BASE))
import replay_candidate04_regression_final as checked

base = checked.base
PREP = HERE / "prepared01"
JOBS = 6


def resource_state(out):
    raw = subprocess.run(["pgrep","-a","-x","simv"],capture_output=True,text=True)
    base.require(raw.returncode in (0,1),"Cannot inventory live VCS")
    external = [x for x in raw.stdout.splitlines() if str(out) not in x]
    # Parent-declared parallel campaigns retain slots even between test processes.
    reservations = {"indexed_review":2,"candidate04_regression38_03":4,
                    "nf8_strided_review/sv39_full192":8,"gather_original_review":4}
    spare = sum(max(0,n-sum(label in x for x in external)) for label,n in reservations.items())
    memory = dict(x.split(":",1) for x in Path("/proc/meminfo").read_text().splitlines())
    available = int(memory["MemAvailable"].split()[0])*1024
    base.require(len(external)+spare+JOBS<=24,"Resource cap exceeded; no automatic retry")
    base.require(available>=32*1024**3,"Available memory below32GiB")
    return dict(time=time.time(),external=external,reservations=reservations,
                unoccupied_reserved=spare,own_jobs=JOBS,available_bytes=available)


def validate_reference():
    evidence = base.read(PREP / "complete.json")
    base.require(evidence["status"]=="HOST_SPIKE_FULL1134_AND_20_PARTITIONS_PASS_NOT_DUT",
                 "Reference campaign incomplete")
    base.verify_pins(base.read(PREP / "source_pins.json"))
    expected = {"whole_all"}|{f"whole_op{x:02d}" for x in range(20)}
    refs = evidence["reference_results"]
    base.require(len(refs)==21 and {x["name"] for x in refs}==expected and
                 all(x["status"]=="PASS" for x in refs),"Reference membership incomplete")
    for row in refs:
        name=row["name"]
        base.require(base.sha(PREP / "spike" / (name+".elf"))==row["elf_sha256"] and
                     base.sha(PREP / "spike" / (name+".spike.log"))==row["log_sha256"],
                     "Reference result identity drift")
    programs = base.read(PREP / "soc/programs.json")["programs"]
    base.require(set(programs)==expected and evidence["programs"]["soc"]==programs,
                 "Prepared SoC membership differs")
    for name,program in programs.items():
        base.require(base.sha(Path(program["path"]))==program["sha256"],"SoC ELF drift")
        if name!="whole_all":
            op=int(name[-2:])
            base.require(program["first_op"]==op and program["end_op"]==op+1,"Wrong partition")
    tuples = base.read(PREP / "tuples.json")
    key=lambda x:(x["seed"],x["op"],x["mode"],x["index"])
    base.require(len(tuples["cases"])==len(set(map(key,tuples["cases"])))==1134 and
                 len(tuples["skipped"])==366,"Original tuple count changed")
    counts=Counter(x["op"] for x in tuples["cases"])
    base.require(all(programs[f"whole_op{x:02d}"]["original_cases"]==counts[x]
                     for x in range(20)),"Partition cardinality mismatch")
    return programs


def prepare(out):
    programs=validate_reference()
    ledger,repo,_=checked.original.identity()
    base.require(out.is_relative_to(HERE) and out!=HERE,"Output must be owned")
    out.mkdir(parents=True,exist_ok=False)
    # Begin with the four originally failing move forms; retain every load control.
    order=list(range(16,20))+list(range(16))
    entries=[]
    for op in order:
        name=f"whole_op{op:02d}"
        p=programs[name]
        entries.append(dict(id=name,elf=p["path"],sha256=p["sha256"],original_name=name,
            timeout_s=5400,pass_markers=p["pass_markers"],cases=p["cases"],
            original_cases=p["original_cases"],original_skips=p["original_skips"]))
    pins=dict(base.read(PREP / "source_pins.json"))
    pins.update(ledger["files"])
    snapshot=Path(ledger["snapshot"])
    pins.update({str(repo/p):h for p,h in base.read(snapshot / "snapshot.json")["files"].items()})
    for path in [Path(__file__),BASE / "replay_candidate04_regression_final.py",
        BASE / "replay_candidate04_regression_successor.py",BASE / "replay_candidate04_regression.py",
        BASE / "replay_memory_regression.py",BASE / "run.py",BASE / "prepare.py",
        checked.original.IMAGE / "image.json",snapshot / "snapshot.json",
        *[p for p in PREP.rglob("*") if p.is_file()]]:
        pins[str(path)]=base.sha(path)
    plan=dict(status="PREPARED_NOT_LAUNCHED",cases=entries,pins=pins,jobs=JOBS,
        original_cases=1134,original_skips=366,image_sha256=checked.original.IMAGE_SHA,
        stop_first_fail=True,outer_timeout_s=30000,
        scope="All1134 original configurations in20 operation partitions; no unmodified Linux ELF replay")
    base.save(out / "plan.json",plan)
    results=execute(plan,out / "dryrun",True)
    base.require(len(results)==20 and all(x.status=="DRY_RUN" for x in results),"Unexpected dry run")
    base.verify_pins(pins)
    base.save(out / "preflight.json",dict(status="READY_NOT_LAUNCHED",cases=20,
        original_cases=1134,jobs=JOBS,plan_sha256=base.sha(out / "plan.json")))
    print("READY_NOT_LAUNCHED "+base.sha(out / "plan.json"),flush=True)


def execute(plan,out,dry):
    ledger,repo,(runner,options_type,testcase,_)=base.image_context()
    tests=[testcase(c["id"],"app","",Path(c["elf"]),c["original_name"],c["timeout_s"])
           for c in plan["cases"]]
    options=options_type(repo,out,"default",JOBS,1,dry,False,True,Path(ledger["simv"]),True,None)
    entries={c["id"]:c for c in plan["cases"]}
    return checked.runner_class(runner,entries)(options,tests,sys.argv).run()


def work(out,seal):
    base.require(seal==base.sha(out / "plan.json"),"Wrong approved plan")
    plan=base.read(out / "plan.json")
    base.require(plan["jobs"]==JOBS and plan["image_sha256"]==checked.original.IMAGE_SHA and
                 len(plan["cases"])==20 and sum(x["original_cases"] for x in plan["cases"])==1134,
                 "Plan scope changed")
    base.verify_pins(plan["pins"])
    validate_reference()
    checked.original.identity()
    admission=resource_state(out)
    with (out / "launch.json").open("x") as stream:
        json.dump(dict(pid=os.getpid(),time=time.time(),plan_sha256=seal,admission=admission),stream,indent=2)
    try:
        results=execute(plan,out / "replay",False)
        base.verify_pins(plan["pins"])
        checked.original.identity()
        passed=len(results)==20 and all(x.status=="PASS" and x.returncode==0 for x in results)
        base.save(out / "complete.json",dict(status="PASS_1134_IN_20_PARTITIONS" if passed else "NOT_PASS",
            plan_sha256=seal,image_sha256=checked.original.IMAGE_SHA,pins_unchanged=True,
            results=[dict(name=x.name,status=x.status,returncode=x.returncode,
                          elapsed_s=x.elapsed_s,reason=x.reason) for x in results],
            finished=time.time(),scope=plan["scope"]))
        return int(not passed)
    except BaseException as error:
        base.save(out / "complete.json",dict(status="ERROR_NOT_PASS",error=str(error),finished=time.time()))
        raise


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode",choices=("prepare","work"))
    cli.add_argument("--out",type=Path,required=True)
    cli.add_argument("--seal")
    args=cli.parse_args()
    env=base.shared.environment()
    os.environ.clear();os.environ.update(env)
    target=args.out.resolve()
    base.require(target.is_relative_to(HERE) and target!=HERE,"Output must be owned")
    if args.mode=="prepare":
        prepare(target)
    else:
        raise SystemExit(work(target,args.seal))
