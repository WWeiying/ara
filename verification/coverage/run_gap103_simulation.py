"""Sealed GAP103 single-case old-image lifecycle; explicit run only after review."""
import argparse
import json
from pathlib import Path

import prove_gap103_snapshot_scope as snapshot
import run_gap95_simulation as life

proof = snapshot.pre
PRE, PRE_SEAL = snapshot.PRE, snapshot.SEAL
STATIC = life.OUT/"gap103-snapshot-static-proof-719-20261006-01.json"
STATIC_SEAL = "6fd5b8316e983381831a1eb3ef4214d32cbc8762a3b3365c556c2b74cb488560"
ELF = PRE/"input.elf"
ELF_SEAL = "39b3f34cee1c7c8e92f4f002493f09cf249ea02bf0ca320752bad04ee871ab1a"
LIFE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"
IMAGE_SEAL = "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3"
NAME, SCOPE = proof.NAME, proof.old.SCOPE


def validate(pre):
    expected = dict(status="GAP103_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS",case=NAME,baseline_tests=719,
        checks=1245,input_elf=str(ELF),input_spike_trace=str(PRE/"spike.trace"),
        target_before=str(PRE/"target-before.json"),target_unhit_count=4,coverage_admitted=False,
        rtl_changed=False,vcs_started=False,measured_raw_increment=None)
    if any(k not in pre or type(pre[k]) is not type(v) or pre[k] != v for k,v in expected.items()):
        raise ValueError("Exact GAP103 preflight contract differs")
    oracle = dict(status="GAP103_SPIKE_CANONICAL_FULL_VRF_ORACLE_PASS_NOT_DUT",checks=1245,
        opcode="0xb2860457",vl=129,vstart=13,active_destination_bytes=232,
        before_vrf_bytes=4096,after_vrf_bytes=4096,source_and_guard_bytes=1600,
        csr_snapshots=2,recovery_guard_bytes=64,illegal_traps=0,vector_write_instructions=35,
        vector_declared_bytes=6016,coverage_admitted=False,measured_raw_increment=None)
    if pre.get("validation") != oracle or pre.get("pins",{}).get(str(ELF)) != ELF_SEAL:
        raise ValueError("Canonical full oracle/ELF differs")
    if pre["symbols"]["tohost"] != 0x80001000 or pre["symbols"]["g103_narrow"] != 0x800023ac:
        raise ValueError("Exact ELF terminal/narrow PC differs")
    for path in (PRE/"spike.trace",PRE/"compile-command.json",PRE/"spike-command.json",
                 PRE/"host.log",PRE/"host-reference",PRE/"target-before.json",PRE/"spike-validation.json",
                 proof.APP,Path(proof.__file__).resolve(),Path(proof.__file__).with_name("test_build_gap103_preflight_v2.py")):
        if str(path) not in pre["pins"]: raise ValueError("Unpinned preflight evidence: "+str(path))


def validate_targets(evidence):
    if (evidence.get("status") != "GAP103_RAW719_TARGETS_ZERO_STATIC_HYPOTHESIS_NOT_MEASURED" or
            evidence.get("baseline_tests") != 719 or len(evidence.get("targets",[])) != 4):
        raise ValueError("Exact719 target population differs")
    expected = [("branch",138,"25","991","3771491581",1215,"1558979345","5789",1248),
                ("branch",105,"24","12","1445690029",1215,"1558979345","1284",19),
                ("branch",100,"24","17","1445690029",1215,"1558979345","1330",27),
                ("line",202,"194","","3588353522",1718,"1316526434","1288",0)]
    for row,fields in zip(evidence["targets"],expected):
        metric,index,ident,vector,check,width,checksum,line,leafindex = fields
        point = row["point"]
        if (row["scope"] != SCOPE or row["metric"] != metric or row["width"] != width or
                row["checksum"] != checksum or row["hit_before"] is not False or
                (point["raw_index"],point["native_id"],point["vector"],point["file_id"]) !=
                (index,ident,vector,"547") or point["attributes"]["chksum"] != check):
            raise ValueError("Exact compiled target identity differs")
        if metric == "branch":
            leaf = next(e for e in point["expressions"] if e["id"] == line)
            native = point["native_vector"]["vector"]
            if int(leaf["index"]) != leafindex or native[-leafindex] != "1":
                raise ValueError("One-based true-arm leaf differs")
        elif point["attributes"]["line_num"] != line:
            raise ValueError("Line target differs")


def command(output):
    return [str(life.IMAGE),"-l","run.vcs.log","+NO_FSDB","+ntb_random_seed=1",
        "+PRELOAD="+str(ELF),"+TESTCASE="+NAME,"+COMMIT_TOHOST=80001000",
        "+COMMIT_TRACE="+str(output/"commit_trace.csv"),"+VECTOR_TRACE="+str(output/"vector_trace.csv"),
        "-cm","line+cond+fsm+tgl+branch","-cm_dir",str(output/"code.vdb"),"-cm_name",NAME]


def prepare(output):
    output=Path(output).absolute()
    if output.parent != life.OUT or output.resolve() != output or output.exists():
        raise ValueError("Fresh independent runtime output required")
    helper=Path(life.__file__).resolve()
    if life.digest(helper) != LIFE_SEAL: raise ValueError("Frozen lifecycle differs")
    pre=life.read_bound(PRE/"preflight-manifest.json",PRE_SEAL); validate(pre)
    static=life.read_bound(STATIC,STATIC_SEAL)
    if (static["status"] != "GAP103_SINGLE_REGISTER_SNAPSHOT_STATIC_NONMUTATION_NOT_DUT_PROBE" or
            static["preflight_seal"] != PRE_SEAL or static["source_contract"]["source_reshuffle_gate"] is not False or
            static["source_contract"]["destination_notebook_update"] is not False):
        raise ValueError("Snapshot nonmutation proof differs")
    evidence=life.read_bound(PRE/"target-before.json",pre["pins"][str(PRE/"target-before.json")])
    validate_targets(evidence)
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    if plan["simv"] != str(life.IMAGE) or len(plan["image"]) != 66 or plan["image"].get(str(life.IMAGE)) != IMAGE_SEAL:
        raise ValueError("Exact frozen66-file image differs")
    pins=life.merge_pins(pre["pins"],static["pins"])
    pins=life.merge_pins(pins,plan["image"])
    pins=life.merge_pins(pins,{str(PRE/"preflight-manifest.json"):PRE_SEAL,str(STATIC):STATIC_SEAL,
                             str(helper):LIFE_SEAL,str(life.PLAN):life.PLAN_SEAL})
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_run_gap103_simulation.py"),
                 Path(life.__file__).with_name("test_run_gap95_simulation.py")):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    if evidence != proof.target_evidence() or static != snapshot.evaluate():
        raise ValueError("Fresh frozen source/design719/snapshot proof differs")
    life.check(pins)
    return output,dict(case=NAME,preflight=pre,pins=pins,command=command(output),timeout_s=600,
        input_elf=str(ELF),input_spike_trace=str(PRE/"spike.trace"),target_before=str(PRE/"target-before.json"),
        snapshot_static_proof=str(STATIC),old_image_files_checked=66,baseline_tests=719,
        expected_checks=1245,expected_illegal_traps=0,expected_narrow_opcode="0xb2860457",
        expected_narrow_pc="0x800023ac",expected_architectural_narrow_count=1,
        expected_software_vl=129,expected_narrow_vstart=13,expected_active_narrow_bytes=232,
        expected_full_vrf_snapshot_bytes=8192,expected_source_and_guard_bytes=1600,
        expected_recovery_guard_bytes=64,expected_spike_vector_write_instructions=35,
        expected_spike_declared_bytes=6016,physical_vrf_traffic_count_inferred_from_spike=False,
        predicted_target_raw_branch=[138,105,100],predicted_target_raw_line=[202],target_hit_verified=False,
        dut_self_check_verified=False,coverage_admitted=False,admission_performed=False,
        rtl_changed=False,new_RTL_signoff=False,automatic_retry=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","run"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--prepared-seal")
    args=parser.parse_args(argv)
    if (args.mode == "run") != bool(args.prepared_seal): parser.error("Explicit run alone requires external seal")
    output,manifest=prepare(args.output); record=output.with_name(output.name+".prepared.json")
    if args.mode == "prepare":
        if record.exists(): raise ValueError("Fresh prepared record required")
        life.save(record,manifest)
        print(json.dumps(dict(status="GAP103_RUN_PREPARED_NO_VCS",prepared=str(record),
                              seal=life.digest(record),pins_checked=len(manifest["pins"]))))
    else:
        if life.read_bound(record,args.prepared_seal) != manifest: raise ValueError("Reviewed prepared contract differs")
        life.run(output,manifest)


if __name__ == "__main__": main()
