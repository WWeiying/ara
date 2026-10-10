"""Explicit sealed GAP102B old-image lifecycle; no automatic launch or admission."""
import argparse
import json
from pathlib import Path

import qualify_gap102b_preflight_v3 as proof
import run_gap95_simulation as life

PRE = life.OUT / "gap102b-widen-acc-vstart-preflight-717-20261006-03"
PRE_SEAL = "9658afe68b674bb25fb849b4fcab9b46c1778ee4c4051562d0a162e73df72552"
ELF = proof.PRE / "input.elf"
ELF_SEAL = "5f27f7052c5805c46f80c859713350d15d5037754a2784a75039e245f7a593bd"
LIFE_SEAL = "1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"
IMAGE_SEAL = "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3"
NAME, SCOPE = proof.NAME, proof.frozen.old.SCOPE


def validate(pre):
    fixed = dict(status="GAP102B_HOST_SPIKE_PREFLIGHT_PASS_NOT_VCS",
        schema="GAP102B_PREFLIGHT_STRICT_SUCCESSOR_V3",case=NAME,baseline_tests=717,checks=723,
        input_elf=str(ELF),input_spike_trace=str(proof.PRE/"spike.trace"),
        target_before=str(PRE/"target-before.json"),target_unhit_count=1,
        original_failed_outputs_preserved=True,reused_own_gap102b_raw_spike_without_rerun=True,
        coverage_admitted=False,rtl_changed=False,vcs_started=False,measured_raw_increment=None,
        budget_seconds=600,spike_declared_v10_preserved_bytes_verified_not_skipped=True)
    if any(k not in pre or type(pre[k]) is not type(v) or pre[k]!=v for k,v in fixed.items()):
        raise ValueError("Exact GAP102B03 preflight contract differs")
    oracle = dict(status="GAP102B_SPIKE_INDEPENDENT_FULL_VRF_ORACLE_PASS_NOT_DUT",checks=723,
        mac_opcode="0xf2c56457",vl=129,source_start_wide_element=128,vstart=128,active_result_bytes=4,
        declared_preserved_registers=[10],preserved_declaration_bytes_checked=128,
        vector_write_instructions=35,vector_register_declarations=43,vector_declared_bytes=5504,
        full_vrf_bytes=4096,source_guard_bytes=1536,csr_snapshots=2,recovery_guard_bytes=64,
        illegal_traps=0,coverage_admitted=False,measured_raw_increment=None)
    if pre.get("validation")!=oracle:
        raise ValueError("Exact nonzero-vstart full oracle differs")
    if pre.get("pins",{}).get(str(ELF))!=ELF_SEAL or pre["symbols"]["tohost"]!=0x80001000:
        raise ValueError("Fixed GAP102B ELF/terminal identity differs")
    for path in (proof.PRE/"spike.trace",proof.PRE/"spike-command.json",proof.PRE/"compile-command.json",
                 proof.PRE/"host.log",proof.PRE/"host-reference",PRE/"target-before.json",PRE/"spike-validation.json",
                 Path(proof.__file__).resolve(),Path(proof.frozen.__file__).resolve()):
        if str(path) not in pre["pins"]:
            raise ValueError("Unpinned preflight input: "+str(path))


def validate_targets(evidence):
    rows=evidence.get("targets",[])
    if evidence.get("status")!="GAP102B_RAW717_TARGET_ZERO_NOT_COVERAGE_PROMISE" or evidence.get("baseline_tests")!=717 or len(rows)!=1:
        raise ValueError("Exact717 target population differs")
    row,point=rows[0],rows[0]["point"]
    if (row["scope"]!=SCOPE or row["metric"]!="branch" or row["width"]!=1215 or
        row["checksum"]!="1558979345" or row["hit_before"] is not False or
        (point["raw_index"],point["native_id"],point["vector"],point["file_id"])!=(127,"25","1002","547") or
        point["attributes"]["chksum"]!="3771491581"):
        raise ValueError("Exact target compiled identity differs")
    expressions={e["id"]:e for e in point["expressions"]}
    gate,boundary=expressions["5829"],expressions["5843"]
    if (gate["index"]!="1254" or gate["exprstr"]!="(legal_widen_overlap && ara_req.use_vd_op)" or
        boundary["index"]!="1259" or boundary["parent_bit"]!="1254" or
        boundary["exprstr"]!="((unsigned'(ara_req.vl)) <= overlap_start_element)"):
        raise ValueError("Compiled leaf/parent differs")
    vector=point["native_vector"]["vector"]
    if len(vector)!=1270 or [vector[-i] for i in (1254,1259,1260)]!=["1","0","1"]:
        raise ValueError("One-based false-arm path differs")
    if (evidence.get("gate_audit",{}).get("vd_active")!=[12] or evidence["gate_audit"].get("vs2_active")!=[14] or
        evidence["gate_audit"].get("source_snapshot_expected") is not False or
        evidence["gate_audit"].get("predicate_values_are_static_predictions_not_measured") is not True):
        raise ValueError("Static active-register prediction differs")


def command(output):
    return [str(life.IMAGE),"-l","run.vcs.log","+NO_FSDB","+ntb_random_seed=1",
        "+PRELOAD="+str(ELF),"+TESTCASE="+NAME,"+COMMIT_TOHOST=80001000",
        "+COMMIT_TRACE="+str(output/"commit_trace.csv"),"+VECTOR_TRACE="+str(output/"vector_trace.csv"),
        "-cm","line+cond+fsm+tgl+branch","-cm_dir",str(output/"code.vdb"),"-cm_name",NAME]


def prepare(output):
    output=Path(output).absolute()
    if output.parent!=life.OUT or output.resolve()!=output or output.exists():
        raise ValueError("Fresh independent direct runtime output required")
    helper=Path(life.__file__).resolve()
    if life.digest(helper)!=LIFE_SEAL:
        raise ValueError("Frozen lifecycle differs")
    prefile=PRE/"preflight-manifest.json"
    pre=life.read_bound(prefile,PRE_SEAL)
    validate(pre)
    evidence=life.read_bound(PRE/"target-before.json",pre["pins"][str(PRE/"target-before.json")])
    validate_targets(evidence)
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    if plan["simv"]!=str(life.IMAGE) or len(plan["image"])!=66 or plan["image"].get(str(life.IMAGE))!=IMAGE_SEAL:
        raise ValueError("Exact frozen66-file image differs")
    pins=life.merge_pins(pre["pins"],plan["image"])
    pins=life.merge_pins(pins,{str(prefile):PRE_SEAL,str(helper):LIFE_SEAL,str(life.PLAN):life.PLAN_SEAL})
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_run_gap102b_simulation.py"),
                 Path(life.__file__).with_name("test_run_gap95_simulation.py")):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    if evidence!=proof.frozen.target_evidence():
        raise ValueError("Fresh source/design717 binding differs")
    trace=Path(pre["input_spike_trace"])
    if proof.validate(proof.s.parse_spike_commits(trace),pre["symbols"],trace.read_text())!=pre["validation"]:
        raise ValueError("Independent sealed raw Spike oracle differs")
    life.check(pins)
    return output,dict(case=NAME,preflight=pre,pins=pins,command=command(output),timeout_s=600,
        input_elf=str(ELF),input_spike_trace=str(trace),target_before=str(PRE/"target-before.json"),
        old_image_files_checked=66,baseline_tests=717,expected_checks=723,expected_illegal_traps=0,
        expected_mac_opcode="0xf2c56457",expected_architectural_mac_count=1,expected_software_vl=129,
        expected_mac_vstart=128,expected_active_mac_bytes=4,expected_active_source_load_bytes=2,
        expected_full_vrf_snapshot_bytes=4096,expected_source_guard_bytes=1536,
        expected_recovery_guard_bytes=64,expected_spike_vector_write_instructions=35,
        expected_spike_register_declarations=43,expected_spike_declared_bytes=5504,
        physical_vrf_traffic_count_inferred_from_spike=False,predicted_target_raw=127,
        target_hit_verified=False,dut_self_check_verified=False,coverage_admitted=False,
        admission_performed=False,rtl_changed=False,new_RTL_signoff=False,automatic_retry=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","run"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--prepared-seal")
    args=parser.parse_args(argv)
    if (args.mode=="run")!=bool(args.prepared_seal):
        parser.error("Only explicit run requires external --prepared-seal")
    output,manifest=prepare(args.output)
    record=output.with_name(output.name+".prepared.json")
    if args.mode=="prepare":
        life.save(record,manifest)
        print(json.dumps(dict(status="GAP102B_RUN_PREPARED_NO_VCS",prepared=str(record),
                              seal=life.digest(record),pins_checked=len(manifest["pins"]))))
    else:
        if life.read_bound(record,args.prepared_seal)!=manifest:
            raise ValueError("Reviewed prepared contract differs")
        life.run(output,manifest)


if __name__=="__main__":main()
