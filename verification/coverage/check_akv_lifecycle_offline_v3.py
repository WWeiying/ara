"""Repin all reviewed tests and independently requalify native lifecycle evidence.

No simulator, bitmap union, population approval or formal admission is performed.
"""
import argparse
import json
from pathlib import Path
import sys

import check_akv_lifecycle_offline_v2 as previous
from inventory_operand_debug import Design

life, require = previous.life, previous.require
OLD = life.OUT/"akv-lifecycle-parent-native-scalar-qualification-20261006-02"
OLD_SEAL = "bdcd9bcff3844ea3d5ab3e727de886b5d74c45e2630db99f13bf45bd6aba9ec4"
ENGINE_SHA = "fb7f3f647b734ce639ddf81366b9d5121b25225aad9bcb43e6d97ec5d5ac9bf4"
V2_TEST_SHA = "6a214edf0759ea49fb36f88946af181254a2bbc0f6ecc298c7ae579095714de0"
V2_SHA = "3a9bcbae3062e18d23601e3133eac078d38c9e3d3d4bb001bf78a6c75cffc30e"


def bind_compiled(hierarchy, source, definition, points, target, sources):
    engine = str(life.ROOT/"hardware/src/vlsu/akv/akv_engine.sv")
    require(hierarchy.get("chksum") == target["module_checksum"] == "3509320291",
            "Compiled module checksum mismatch")
    require(source == target["source"] and source["module"] == "akv_engine" and
            source["definition_checksum"] == "3509320291" and source["file_id"] == "580" and
            source["resolved_path"] == source["source_path"] == engine and
            source["definition_lines"] == ["9","1195"] and sources.get(engine) == ENGINE_SHA,
            "Compiled source identity mismatch")
    require(definition.get("chksum") == "2836473276" and len(points) == 392 and
            {p["raw_index"] for p in points} == set(range(392)), "Incomplete/wrong compiled condition shape")
    by_raw = {p["raw_index"]:p for p in points}
    previous.runner.validate_target(target)
    for record in target["targets"]:
        require(record["point"] == by_raw[record["raw_index"]] and record["point"]["file_id"] == "580",
                "Compiled coordinate expression/vector/source mismatch")
    return dict(status="EXACT_COMPILED_AKV_SOURCE_AND_FOUR_COORDINATES_REBOUND_NOT_GAIN_PROOF",
        scope=previous.fixture.SCOPE,source=source,source_sha256=ENGINE_SHA,
        module_checksum="3509320291",condition_checksum="2836473276",condition_width=392,
        coordinates=target["targets"],target_inventory_baseline_tests=721,
        latest_population_bound=False,native_GUI_ID_qualification=False,coverage_admitted=False)


def required_tests():
    here=Path(__file__).resolve().parent
    return [here/name for name in ("test_check_akv_lifecycle_offline.py",
        "test_check_akv_lifecycle_offline_v2.py","test_check_akv_lifecycle_offline_v3.py",
        "test_akv_lifecycle_scalar_oracle.py")]


def canonical(value):
    return json.loads(json.dumps(value))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    out=parser.parse_args().output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    old=life.read_bound(OLD/"qualification-seal.json",OLD_SEAL)
    require(old["status"] == "NATIVE_AND_SCALAR_QUALIFIED_NOT_ADMITTED" and
            old["run"] == str(previous.RUN) and old["run_seal"] == previous.RUN_SEAL and
            not (OLD/"failure.json").exists(),"Wrong predecessor qualification")
    pins=life.merge_pins(old["input_pins"],old["output_pins"])
    pins=life.merge_pins(pins,{str(OLD/"qualification-seal.json"):OLD_SEAL})
    manifest=life.read_bound(previous.RUN/"manifest.json",previous.RUN_SEAL)
    require(life.read_bound(previous.RUN.with_name(previous.RUN.name+".prepared.json"),previous.RUN_SEAL) == manifest,
            "Executed/prepared mismatch")
    require(manifest["command"] == previous.runner.command(manifest["preflight"],previous.RUN) and
            type(manifest["timeout_s"]) is int and manifest["timeout_s"] == 600,"Wrong actual parent600 command")
    previous.runner.validate(manifest["preflight"],previous.runner.PRE)
    previous.terminal_status(json.loads((previous.RUN/"simulation-status.json").read_text()))
    pins=life.merge_pins(pins,manifest["pins"])
    files=required_tests()+[Path(__file__).resolve(),Path(previous.__file__).resolve()]
    design_path=previous.native.common.DESIGN
    design=Design(design_path)
    design_members=sorted(p for p in design_path.rglob("*") if p.is_file())
    require(design_path.resolve() == design_path and design_members and
            not any(p.is_symlink() for p in design_path.rglob("*")),"Missing/aliased frozen design")
    files+=design_members
    for module in list(sys.modules.values()):
        name=getattr(module,"__file__",None)
        if name and Path(name).resolve().parent in (Path(__file__).resolve().parent,
                                                   Path(__file__).resolve().parent/"reviewed_20261004"):
            files.append(Path(name).resolve())
    files+=list((life.ROOT/"verification/ara_verify").rglob("*.py"))
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files})
    require(pins[str(Path(previous.__file__).resolve())] == V2_SHA and
            pins[str(Path(previous.__file__).with_name("test_check_akv_lifecycle_offline_v2.py"))] == V2_TEST_SHA,
            "Frozen v2 source/test drift")
    vdb=previous.RUN/"code.vdb"
    members=sorted(str(p) for p in vdb.rglob("*") if p.is_file())
    require(vdb.resolve() == vdb and members and not any(p.is_symlink() for p in vdb.rglob("*")) and
            members == sorted(p for p in old["input_pins"] if Path(p).is_relative_to(vdb)),
            "Predecessor VDB membership drift")
    sources=life.read_bound(previous.fixture.BUILD/"build-source-pins.json",
                           pins[str(previous.fixture.BUILD/"build-source-pins.json")])
    target_path=previous.runner.PRE/"target-before.json"
    target=life.read_bound(target_path,pins[str(target_path)])
    scope=previous.fixture.SCOPE
    cond=previous.fixture.shape.read_xml(design.db/"shape/cond.verilog.shape.xml")
    definition=previous.fixture.shape.definition(cond,design.hierarchy[scope],"2836473276")
    points=previous.fixture.shape.points("cond",definition,392)
    compiled=bind_compiled(design.hierarchy[scope],design.source(scope),definition,points,target,sources)
    pins,source_proof=previous.base.source_contract(sources,pins)
    life.check(pins)
    out.mkdir()
    try:
        require((previous.RUN/"console.log").read_text().count("Core Test *** SUCCESS ***") == 1,
                "Missing console terminal")
        rows=previous.native.commit_rows(previous.RUN/"commit_trace.csv")
        pre=manifest["preflight"]
        model,scalar=previous.oracle.replay(Path(pre["input_elf"]).read_bytes(),pre["symbols"],rows)
        arch=previous.commit_audit(rows,model)
        vector=previous.vector_audit(previous.native.common.read_csv(previous.RUN/"vector_trace.csv",
                                     previous.native.common.VECTOR_FIELDS),model,arch)
        log=(previous.RUN/"run.vcs.log").read_text()
        contract=previous.stdout_audit(log);perf=previous.perf_audit(log,arch,model)
        artifacts=(("scalar-qualification.json",scalar),("architecture.json",arch),("native-vector.json",vector),
                   ("contract.json",contract),("perf-ledger.json",perf),("source-contract.json",source_proof))
        for name,value in artifacts:
            require(canonical(value) == life.read_bound(OLD/name,old["output_pins"][str(OLD/name)]),
                    "Independent rerun differs from predecessor: "+name)
            life.save(out/name,value)
        life.save(out/"compiled-source-binding.json",compiled)
        require(members == sorted(str(p) for p in vdb.rglob("*") if p.is_file()) and
                design_members == sorted(p for p in design_path.rglob("*") if p.is_file()),"VDB/design membership drift")
        life.check(pins)
        life.save(out/"qualification-seal.json",dict(status="NATIVE_SCALAR_COMPILED_REQUALIFIED_NOT_ADMITTED",
            input_pins=pins,output_pins={str(p):life.digest(p) for p in out.iterdir()},run=str(previous.RUN),
            run_seal=previous.RUN_SEAL,predecessor_seal=OLD_SEAL,tests_pinned=[str(p) for p in required_tests()],
            coverage_admitted=False,minimum_future_formal_baseline=722,requires_fresh_positive_delta=True,
            latest_population_bound=False,native_Spike_comparison=False))
        print(json.dumps(dict(output=str(out),seal=life.digest(out/"qualification-seal.json"))))
    except Exception as error:
        life.save(out/"failure.json",dict(status="REQUALIFICATION_REJECTED_NOT_ADMITTED",reason=str(error)))
        raise


if __name__ == "__main__":main()
