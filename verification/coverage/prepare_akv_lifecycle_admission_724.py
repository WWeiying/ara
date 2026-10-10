"""Stage the reviewed exact723->724 lifecycle admission; commit needs parent authorization."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

import prepare_akv_lifecycle_candidate_723_v2 as candidate

life, require = candidate.life, candidate.require
AUTHORIZATION = "PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL"
PRODUCTS = {"combined-bits.json","combined-inputs.txt","raw-delta.json","gained-compiled-points.json",
            "target-reconciliation723.json","evidence-pins.json","status.json"}


def admission_gate(state, targets, records):
    candidate.exact(state,dict(status="AKV_LIFECYCLE_723_STRICT_CANDIDATE_NOT_ADMITTED",baseline_tests=723,
        proposed_tests=724,new_admitted=0,coverage_admitted=False,full_scalar_independent_qualified=True,
        full_scalar_differential_qualified=False,native_Spike_comparison=False,whole_VRF_CSR_guards_qualified=True,
        checks=7740,exceptions=4,targets_hit=4,targets_total=4,exact723_prefix=True,
        baseline_seal=candidate.BASE_SEAL,qualification_seal=candidate.QUALIFIED_SEAL),"Incomplete exact724 eligibility")
    expected=dict(line=3,cond=4,branch=3,fsm=0)
    require(set(state["raw_delta"]) == set(expected) and
            all(type(state["raw_delta"][m]) is int and state["raw_delta"][m] == n for m,n in expected.items()) and
            sum(state["raw_delta"].values()) > 0,"Not independently reviewed positive723 gain")
    require(len(targets) == 4 and {t["raw_index"] for t in targets} == {8,194,199,201} and
            all(t["baseline723_hit"] is False and t["sample_hit"] is True and t["proposed_hit"] is True and
                t["new_vs723"] is True and t["native_GUI_ID_qualification"] is False for t in targets),
            "Missing exact four fresh targets")
    require(Counter(r["metric"] for r in records) == Counter({m:n for m,n in expected.items() if n}),
            "Incomplete compiled gained points")
    coordinates=[(r["metric"],r["scope"],r["point"]["raw_index"]) for r in records]
    require(len(coordinates) == len(set(coordinates)) and
            all(r["baseline_hit"] is False and r["sample_hit"] is True and r["proposed_hit"] is True and
                r["native_GUI_ID_qualification"] is False for r in records),"Duplicate/incomplete gained coordinates")


def fresh(path):
    require(path.parent == life.OUT and path.resolve() == path and not path.exists(),"Fresh direct output required")


def check_candidate(path, seal):
    # Isolate the frozen verifier's loaded-module pin inventory from this caller.
    result=subprocess.run([sys.executable,str(Path(candidate.__file__).resolve()),"check",
        "--output",str(path),"--seal",seal],cwd=life.ROOT,capture_output=True,text=True,timeout=180,check=True)
    value=json.loads(result.stdout)
    require(value["output"] == str(path) and value["seal"] == seal,"Foreign candidate verifier result")
    return value["result"]


def prepare(out, formal_output, path, seal):
    fresh(out);fresh(formal_output);require(out != formal_output,"Prepare is not formal output")
    state=check_candidate(path,seal)
    receipt=life.read_bound(path/"candidate-seal.json",seal)
    def read(name):return life.read_bound(path/name,receipt["output_pins"][str(path/name)])
    targets,records=read("target-reconciliation723.json"),read("gained-compiled-points.json")
    admission_gate(state,targets,records)
    pins=life.merge_pins(receipt["input_pins"],receipt["output_pins"])
    pins=life.merge_pins(pins,{str(path/"candidate-seal.json"):seal})
    for p in (Path(__file__).resolve(),Path(__file__).with_name("test_prepare_akv_lifecycle_admission_724.py"),
              Path(sys.executable).resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    out.mkdir()
    values={"combined-bits.json":read("proposed-combined-bits.json"),"raw-delta.json":read("raw-delta.json"),
            "gained-compiled-points.json":records,"target-reconciliation723.json":targets,"evidence-pins.json":pins,
            "status.json":dict(state,status="AKV_HISTORICAL724_PREPARED_NOT_ADMITTED",formal_output=str(formal_output))}
    for name,value in values.items():life.save(out/name,value)
    with (out/"combined-inputs.txt").open("x") as stream:stream.write((path/"proposed-inputs.txt").read_text())
    life.check(pins)
    life.save(out/"prepared-seal.json",dict(schema="AKV_LIFECYCLE_HISTORICAL724_PREPARE_V1",output=str(out),
        formal_output=str(formal_output),baseline=str(candidate.BASE),baseline_seal=candidate.BASE_SEAL,
        candidate=str(path),candidate_seal=seal,qualification_seal=candidate.QUALIFIED_SEAL,
        input_pins=pins,output_pins={str(out/n):life.digest(out/n) for n in PRODUCTS},coverage_admitted=False,
        new_admitted=0,requires_parent_authorization=True))
    return life.digest(out/"prepared-seal.json")


def check(out, seal):
    require(out.parent == life.OUT and out.resolve() == out,"Canonical prepared directory required")
    receipt=life.read_bound(out/"prepared-seal.json",seal)
    candidate.exact(receipt,dict(schema="AKV_LIFECYCLE_HISTORICAL724_PREPARE_V1",output=str(out),
        baseline=str(candidate.BASE),baseline_seal=candidate.BASE_SEAL,qualification_seal=candidate.QUALIFIED_SEAL,
        coverage_admitted=False,new_admitted=0,requires_parent_authorization=True),"Prepared identity drift")
    require(set(receipt["output_pins"]) == {str(out/n) for n in PRODUCTS},"Missing/foreign prepared products")
    life.check(receipt["input_pins"]);life.check(receipt["output_pins"])
    path=Path(receipt["candidate"]);check_candidate(path,receipt["candidate_seal"])
    c=life.read_bound(path/"candidate-seal.json",receipt["candidate_seal"])
    def read(name):return life.read_bound(out/name,receipt["output_pins"][str(out/name)])
    state=read("status.json")
    original=life.read_bound(path/"status.json",c["output_pins"][str(path/"status.json")])
    require(state == dict(original,status="AKV_HISTORICAL724_PREPARED_NOT_ADMITTED",formal_output=receipt["formal_output"]),
            "Prepared state mismatch")
    admission_gate(original,read("target-reconciliation723.json"),read("gained-compiled-points.json"))
    for staged,source in (("combined-bits.json","proposed-combined-bits.json"),("combined-inputs.txt","proposed-inputs.txt"),
                          ("raw-delta.json","raw-delta.json"),("gained-compiled-points.json","gained-compiled-points.json"),
                          ("target-reconciliation723.json","target-reconciliation723.json")):
        require(receipt["output_pins"][str(out/staged)] == c["output_pins"][str(path/source)],"Prepared/candidate product drift")
    require(read("evidence-pins.json") == receipt["input_pins"],"Prepared input inventory differs")
    return receipt


def admit(prepared, seal, output, authorization):
    require(authorization == AUTHORIZATION,"Separate explicit parent authorization required")
    receipt=check(prepared,seal)
    require(str(output) == receipt["formal_output"],"Different formal output requires fresh prepare")
    fresh(output)
    pins=life.merge_pins(receipt["input_pins"],receipt["output_pins"])
    pins=life.merge_pins(pins,{str(prepared/"prepared-seal.json"):seal})
    life.check(pins);output.mkdir()
    for name in PRODUCTS-{"status.json","evidence-pins.json"}:
        with (output/name).open("xb") as stream:stream.write((prepared/name).read_bytes())
    life.save(output/"evidence-pins.json",pins)
    state=life.read_bound(prepared/"status.json",receipt["output_pins"][str(prepared/"status.json")])
    state=dict(state,status="PASS_RAW_UNION_HISTORICAL_ONLY",baseline=723,aggregate_passed=724,new_passed=1,
               new_admitted=1,coverage_admitted=True)
    life.save(output/"status.json",state);life.check(pins)
    life.save(output/"admission-manifest.json",dict(schema="AKV_LIFECYCLE_HISTORICAL724_ADMISSION_V1",output=str(output),
        baseline=str(candidate.BASE),baseline_seal=candidate.BASE_SEAL,prepared=str(prepared),prepared_seal=seal,
        candidate=receipt["candidate"],candidate_seal=receipt["candidate_seal"],qualification_seal=candidate.QUALIFIED_SEAL,
        output_pins={str(output/n):life.digest(output/n) for n in PRODUCTS},authorization=authorization))
    return life.digest(output/"admission-manifest.json")


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("mode",choices=("prepare","check","admit"))
    p.add_argument("--output",type=Path);p.add_argument("--formal-output",type=Path)
    p.add_argument("--candidate",type=Path);p.add_argument("--candidate-seal")
    p.add_argument("--prepared",type=Path);p.add_argument("--seal");p.add_argument("--authorization");a=p.parse_args()
    if a.mode == "prepare":
        require(a.output and a.formal_output and a.candidate and a.candidate_seal and
                not (a.prepared or a.seal or a.authorization),"Exact prepare arguments required")
        seal=prepare(a.output.absolute(),a.formal_output.absolute(),a.candidate.absolute(),a.candidate_seal)
        print(json.dumps(dict(status="PREPARED_NOT_ADMITTED",output=str(a.output.absolute()),seal=seal)))
    elif a.mode == "check":
        require(a.prepared and a.seal and not (a.output or a.formal_output or a.candidate or a.candidate_seal or a.authorization),
                "Exact readonly check arguments required")
        check(a.prepared.absolute(),a.seal);print("PREPARED724_CHECK_PASS_NOT_ADMITTED")
    else:
        require(a.prepared and a.seal and a.output and a.authorization and
                not (a.formal_output or a.candidate or a.candidate_seal),"Explicit parent commit arguments required")
        seal=admit(a.prepared.absolute(),a.seal,a.output.absolute(),a.authorization)
        print(json.dumps(dict(output=str(a.output.absolute()),seal=seal,status="PASS_RAW_UNION_HISTORICAL_ONLY")))


if __name__ == "__main__":main()
