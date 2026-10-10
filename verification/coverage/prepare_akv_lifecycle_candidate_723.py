"""Exact formal723 plus independently qualified lifecycle: prepare/check only.

No simulation, DVE, exclusions, admission operation or inherited-test readmission.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

import check_akv_lifecycle_offline_v3 as qualification
import closure_point_inventory as shape
import coverage_bitmap_delta as bitmap
from inventory_operand_debug import Design

life, require = qualification.life, qualification.require
BASE = life.OUT/"narrow-reject-r1-cached-offline-admitted-723-20261006-01"
BASE_SEAL = "2f68f64b880b95164f8db6aa2b569d305bd831ad4a05056563b2ab42eade45a4"
PARENT = life.OUT/"gap104-offline-admitted-722-20261006-02"
PARENT_SEAL = "b9ad9d11e0eeb709ebcf3e4bd6d5ccbdd94d4a229e9c80b144ef10cf8213415a"
QUALIFIED = life.OUT/"akv-lifecycle-parent-native-scalar-qualification-20261006-03"
QUALIFIED_SEAL = "e27229c47359b655eda66c246d652c7b941798c384263736d0e4b60c395bef50"
R1 = life.OUT/"narrow-reject-r1-cached-strict-candidate-719-20261006-01"
R1_SEAL = "81df1b592740010754f8208ae96daf0500d89c750e8891386134279da3589301"
RUN = qualification.previous.RUN
DESIGN = qualification.previous.native.common.DESIGN
OUTPUTS = {"single-raw-bits.json","proposed-combined-bits.json","raw-delta.json",
           "gained-compiled-points.json","target-reconciliation723.json","status.json",
           "candidate-inputs.txt","proposed-inputs.txt"}


def exact(actual, expected, label):
    require(all(k in actual and type(actual[k]) is type(v) and actual[k] == v for k,v in expected.items()),label)


def qualification_contract(seal, scalar, vector, contract, compiled):
    exact(seal,dict(status="NATIVE_SCALAR_COMPILED_REQUALIFIED_NOT_ADMITTED",run=str(RUN),
        run_seal=qualification.previous.RUN_SEAL,coverage_admitted=False,latest_population_bound=False),
        "Wrong exact lifecycle qualification")
    exact(scalar,dict(status="LIFECYCLE_COMPLETE_INDEPENDENT_SCALAR_MATCH_NOT_ADMISSION",
        matched_retirements=154769,matched_GPR_writes=104854,independently_executed_steps=154773,
        skipped_retirements=0,unknown_state_reads=0,mismatches=0,full_scalar_independent_qualified=True,
        full_scalar_differential_qualified=False,coverage_admitted=False),"Incomplete full scalar qualification")
    exact(vector,dict(status="NATIVE_BYTES_BOUND_TO_INDEPENDENT_MODEL",seed_bytes=4096,
        custom_write_bytes=128,snapshot_stores=320,rejected_write_bytes=0,backend_mirror_complete=True),
        "Incomplete exact native qualification")
    exact(contract,dict(requests=426,responses=426,exceptions=4,protocol_errors=0,outstanding=0,
        mmu_request_cycles=0,req_stalled=0,resp_stalled=0),"Incomplete terminal contract")
    exact(compiled,dict(status="EXACT_COMPILED_AKV_SOURCE_AND_FOUR_COORDINATES_REBOUND_NOT_GAIN_PROOF",
        module_checksum="3509320291",condition_checksum="2836473276",condition_width=392,
        source_sha256=qualification.ENGINE_SHA,latest_population_bound=False,coverage_admitted=False),
        "Missing compiled qualification")
    required={str(p) for p in qualification.required_tests()}
    require(set(seal["tests_pinned"]) == required and required <= set(seal["input_pins"]),
            "Missing reviewed qualification tests")


def baseline_contract(manifest, status, before, parent, r1, ledger):
    exact(manifest,dict(schema="R1_CACHED_HISTORICAL723_ADMISSION_V1",output=str(BASE),baseline=str(PARENT),
        baseline_seal=PARENT_SEAL,candidate=str(R1),candidate_seal=R1_SEAL),"Wrong formal723 ancestry")
    exact(status,dict(status="PASS_RAW_UNION_HISTORICAL_ONLY",aggregate_passed=723,baseline=722,
        new_passed=1,coverage_admitted=True,rtl_changed=False),"Not formal PASS723")
    require(len(parent["tests"]) == len(set(parent["tests"])) == 722 and
            len(before["tests"]) == len(set(before["tests"])) == 723 and
            before["tests"][:-1] == parent["tests"] and r1["tests"] == before["tests"][-1:] and
            before == bitmap.combine(parent,r1),"Broken independent722->723 OR/prefix")
    require(ledger == [str(DESIGN),*before["tests"]],"Wrong full ordered723 ledger")


def validate_bitmap(value):
    require(set(value["metrics"]) == set(bitmap.METRICS),"Incomplete raw metric set")
    for rows in value["metrics"].values():
        require(rows,"Empty metric universe")
        for record in rows.values():
            require(type(record["width"]) is int and record["width"] >= 0 and
                    isinstance(record["checksum"],str) and re.fullmatch(r"[0-9]+",record["checksum"]) and
                    isinstance(record["bits"],str) and re.fullmatch(r"0x[0-9a-f]+",record["bits"]) and
                    0 <= int(record["bits"],16) < 1 << record["width"],"Malformed/overflow raw bitmap")


def population(before, single):
    validate_bitmap(before);validate_bitmap(single)
    new=str(RUN/"code.vdb")
    require(len(before["tests"]) == len(set(before["tests"])) == 723 and single["tests"] == [new] and
            new not in before["tests"],"Wrong/duplicate lifecycle singleton")
    life.merge_pins(before["input_hashes"],single["input_hashes"])
    proposed=bitmap.combine(before,single)
    require(proposed["tests"] == before["tests"]+[new] and len(set(proposed["tests"])) == 724,
            "Not exact723 prefix plus one qualified test")
    delta=bitmap.delta(before,proposed)
    require(all(type(n) is int and n >= 0 for n in delta["metrics"].values()) and
            sum(delta["metrics"].values()) > 0,"Zero actual fresh gain cannot prepare admission")
    return proposed,delta


def unique_elf(elf_sha, base_pins):
    require(re.fullmatch(r"[0-9a-f]{64}",elf_sha) is not None and
            not any(p.endswith(".elf") and h == elf_sha for p,h in base_pins.items()),"Duplicate baseline ELF")


def raw_hit(record, raw):
    require(type(raw) is int and 0 <= raw < record["width"],"Invalid raw coordinate")
    return bool(int(record["bits"],16) >> (record["width"]-1-raw) & 1)


def gain_points(before, proposed, single, design, sources, pins):
    records=[]
    cond=shape.read_xml(design.db/"shape/cond.verilog.shape.xml")
    for metric in bitmap.METRICS:
        for scope,old in before["metrics"][metric].items():
            new=proposed["metrics"][metric][scope]
            gain=int(new["bits"],16) & ~int(old["bits"],16)
            if not gain:continue
            require(metric != "fsm","New FSM points require a separately reviewed mapper")
            node=shape.definition(cond,design.hierarchy[scope],old["checksum"]) if metric == "cond" else design.definition(scope,metric)
            require(node.get("chksum") == old["checksum"],"Gained metric checksum drift")
            points={p["raw_index"]:p for p in shape.points(metric,node,old["width"])}
            source=design.source(scope);path=Path(source["resolved_path"])
            require(str(path) in sources,"Gained source not in frozen build")
            if life.digest(path) != sources[str(path)]:
                require(path == life.ROOT/"hardware/src/ara_dispatcher.sv","Unresolved gained frozen source bytes")
                path=life.OUT/"old-image-source-evidence-20261006-01/ara_dispatcher.sv"
            pins=life.merge_pins(pins,{str(path):sources[source["resolved_path"]]})
            for raw in range(old["width"]):
                if not gain >> (old["width"]-1-raw) & 1:continue
                require(raw in points and raw_hit(single["metrics"][metric][scope],raw),"Unresolved/not-single gained coordinate")
                records.append(dict(scope=scope,metric=metric,point=points[raw],source=source,
                    source_evidence=str(path),source_sha256=sources[source["resolved_path"]],
                    module_checksum=design.hierarchy[scope].get("chksum"),metric_checksum=old["checksum"],
                    width=old["width"],bitmap_LSB_index=old["width"]-1-raw,baseline_hit=False,
                    sample_hit=True,proposed_hit=True,native_GUI_ID_qualification=False))
    return pins,records


def evaluate(single_inputs):
    q=life.read_bound(QUALIFIED/"qualification-seal.json",QUALIFIED_SEAL)
    require(not (QUALIFIED/"failure.json").exists(),"Rejected qualification")
    pins=life.merge_pins(q["input_pins"],q["output_pins"])
    pins=life.merge_pins(pins,{str(QUALIFIED/"qualification-seal.json"):QUALIFIED_SEAL})
    manifest=life.read_bound(BASE/"admission-manifest.json",BASE_SEAL)
    require(all(Path(p).parent == BASE for p in manifest["output_pins"]),"Foreign baseline products")
    pins=life.merge_pins(pins,manifest["output_pins"])
    def read(path):
        require(str(path) in pins,"Unpinned evidence: "+str(path))
        return life.read_bound(path,pins[str(path)])
    base_pins=read(BASE/"evidence-pins.json")
    pins=life.merge_pins(pins,base_pins)
    pins=life.merge_pins(pins,{str(BASE/"admission-manifest.json"):BASE_SEAL})
    qualification_contract(q,read(QUALIFIED/"scalar-qualification.json"),read(QUALIFIED/"native-vector.json"),
                           read(QUALIFIED/"contract.json"),read(QUALIFIED/"compiled-source-binding.json"))
    ancestor=life.read_bound(PARENT/"admission-manifest.json",PARENT_SEAL)
    require(ancestor["schema"] == "GAP104_HISTORICAL722_ADMISSION_V2" and ancestor["output"] == str(PARENT),
            "Wrong formal722 ancestor")
    pins=life.merge_pins(pins,ancestor["output_pins"])
    pins=life.merge_pins(pins,{str(PARENT/"admission-manifest.json"):PARENT_SEAL})
    r1=life.read_bound(R1/"status.json",R1_SEAL)
    exact(r1,dict(status="R1_CACHED_STRICT_CANDIDATE_VERIFIED_NOT_ADMITTED",coverage_admitted=False),"Wrong sealed R1 predecessor")
    pins=life.merge_pins(pins,r1["pins"])
    pins=life.merge_pins(pins,{str(R1/"status.json"):R1_SEAL})
    before=read(BASE/"combined-bits.json");parent=read(PARENT/"combined-bits.json")
    old_single=read(R1/"single-raw-bits.json")
    baseline_contract(manifest,read(BASE/"status.json"),before,parent,old_single,
                      (BASE/"combined-inputs.txt").read_text().splitlines())
    for value in (before,parent,old_single):
        require(all(pins.get(p) == h for p,h in value["input_hashes"].items()),"Unbound inherited bitmap input")
    run=read(RUN/"manifest.json")
    unique_elf(run["pins"][run["input_elf"]],base_pins)
    require(run["pins"][run["input_elf"]] == qualification.previous.runner.ELF_SHA,"Wrong new ELF")
    design=Design(DESIGN)
    for rel,sha in before["design"].items():
        require(pins.get(str(design.db/rel)) == sha,"Inherited frozen design unbound")
    test_vdb=RUN/"code.vdb"
    members=sorted(str(p) for p in test_vdb.rglob("*") if p.is_file())
    require(test_vdb.resolve() == test_vdb and members == sorted(p for p in q["input_pins"] if Path(p).is_relative_to(test_vdb)) and
            not any(p.is_symlink() for p in test_vdb.rglob("*")),"Qualified VDB membership drift")
    files=[Path(__file__).resolve(),Path(__file__).with_name("test_prepare_akv_lifecycle_candidate_723.py")]
    for module in list(sys.modules.values()):
        name=getattr(module,"__file__",None)
        if name and Path(name).resolve().is_relative_to(Path(__file__).resolve().parent):files.append(Path(name).resolve())
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files})
    life.check(pins)
    require(single_inputs.read_text().splitlines() == [str(DESIGN),str(test_vdb)],"Wrong collector inputs")
    single=bitmap.collect(single_inputs)
    pins=life.merge_pins(pins,single["input_hashes"])
    proposed,delta=population(before,single)
    sources=read(qualification.previous.fixture.BUILD/"build-source-pins.json")
    pins,records=gain_points(before,proposed,single,design,sources,pins)
    counts=Counter(r["metric"] for r in records)
    require(all(counts[m] == n for m,n in delta["metrics"].items()),"Mapped product gain count mismatch")
    target=read(qualification.previous.runner.PRE/"target-before.json")
    cond=shape.read_xml(design.db/"shape/cond.verilog.shape.xml")
    node=shape.definition(cond,design.hierarchy[qualification.previous.fixture.SCOPE],"2836473276")
    binding=qualification.bind_compiled(design.hierarchy[qualification.previous.fixture.SCOPE],
        design.source(qualification.previous.fixture.SCOPE),node,shape.points("cond",node,392),target,sources)
    targets=[]
    for t in binding["coordinates"]:
        scope=t["scope"];raw=t["raw_index"]
        a,b,c=(value["metrics"]["cond"][scope] for value in (before,single,proposed))
        require(all((r["width"],r["checksum"]) == (392,"2836473276") for r in (a,b,c)),"Target shape drift")
        targets.append(dict(t,inventory721_hit=t["baseline_hit"],baseline723_hit=raw_hit(a,raw),
            sample_hit=raw_hit(b,raw),proposed_hit=raw_hit(c,raw),new_vs723=not raw_hit(a,raw) and raw_hit(b,raw)))
    require(members == sorted(str(p) for p in test_vdb.rglob("*") if p.is_file()),"Sample VDB changed")
    life.check(pins)
    artifacts={"single-raw-bits.json":single,"proposed-combined-bits.json":proposed,"raw-delta.json":delta,
        "gained-compiled-points.json":records,"target-reconciliation723.json":targets,
        "status.json":dict(status="AKV_LIFECYCLE_723_STRICT_CANDIDATE_NOT_ADMITTED",baseline_tests=723,
            proposed_tests=724,new_admitted=0,coverage_admitted=False,raw_delta=delta["metrics"],
            baseline_seal=BASE_SEAL,qualification_seal=QUALIFIED_SEAL,exact723_prefix=True,
            full_scalar_independent_qualified=True,full_scalar_differential_qualified=False,
            native_Spike_comparison=False,whole_VRF_CSR_guards_qualified=True,exceptions=4,checks=7740,
            targets_hit=sum(t["sample_hit"] for t in targets),targets_total=4,
            historical_old_image_only=True,inherited723_replayed=False,inherited723_pins_rechecked=True,
            official_DVE_report=False,new_RTL_signoff=False,rtl_changed=False,simulations_started=False)}
    return pins,artifacts,"\n".join([str(DESIGN),*proposed["tests"]])+"\n"


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(),"Fresh direct candidate directory required")
    out.mkdir()
    inputs=out/"candidate-inputs.txt"
    with inputs.open("x") as stream:stream.write(str(DESIGN)+"\n"+str(RUN/"code.vdb")+"\n")
    try:
        pins,artifacts,text=evaluate(inputs)
        for name,value in artifacts.items():life.save(out/name,value)
        with (out/"proposed-inputs.txt").open("x") as stream:stream.write(text)
        pins=life.merge_pins(pins,{str(inputs):life.digest(inputs)})
        life.check(pins)
        life.save(out/"candidate-seal.json",dict(input_pins=pins,
            output_pins={str(out/name):life.digest(out/name) for name in OUTPUTS},coverage_admitted=False,
            baseline=str(BASE),baseline_seal=BASE_SEAL,qualification_seal=QUALIFIED_SEAL))
        return artifacts["status.json"]
    except Exception as error:
        life.save(out/"failure.json",dict(status="CANDIDATE_REJECTED_NOT_ADMITTED",reason=str(error)))
        raise


def check(out, seal):
    require(out.parent == life.OUT and out.resolve() == out and not (out/"failure.json").exists(),"Rejected/aliased candidate")
    record=life.read_bound(out/"candidate-seal.json",seal)
    exact(record,dict(coverage_admitted=False,baseline=str(BASE),baseline_seal=BASE_SEAL,
                     qualification_seal=QUALIFIED_SEAL),"Candidate identity drift")
    require(set(record["output_pins"]) == {str(out/name) for name in OUTPUTS},"Incomplete candidate products")
    life.check(record["input_pins"]);life.check(record["output_pins"])
    pins,artifacts,text=evaluate(out/"candidate-inputs.txt")
    pins=life.merge_pins(pins,{str(out/"candidate-inputs.txt"):life.digest(out/"candidate-inputs.txt")})
    require(pins == record["input_pins"],"Candidate input pin set drift")
    for name,value in artifacts.items():
        require(life.read_bound(out/name,record["output_pins"][str(out/name)]) == value,"Candidate recomputation mismatch")
    require((out/"proposed-inputs.txt").read_text() == text,"Proposed full membership drift")
    return artifacts["status.json"]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("mode",choices=("prepare","check"))
    p.add_argument("--output",type=Path,required=True);p.add_argument("--seal");a=p.parse_args()
    require((a.mode == "check") == bool(a.seal),"Only check requires a candidate seal")
    out=a.output.absolute()
    result=prepare(out) if a.mode == "prepare" else check(out,a.seal)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/"candidate-seal.json"),result=result)))


if __name__ == "__main__":main()
