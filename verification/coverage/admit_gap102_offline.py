"""Parent-sealed GAP102 candidate to exact historical718; never run EDA."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import collect_gap102_strict as collector

life, bitmap, proof, require = collector.life, collector.bitmap, collector.proof, collector.require
OUT = life.OUT
CANDIDATE = OUT / "gap102-strict-candidate-717-20261006-01"
FILES = ("diagnostic-inputs.txt", "evidence-pins.json", "lifecycle.json", "observed-data.json",
         "raw-bitmap-delta.json", "raw-union.proposed.json", "scalar-comparison.json",
         "single-raw-bits.json", "status.json", "target-hits.json", "vector-comparison.json")
COLLECTOR_PINS = {
    str(Path(collector.__file__).resolve()): "193d420fb732a365a4080f1a3dda7438dea4d555968144053b36a7d40f6b0092",
    str(Path(collector.__file__).with_name("test_collect_gap102_strict.py")):
        "5b2a58b15d5c971929a4725860e7e49f79fc6b02854306d8075efcd1b0f5a9cd"}


def bound(path, expected):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), "Aliased evidence")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "Expected evidence hash differs: " + str(path))
    return raw


def population(before, single, proposed):
    new = str(collector.RUN / "code.vdb")
    require(len(before["tests"]) == len(set(before["tests"])) == 717 and single["tests"] == [new],
            "Wrong717/single population")
    require(not any("gap101-illegal-segment-store-old-image" in t for t in before["tests"]+[new]),
            "Original GAP101 FAIL mixed")
    union = bitmap.combine(before,single)
    require(union == proposed and union["tests"] == before["tests"]+[new] and
            len(union["tests"]) == len(set(union["tests"])) == 718, "Not exact717 prefix plus single")
    return union, bitmap.delta(before,union)


def review_pins(path, seal):
    pins = json.loads(bound(path,seal))
    require(type(pins) is dict and set(pins) == {str(CANDIDATE/name) for name in FILES},
            "Parent review must seal all exact eleven candidate artifacts")
    require(all(isinstance(h,str) and len(h)==64 and all(c in "0123456789abcdef" for c in h)
                for h in pins.values()), "Malformed expected review hashes")
    return pins


def evaluate(review_path, review_seal):
    seals = review_pins(review_path,review_seal)
    raw = {path:bound(path,h) for path,h in seals.items()}
    def candidate(name): return json.loads(raw[str(CANDIDATE/name)])
    state = candidate("status.json")
    require(state["status"] == "GAP102_STRICT_CANDIDATE_NOT_ADMITTED" and state["baseline_tests"] == 717
            and all(state[k] is False for k in ("coverage_admitted","aggregate_admission","rtl_changed",
                                              "simulations_started","official_DVE_report")), "Candidate is not complete PASS")
    require(not (CANDIDATE/"failure.json").exists(), "Rejected candidate cannot admit")
    pins = life.merge_pins(seals,candidate("evidence-pins.json"))
    pins = life.merge_pins(pins,COLLECTOR_PINS)
    pins = life.merge_pins(pins,{str(Path(review_path)):review_seal})
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_admit_gap102_offline.py")):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    base_manifest = json.loads(bound(proof.BASE/"admission-manifest.json",proof.BASE_SEAL))
    base_paths = {str(proof.BASE/name):base_manifest["output_pins"][str(proof.BASE/name)]
                  for name in ("combined-bits.json","combined-inputs.txt","status.json","evidence-pins.json")}
    base_raw = {path:bound(path,h) for path,h in base_paths.items()}
    pins = life.merge_pins(pins,base_paths)
    pins = life.merge_pins(pins,{str(proof.BASE/"admission-manifest.json"):proof.BASE_SEAL})
    pins = life.merge_pins(pins,json.loads(base_raw[str(proof.BASE/"evidence-pins.json")]))
    life.check(pins)
    def input_bytes(path):
        require(str(path) in pins,"Missing expected input pin: "+str(path))
        return bound(path,pins[str(path)])
    base_state = json.loads(base_raw[str(proof.BASE/"status.json")])
    require(base_state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and base_state["aggregate_passed"] == 717,
            "Wrong frozen717 baseline")
    prepared = json.loads(bound(collector.RUN.with_name(collector.RUN.name+".prepared.json"),collector.PREPARED_SEAL))
    runtime = json.loads(input_bytes(collector.RUN/"manifest.json"))
    require(runtime == prepared and runtime["command"] == collector.runner.command(collector.RUN), "Run differs")
    collector.runner.validate(runtime["preflight"])
    require(life.merge_pins(pins,runtime["pins"]) == pins, "Runtime evidence absent from candidate pins")
    terminal = json.loads(input_bytes(collector.RUN/"simulation-status.json"))
    require(terminal["status"] == "SIMULATION_EXITED_NOT_ADMITTED" and terminal["returncode"] == 0 and
            terminal["case"] == collector.runner.NAME and terminal["coverage_admitted"] is False, "Run not successful")
    collector.scalar_exact(candidate("scalar-comparison.json"),collector.SCALAR_COUNTS)
    collector.vector_exact(candidate("vector-comparison.json"))
    rows = list(csv.DictReader(io.StringIO(input_bytes(collector.RUN/"commit_trace.csv").decode())))
    vectors = list(csv.DictReader(io.StringIO(input_bytes(collector.RUN/"vector_trace.csv").decode())))
    symbols = runtime["preflight"]["symbols"]
    require(collector.lifecycle(rows,vectors,symbols) == candidate("lifecycle.json"), "Actual lifecycle differs")
    require(collector.observed(rows,symbols) == candidate("observed-data.json"), "Actual complete data oracle differs")
    before = json.loads(base_raw[str(proof.BASE/"combined-bits.json")])
    design = proof.old.BUILD/"sim/simv.vdb"
    require(base_raw[str(proof.BASE/"combined-inputs.txt")].decode().splitlines() == [str(design),*before["tests"]]
            and raw[str(CANDIDATE/"diagnostic-inputs.txt")].decode().splitlines() ==
            [str(design),str(collector.RUN/"code.vdb")], "Input identity/order differs")
    single = bitmap.collect(CANDIDATE/"diagnostic-inputs.txt")
    require(single == candidate("single-raw-bits.json"), "Actual raw VDB differs")
    union,delta = population(before,single,candidate("raw-union.proposed.json"))
    require(delta == candidate("raw-bitmap-delta.json") and delta["metrics"] == state["raw_delta"], "Delta differs")
    target = json.loads(input_bytes(collector.runner.PRE/"target-before.json"))
    collector.runner.validate_targets(target)
    expected_hits = []
    for row in target["targets"]:
        scope,metric,index = row["scope"],row["metric"],row["point"]["raw_index"]
        old,new = before["metrics"][metric][scope],single["metrics"][metric][scope]
        require((old["width"],old["checksum"]) == (row["width"],row["checksum"]) ==
                (new["width"],new["checksum"]), "Target shape differs")
        bit = 1 << (old["width"]-1-index)
        require(not int(old["bits"],16)&bit and int(new["bits"],16)&bit, "No actual target increment")
        expected_hits.append(dict(scope=scope,metric=metric,raw_index=index,hit_before=False,hit_single=True))
    require(candidate("target-hits.json") == expected_hits, "Target evidence differs")
    pins = life.merge_pins(pins,union["input_hashes"])
    pins = life.merge_pins(pins,{str(design/"snps/coverage/db"/p):h for p,h in union["design"].items()})
    life.check(pins)
    outputs = {name:candidate(name) for name in ("scalar-comparison.json","vector-comparison.json",
               "observed-data.json","lifecycle.json","target-hits.json")}
    outputs.update({"combined-bits.json":union,"raw-bitmap-delta.json":delta,"evidence-pins.json":pins})
    outputs["status.json"] = dict(status="PASS_RAW_UNION_HISTORICAL_ONLY",baseline=717,aggregate_passed=718,
        new_passed=1,official_DVE_report=False,rtl_changed=False,new_RTL_signoff=False,simulations_started=False,
        inherited_717_full_oracle_readmission=False,sealed_strict_oracle_reused=True,
        actual_trace_and_single_vdb_rechecked=True,original_gap101_fail_excluded=True,
        original_717_order_preserved=True,raw_delta=delta["metrics"],checks=723,exceptions=0,
        scalar_exact_counts=collector.SCALAR_COUNTS,scalar_skips=0,vector_instructions=35,vector_bytes=6144,
        verified_input_pins=len(pins))
    return outputs,"\n".join([str(design),*union["tests"]])+"\n"


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--review-pins",type=Path,required=True)
    parser.add_argument("--review-seal",required=True)
    parser.add_argument("--verify",action="store_true")
    parser.add_argument("--seal")
    args=parser.parse_args(argv)
    out=args.output.absolute(); review=args.review_pins.absolute()
    require(out.parent==OUT and out.resolve()==out and review.parent==OUT and review.resolve()==review,
            "Independent canonical outputs/review evidence required")
    if args.verify:
        require(args.seal is not None,"External admission seal required")
        manifest=json.loads(bound(out/"admission-manifest.json",args.seal))
        require(manifest["schema"]=="GAP102_HISTORICAL718_ADMISSION_V1" and manifest["output"]==str(out)
                and manifest["review_pins"]==str(review) and manifest["review_seal"]==args.review_seal,"Manifest differs")
        for path,h in manifest["output_pins"].items():
            require(Path(path).parent==out,"Foreign output"); bound(path,h)
    else:
        require(args.seal is None and not out.exists(),"Fresh output; no overwrite or automatic retry")
    outputs,text=evaluate(review,args.review_seal)
    if args.verify:
        require(set(manifest["output_pins"])=={str(out/n) for n in [*outputs,"combined-inputs.txt"]},"Incomplete seal")
        for name,obj in outputs.items(): require(json.loads((out/name).read_bytes())==obj,"Reconstructed output differs")
        require((out/"combined-inputs.txt").read_text()==text,"Population differs")
        print("GAP102_HISTORICAL718_OFFLINE_REVERIFIED "+args.seal)
        return
    require(not out.exists(),"Output appeared during audit")
    out.mkdir()
    for name,obj in outputs.items(): life.save(out/name,obj)
    with (out/"combined-inputs.txt").open("x") as stream: stream.write(text)
    life.check(outputs["evidence-pins.json"])
    life.save(out/"admission-manifest.json",dict(schema="GAP102_HISTORICAL718_ADMISSION_V1",output=str(out),
        candidate=str(CANDIDATE),baseline=str(proof.BASE),review_pins=str(review),review_seal=args.review_seal,
        output_pins={str(out/n):life.digest(out/n) for n in [*outputs,"combined-inputs.txt"]}))
    print(json.dumps(dict(output=str(out),seal=life.digest(out/"admission-manifest.json"))))


if __name__=="__main__": main()
