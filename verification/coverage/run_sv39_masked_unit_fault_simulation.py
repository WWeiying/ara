"""Reviewed simv66/180s foreground runner; prepare/verify never launch."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import build_sv39_masked_unit_fault_preflight as p
import run_gap95_simulation as life
import run_pure_war_simulation as frozen

PRE = life.OUT/'sv39-masked-unit-fault-preflight-735-parent-20261006-01'
PRE_SEAL = 'a8e1d8e8bb524a361de18e63a7ab613b6a1695240ef8f99f11fa7957e1229b55'
BASE = life.OUT/'readonly-csr-offline-admitted-735-parent-20261006-01'
BASE_SEAL = '4fb3c0219a791c9a669ad9403d97634042f57b423e0e94d7c65bdf57cfa59397'
LIFE_SEAL = '1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8'
FROZEN_SEAL = '2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'
IMAGE_SEAL = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
NAME, BUDGET, require = 'vsv39_masked_unit_fault_retry', 180, p.require


def exact(obj, expected, message):
    require(all(k in obj and type(obj[k]) is type(v) and obj[k] == v
                for k,v in expected.items()), message)


def verify_preflight():
    pre = life.read_bound(PRE/'preflight-manifest.json', PRE_SEAL)
    exact(pre, dict(status='MASKED_UNIT_FAULT_SPIKE_PREFLIGHT_PASS_NOT_DUT',
        input_elf=str(PRE/'input.elf'), VCS_budget_seconds=180, VCS_launched=False,
        native_DUT_qualified=False, rtl_changed=False, coverage_admitted=False,
        future_delta_requires_explicit_latest_admission_seal=True), 'Exact735 preflight differs')
    exact(pre['spike_validation'], dict(status='SPIKE_MASKED_FAULT_RETRY_ORACLE_PASS_NOT_DUT',
        checks=85, retired=35996, verified_final_memory_bytes=19460, traps=2,
        masked_active_bytes=9, recovery_active_bytes=17, full_destination_bytes=256,
        mask_tail_snapshots_verified=True, original_PC_retry_verified=True,
        scalar_DUT_differential_qualified=False, coverage_admitted=False), 'Software oracle scope differs')
    require(pre['baseline_binding']['baseline'] == str(BASE) and
            pre['baseline_binding']['admission_seal'] == BASE_SEAL and
            pre['baseline_binding']['tests'] == 735 and pre['symbols']['tohost'] == 0x80001000,
            'Explicit735 provenance differs')
    pins = life.merge_pins(pre['pins'], pre['output_pins'])
    for name in ('input.elf','spike.trace','spike-command.json','compile-command.json','target-before.json'):
        require(str(PRE/name) in pre['output_pins'], 'Missing software artifact pin')
    life.check(pins)
    require(json.loads((PRE/'spike-command.json').read_bytes()) == [str(p.shared.SPIKE),
        '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
        '-l','--log-commits',str(PRE/'input.elf')], 'Reference command differs')
    require(p.validate_trace((PRE/'spike.trace').read_text(),pre['symbols']) == pre['spike_validation'],
            'Independent reference oracle differs')
    before, freshpins = p.bind_baseline(BASE, BASE_SEAL)
    require(before == pre['baseline_binding'] and json.loads((PRE/'target-before.json').read_bytes()) == before,
            'Actual735 target/baseline drift')
    pins = life.merge_pins(pins, freshpins)
    return pre, pins


def command(output):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD='+str(PRE/'input.elf'), '+TESTCASE='+NAME, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'), '+VECTOR_TRACE='+str(output/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),'-cm_name',NAME]


def prepare(output):
    require(output.parent == life.OUT and output.resolve() == output and not output.exists(),
            'Fresh direct output required')
    require(life.digest(Path(life.__file__)) == LIFE_SEAL and
            life.digest(Path(frozen.__file__)) == FROZEN_SEAL, 'Frozen lifecycle drift')
    pre, pins = verify_preflight()
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(image['simv'] == str(life.IMAGE) and len(image['image']) == 66 and
            image['image'][str(life.IMAGE)] == IMAGE_SEAL, 'Old image66 identity differs')
    pins = life.merge_pins(pins, image['image'])
    pins = life.merge_pins(pins, {str(PRE/'preflight-manifest.json'):PRE_SEAL,
        str(life.PLAN):life.PLAN_SEAL,str(Path(life.__file__).resolve()):LIFE_SEAL,
        str(Path(frozen.__file__).resolve()):FROZEN_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_run_sv39_masked_unit_fault_simulation.py')):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    return dict(case=NAME,output=str(output),preflight=str(PRE/'preflight-manifest.json'),
        preflight_seal=PRE_SEAL,pins=pins,command=command(output),timeout_s=BUDGET,
        baseline_tests=735,baseline=str(BASE),baseline_seal=BASE_SEAL,old_image_files_checked=66,
        elf_sha256=pins[str(PRE/'input.elf')],image_sha256=IMAGE_SEAL,software_checks=85,
        expected_traps=2,expected_CVX_exceptions=1,foreground_lifetime=True,automatic_retry=False,
        no_FSDB=True,parent_review_required=True,dut_self_check_verified=False,
        terminal_oracle_verified=False,coverage_admitted=False,admission_performed=False,
        rtl_changed=False,new_RTL_signoff=False,systemd_policy=dict(RuntimeMaxSec=240,
            TimeoutStopSec=10,KillMode='control-group'))


def invoke_run(output, manifest):
    require(prepare(output) == manifest,'Prepared execution drift')
    # Same frozen run body, with case/budget constants in a private namespace.
    # No module-global mutation, timeout substitution in subprocess, or retries.
    globals_ = dict(frozen.run.__globals__,BUDGET=BUDGET,PRE=PRE,ELF_SEAL=manifest['elf_sha256'],
        IMAGE_SEAL=IMAGE_SEAL,preflight=SimpleNamespace(NAME=NAME),command=command)
    run = FunctionType(frozen.run.__code__,globals_,frozen.run.__name__,frozen.run.__defaults__)
    return run(output,manifest)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','verify','run'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepared-seal')
    parser.add_argument('--parent-authorized',action='store_true')
    args=parser.parse_args()
    require((args.mode!='prepare') == bool(args.prepared_seal),'Reviewed seal required')
    require((args.mode=='run') == args.parent_authorized,'Separate run authorization required')
    output=args.output.absolute(); manifest=prepare(output)
    record=output.with_name(output.name+'.prepared.json')
    if args.mode=='prepare':
        life.save(record,manifest)
        print(json.dumps(dict(status='SV39_MASKED_RUN735_PREPARED_NO_VCS',prepared=str(record),
            seal=life.digest(record),pins=len(manifest['pins']))))
    else:
        require(life.read_bound(record,args.prepared_seal)==manifest,'Prepared seal/contract drift')
        if args.mode=='run': invoke_run(output,manifest)
        else: print('VERIFY_PASS simv66/735/180s NO_VCS')


if __name__=='__main__': main()
