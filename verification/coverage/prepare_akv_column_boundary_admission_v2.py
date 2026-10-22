"""Exact formal719 AKV successor; independent scalar qualification, no simulation."""
import argparse
from collections import Counter
import json
from pathlib import Path

import prepare_akv_column_boundary_admission_719 as old
import akv_column_scalar_oracle as oracle

life, require = old.life, old.require
BASE_SEAL = "0edf5405a8139eea50d82af6181f7d53ccb70699c2b232c8e3001add0ec242bb"
COMPILED = life.OUT / "akv-column-boundary-v5-admission-prepared719-20261006-01"
COMPILED_SEAL = "c4ea51af6bc7e4e07881971d99ec2b362436a233b9e87a38e2001b4a0ea6edeb"
QUALIFICATION = life.OUT / "akv-column-scalar-qualification-20261006-01"
QUALIFICATION_SEAL = "2b180eecec58330dd8e853489cc4d6d6f6a0f53ec9185856985b8187bfd8f54b"
QUAL_FILES = {"scalar-qualification.json", "source-contract.json",
              "independent-custom-ledger.json", "independent-native-byte-binding.json"}


def validate_scalar(result, contract, effects, ledger, symbols):
    require(result["status"] == "COMPLETE_BOUNDED_INDEPENDENT_SCALAR_ISA_AND_AKV_MODEL_MATCH_NOT_ADMISSION",
            "Incomplete scalar qualification")
    exact = dict(matched_retirements=103458, independently_executed_steps=103459,
                 matched_GPR_writes=76176, matched_scalar_loads=18698, matched_scalar_stores=7819,
                 skipped_retirements=0, unknown_state_reads=0, mismatches=0)
    for key, value in exact.items():
        require(type(result[key]) is int and result[key] == value, "Wrong scalar boundary: "+key)
    require(result["full_scalar_independent_qualified"] is True and
            result["full_scalar_differential_qualified"] is False and
            result["native_Spike_comparison"] is False and result["coverage_admitted"] is False,
            "Missing independent scalar scope / false Spike claim")
    require(result["independently_derived_traps"] == [dict(pc=symbols["boundary_bad"], cause=2,
            tval=0, handler=symbols["boundary_handler"])], "Wrong precise exception")
    require(contract["status"] == "FROZEN_SOURCE_AND_ELABORATION_INITIAL_STATE_CONTRACT_VERIFIED" and
            contract["elaborated_GPR_scope"] == oracle.GPR_SCOPE and contract["module_checksum"] == "1875497202" and
            contract["reset_GPRs_all_zero"] is True and contract["initial_privilege"] == "M" and
            contract["initial_mstatus"] == "0xa00000000" and contract["initial_mtvec"] == "0x80000040" and
            contract["initial_vtype"] == "0x8000000000000000" and
            contract["dirty_and_MRET_source_anchors_verified"] is True and
            contract["ELF_no_compressed_instructions"] is True, "Missing reset/elaboration contract")
    require(effects == dict(status="INDEPENDENT_MODEL_BYTES_EXACTLY_BOUND_TO_NATIVE_WRITES",
            matched_seed_bytes=4096, matched_custom_bytes=388, expected_values_not_derived_from_DUT=True),
            "Missing independent native-byte binding")
    require(len(ledger) == 8 and [c["fault"] for c in ledger] ==
            [False, False, True, False, False, False, False, False] and
            sum(c["write_bytes"] for c in ledger) == 388, "Incomplete independent custom ledger")


def bind_qualification(seal, pins):
    require(seal["coverage_admitted"] is False and
            set(seal["output_pins"]) == {str(QUALIFICATION/name) for name in QUAL_FILES},
            "Missing/foreign scalar evidence")
    native_path = old.r.CANDIDATE / "candidate-seal.json"
    require(seal["input_pins"].get(str(native_path)) == old.r.CANDIDATE_SEAL,
            "Scalar qualification bound to different native candidate")
    require(seal["input_pins"].get(str(oracle.native.RUN/"manifest.json")) == oracle.native.RUN_SEAL,
            "Different scalar run")
    merged = life.merge_pins(pins, seal["input_pins"])
    return life.merge_pins(merged, seal["output_pins"])


def evaluate(baseline_seal):
    require(baseline_seal == BASE_SEAL, "Different baseline requires fresh ancestry/delta rebind, not719 reuse")
    pins, union, delta, _ = old.r.evaluate(baseline_seal)
    path = COMPILED/"prepared-seal.json"
    sealed = life.read_bound(path, COMPILED_SEAL)
    require(sealed["coverage_admitted"] is False and
            all(Path(p).parent == COMPILED for p in sealed["output_pins"]), "Foreign compiled proof")
    pins = life.merge_pins(pins, sealed["input_pins"])
    pins = life.merge_pins(pins, sealed["output_pins"])
    pins = life.merge_pins(pins, {str(path):COMPILED_SEAL})
    path = QUALIFICATION/"qualification-seal.json"
    qualification = life.read_bound(path, QUALIFICATION_SEAL)
    pins = bind_qualification(qualification, pins)
    pins = life.merge_pins(pins, {str(path):QUALIFICATION_SEAL})
    for module in (old, oracle):
        for path in (Path(module.__file__).resolve(), Path(module.__file__).with_name("test_"+Path(module.__file__).name)):
            require(pins.get(str(path)) == life.digest(path), "Pinned verifier source drift")
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_prepare_akv_column_boundary_admission_v2.py")):
        pins = life.merge_pins(pins, {str(path):life.digest(path)})
    life.check(pins)
    def read(path):
        require(str(path) in pins, "Missing evidence pin: "+str(path))
        return life.read_bound(path, pins[str(path)])
    require(not (QUALIFICATION/"failure.json").exists(), "Rejected scalar qualification")
    manifest = read(oracle.native.RUN/"manifest.json")
    symbols = dict(manifest["preflight"]["symbols"])
    elf = Path(manifest["preflight"]["input_elf"])
    require(pins.get(str(elf)) == oracle.ELF_SHA, "Scalar/native ELF mismatch")
    for name in ("query", "key", "value", "descriptor", "seed"):
        symbols[name] = oracle.native.software.shared._elf_symbol(elf,oracle.native.software.shared.LLVM/"llvm-readelf",name)
    result = read(QUALIFICATION/"scalar-qualification.json")
    contract = read(QUALIFICATION/"source-contract.json")
    effects = read(QUALIFICATION/"independent-native-byte-binding.json")
    ledger = read(QUALIFICATION/"independent-custom-ledger.json")
    validate_scalar(result, contract, effects, ledger, symbols)
    sources = read(oracle.native.software.BUILD/"build-source-pins.json")
    _, fresh_contract = oracle.source_contract(sources,pins)
    require(contract == fresh_contract, "Source contract rederivation mismatch")
    rows = oracle.native.commit_rows(oracle.native.RUN/"commit_trace.csv")
    model, fresh_result = oracle.replay(elf.read_bytes(),symbols,rows)
    arch = oracle.native.commit_audit(rows,symbols,elf.read_bytes())
    oracle.native.vector_audit(oracle.native.RUN/"vector_trace.csv",arch)
    fresh_effects = oracle.bind_native_effects(model,arch,oracle.native.common.read_csv(
        oracle.native.RUN/"vector_trace.csv",oracle.native.common.VECTOR_FIELDS))
    oracle.native.stdout_audit((oracle.native.RUN/"run.vcs.log").read_text())
    require(result == fresh_result and ledger == model.commands and effects == fresh_effects,
            "Scalar qualification independent replay mismatch")
    before = read(old.r.BASE/"combined-bits.json")
    single = read(old.r.CANDIDATE/"sample-bits.json")
    records = read(COMPILED/"actual-gained-compiled-points.json")
    design = old.Design(old.r.c.common.DESIGN)
    db = old.r.c.common.DESIGN/"snps/coverage/db"
    cond = old.shape.read_xml(db/"shape/cond.verilog.shape.xml")
    expected = []
    for metric in ("line", "cond", "branch"):
        for scope, previous in before["metrics"][metric].items():
            indices = old.gain_indices(previous,union["metrics"][metric][scope])
            if not indices: continue
            node = (old.shape.definition(cond,design.hierarchy[scope],previous["checksum"])
                    if metric == "cond" else design.definition(scope,metric))
            points = {p["raw_index"]:p for p in old.shape.points(metric,node,previous["width"])}
            source = design.source(scope)
            for raw in indices:
                require(raw in points, "Unmapped compiled gain")
                expected.append(dict(scope=scope,metric=metric,point=points[raw],
                    bitmap_LSB_index=previous["width"]-1-raw,source=source,baseline_hit=False,
                    sample_hit=old.raw_hit(single["metrics"][metric][scope],raw),union_hit=True,
                    native_GUI_ID_qualification=False))
    require(records == expected and dict(Counter(r["metric"] for r in records)) ==
            {m:n for m,n in delta["metrics"].items() if n}, "Compiled gain rebind mismatch")
    life.check(pins)
    status = dict(status="AKV719_SCALAR_AND_NATIVE_ADMISSION_PREPARED_NOT_ADMITTED",
        baseline_tests=719,proposed_tests=720,raw_delta=delta["metrics"],coverage_admitted=False,
        full_scalar_independent_qualified=True,full_scalar_differential_qualified=False,
        native_Spike_comparison=False,raw24_target_objective_met=False,
        historical_old_image_only=True,rtl_changed=False,simulations_started=False,
        qualification_seal=QUALIFICATION_SEAL,baseline_seal=BASE_SEAL)
    return pins, union, delta, records, status


def fresh_output(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")


def prepare(out, baseline_seal):
    fresh_output(out)
    pins, union, delta, records, status = evaluate(baseline_seal)
    out.mkdir()
    for name, value in (("proposed-combined-bits.json",union),("raw-delta.json",delta),
                        ("actual-gained-compiled-points.json",records),("status.json",status)):
        life.save(out/name,value)
    life.save(out/"prepared-seal.json",dict(input_pins=pins,
        output_pins={str(p):life.digest(p) for p in out.iterdir()},coverage_admitted=False))
    return status


def check(prepared, seal_hash):
    require(prepared.parent == life.OUT and prepared.resolve() == prepared, "Wrong prepared path")
    seal = life.read_bound(prepared/"prepared-seal.json",seal_hash)
    require(seal["coverage_admitted"] is False and set(seal["output_pins"]) ==
            {str(prepared/name) for name in ("proposed-combined-bits.json", "raw-delta.json",
                                           "actual-gained-compiled-points.json", "status.json")},
            "Incomplete prepared evidence")
    life.check(seal["input_pins"]);life.check(seal["output_pins"])
    pins, union, delta, records, status = evaluate(BASE_SEAL)
    require(pins == seal["input_pins"], "Prepared input pin set drift")
    for name, value in (("proposed-combined-bits.json",union),("raw-delta.json",delta),
                        ("actual-gained-compiled-points.json",records),("status.json",status)):
        require(life.read_bound(prepared/name,seal["output_pins"][str(prepared/name)]) == value,
                "Prepared evidence differs")
    return seal, union, status


def admit(out, prepared, seal_hash):
    fresh_output(out)
    seal, union, status = check(prepared,seal_hash)
    pins = life.merge_pins(seal["input_pins"],seal["output_pins"])
    pins = life.merge_pins(pins,{str(prepared/"prepared-seal.json"):seal_hash})
    life.check(pins)
    out.mkdir()
    life.save(out/"combined-bits.json",union)
    (out/"combined-inputs.txt").write_text("\n".join([str(old.r.c.common.DESIGN),*union["tests"]])+"\n")
    life.save(out/"raw-delta.json",life.read_bound(prepared/"raw-delta.json",pins[str(prepared/"raw-delta.json")]))
    life.save(out/"evidence-pins.json",pins)
    status = dict(status, status="PASS_RAW_UNION_HISTORICAL_ONLY",aggregate_passed=720,
                  baseline=719,new_passed=1,coverage_admitted=True,official_DVE_report=False)
    life.save(out/"status.json",status)
    life.save(out/"admission-manifest.json",dict(schema="AKV_INDEPENDENT_SCALAR_HISTORICAL720_ADMISSION_V1",
        output=str(out),baseline=str(old.r.BASE),baseline_seal=BASE_SEAL,prepared=str(prepared),
        prepared_seal=seal_hash,qualification_seal=QUALIFICATION_SEAL,
        output_pins={str(p):life.digest(p) for p in out.iterdir()}))
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","check","admit"))
    parser.add_argument("--output",type=Path)
    parser.add_argument("--baseline-seal",default=BASE_SEAL)
    parser.add_argument("--prepared",type=Path)
    parser.add_argument("--seal")
    args = parser.parse_args()
    require(args.baseline_seal == BASE_SEAL,"New baseline needs fresh rebind")
    if args.mode == "prepare":
        require(args.output is not None and args.prepared is None and args.seal is None,"Wrong prepare arguments")
        out=args.output.absolute();status=prepare(out,args.baseline_seal)
        print(json.dumps(dict(output=str(out),seal=life.digest(out/"prepared-seal.json"),result=status)))
    else:
        require(args.prepared is not None and args.seal is not None,"Prepared path/seal required")
        if args.mode == "check":
            require(args.output is None,"Check cannot write output")
            _,_,status=check(args.prepared.absolute(),args.seal)
        else:
            require(args.output is not None,"Admission needs fresh output")
            status=admit(args.output.absolute(),args.prepared.absolute(),args.seal)
        print(json.dumps(status))


if __name__ == "__main__":
    main()
