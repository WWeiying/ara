"""Exact historical721 prefix plus sealed GAP104 v2, fresh diagnostic replay; no EDA."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import collect_gap104_strict_v2 as c

life, bitmap, require = c.life, c.bitmap, c.require
OUT = life.OUT
BASE = c.BASE
HISTORICAL = OUT / "gap103-offline-admitted-720-20261006-01"
HISTORICAL_SEAL = "2a39f961402fd2ec536f58672466583942b6407e2028638736145713ba13955e"
BASE_SEAL = c.BASE_SEAL
CANDIDATE = OUT / "gap104-strict-candidate-721-20261006-02"
CANDIDATE_HASHES = {
    "evidence-pins.json": "ad5cccbbb967d2babd7b98751bb91950287759ad4fa7fb05f674aea008fe2939",
    "lifecycle.json": "b00eee538f99a1724a8d334b7da32c3155acb52e850b98e6e9a6d7f270f3a53b",
    "observed-data.json": "53be702fbe5cff12e5f5bf160c1fca33e9fd28453c125f304b11090abf9cca74",
    "raw-bitmap-delta.json": "74cf9dd1fcff2f2b25b256902491dc26d73b905b0ca98c7d4214df2849eebeef",
    "raw-union.proposed.json": "251ca8bceeab02f7fc594cf9fcdd2a162ba456b81a35c0e84f33a31c6b091c3e",
    "scalar-comparison.json": "72ce9c7df976f3ba4b10a1d8e2fd7a2b19e04ac1462af85834eb3249eb529bba",
    "single-raw-bits.json": "19d87f852f0d81b611ef78830f889f49cd13c481f0556611975615e39a007c15",
    "status.json": "db2f4137b073725caeeff241180f0f979d3a210141a04e287392755f22159f7e",
    "target-hits.json": "17f00cc4d9ee294e931ab15cd8659ff9a618f8777c84c412fa99601922b3edb9",
    "transport-byte-audit.json": "a4005646f0f7ccb34344c9dfbd87a3e998b8c981d3010e6ef52d40a0f8d8c058",
    "trap-ledger.json": "92a97e04fc76de63340e520af47c2e05fdda0dfeb4829183ed151153251d8c96",
    "vector-comparison.json": "f09991ca494e619371d13a4885877aeb2281990783c6c92ef6e2ad0f0448e9e9",
    "diagnostic-inputs.txt": "bbe8868457791a517a28272e771e2e4c50107df64b2179edf931c4d716f14ba7"
}


def bound(path, expected):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), "Aliased evidence")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "Expected evidence hash differs: " + str(path))
    return raw


def population(before, single):
    new = str(c.RUN / "code.vdb")
    require(len(before["tests"]) == len(set(before["tests"])) == 721 and single["tests"] == [new],
            "Wrong exact721/single population")
    require(new not in before["tests"], "Duplicate candidate VDB")
    require(not any("gap101-illegal-segment-store-old-image" in p or
                    "/results/gap71_qbs_fault/" in p for p in before["tests"]+[new]),
            "Historical FAIL mixed")
    union = bitmap.combine(before, single)
    require(union["tests"] == before["tests"]+[new] and
            len(union["tests"]) == len(set(union["tests"])) == 722, "Not exact721 prefix plus single")
    change = bitmap.delta(before, union)
    require(sum(change["metrics"].values()) > 0, "No fresh721 coverage gain")
    return union, change


def baseline_contract(manifest, state, before, historical):
    require(manifest["schema"] == "AKV_INDEPENDENT_SCALAR_HISTORICAL721_ADMISSION_V1" and
            manifest["output"] == str(BASE) and manifest["baseline"] == str(HISTORICAL) and
            manifest["baseline_seal"] == HISTORICAL_SEAL, "Only formal AKV721 baseline allowed")
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and
            state["baseline"] == 720 and state["aggregate_passed"] == 721 and
            state["new_passed"] == 1 and state["coverage_admitted"] is True, "Wrong formal721 status")
    require(len(historical["tests"]) == len(set(historical["tests"])) == 720 and
            before["tests"][:-1] == historical["tests"] and
            len(before["tests"]) == len(set(before["tests"])) == 721 and
            before["tests"][-1] == str(OUT / "akv-column-boundary-v2-old-image-20261006-01/code.vdb"),
            "Not exact sealed720 prefix plus AKV")


def candidate_contract(state):
    require(state["status"] == "GAP104_STRICT_V2_CANDIDATE_NOT_ADMITTED" and
            state["architecture_oracle_pass"] is True and state["target_hit_verified"] is True and
            state["fresh_target_gain_verified"] is True and state["static_target_baseline_tests"] == 720 and
            state["coverage_candidate_qualified"] is True and
            state["coverage_admitted"] is False and state["aggregate_admission"] is False and
            state["official_DVE_report"] is False and state["rtl_changed"] is False and
            state["simulations_started"] is False and state["baseline_tests"] == 721,
            "Not strict architecture-qualified candidate")


def evaluate(base_seal):
    require(base_seal == BASE_SEAL, "Only authoritative721 seal allowed")
    pins = {str(CANDIDATE/n):h for n,h in CANDIDATE_HASHES.items()}
    raw = {p:bound(p,h) for p,h in pins.items()}
    def candidate(name): return json.loads(raw[str(CANDIDATE/name)])
    require(not (CANDIDATE/"failure.json").exists(), "Rejected candidate cannot admit")
    state = candidate("status.json")
    candidate_contract(state)
    pins = life.merge_pins(pins,candidate("evidence-pins.json"))
    mpath = BASE/"admission-manifest.json"
    manifest = json.loads(bound(mpath,base_seal))
    require(all(Path(p).parent == BASE for p in manifest["output_pins"]), "Foreign baseline output")
    base_raw = {p:bound(p,h) for p,h in manifest["output_pins"].items()}
    pins = life.merge_pins(pins,{str(mpath):base_seal})
    pins = life.merge_pins(pins,manifest["output_pins"])
    pins = life.merge_pins(pins,json.loads(base_raw[str(BASE/"evidence-pins.json")]))
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_admit_gap104_offline.py")):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    def input_bytes(path):
        require(str(path) in pins,"Missing expected input pin: "+str(path))
        return bound(path,pins[str(path)])
    historical = json.loads(input_bytes(HISTORICAL/"combined-bits.json"))
    before = json.loads(base_raw[str(BASE/"combined-bits.json")])
    baseline_contract(manifest,json.loads(base_raw[str(BASE/"status.json")]),before,historical)
    require(base_raw[str(BASE/"combined-inputs.txt")].decode().splitlines() ==
            [str(c.DESIGN),*before["tests"]], "721 input identity/order differs")
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
    counts = c.shared.reference_counts(reference,pre["symbols"])
    require(counts == c.SCALAR_COUNTS,"Scalar reference count differs")
    scalar = c.shared.spike_trace.compare_commit_prefix(Path(pre["input_spike_trace"]),c.RUN/"commit_trace.csv",
        0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout="unshifted")
    c.shared.scalar_exact(scalar,counts)
    require(scalar == candidate("scalar-comparison.json"),"Actual scalar comparison differs")
    rows = list(csv.DictReader(io.StringIO(input_bytes(c.RUN/"commit_trace.csv").decode())))
    vectors = list(csv.DictReader(io.StringIO(input_bytes(c.RUN/"vector_trace.csv").decode())))
    control = c.lifecycle(rows,vectors)
    require(control == candidate("lifecycle.json") and c.observed(rows,pre["symbols"]) ==
            candidate("observed-data.json"),"Actual lifecycle/full oracle differs")
    transport = c.transport_exact(vectors)
    require(transport == candidate("transport-byte-audit.json"),"Actual granted byte audit differs")
    vector = c.shared.compare_vector_commits(Path(pre["input_spike_trace"]),c.RUN/"commit_trace.csv",
                                     c.RUN/"vector_trace.csv",0x80000000)
    c.vector_exact(vector,control,transport)
    require(vector == candidate("vector-comparison.json"),"Actual vector comparison differs")
    require(raw[str(CANDIDATE/"diagnostic-inputs.txt")].decode().splitlines() ==
            [str(c.DESIGN),str(c.RUN/"code.vdb")],"Single input identity differs")
    single = bitmap.collect(CANDIDATE/"diagnostic-inputs.txt")
    require(single == candidate("single-raw-bits.json"),"Actual single VDB differs")
    union, delta = population(before,single)
    target = json.loads(input_bytes(c.runner.PRE/"target-before.json"))
    hits = c.measure_targets(before,single,target)
    require(all(h["hit_single"] and h["fresh_latest_hit"] and not h["hit_before"] for h in hits),
            "No incremental exact targets on721")
    require(target == c.proof.target_evidence(), "Frozen720 target proof differs")
    traps = c.tracer_exact(input_bytes(c.RUN/"trace_hart_0.log").decode(),rows,pre["symbols"])
    require(traps == candidate("trap-ledger.json"), "Independent actual exception tracer differs")
    require(union == candidate("raw-union.proposed.json") and delta == candidate("raw-bitmap-delta.json") and
            hits == candidate("target-hits.json"), "Candidate raw union/delta/targets differ")
    console = input_bytes(c.RUN/"console.log").decode()
    vcslog = input_bytes(c.RUN/"run.vcs.log").decode()
    contracts = c.re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)',console)
    require(len(contracts) == 1 and tuple(map(int,contracts[0])) ==
            (control["requests"],control["responses"],2,0,0) and
            not c.shared.check_contract_log(c.RUN/"run.vcs.log") and vcslog.count("Core Test *** SUCCESS ***") == 1,
            "Contract/software SUCCESS differs")
    pins = life.merge_pins(pins,union["input_hashes"])
    pins = life.merge_pins(pins,{str(c.DESIGN/"snps/coverage/db"/p):h for p,h in union["design"].items()})
    life.check(pins)
    outputs = {n:candidate(n) for n in ("scalar-comparison.json","vector-comparison.json",
        "transport-byte-audit.json","observed-data.json","lifecycle.json","trap-ledger.json")}
    outputs.update({"combined-bits.json":union,"raw-bitmap-delta.json":delta,
                    "evidence-pins.json":pins,"target-hits.json":hits})
    outputs["status.json"] = dict(status="PASS_RAW_UNION_HISTORICAL_ONLY",baseline=721,
        aggregate_passed=722,new_passed=1,raw_delta=delta["metrics"],official_DVE_report=False,
        rtl_changed=False,new_RTL_signoff=False,simulations_started=False,
        inherited_721_full_oracle_readmission=False,sealed_strict_oracle_reused=True,
        actual_trace_and_single_vdb_rechecked=True,original_721_order_preserved=True,
        candidate_721_delta_rebuilt=True,checks=1309,exceptions=2,
        scalar_exact_counts=counts,scalar_skips=0,vector_instructions=64,vector_bytes=8192,
        shared_comparer_skipped_bytes=0,all_granted_bytes_independently_checked=True,
        independently_checked_unique_vrf_bytes=8192,
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
        require(manifest["schema"] == "GAP104_HISTORICAL722_ADMISSION_V1" and
                manifest["output"] == str(out) and manifest["baseline_seal"] == args.base_seal,
                "Admission identity differs")
        for path,h in manifest["output_pins"].items():
            require(Path(path).parent == out,"Foreign formal product"); bound(path,h)
    else:
        require(not out.exists(),"Fresh722 output required")
        if args.mode == "prepare": require(not record.exists(),"Fresh prepared record required")
    outputs,text = evaluate(args.base_seal)
    hashes = fingerprints(out,outputs,text)
    if args.mode == "verify":
        require(manifest["output_pins"] == hashes,"Formal products differ from exact reconstruction")
        print("GAP104_HISTORICAL722_OFFLINE_REVERIFIED "+args.seal)
        return
    proposal = dict(schema="GAP104_HISTORICAL722_PREPARED_V1",output=str(out),candidate=str(CANDIDATE),
        candidate_seals=CANDIDATE_HASHES,baseline=str(BASE),baseline_seal=args.base_seal,
        output_pins=hashes,input_pins=outputs["evidence-pins.json"],raw_delta=outputs["status.json"]["raw_delta"])
    if args.mode == "prepare":
        life.save(record,proposal)
        print(json.dumps(dict(prepared=str(record),seal=life.digest(record))))
        return
    require(json.loads(bound(record,args.seal)) == proposal,"Prepared722 contract differs")
    require(not out.exists(),"Output appeared during audit")
    out.mkdir()
    for name,value in outputs.items(): life.save(out/name,value)
    with (out/"combined-inputs.txt").open("x") as stream: stream.write(text)
    life.check(outputs["evidence-pins.json"])
    for path,h in hashes.items(): bound(path,h)
    life.save(out/"admission-manifest.json",dict(schema="GAP104_HISTORICAL722_ADMISSION_V1",
        output=str(out),candidate=str(CANDIDATE),candidate_seals=CANDIDATE_HASHES,
        baseline=str(BASE),baseline_seal=args.base_seal,prepared=str(record),prepared_seal=args.seal,
        output_pins=hashes))
    print(json.dumps(dict(output=str(out),seal=life.digest(out/"admission-manifest.json"),
                          aggregate_passed=722,raw_delta=outputs["status.json"]["raw_delta"])))


if __name__ == "__main__": main()

