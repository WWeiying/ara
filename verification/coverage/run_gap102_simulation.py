"""Prepare/run one explicitly sealed GAP102 old-image job, never admit or retry."""
import argparse
import json
from pathlib import Path

import build_gap102_preflight_v2 as proof
import run_gap95_simulation as life
from closure_point_inventory import points

PRE = life.OUT / "gap102-widen-acc-cross-preflight-717-20261006-02"
PRE_SEAL = "703f8609edcccbb5a487bb047fcc8f333a05a13d649de0a1df1b4848cd31cb0b"
ELF_SEAL = "ee65c0c43fd7a3e36168673a3403b7b2316e26c153098a7c237ec7f597eba3c1"
LIFE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"
CALIBRATION = life.OUT / "gap102-branch-path-measured-calibration-20261006-01.json"
CALIBRATION_SEAL = "9fbc480284de4e48d095db95c0465e24ae10834a02c59a7970f44f8bc1b78023"
NAME = "vgap102_widen_acc_cross_v2"
SCOPE = proof.old.SCOPE


def validate(pre):
    expected = dict(status="GAP102_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME, baseline_tests=717,
        checks=723, target_unhit_count=1, input_elf=str(PRE / "input.elf"),
        input_spike_trace=str(PRE / "spike.trace"), target_before=str(PRE / "target-before.json"),
        measured_raw_increment=None, coverage_admitted=False, rtl_changed=False, vcs_started=False)
    if any(k not in pre or type(pre[k]) is not type(v) or pre[k] != v for k,v in expected.items()):
        raise ValueError("GAP102 exact preflight contract differs")
    oracle = dict(status="GAP102_SPIKE_INDEPENDENT_FULL_VRF_ORACLE_PASS_NOT_DUT", checks=723,
        mac_opcode="0xf2c56457", vl=129, source_start_wide_element=128, active_result_bytes=516,
        full_vrf_bytes=4096, source_guard_bytes=1536, csr_snapshots=2, recovery_guard_bytes=64,
        illegal_traps=0, coverage_admitted=False, measured_raw_increment=None)
    if pre.get("validation") != oracle:
        raise ValueError("Exact GAP102 oracle differs")
    if pre.get("pins",{}).get(str(PRE / "input.elf")) != ELF_SEAL or pre["symbols"]["tohost"] != 0x80001000:
        raise ValueError("Fixed ELF/terminal identity differs")
    for name in ("spike.trace", "spike-validation.json", "spike-command.json", "compile-command.json",
                 "target-before.json", "host.log", "host-reference"):
        if str(PRE / name) not in pre["pins"]:
            raise ValueError("Unpinned preflight evidence: " + name)


def validate_targets(evidence):
    rows = evidence.get("targets",[])
    if (evidence.get("status") != "GAP102_RAW717_TARGET_ZERO_NOT_COVERAGE_PROMISE" or
            evidence.get("baseline_tests") != 717 or len(rows) != 1):
        raise ValueError("Exact717 target population differs")
    row, point = rows[0], rows[0]["point"]
    if (row["scope"] != SCOPE or row["metric"] != "branch" or row["checksum"] != "1558979345" or
            row["hit_before"] is not False or (point["raw_index"],point["native_id"],point["vector"]) != (127,"25","1002") or
            point["attributes"]["chksum"] != "3771491581"):
        raise ValueError("Exact target compiled identity differs")
    expressions = {e["id"]:e for e in point["expressions"]}
    gate, boundary = expressions["5829"], expressions["5843"]
    if (gate["index"] != "1254" or gate["exprstr"] != "(legal_widen_overlap && ara_req.use_vd_op)" or
            boundary["index"] != "1259" or boundary["parent_bit"] != "1254" or
            boundary["exprstr"] != "((unsigned'(ara_req.vl)) <= overlap_start_element)"):
        raise ValueError("Compiled leaf/parent identity differs")
    vector = point["native_vector"]["vector"]
    if len(vector) != 1270 or [vector[-i] for i in (1254,1259,1260)] != ["1","0","1"]:
        raise ValueError("One-based LSB path / false boundary differs")


def command(output):
    return [str(life.IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
            "+PRELOAD="+str(PRE / "input.elf"), "+TESTCASE="+NAME, "+COMMIT_TOHOST=80001000",
            "+COMMIT_TRACE="+str(output / "commit_trace.csv"), "+VECTOR_TRACE="+str(output / "vector_trace.csv"),
            "-cm", "line+cond+fsm+tgl+branch", "-cm_dir", str(output / "code.vdb"), "-cm_name", NAME]


def prepare(output):
    output = Path(output).absolute()
    if output.parent != life.OUT or output.resolve() != output or output.exists():
        raise ValueError("Fresh independent direct output required")
    helper = Path(life.__file__).resolve()
    if life.digest(helper) != LIFE_SEAL:
        raise ValueError("Frozen lifecycle differs")
    prefile = PRE / "preflight-manifest.json"
    pre = life.read_bound(prefile,PRE_SEAL)
    validate(pre)
    evidence = life.read_bound(PRE / "target-before.json",pre["pins"][str(PRE / "target-before.json")])
    validate_targets(evidence)
    if evidence != proof.target_evidence():
        raise ValueError("Fresh717 source/compiled target rebind differs")
    calibration = life.read_bound(CALIBRATION,CALIBRATION_SEAL)
    if (calibration["status"] != "GAP102_EXPRESSION_INDEX_MEASURED_CALIBRATION_NOT_NATIVE_EL_APPROVAL" or
            calibration["calibration"]["registers"] != 16 or calibration["calibration"]["left_character_index"] != 285 or
            calibration["calibration"]["actual_character"] != "1" or calibration["target"]["raw"] != 127):
        raise ValueError("Measured calibration contract differs")
    design = proof.s.Design(proof.old.BUILD / "sim/simv.vdb")
    line = next(p for p in points("line",design.definition(SCOPE,"line"),
                                 json.loads((proof.BASE / "combined-bits.json").read_bytes())["metrics"]["line"][SCOPE]["width"])
                if p["raw_index"] == 1334)
    if (line["line"],line["file_id"],line["native_id"]) != ("4542","547","1326"):
        raise ValueError("Measured calibration body source/line differs")
    plan = life.read_bound(life.PLAN,life.PLAN_SEAL)
    if (plan["simv"] != str(life.IMAGE) or len(plan["image"]) != 66 or
            plan["image"].get(str(life.IMAGE)) != "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3"):
        raise ValueError("Exact frozen66-file old image differs")
    pins = life.merge_pins(pre["pins"],plan["image"])
    pins = life.merge_pins(pins,calibration["pins"])
    pins = life.merge_pins(pins,{str(prefile):PRE_SEAL,str(helper):LIFE_SEAL,str(life.PLAN):life.PLAN_SEAL,
                                str(CALIBRATION):CALIBRATION_SEAL})
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_run_gap102_simulation.py")):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    commits = proof.s.parse_spike_commits(PRE / "spike.trace")
    if proof.validate(commits,pre["symbols"],(PRE / "spike.trace").read_text()) != pre["validation"]:
        raise ValueError("Independent raw Spike revalidation differs")
    vector = [c for c in commits if c.vector_writes]
    if len(vector) != 35 or sum(len(c.vector_writes) for c in vector) != 48:
        raise ValueError("Exact architectural vector population differs")
    life.check(pins)
    return output, dict(case=NAME,preflight=pre,pins=pins,command=command(output),timeout_s=600,
        input_elf=str(PRE / "input.elf"),input_spike_trace=str(PRE / "spike.trace"),
        target_before=str(PRE / "target-before.json"),old_image_files_checked=66,baseline_tests=717,
        expected_checks=723,expected_illegal_traps=0,expected_architectural_mac_count=1,
        expected_mac_opcode="0xf2c56457",expected_software_vl=129,expected_vector_instructions=35,
        expected_vector_register_writes=48,expected_vector_bytes=6144,expected_full_vrf_snapshot_bytes=4096,
        expected_source_guard_bytes=1536,expected_recovery_guard_bytes=64,
        calibration=str(CALIBRATION),calibration_sha256=CALIBRATION_SEAL,
        calibration_body_line_point=line,dut_self_check_verified=False,coverage_admitted=False,
        admission_performed=False,rtl_changed=False,new_RTL_signoff=False,automatic_retry=False)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=("prepare","run"))
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--prepared-seal")
    args = p.parse_args(argv)
    if (args.mode == "run") != bool(args.prepared_seal):
        p.error("Only explicit run requires --prepared-seal")
    output,manifest = prepare(args.output)
    record = output.with_name(output.name+".prepared.json")
    if args.mode == "prepare":
        life.save(record,manifest)
        print(json.dumps(dict(status="GAP102_RUN_PREPARED_NO_VCS",prepared=str(record),
                              seal=life.digest(record),pins_checked=len(manifest["pins"]))))
    else:
        if life.read_bound(record,args.prepared_seal) != manifest:
            raise ValueError("Reviewed prepared contract differs")
        life.run(output,manifest)


if __name__ == "__main__":
    main()
