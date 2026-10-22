"""Compiled-point/native-scope admission preparation; remaining scalar is a hard gate."""
import argparse
from collections import Counter
import json
from pathlib import Path

import rebind_akv_column_boundary_719 as r
import closure_point_inventory as shape
from inventory_operand_debug import Design

life, require = r.life, r.require
PROPOSAL = life.OUT / "akv-column-boundary-v5-relative719-20261006-01"
PROPOSAL_SEAL = "a05e4d38509af1d506e6627606f775a37f49e0928bafc95c6a55b1a192a0aa12"


def raw_hit(record, raw):
    require(type(raw) is int and 0 <= raw < record["width"], "Out-of-range raw coordinate")
    return bool(int(record["bits"], 16) & (1 << (record["width"]-1-raw)))


def gain_indices(old, new):
    require((old["width"], old["checksum"]) == (new["width"], new["checksum"]), "Compiled shape drift")
    require(0 <= int(old["bits"],16) < (1 << old["width"]) and
            0 <= int(new["bits"],16) < (1 << new["width"]), "Bitmap width overflow")
    return [raw for raw in range(old["width"]) if not raw_hit(old,raw) and raw_hit(new,raw)]


def admission_gate():
    # No available native Spike custom model or independently complete scalar checker.
    # ELF instruction identity and the final signature are not an ISA result oracle.
    raise ValueError("ADMISSION_BLOCKED: remaining scalar GPR/control-flow/load/store semantics not independently qualified")


def prepare(out):
    proposal_seal_path = PROPOSAL / "proposal-seal.json"
    seal = life.read_bound(proposal_seal_path, PROPOSAL_SEAL)
    pins = life.merge_pins(seal["input_pins"],seal["output_pins"])
    pins = life.merge_pins(pins,{str(proposal_seal_path):PROPOSAL_SEAL})
    require(seal["coverage_admitted"] is False and
            all(Path(p).parent == PROPOSAL for p in seal["output_pins"]), "Foreign/admitted proposal")
    def read(path):
        require(str(path) in pins,"Unpinned evidence: "+str(path))
        return life.read_bound(path,pins[str(path)])
    state = read(PROPOSAL / "status.json")
    require(state["status"] == "AKV_NATIVE_ORACLE_VERIFIED_719_REBOUND_NOT_ADMITTED" and
            state["aggregate_admission_performed"] is False and
            state["full_scalar_differential_qualified"] is False, "Wrong proposal boundary")
    before = read(r.BASE / "combined-bits.json")
    single = read(r.CANDIDATE / "sample-bits.json")
    union, delta = r.population(before,single)
    require(union == read(PROPOSAL / "proposed-combined-bits.json") and
            delta == read(PROPOSAL / "raw-delta.json"), "Independent OR/delta mismatch")
    collector_manifest = read(r.CANDIDATE / "candidate-seal.json")
    require(collector_manifest["full_scalar_differential_qualified"] is False,
            "Native observed oracle cannot be relabelled full scalar")
    arch = read(r.CANDIDATE / "architecture-audit.json")
    vector = read(r.CANDIDATE / "native-vector-audit.json")
    require(arch["requests"] == arch["responses"] == 196 and arch["exceptions"] == 1 and
            arch["boundary_CSR_audit"]["actual_readbacks"] == 24 and
            vector["custom_destination_bytes"] == 388 and vector["rejected_write_bytes"] == 0 and
            vector["zero_enable_handshakes"] == 6 and vector["snapshot_stores"] == 128,
            "Missing exact native oracle")
    db = r.c.common.DESIGN / "snps/coverage/db"
    compiled_paths = [db / "auxiliary/verilog.sourceinfo.xml"]
    compiled_paths += [db / ("shape/"+metric+".verilog."+suffix+".xml")
                      for metric in ("line","cond","branch") for suffix in ("shape","info")]
    for path in compiled_paths:
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_prepare_akv_column_boundary_admission_719.py"),
                 Path(shape.__file__).resolve(),Path(r.__file__).resolve()):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    design = Design(r.c.common.DESIGN)
    cond = shape.read_xml(db / "shape/cond.verilog.shape.xml")
    sources = read(r.c.software.BUILD / "build-source-pins.json")
    records = []
    for metric in ("line","cond","branch"):
        for scope, old in before["metrics"][metric].items():
            new = union["metrics"][metric][scope]
            indices = gain_indices(old,new)
            if not indices: continue
            node = (shape.definition(cond,design.hierarchy[scope],old["checksum"])
                    if metric == "cond" else design.definition(scope,metric))
            mapped = {p["raw_index"]:p for p in shape.points(metric,node,old["width"])}
            source = design.source(scope)
            path = Path(source["resolved_path"])
            require(str(path) in sources,"No frozen source pin for new gain")
            pins = life.merge_pins(pins,{str(path):sources[str(path)]})
            for raw in indices:
                require(raw in mapped,"Unresolved gained compiled point")
                records.append(dict(scope=scope,metric=metric,point=mapped[raw],
                    bitmap_LSB_index=old["width"]-1-raw,source=source,
                    baseline_hit=False,sample_hit=raw_hit(single["metrics"][metric][scope],raw),
                    union_hit=True,native_GUI_ID_qualification=False))
    counts = Counter(rec["metric"] for rec in records)
    require(all(counts[m] == delta["metrics"][m] for m in delta["metrics"]), "Mapped gain count mismatch")
    branch = before["metrics"]["branch"][r.c.software.SCOPE]
    target = shape.points("branch",design.definition(r.c.software.SCOPE,"branch"),branch["width"])[24]
    require(target["native_id"] == "5" and target["vector"] == "4" and
            target["native_vector"]["vector"] == "000110101010" and branch["width"] == 166,
            "Original raw24 XML identity drift")
    target_audit = dict(raw_index=24,bitmap_LSB_index=141,compiled_XML_point=target,
        baseline_hit=raw_hit(branch,24),sample_hit=raw_hit(single["metrics"]["branch"][r.c.software.SCOPE],24),
        native_GUI_ID_qualification=False,semantic_trigger_mapping_not_proven=True,
        original_target_not_replaced=True)
    life.check(pins)
    result = dict(status="AKV719_ADMISSION_PREPARED_BLOCKED_REMAINING_SCALAR",
        baseline_tests=719,proposed_tests=720,raw_delta=delta["metrics"],
        native_observed_oracle_scope="8 commands; whole VRF 4 frames; accepted388 bytes; related observed memory; 24 CSR readbacks; precise exception/recovery/release",
        scalar_trace_identity_rows=arch["retirement_rows"],
        scalar_GPR_and_control_flow_results_independently_qualified=False,
        full_scalar_differential_qualified=False,coverage_admitted=False,
        remaining_gate="Independent complete remaining scalar result/control-flow/memory oracle; signature and PC/opcode matching alone insufficient",
        raw24_target_objective_met=False,simulations_started=False,rtl_changed=False)
    out.mkdir()
    for name,value in (("actual-gained-compiled-points.json",records),("raw24-mapping-audit.json",target_audit),
                       ("status.json",result)):
        life.save(out / name,value)
    life.save(out / "prepared-seal.json",dict(input_pins=pins,
        output_pins={str(p):life.digest(p) for p in out.iterdir()},coverage_admitted=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","admit"))
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    if args.mode == "admit": admission_gate()
    out = args.output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(),"Fresh direct output required")
    result = prepare(out)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/"prepared-seal.json"),result=result)))


if __name__ == "__main__":
    main()
