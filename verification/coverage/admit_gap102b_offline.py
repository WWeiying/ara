"""Fresh exact VSBC718 prefix plus strictly sealed GAP102B; no EDA."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import collect_gap102b_strict_v3 as c

life, bitmap, require = c.life, c.bitmap, c.require
OUT = life.OUT
BASE = OUT / "opivx-vsbc-vd0-offline-admitted-718-20261006-01"
CANDIDATE = OUT / "gap102b-strict-candidate-717-20261006-03"
QUALIFICATION_SEAL = "8176e9ce76d98b05432313b091202ab916cde5f810c3ca447b55decbb534e2a7"


def bound(path, expected):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), "Aliased evidence")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "Expected evidence hash differs: " + str(path))
    return raw


def population(before, single):
    new = str(c.RUN / "code.vdb")
    require(len(before["tests"]) == len(set(before["tests"])) == 718 and single["tests"] == [new],
            "Wrong exact718/single population")
    require(new not in before["tests"], "Duplicate candidate VDB")
    require(not any("gap101-illegal-segment-store-old-image" in p or
                    "/results/gap71_qbs_fault/" in p for p in before["tests"]+[new]),
            "Historical FAIL mixed")
    union = bitmap.combine(before, single)
    require(union["tests"] == before["tests"]+[new] and
            len(union["tests"]) == len(set(union["tests"])) == 719, "Not exact718 prefix plus single")
    change = bitmap.delta(before, union)
    require(sum(change["metrics"].values()) > 0, "No fresh718 coverage gain")
    return union, change


def baseline_contract(manifest, state, before, historical):
    require(manifest["schema"] == "OPIVX_VSBC_HISTORICAL718_ADMISSION_V1" and
            manifest["output"] == str(BASE) and manifest["baseline"] == str(c.BASE),
            "Only formal VSBC718 baseline allowed")
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and
            state["baseline"] == 717 and state["aggregate_passed"] == 718 and
            state["new_passed"] == 1, "Wrong formal718 status")
    require(len(historical["tests"]) == len(set(historical["tests"])) == 717 and
            before["tests"][:-1] == historical["tests"] and len(before["tests"]) == 718 and
            before["tests"][-1] == str(OUT / "opivx-vsbc-vd0-old-image-717-20261006-01/code.vdb"),
            "Not exact sealed717 prefix plus VSBC")


def evaluate(base_seal):
    qpath = CANDIDATE / "qualification-manifest.json"
    qualification = json.loads(bound(qpath, QUALIFICATION_SEAL))
    require(qualification["status"] == "STRICT_ARCHITECTURE_AND_RAW_TARGET_VERIFIED_NOT_ADMITTED" and
            qualification["coverage_admitted"] is False and qualification["tests_passed"] == 24,
            "Wrong frozen qualification")
    pins = {str(qpath): QUALIFICATION_SEAL}
    pins = life.merge_pins(pins, qualification["output_pins"])
    pins = life.merge_pins(pins, qualification["collector_and_test_pins"])
    require(all(Path(p).parent == CANDIDATE for p in qualification["output_pins"]), "Foreign candidate output")
    raw = {p: bound(p,h) for p,h in qualification["output_pins"].items()}
    def candidate(name): return json.loads(raw[str(CANDIDATE/name)])
    require(not (CANDIDATE/"failure.json").exists(), "Rejected candidate cannot admit")
    state = candidate("status.json")
    require(state["status"] == "GAP102B_STRICT_V3_CANDIDATE_NOT_ADMITTED" and
            state["architecture_oracle_pass"] is True and state["target_hit_verified"] is True and
            state["coverage_admitted"] is False and state["baseline_tests"] == 717,
            "Not strict architecture-qualified candidate")
    pins = life.merge_pins(pins,candidate("evidence-pins.json"))
    mpath = BASE/"admission-manifest.json"
    manifest = json.loads(bound(mpath,base_seal))
    require(all(Path(p).parent == BASE for p in manifest["output_pins"]), "Foreign baseline output")
    base_raw = {p:bound(p,h) for p,h in manifest["output_pins"].items()}
    pins = life.merge_pins(pins,{str(mpath):base_seal})
    pins = life.merge_pins(pins,manifest["output_pins"])
    pins = life.merge_pins(pins,json.loads(base_raw[str(BASE/"evidence-pins.json")]))
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_admit_gap102b_offline.py")):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    def input_bytes(path):
        require(str(path) in pins,"Missing expected input pin: "+str(path))
        return bound(path,pins[str(path)])
    historical = json.loads(input_bytes(c.BASE/"combined-bits.json"))
    before = json.loads(base_raw[str(BASE/"combined-bits.json")])
    baseline_contract(manifest,json.loads(base_raw[str(BASE/"status.json")]),before,historical)
    require(base_raw[str(BASE/"combined-inputs.txt")].decode().splitlines() ==
            [str(c.DESIGN),*before["tests"]], "718 input identity/order differs")
    prepared = json.loads(bound(c.RUN.with_name(c.RUN.name+".prepared.json"),c.PREPARED_SEAL))
    runtime = json.loads(input_bytes(c.RUN/"manifest.json"))
    require(runtime == prepared and runtime["command"] == c.runner.command(c.RUN) and
            runtime["timeout_s"] == 600 and runtime["old_image_files_checked"] == 66,
            "Run/prepared contract differs")
    c.runner.validate(runtime["preflight"])
    require(life.merge_pins(pins,runtime["pins"]) == pins,"Runtime evidence missing")
    terminal = json.loads(input_bytes(c.RUN/"simulation-status.json"))
    require(terminal["status"] == "SIMULATION_EXITED_NOT_ADMITTED" and terminal["returncode"] == 0 and
            terminal["case"] == c.runner.NAME and terminal["coverage_admitted"] is False,"Not successful run")
    pre = runtime["preflight"]
    reference = c.proof.s.parse_spike_commits(Path(pre["input_spike_trace"]))
    require(c.proof.validate(reference,pre["symbols"],input_bytes(Path(pre["input_spike_trace"])).decode()) ==
            pre["validation"],"Independent reference differs")
    counts = c.reference_counts(reference,pre["symbols"])
    require(counts == c.SCALAR_COUNTS,"Scalar reference count differs")
    scalar = c.spike_trace.compare_commit_prefix(Path(pre["input_spike_trace"]),c.RUN/"commit_trace.csv",
        0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout="unshifted")
    c.scalar_exact(scalar,counts)
    require(scalar == candidate("scalar-comparison.json"),"Actual scalar comparison differs")
    rows = list(csv.DictReader(io.StringIO(input_bytes(c.RUN/"commit_trace.csv").decode())))
    vectors = list(csv.DictReader(io.StringIO(input_bytes(c.RUN/"vector_trace.csv").decode())))
    control = c.lifecycle(rows,vectors,pre["symbols"])
    require(control == candidate("lifecycle.json") and c.observed(rows,pre["symbols"]) ==
            candidate("observed-data.json"),"Actual lifecycle/full oracle differs")
    transport = c.transport_exact(vectors)
    require(transport == candidate("transport-byte-audit.json"),"Actual granted byte audit differs")
    vector = c.compare_vector_commits(Path(pre["input_spike_trace"]),c.RUN/"commit_trace.csv",
                                     c.RUN/"vector_trace.csv",0x80000000)
    c.vector_exact(vector,transport)
    require(vector == candidate("vector-comparison.json"),"Actual vector comparison differs")
    require(raw[str(CANDIDATE/"diagnostic-inputs.txt")].decode().splitlines() ==
            [str(c.DESIGN),str(c.RUN/"code.vdb")],"Single input identity differs")
    single = bitmap.collect(CANDIDATE/"diagnostic-inputs.txt")
    require(single == candidate("single-raw-bits.json"),"Actual single VDB differs")
    union, delta = population(before,single)
    target = json.loads(input_bytes(c.runner.PRE/"target-before.json"))
    hits = c.measure_targets(before,single,target)
    require(all(h["hit_single"] and not h["hit_before"] for h in hits),"No incremental target on718")
    pins = life.merge_pins(pins,union["input_hashes"])
    pins = life.merge_pins(pins,{str(c.DESIGN/"snps/coverage/db"/p):h for p,h in union["design"].items()})
    life.check(pins)
    outputs = {n:candidate(n) for n in ("scalar-comparison.json","vector-comparison.json",
        "transport-byte-audit.json","observed-data.json","lifecycle.json")}
    outputs.update({"combined-bits.json":union,"raw-bitmap-delta.json":delta,
                    "evidence-pins.json":pins,"target-hits.json":hits})
    outputs["status.json"] = dict(status="PASS_RAW_UNION_HISTORICAL_ONLY",baseline=718,
        aggregate_passed=719,new_passed=1,raw_delta=delta["metrics"],official_DVE_report=False,
        rtl_changed=False,new_RTL_signoff=False,simulations_started=False,
        inherited_718_full_oracle_readmission=False,sealed_strict_oracle_reused=True,
        actual_trace_and_single_vdb_rechecked=True,original_718_order_preserved=True,
        diagnostic_717_delta_not_reused=True,checks=723,exceptions=0,
        scalar_exact_counts=counts,scalar_skips=0,vector_instructions=35,vector_bytes=5252,
        shared_comparer_skipped_bytes=128,all_granted_bytes_independently_checked=5382,
        unknown_granted_bytes=0,verified_input_pins=len(pins))
    return outputs,"\n".join([str(c.DESIGN),*union["tests"]])+"\n"


def fingerprints(out, outputs, text):
    result = {str(out/n):hashlib.sha256((json.dumps(v,indent=2)+"\n").encode()).hexdigest()
              for n,v in outputs.items()}
    result[str(out/"combined-inputs.txt")] = hashlib.sha256(text.encode()).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","admit","verify"))
    parser.add_argument("--base-seal",required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seal")
    args = parser.parse_args(argv); out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out,"Direct independent output required")
    require((args.mode != "prepare") == bool(args.seal),"Admit/verify require fixed seal")
    record = out.with_name(out.name+".prepared.json")
    if args.mode == "verify":
        manifest = json.loads(bound(out/"admission-manifest.json",args.seal))
        require(manifest["schema"] == "GAP102B_HISTORICAL719_ADMISSION_V1" and
                manifest["output"] == str(out) and manifest["baseline_seal"] == args.base_seal,
                "Admission identity differs")
        for path,h in manifest["output_pins"].items():
            require(Path(path).parent == out,"Foreign formal product"); bound(path,h)
    else:
        require(not out.exists(),"Fresh719 output required")
        if args.mode == "prepare": require(not record.exists(),"Fresh prepared record required")
    outputs,text = evaluate(args.base_seal)
    hashes = fingerprints(out,outputs,text)
    if args.mode == "verify":
        require(manifest["output_pins"] == hashes,"Formal products differ from exact reconstruction")
        print("GAP102B_HISTORICAL719_OFFLINE_REVERIFIED "+args.seal)
        return
    proposal = dict(schema="GAP102B_HISTORICAL719_PREPARED_V1",output=str(out),candidate=str(CANDIDATE),
        qualification_seal=QUALIFICATION_SEAL,baseline=str(BASE),baseline_seal=args.base_seal,
        output_pins=hashes,input_pins=outputs["evidence-pins.json"],raw_delta=outputs["status.json"]["raw_delta"])
    if args.mode == "prepare":
        life.save(record,proposal)
        print(json.dumps(dict(prepared=str(record),seal=life.digest(record))))
        return
    require(json.loads(bound(record,args.seal)) == proposal,"Prepared719 contract differs")
    require(not out.exists(),"Output appeared during audit")
    out.mkdir()
    for name,value in outputs.items(): life.save(out/name,value)
    with (out/"combined-inputs.txt").open("x") as stream: stream.write(text)
    life.check(outputs["evidence-pins.json"])
    for path,h in hashes.items(): bound(path,h)
    life.save(out/"admission-manifest.json",dict(schema="GAP102B_HISTORICAL719_ADMISSION_V1",
        output=str(out),candidate=str(CANDIDATE),qualification_seal=QUALIFICATION_SEAL,
        baseline=str(BASE),baseline_seal=args.base_seal,prepared=str(record),prepared_seal=args.seal,
        output_pins=hashes))
    print(json.dumps(dict(output=str(out),seal=life.digest(out/"admission-manifest.json"),
                          aggregate_passed=719,raw_delta=outputs["status.json"]["raw_delta"])))


if __name__ == "__main__": main()
