"""Cross-check one-based expression-vector indexing with measured GAP101A, offline."""
import argparse
import csv
import io
import json
from pathlib import Path

import collect_gap101a_strict_v2 as c
from closure_point_inventory import points

ROOT, OUT, require = c.ROOT, c.OUT, c.require
BASE716 = OUT / "gap101a-offline-admitted-716-20261006-01"
BASE716_SEAL = "df9e35f425734bce6d22416acf3f91fbea85f007ceb1e45f2e1eee703da4fd8a"
PRE102 = OUT / "gap102-widen-acc-cross-preflight-717-20261006-02"
PRE102_SEAL = "703f8609edcccbb5a487bb047fcc8f333a05a13d649de0a1df1b4848cd31cb0b"
SCOPE = c.software.original.SCOPE


def expression_bit(vector, index):
    require(type(index) is int and 0 < index <= len(vector), "Not a one-based expression index")
    return vector[len(vector)-index]


def leaf_checks(calibration, target):
    require((calibration["raw_index"], calibration["native_id"], calibration["vector"]) == (345,"25","784"),
            "Wrong measured calibration coordinate")
    require((target["raw_index"], target["native_id"], target["vector"]) == (127,"25","1002"),
            "Wrong MAC target coordinate")
    expressions = {e["id"]: e for e in calibration["expressions"]}
    require(expressions["4541"]["index"] == "985" and
            expressions["4541"]["exprstr"] == "(segment_register_count(ara_req.nf, ara_req.emul) > 8)",
            "Calibration source leaf differs")
    vector = calibration["native_vector"]["vector"]
    require(len(vector) == 1270 and expression_bit(vector,985) == "1" and
            vector[985] == vector[-1-985] == "0", "Index convention/calibration differs")
    expressions = {e["id"]: e for e in target["expressions"]}
    require(expressions["5829"]["index"] == "1254" and
            expressions["5843"]["index"] == "1259" and expressions["5843"]["parent_bit"] == "1254" and
            expressions["5843"]["exprstr"] == "((unsigned'(ara_req.vl)) <= overlap_start_element)",
            "Target compiled leaf/parent differs")
    vector = target["native_vector"]["vector"]
    require([expression_bit(vector,i) for i in (1254,1259,1260)] == ["1","0","1"],
            "Not accumulator path / false boundary arm")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    out = p.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    pins = {}
    def read(path, expected):
        path = Path(path).absolute()
        raw = path.read_bytes()
        require(c.runner.life.digest(path) == expected, "Expected calibration input changed: " + str(path))
        pins.update(c.runner.life.merge_pins(pins, {str(path): expected}))
        return raw
    manifest = json.loads(read(BASE716 / "admission-manifest.json", BASE716_SEAL))
    book = json.loads(read(BASE716 / "evidence-pins.json", manifest["output_pins"][str(BASE716 / "evidence-pins.json")]))
    def approved(path):
        return read(path, book[str(Path(path).absolute())])
    before = json.loads(approved(c.BASE / "combined-bits.json"))
    source_path = OUT / "old-image-source-evidence-20261006-01/ara_dispatcher.sv"
    source = approved(source_path).decode()
    require(pins[str(source_path)] == "9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43" and
            "segment_register_count = (unsigned'(nf) + 1) * lmul_register_count(emul);" in source and
            "LMUL_2: lmul_register_count = 2;" in source and
            source.splitlines()[4540].strip() == "if (segment_register_count(ara_req.nf, ara_req.emul) > 8)",
            "Independent old-source predicate differs")
    for relative in ("design/verilog.design.xml", "shape/branch.verilog.shape.xml", "shape/line.verilog.shape.xml",
                     "shape/tgl.verilog.shape.xml", "auxiliary/verilog.sourceinfo.xml",
                     "shape/branch.verilog.info.xml", "shape/line.verilog.info.xml", "shape/tgl.verilog.info.xml"):
        approved(c.DESIGN / "snps/coverage/db" / relative)
    design = c.software.original.shared.Design(c.DESIGN)
    require(design.source(SCOPE)["resolved_path"] == str(ROOT / "hardware/src/ara_dispatcher.sv"), "Wrong owner")
    record = before["metrics"]["branch"][SCOPE]
    definition = design.definition(SCOPE,"branch")
    require(record["checksum"] == definition.get("chksum") == "1558979345", "Compiled branch binding differs")
    mapped = points("branch",definition,record["width"])
    calibration, target = [next(p for p in mapped if p["raw_index"] == i) for i in (345,127)]
    leaf_checks(calibration,target)
    candidate = OUT / "gap101a-strict-candidate-715-20261006-02"
    approved(candidate / "diagnostic-inputs.txt")
    expected_single = json.loads(approved(candidate / "single-raw-bits.json"))
    for path, expected in expected_single["input_hashes"].items():
        read(path, expected)
    single = c.bitmap.collect(candidate / "diagnostic-inputs.txt")
    require(single == expected_single, "Measured raw VDB differs")
    for metric,index in (("branch",345),("line",1334)):
        old, new = before["metrics"][metric][SCOPE], single["metrics"][metric][SCOPE]
        require((old["width"],old["checksum"]) == (new["width"],new["checksum"]), "Metric shape differs")
        mask = 1 << (old["width"]-1-index)
        require(not int(old["bits"],16)&mask and int(new["bits"],16)&mask, "Calibration lacks actual new hit")
    data = json.loads(approved(candidate / "observed-data.json"))
    control = json.loads(approved(candidate / "lifecycle.json"))
    rows = list(csv.DictReader(io.StringIO(approved(c.RUN / "commit_trace.csv").decode())))
    vectors = list(csv.DictReader(io.StringIO(approved(c.RUN / "vector_trace.csv").decode())))
    require(c.lifecycle(rows,vectors) == control, "Actual rejected request lifecycle differs")
    ledger = data["trap_ledger"]
    word, vtype = ledger[2], ledger[4]
    nf = ((word >> 29)&7)+1
    require(word == 0xe2050827 and vtype == 1 and (word >> 12)&7 == 0 and
            ledger[0] == 2 and control["exception_arch_seq"] == 37, "Actual trap/opcode/vtype differs")
    count = nf * (1 << (vtype & 7))
    require(count == 16 and count > 8, "Independent NF*EMUL predicate is not true")
    pre = json.loads(read(PRE102 / "preflight-manifest.json", PRE102_SEAL))
    plan = json.loads(read(PRE102 / "target-before.json", pre["pins"][str(PRE102 / "target-before.json")]))
    require(plan["targets"][0]["point"] == target and plan["baseline_tests"] == 717, "GAP102 prepared leaf differs")
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_calibrate_gap102_branch_path.py"),
                 Path(c.__file__).resolve(), ROOT / "verification/coverage/closure_point_inventory.py"):
        read(path,c.runner.life.digest(path))
    c.runner.life.check(pins)
    c.runner.life.save(out, dict(status="GAP102_EXPRESSION_INDEX_MEASURED_CALIBRATION_NOT_NATIVE_EL_APPROVAL",
        pins=pins, vector_length=1270, convention="expression indices are one-based from right; left offset=N-index, NOT N-1-index",
        calibration=dict(raw=345, spec="25", vector="784", source_line=4541, expression_index=985,
                         left_character_index=285, actual_character="1", wrong_left_985="0", wrong_right_986="0",
                         actual_opcode=hex(word), actual_vtype=vtype, nfields=nf, emul=2, registers=count,
                         observed_branch_new_hit=True, observed_body_line1334_new_hit=True,
                         actual_illegal_exception_arch_seq=37),
        target=dict(raw=127,spec="25",vector="1002",source_line=5843,
                    gate_index=1254, gate_left_offset=16, gate_value="1", expression_index=1259,
                    left_character_index=11, actual_character="0", false_arm_index=1260,
                    false_arm_left_offset=10,false_arm_value="1",raw717_hit=False),
        measured_GAP102_gain=None, exclusions_generated=False, vcs_started=False))
    print(json.dumps(dict(output=str(out),seal=c.runner.life.digest(out),pins=len(pins))))


if __name__ == "__main__":
    main()
