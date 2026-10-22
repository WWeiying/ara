"""Single 300/600s reviewed old-image lifecycle run; no automatic oracle or admission."""
import argparse
import json
from pathlib import Path
import subprocess

import run_gap95_simulation as life
import build_akv_lifecycle_v2_preflight as fixture

require=fixture.first.require

NAME="vakv_lifecycle_boundary_v2"
PRE=life.OUT/"akv-lifecycle-preflight-721-20261006-02"
PRE_SEAL="acbc1d702e22a2c33bafe40c689051175f3bd09acf3187eea3aef05cddf70aad"
ELF_SHA="bcff4647bed54e8776b6e59be6e54a9692cac16f505377a340873fb744263a11"
LIFE_SEAL="1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8"


def validate(pre,directory):
    expected=dict(status="AKV_LIFECYCLE_721_SOFTWARE_PREFLIGHT_PASS_NOT_VCS",case=NAME,
        baseline_tests=721,baseline_seal=fixture.first.BASE_SEAL,input_elf=str(directory/"input.elf"),
        software_elf=str(directory/"software.elf"),dut_checks=7740,dut_expected_commands=10,
        native_expected_custom_write_bytes=128,dut_expected_vrf_frames=10,dut_expected_CSR_bytes=480,
        full_scalar_differential_qualified=False,full_scalar_independent_qualified=False,
        old_image_budget_s=300,source_ISA="rv64gv_zfh_zvfh",coverage_admitted=False,vcs_launched=False,rtl_changed=False)
    require(all(k in pre and type(pre[k]) is type(v) and pre[k]==v for k,v in expected.items()),
                 "Wrong exact lifecycle preflight boundary")
    validation=dict(status="HOST_SPIKE_SOFTWARE_REFERENCE_PASS_NOT_NATIVE_CUSTOM",checks=7735,
        full_VRF_frames=10,snapshot_data_bytes=40960,snapshot_guard_bytes=1280,actual_CSR_snapshot_bytes=480,
        semantic_rejections=4,real_Spike_traps=0,native_custom_executed=False,native_expected_write_bytes=128,
        coverage_increment_measured=False)
    require(pre["validation"]==validation and pre["symbols"]["tohost"]==0x80001000,
                 "Wrong software reference/terminal contract")
    expected_traps=[dict(phase=i,pc=pre["symbols"]["lifecycle_site_"+str(i)],cause=2,tval=0,validation_error=e)
                    for i,e in zip(fixture.first.BAD_PHASES,fixture.first.ERRORS)]
    require(pre["dut_expected_traps"]==expected_traps and
                 len({t["pc"] for t in expected_traps})==4,"Wrong exact four trap PCs/errors")
    for name in ("input.elf","software.elf","host","host.stdout","target-before.json","native-elf-audit.json",
                 "independent-lifecycle-oracle.json","spike.stderr","spike-validation.json",
                 "native-compile-command.json","software-compile-command.json","spike-command.json"):
        require(str(directory/name) in pre["pins"],"Missing preflight pin: "+name)
    require(pre["pins"][str(directory/"input.elf")]==ELF_SHA,"Wrong native ELF identity")


def validate_target(target):
    require(target["baseline_tests"]==721 and target["baseline_seal"]==fixture.first.BASE_SEAL and
                 target["module_checksum"]=="3509320291" and
                 target["command_return_CSR_capture_before_snapshot_VSET"] is True and
                 target["expected_native_vsets"]==11 and target["expected_vector_loads"]==32 and
                 target["expected_vector_stores"]==320,"Missing immediate CSR/compiled contract")
    expected={8:("4","305","01"),194:("78","947","1"),199:("80","953","0"),201:("81","958","0")}
    require(len(target["targets"])==4 and {r["raw_index"] for r in target["targets"]}==set(expected),
                 "Missing/duplicate target coordinate")
    for r in target["targets"]:
        p=r["point"];raw=r["raw_index"]
        require(type(raw) is int and r["scope"]==fixture.first.SCOPE and r["metric"]=="cond" and
                     r["width"]==392 and r["checksum"]=="2836473276" and r["bitmap_LSB_index"]==391-raw and
                     (p["native_id"],p["line"],p["vector"])==expected[raw] and
                     p["raw_index"]==raw and r["baseline_hit"] is False and
                     r["native_GUI_ID_qualification"] is False,"Wrong721 compiled zero target")


def command(pre,output):
    return [str(life.IMAGE),"-l","run.vcs.log","+NO_FSDB","+ntb_random_seed=1","+AKV_PERF",
        "+PRELOAD="+pre["input_elf"],"+TESTCASE="+NAME,"+COMMIT_TOHOST=80001000",
        "+COMMIT_TRACE="+str(output/"commit_trace.csv"),"+VECTOR_TRACE="+str(output/"vector_trace.csv"),
        "-cm","line+cond+fsm+tgl+branch","-cm_dir",str(output/"code.vdb"),"-cm_name",NAME]


def prepare(directory,seal,output,timeout_s):
    require(type(timeout_s) is int and timeout_s in (300,600),"Only single300/600 budgets allowed")
    directory,output=Path(directory).absolute(),Path(output).absolute()
    require(directory==PRE and directory.resolve()==directory and seal==PRE_SEAL and
                 output.parent==life.OUT and output.resolve()==output and not output.exists(),
                 "Exact preflight / fresh independent output required")
    helper=Path(life.__file__).resolve()
    require(life.digest(helper)==LIFE_SEAL,"Frozen lifecycle drift")
    pre=life.read_bound(directory/"preflight-manifest.json",seal);validate(pre,directory)
    target=life.read_bound(directory/"target-before.json",pre["pins"][str(directory/"target-before.json")])
    validate_target(target)
    audit=fixture.first.native_elf_audit((directory/"input.elf").read_bytes(),pre["symbols"])
    require(audit==life.read_bound(directory/"native-elf-audit.json",
                 pre["pins"][str(directory/"native-elf-audit.json")]),"Native instruction-site audit differs")
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(plan["simv"]==str(life.IMAGE) and len(plan["image"])==66 and plan["image"][str(life.IMAGE)]==
                 "2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3","Wrong old image66")
    pins=life.merge_pins(pre["pins"],plan["image"])
    pins=life.merge_pins(pins,{str(directory/"preflight-manifest.json"):seal,str(helper):LIFE_SEAL,
                             str(life.PLAN):life.PLAN_SEAL})
    for path in (Path(__file__).resolve(),Path(__file__).with_name("test_run_akv_lifecycle_simulation.py")):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    return output,dict(case=NAME,preflight=pre,pins=pins,command=command(pre,output),timeout_s=timeout_s,
        input_elf=pre["input_elf"],old_image_files_checked=66,target_baseline_tests=721,
        minimum_admission_baseline_tests=722,admission_requires_fresh_latest_OR_delta=True,
        expected_commands=10,expected_validation_exceptions=4,expected_traps=pre["dut_expected_traps"],
        expected_custom_write_bytes=128,expected_vector_seed_bytes=4096,expected_snapshot_stores=320,
        expected_vsets=11,CSR_snapshot_bytes=480,full_VRF_frames=10,full_VRF_snapshot_bytes=40960,
        required_native_oracle="10 commands/4 exact trap PCs cause2 tval0; wholeVRF/CSR/source/guards; D64 recovery",
        required_scalar_oracle="Complete independent ISA replay of THIS sealed ELF; not old hardcoded fixture or signature-only",
        full_scalar_independent_qualified=False,full_scalar_differential_qualified=False,
        software_reference_not_native_Spike=True,admission_performed=False,coverage_admitted=False,
        rtl_changed=False,new_RTL_signoff=False)


def run(output,manifest):
    life.check(manifest["pins"])
    output.mkdir();life.save(output/"manifest.json",manifest)
    try:
        with (output/"console.log").open("x") as log:
            result=subprocess.run(manifest["command"],cwd=output,stdout=log,stderr=subprocess.STDOUT,
                                  timeout=manifest["timeout_s"],check=True)
        life.check(manifest["pins"])
        life.save(output/"simulation-status.json",dict(status="SIMULATION_EXITED_NOT_ADMITTED",
            returncode=result.returncode,case=NAME,coverage_admitted=False,native_oracle_qualified=False,
            full_scalar_independent_qualified=False))
    except Exception as error:
        drift=None
        try:life.check(manifest["pins"])
        except Exception as pin_error:drift=str(pin_error)
        life.save(output/"simulation-status.json",dict(status="SIMULATION_FAILED_NOT_ADMITTED",
            reason=str(error),post_failure_pin_error=drift,case=NAME,coverage_admitted=False))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","run"))
    parser.add_argument("--preflight",type=Path,required=True);parser.add_argument("--preflight-seal",required=True)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--timeout-s",type=int,choices=(300,600),required=True)
    parser.add_argument("--prepared-seal")
    args=parser.parse_args()
    require((args.mode=="run")==bool(args.prepared_seal),"Only run requires prepared seal")
    output=args.output.absolute();record=output.with_name(output.name+".prepared.json")
    if args.mode=="prepare":require(not record.exists(),"Prepared record already exists; never overwrite")
    output,manifest=prepare(args.preflight,args.preflight_seal,output,args.timeout_s)
    if args.mode=="prepare":
        life.save(record,manifest)
        print(json.dumps(dict(status="AKV_LIFECYCLE_RUN_PREPARED_NO_VCS",prepared=str(record),
                             seal=life.digest(record),pins_checked=len(manifest["pins"]),timeout_s=args.timeout_s)))
    else:
        require(life.read_bound(record,args.prepared_seal)==manifest,"Reviewed prepared contract differs")
        run(output,manifest)


if __name__=="__main__":main()
