"""Fresh AKV rebind to formal GAP103 historical720; no simulation or automatic admission."""
import argparse
from collections import Counter
import json
from pathlib import Path

import prepare_akv_column_boundary_admission_v2 as prior

life, require = prior.life, prior.require
BASE = life.OUT/"gap103-offline-admitted-720-20261006-01"
BASE_SEAL = "2a39f961402fd2ec536f58672466583942b6407e2028638736145713ba13955e"
PREVIOUS = life.OUT/"akv-column-boundary-scalar-admission-prepared719-20261006-01"
PREVIOUS_SEAL = "ca24fe74ab498de1dca564a19d56d3aec700bac3494b72934c81ee922646b063"
OUTPUTS = {"proposed-combined-bits.json", "raw-delta.json", "actual-gained-compiled-points.json",
           "raw24-mapping-audit.json", "status.json"}


def population(before, historical, gap103, single):
    new = str(prior.old.r.c.RUN/"code.vdb")
    require(len(historical["tests"]) == len(set(historical["tests"])) == 719 and
            len(before["tests"]) == len(set(before["tests"])) == 720 and
            before["tests"][:-1] == historical["tests"] and
            gap103["tests"] == before["tests"][-1:], "Broken exact719->720 prefix")
    require(before == prior.old.r.c.common.bitmap.combine(historical,gap103),
            "Formal720 differs from independent719/GAP103 OR")
    require(single["tests"] == [new] and new not in before["tests"], "Wrong/duplicate AKV singleton")
    require(not any("akv-column-boundary-old-image-20261006-01/" in p or
                    "gap101-illegal-segment-store-old-image" in p or
                    "/results/gap71_qbs_fault/" in p for p in before["tests"]+[new]),
            "Known FAIL/timeout population")
    union = prior.old.r.c.common.bitmap.combine(before,single)
    require(union["tests"] == before["tests"]+[new] and len(set(union["tests"])) == 721,
            "Not exact720 plus successful AKV")
    delta = prior.old.r.c.common.bitmap.delta(before,union)
    require(all(type(n) is int and n >= 0 for n in delta["metrics"].values()) and
            sum(delta["metrics"].values()) > 0, "No actual positive coverage gain; cannot add a zero-gain case")
    return union,delta


def evaluate():
    previous, _, _ = prior.check(PREVIOUS,PREVIOUS_SEAL)
    pins = life.merge_pins(previous["input_pins"],previous["output_pins"])
    pins = life.merge_pins(pins,{str(PREVIOUS/"prepared-seal.json"):PREVIOUS_SEAL})
    manifest = life.read_bound(BASE/"admission-manifest.json",BASE_SEAL)
    require(manifest["schema"] == "GAP103_HISTORICAL720_ADMISSION_V1" and
            manifest["output"] == str(BASE) and manifest["baseline"] == str(prior.old.r.BASE) and
            manifest["baseline_seal"] == prior.BASE_SEAL and
            all(Path(p).parent == BASE for p in manifest["output_pins"]), "Wrong formal720 ancestry")
    pins = life.merge_pins(pins,{str(BASE/"admission-manifest.json"):BASE_SEAL})
    pins = life.merge_pins(pins,manifest["output_pins"])
    def read(path):
        require(str(path) in pins,"Unpinned evidence: "+str(path))
        return life.read_bound(path,pins[str(path)])
    state = read(BASE/"status.json")
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and
            type(state["aggregate_passed"]) is int and state["aggregate_passed"] == 720 and
            type(state["baseline"]) is int and state["baseline"] == 719 and
            type(state["new_passed"]) is int and state["new_passed"] == 1, "Not formal PASS720")
    pins = life.merge_pins(pins,read(BASE/"evidence-pins.json"))
    require(pins.get(str(prior.old.r.BASE/"admission-manifest.json")) == prior.BASE_SEAL,
            "Missing sealed719 parent")
    candidate = Path(manifest["candidate"])
    require(candidate == life.OUT/"gap103-strict-candidate-719-20261006-01", "Foreign GAP103 candidate")
    for name, hash_value in manifest["candidate_seals"].items():
        require(Path(name).name == name and pins.get(str(candidate/name)) == hash_value,
                "Missing GAP103 candidate binding")
    before = read(BASE/"combined-bits.json")
    historical = read(prior.old.r.BASE/"combined-bits.json")
    gap103 = read(candidate/"single-raw-bits.json")
    single = read(prior.old.r.CANDIDATE/"sample-bits.json")
    for bitmap in (before,historical,gap103,single):
        require(all(pins.get(p) == h for p,h in bitmap["input_hashes"].items()), "Unbound bitmap inputs")
    require((BASE/"combined-inputs.txt").read_text().splitlines() ==
            [str(prior.old.r.c.common.DESIGN),*before["tests"]], "Wrong ordered720 ledger")
    union,delta = population(before,historical,gap103,single)
    design = prior.old.Design(prior.old.r.c.common.DESIGN)
    db = prior.old.r.c.common.DESIGN/"snps/coverage/db"
    cond = prior.old.shape.read_xml(db/"shape/cond.verilog.shape.xml")
    records = []
    for metric in ("line","cond","branch"):
        for scope, previous_record in before["metrics"][metric].items():
            indices = prior.old.gain_indices(previous_record,union["metrics"][metric][scope])
            if not indices: continue
            node = (prior.old.shape.definition(cond,design.hierarchy[scope],previous_record["checksum"])
                    if metric == "cond" else design.definition(scope,metric))
            mapped = {p["raw_index"]:p for p in prior.old.shape.points(metric,node,previous_record["width"])}
            source = design.source(scope)
            require(str(Path(source["resolved_path"])) in pins,"Unpinned gained source")
            for raw in indices:
                require(raw in mapped,"Unresolved gained compiled point")
                records.append(dict(scope=scope,metric=metric,point=mapped[raw],source=source,
                    bitmap_LSB_index=previous_record["width"]-1-raw,baseline_hit=False,
                    sample_hit=prior.old.raw_hit(single["metrics"][metric][scope],raw),union_hit=True,
                    native_GUI_ID_qualification=False))
    require(dict(Counter(r["metric"] for r in records)) ==
            {m:n for m,n in delta["metrics"].items() if n},"Compiled gain count mismatch")
    old_records = read(PREVIOUS/"actual-gained-compiled-points.json")
    require(all(record in old_records for record in records),"Impossible new gain beyond719 qualification")
    target = read(prior.COMPILED/"raw24-mapping-audit.json")
    branch = before["metrics"]["branch"][prior.old.r.c.software.SCOPE]
    target = dict(target,baseline_hit=prior.old.raw_hit(branch,24),
                  sample_hit=prior.old.raw_hit(single["metrics"]["branch"][prior.old.r.c.software.SCOPE],24),
                  union_hit=prior.old.raw_hit(union["metrics"]["branch"][prior.old.r.c.software.SCOPE],24),
                  baseline_tests=720)
    for path in (Path(prior.__file__).resolve(),Path(prior.__file__).with_name("test_"+Path(prior.__file__).name)):
        require(pins.get(str(path)) == life.digest(path),"Previous verifier source drift")
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_prepare_akv_column_boundary_admission_720.py")):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    status = dict(status="AKV720_SCALAR_AND_NATIVE_ADMISSION_PREPARED_NOT_ADMITTED",
        baseline_tests=720,proposed_tests=721,raw_delta=delta["metrics"],coverage_admitted=False,
        full_scalar_independent_qualified=True,full_scalar_differential_qualified=False,
        native_Spike_comparison=False,historical_old_image_only=True,rtl_changed=False,simulations_started=False,
        raw24_target_objective_met=target["sample_hit"],qualification_seal=prior.QUALIFICATION_SEAL,
        baseline_seal=BASE_SEAL,exact720_prefix_preserved=True)
    return pins,dict(zip(("proposed-combined-bits.json","raw-delta.json","actual-gained-compiled-points.json",
                         "raw24-mapping-audit.json","status.json"),(union,delta,records,target,status)))


def prepare(out):
    prior.fresh_output(out)
    pins,artifacts = evaluate()
    out.mkdir()
    for name,value in artifacts.items():life.save(out/name,value)
    life.save(out/"prepared-seal.json",dict(input_pins=pins,
        output_pins={str(out/name):life.digest(out/name) for name in artifacts},coverage_admitted=False))
    return artifacts["status.json"]


def check(prepared, seal_hash):
    require(prepared.parent == life.OUT and prepared.resolve() == prepared,"Wrong prepared path")
    seal = life.read_bound(prepared/"prepared-seal.json",seal_hash)
    require(seal["coverage_admitted"] is False and
            set(seal["output_pins"]) == {str(prepared/name) for name in OUTPUTS},"Incomplete prepared evidence")
    life.check(seal["input_pins"]);life.check(seal["output_pins"])
    pins,artifacts = evaluate()
    require(pins == seal["input_pins"],"Prepared input pin set drift")
    for name,value in artifacts.items():
        require(life.read_bound(prepared/name,seal["output_pins"][str(prepared/name)]) == value,
                "Prepared rebind differs")
    return seal,artifacts


def admit(out, prepared, seal_hash):
    prior.fresh_output(out)
    seal,artifacts = check(prepared,seal_hash)
    pins = life.merge_pins(seal["input_pins"],seal["output_pins"])
    pins = life.merge_pins(pins,{str(prepared/"prepared-seal.json"):seal_hash})
    life.check(pins)
    out.mkdir()
    union = artifacts["proposed-combined-bits.json"]
    life.save(out/"combined-bits.json",union)
    (out/"combined-inputs.txt").write_text("\n".join([str(prior.old.r.c.common.DESIGN),*union["tests"]])+"\n")
    life.save(out/"raw-delta.json",artifacts["raw-delta.json"])
    life.save(out/"evidence-pins.json",pins)
    status = dict(artifacts["status.json"],status="PASS_RAW_UNION_HISTORICAL_ONLY",baseline=720,
                  aggregate_passed=721,new_passed=1,coverage_admitted=True,official_DVE_report=False)
    life.save(out/"status.json",status)
    life.save(out/"admission-manifest.json",dict(schema="AKV_INDEPENDENT_SCALAR_HISTORICAL721_ADMISSION_V1",
        output=str(out),baseline=str(BASE),baseline_seal=BASE_SEAL,prepared=str(prepared),prepared_seal=seal_hash,
        qualification_seal=prior.QUALIFICATION_SEAL,output_pins={str(p):life.digest(p) for p in out.iterdir()}))
    return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","check","admit"))
    parser.add_argument("--baseline-seal",required=True)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--prepared",type=Path)
    parser.add_argument("--seal")
    args=parser.parse_args()
    require(args.baseline_seal == BASE_SEAL,"Different baseline requires fresh rebind")
    if args.mode == "prepare":
        require(args.output is not None and args.prepared is None and args.seal is None,"Wrong prepare arguments")
        out=args.output.absolute();status=prepare(out)
        print(json.dumps(dict(output=str(out),seal=life.digest(out/"prepared-seal.json"),result=status)))
    else:
        require(args.prepared is not None and args.seal is not None,"Prepared path/seal required")
        if args.mode == "check":
            require(args.output is None,"Check cannot write output")
            _,artifacts=check(args.prepared.absolute(),args.seal);status=artifacts["status.json"]
        else:
            require(args.output is not None,"Admission needs fresh output")
            status=admit(args.output.absolute(),args.prepared.absolute(),args.seal)
        print(json.dumps(status))


if __name__ == "__main__":
    main()
