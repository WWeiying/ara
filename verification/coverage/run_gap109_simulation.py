"""One reviewed GAP109 old-image run; raw evidence only, never admission."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import run_gap95_simulation as life

PRE = life.OUT/'gap109-k2-sticky-preflight-731-20261006-01'
PRE_SEAL = '37f8e166e013483c1b3c99b90968d402cf88d89299dfe0e4043df4a2b17e6a06'
NAME = 'qbs_gap109_k2_sticky'
ELF = PRE/(NAME+'.elf')
ELF_SEAL = '7882d8878241e7770d966bd78d0e3f1dee49c131696f479df8ecc399f330cd92'
LIFE_SEAL = '1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8'
IMAGE_SEAL = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
BASE_SEAL = '79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641'
BUDGET = 600


def exact(actual, expected, label):
    for key, value in expected.items():
        if key not in actual or type(actual[key]) is not type(value) or actual[key] != value:
            raise ValueError(label+': '+key)


TARGET_SEAL = '3f3d687661822268f2385ab514bfb5fd11c2add341a35bb5e4e87d34d274de66'


def oracle_expected(phase):
    if type(phase) is not int or phase not in (0,1):
        raise ValueError('Only two reviewed numeric phases')
    first = [0x43800000,0,0,0,0,0] if phase == 0 else [
        0x43800000,0,0x21800000,0,0x25800000,0x25800000]
    return dict(phase=phase,scope='bounded-native-IEEE-host-only',dot=256,
        correction=0,bits=0x43800000,flags=phase,csr_flags=8|phase,
        stage_bits=first+[0x43800000,0,0x3f800000,0,0x43800000,0x43800000],
        stage_flags=[0]*12 if phase==0 else [0]*10+[1,0])


def spike_ledger():
    values=[]
    for phase in (0,1):
        row=oracle_expected(phase)
        for bits,flags in zip(row['stage_bits'],row['stage_flags']):
            values.extend((bits,flags))
        values.extend((row['csr_flags'],2))
    return values


def validate(pre):
    exact(pre,dict(status='GAP109_HOST_ORACLE_STATIC_ELF_READY_NOT_RTL_PASS',
        name=NAME,binary=str(ELF),binary_sha256=ELF_SEAL,baseline_seal=BASE_SEAL,
        baseline=str(life.OUT/'pure-war-offline-admitted-731-parent-20261006-01'),
        host_checks=44,dut_checks=41,commands=2,host_negative_tests=46,budget_s=600,
        full_vrf_words_per_command=1024,expected_bits_per_command=[[0x43800000],[0x43800000]],
        expected_fflags=[0,1],expected_csr_fflags=[8,9],native_runtime_qualification_required=True,
        measured_gain=None,vcs_launched=False,rtl_changed=False,coverage_admitted=False),
        'Exact GAP109 preflight differs')
    exact(pre['spike'],dict(status='STANDARD_FP32_STAGED_NUMERIC_PASS_NOT_CUSTOM_APP',
        stage_operations=24,phase_oracles=[oracle_expected(0),oracle_expected(1)],ledger=spike_ledger(),
        timeout_s=15,returncode=0,custom_isa_pass=False,
        qbs_app_spike_executed=False,full_scalar_isa_verified=False),'No custom Spike/full ISA claim')
    exact(pre['elf_proof'],dict(status='STATIC_ELF_VERIFIED_NOT_EXECUTED',elf=str(ELF),
        elf_sha256=ELF_SEAL,m=1,n=1,k_blocks=2,weight_profile='Q5_K',
        activation_mod16=[0,0],custom_commands=2,active_outputs_per_command=1,
        full_vrf_words_checked=2048,initial_words_checked=2048,source_bytes_checked=6880,
        csr_words_checked=24,dut_checks=41,vl=1,vtype=16,vstart=0,frm=2,
        fflags_seed=8,expected_fflags_after=[8,9],vcsr=5,vcs_launched=False,
        full_scalar_isa_verified=False,custom_spike_pass=False,
        exact_seed_and_snapshot_instructions=True,immediate_pre_post_CSR_instructions_verified=True,
        sites=[dict(pc=0x8000017a,symbol='gap109_qbexec_site0',word=0x00b5045b),
               dict(pc=0x80000252,symbol='gap109_qbexec_site1',word=0x00b5045b)]),
        'ELF contract differs')
    target=life.read_bound(PRE/'target-static-contract.json',TARGET_SEAL)
    if pre['targets']!=target['targets'] or len(pre['targets'])!=1 or not all(
            t['before_hit'] is False and t['measured_hit'] is None for t in pre['targets']):
        raise ValueError('Exact731 compiled1-target prediction differs')
    exact(pre['numeric_proof'],dict(scope='bounded-integer-dyadic-RNE-not-RTL-execution',
        phase_oracles=[oracle_expected(0),oracle_expected(1)],
        arithmetic='two sequential K blocks, six separately rounded I2F/MUL/FMA stages each; no whole-expression fusion',
        rounding='RNE numerical contract; architectural frm preserved2',
        underflow='tininess after rounding AND inexact',flags_combination='bitwise OR',
        architectural_seed=8,architectural_after=[8,9],host_float_used=False),
        'Separately rounded stages/flags differ')


def backend_contract(pre):
    shape = pre['elf_proof']
    exact(shape,dict(m=1,n=1,k_blocks=2,custom_commands=2,weight_profile='Q5_K'),
          'Exact backend geometry differs')
    results = shape['m'] * shape['n'] * shape['k_blocks']
    commands = shape['custom_commands']
    return dict(scope='successful-Q5_K-affine-path-derived-not-observed',
        integer_results_per_command=results,fp_stages_per_result=6,
        fp_uop_issues_per_command=6*results,accumulator_updates_per_command=results,
        fp_uop_issues_total=commands*6*results,accumulator_updates_total=commands*results,
        architectural_custom_requests=commands,architectural_custom_responses=commands,
        vrf_write_bytes_per_command=128,active_write_bytes_per_command=4,
        zero_tail_bytes_per_command=124,observed=False)


def command(output):
    # Common CRT uses TB EOC, not an HTIF tohost address.
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(ELF),'+TESTCASE='+NAME,
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'),
        '+VECTOR_TRACE='+str(output/'vector_trace.csv'),'+QBS_PERF',
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),'-cm_name',NAME]


def prepare(output):
    output = Path(output).absolute()
    if output.parent != life.OUT or output.resolve() != output or output.exists():
        raise ValueError('Fresh independent runtime output required')
    helper = Path(life.__file__).resolve()
    if life.digest(helper) != LIFE_SEAL:
        raise ValueError('Frozen lifecycle differs')
    pre = life.read_bound(PRE/'preflight-manifest.json',PRE_SEAL)
    validate(pre)
    pins = life.merge_pins({},pre['input_pins'])
    pins = life.merge_pins(pins,pre['output_pins'])
    artifacts = life.read_bound(PRE/'artifact_hashes.json',pins[str(PRE/'artifact_hashes.json')])
    pins = life.merge_pins(pins,artifacts)
    if len(pins) != 333:
        raise ValueError('Exact333 preflight pins differ')
    if pins.get(str(ELF)) != ELF_SEAL:
        raise ValueError('Conflicting/missing ELF pin')
    for name in ('host-app.log','host-reference.log','oracle-command0.json','oracle-command1.json','numeric-proof.json',
                 'host-negative-tests.json','host-oracle-tests.log','spike-preflight.json',
                 'spike-numeric.elf','spike-numeric.stderr.log','elf-proof.json','target-static-contract.json',
                 'weight-native0.bin','weight-native1.bin','activation-native0.bin','activation-native1.bin','elf-fit.json'):
        if str(PRE/name) not in artifacts:
            raise ValueError('Missing software evidence: '+name)
    plan = life.read_bound(life.PLAN,life.PLAN_SEAL)
    if (plan['simv'] != str(life.IMAGE) or len(plan['image']) != 66 or
            plan['image'].get(str(life.IMAGE)) != IMAGE_SEAL):
        raise ValueError('Frozen66-file image differs')
    pins = life.merge_pins(pins,plan['image'])
    pins = life.merge_pins(pins,{str(PRE/'preflight-manifest.json'):PRE_SEAL,
                               str(life.PLAN):life.PLAN_SEAL,str(helper):LIFE_SEAL})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_run_gap109_simulation.py'),
                 Path(life.__file__).with_name('test_run_gap95_simulation.py')):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    build_path=life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    build_sha='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
    build=life.read_bound(build_path,build_sha)
    pins=life.merge_pins(pins,{str(build_path):build_sha})
    for p,h in pre['input_pins'].items():
        if p.startswith(str(life.ROOT/'hardware')+'/'):
            if build.get(p) != h:
                raise ValueError('Historical build/source differs: '+p)
    dispatcher=life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    if pins.get(str(dispatcher)) != build[str(life.ROOT/'hardware/src/ara_dispatcher.sv')]:
        raise ValueError('Historical dispatcher snapshot differs')
    monitor=life.ROOT/'hardware/tb/ara_commit_monitor.sv'
    pins=life.merge_pins(pins,{str(monitor):build[str(monitor)]})
    life.check(pins)
    for phase in (0,1):
        oracle=life.read_bound(PRE/('oracle-command%d.json'%phase),pins[str(PRE/('oracle-command%d.json'%phase))])
        if oracle!=oracle_expected(phase):
            raise ValueError('Independent stage-by-stage native oracle differs')
    if pins.get(str(PRE/'target-static-contract.json'))!=TARGET_SEAL:
        raise ValueError('Exact static target record pin differs')
    numeric = life.read_bound(PRE/'numeric-proof.json',pins[str(PRE/'numeric-proof.json')])
    if numeric != pre['numeric_proof']:
        raise ValueError('Numeric evidence differs')
    spike=life.read_bound(PRE/'spike-preflight.json',pins[str(PRE/'spike-preflight.json')])
    if spike != pre['spike'] or spike['elf'] != str(PRE/'spike-numeric.elf') or (
            pins.get(spike['elf']) != spike['elf_sha256'] or
            pins.get(str(PRE/'spike-numeric.stderr.log')) != spike['trace_sha256']):
        raise ValueError('Standard Spike probe artifact identity differs')
    if (PRE/'host-oracle-tests.log').read_text().strip() != (
            'GAP109 integer dyadic/RNE oracle tests=22 PASS'):
        raise ValueError('Integer oracle boundary checks differ')
    expected_log = ['GAP109 command=0 checks=18 errors=0','GAP109 command=1 checks=18 errors=0',
        'GAP109 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
        'PASSED: '+NAME+' checks=44 errors=0']
    if (PRE/'host-app.log').read_text().splitlines() != expected_log:
        raise ValueError('Host complete checks differ')
    negatives = life.read_bound(PRE/'host-negative-tests.json',pins[str(PRE/'host-negative-tests.json')])
    mutations = {'dest','tail','register','initial','source','activation','descriptor',
                 'guard','sourceguard','csrguard','vl','vtype','vstart','frm','flags','vcsr','skip',
                 'byte:weights:799','byte:activation:2495','byte:descriptor:143',
                 'byte:initial:4223','byte:actual:4223','byte:csr:159'}
    if (len(negatives) != 46 or {(r['phase'],r['mutation']) for r in negatives} !=
            {(c,m) for c in (0,1) for m in mutations}):
        raise ValueError('Host negative population differs')
    for row in negatives:
        if pins.get(row['log']) != row['sha256']:
            raise ValueError('Negative log pin differs')
        raw = Path(row['log']).read_text()
        if 'FAILED: '+NAME not in raw or 'PASSED:' in raw or 'unknown fault' in raw:
            raise ValueError('Negative did not reject')
    life.check(pins)
    return output, dict(case=NAME,preflight=pre,pins=pins,command=command(output),timeout_s=BUDGET,
        old_image_files_checked=66,preflight_files_checked=333,baseline_tests=731,coverage_delta_requires_latest_formal_baseline=True,
        backend_on_success=backend_contract(pre),
        expected_external_request_count=None,
        external_contract='Reconstruct full trace request count; exact responses/conservation; do not infer from K or FP uops',
        expected_dut_checks=41,expected_checks_per_command=17,expected_commands=2,
        expected_output_bits=[0x43800000,0x43800000],expected_generated_fflags=[0,1],
        expected_csr_fflags=[8,9],native_total_write_bytes_per_command=128,
        qualification_required='Independent ISA or complete software/native qualifier before admission',
        spike_custom_isa_pass=False,simulator_exit_is_not_functional_pass=True,
        target_hit_verified=False,dut_self_check_verified=False,coverage_admitted=False,
        admission_performed=False,rtl_changed=False,new_RTL_signoff=False,automatic_retry=False)


def run(output, manifest):
    if manifest['timeout_s'] != BUDGET or manifest['command'] != command(output):
        raise ValueError('Bounded execution contract differs')
    life.check(manifest['pins'])
    output.mkdir()
    life.save(output/'manifest.json',manifest)
    process = None
    try:
        life.check(manifest['pins'])
        with (output/'console.log').open('x') as log:
            process = subprocess.Popen(manifest['command'],cwd=output,stdout=log,
                                       stderr=subprocess.STDOUT,start_new_session=True)
            life.save(output/'started.json',dict(pid=process.pid,launcher_pid=os.getpid(),
                unix_time=time.time(),budget_s=BUDGET,input_elf=str(ELF),elf_sha256=ELF_SEAL,
                image=str(life.IMAGE),image_sha256=IMAGE_SEAL,command=manifest['command'],
                live_identity_verified=False,coverage_admitted=False))
            result = process.wait(timeout=BUDGET)
        if result != 0:
            raise ValueError('Nonzero simulator exit: '+str(result))
        life.check(manifest['pins'])
        life.save(output/'simulation-status.json',dict(status='SIMULATION_EXITED_NOT_ADMITTED',
            returncode=result,case=NAME,coverage_admitted=False,admission_performed=False,
            dut_self_check_verified=False,spike_custom_isa_pass=False))
    except BaseException as error:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        drift = None
        try:
            life.check(manifest['pins'])
        except Exception as pin_error:
            drift = str(pin_error)
        life.save(output/'simulation-status.json',dict(status='SIMULATION_NOT_ADMITTED',
            reason=type(error).__name__+': '+str(error),post_failure_pin_error=drift,
            coverage_admitted=False,admission_performed=False))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','run'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepared-seal')
    args = parser.parse_args(argv)
    if (args.mode == 'run') != bool(args.prepared_seal):
        parser.error('Only explicit run requires external prepared seal')
    output, manifest = prepare(args.output)
    record = output.with_name(output.name+'.prepared.json')
    if args.mode == 'prepare':
        life.save(record,manifest)
        print(json.dumps(dict(status='GAP109_PREPARED_NO_VCS',prepared=str(record),
                              seal=life.digest(record),pins_checked=len(manifest['pins']))))
    else:
        if life.read_bound(record,args.prepared_seal) != manifest:
            raise ValueError('Reviewed prepared contract differs')
        run(output,manifest)


if __name__ == '__main__':
    main()


