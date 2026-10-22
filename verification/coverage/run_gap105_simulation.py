"""One reviewed GAP105 old-image run; raw evidence only, never admission."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import run_gap95_simulation as life

PRE = life.OUT/'gap105-m8-phase8-preflight-723-20261006-03'
PRE_SEAL = 'c8992acc83cd3bb51d75518ba6e7383e2c6b453375c929807bf30d5bf63fd28d'
NAME = 'qbs_gap105_m8_phase8'
ELF = PRE/(NAME+'.elf')
ELF_SEAL = 'd18a70425176dc76f001fcca80a4f6ab88571164f57aca8469428528cd106565'
LIFE_SEAL = '1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8'
IMAGE_SEAL = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
BASE_SEAL = '2f68f64b880b95164f8db6aa2b569d305bd831ad4a05056563b2ab42eade45a4'
BUDGET = 1200


def exact(actual, expected, label):
    for key, value in expected.items():
        if key not in actual or type(actual[key]) is not type(value) or actual[key] != value:
            raise ValueError(label+': '+key)


def validate(pre):
    exact(pre, dict(status='HOST_ORACLE_ELF_READY_SPIKE_CUSTOM_ISA_UNSUPPORTED_NOT_RTL_PASS',
        name=NAME, binary=str(ELF), binary_sha256=ELF_SEAL, baseline_seal=BASE_SEAL,
        host_checks=44, dut_checks=41, commands=2, phase_order=[4,8], host_negative_tests=34,
        full_vrf_words_per_command=1024, measured_gain=None, vcs_launched=False,
        rtl_changed=False, coverage_admitted=False), 'Exact preflight differs')
    exact(pre['spike'], dict(status='QBS_CUSTOM_ISA_UNSUPPORTED_NOT_FUNCTIONAL_PASS',
        capability_probe_completed=True, custom_isa_pass=False, qbs_app_spike_executed=False),
        'Unsupported custom ISA boundary differs')
    exact(pre['elf_proof'], dict(status='STATIC_ELF_VERIFIED_NOT_EXECUTED', elf=str(ELF),
        elf_sha256=ELF_SEAL, m=8, n=1, k_blocks=1, weight_profile='Q5_K',
        activation_mod16=[4,8], custom_commands=2, active_outputs_per_command=8,
        full_vrf_words_checked=2048, initial_words_checked=2048, source_bytes_checked=6880,
        csr_words_checked=24, dut_checks=41, vl=1, vtype=16, vstart=0, frm=2,
        fflags_seed=8, vcsr=5, vcs_launched=False,
        sites=[dict(pc=0x8000017a,symbol='gap105_qbexec_site0',word=0x0eb5045b),
               dict(pc=0x80000252,symbol='gap105_qbexec_site1',word=0x0eb5045b)]),
        'ELF contract differs')
    if len(pre['targets']) != 12 or len({p['raw_index'] for p in pre['targets']}) != 12:
        raise ValueError('Exact twelve targets required')


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
    if pins.get(str(ELF)) != ELF_SEAL:
        raise ValueError('Conflicting/missing ELF pin')
    for name in ('host-app.log','host-reference.log','oracle-command0.json',
                 'host-negative-tests.json','elf-proof.json','spike-preflight.json'):
        if str(PRE/name) not in artifacts:
            raise ValueError('Missing software evidence: '+name)
    plan = life.read_bound(life.PLAN,life.PLAN_SEAL)
    if (plan['simv'] != str(life.IMAGE) or len(plan['image']) != 66 or
            plan['image'].get(str(life.IMAGE)) != IMAGE_SEAL):
        raise ValueError('Frozen66-file image differs')
    pins = life.merge_pins(pins,plan['image'])
    pins = life.merge_pins(pins,{str(PRE/'preflight-manifest.json'):PRE_SEAL,
                               str(life.PLAN):life.PLAN_SEAL,str(helper):LIFE_SEAL})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_run_gap105_simulation.py'),
                 Path(life.__file__).with_name('test_run_gap95_simulation.py')):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    oracle = life.read_bound(PRE/'oracle-command0.json',pins[str(PRE/'oracle-command0.json')])
    exact(oracle, dict(scope='host-reference-only', independent_native_decode=True,
        m8_packing_checked=True, m=8, n=1, fflags=0,
        custom_instruction_execution_prechecked=False,
        integer_dot=[256*c for c in range(1,9)],integer_correction=[0]*8,
        expected_bits=pre['expected_bits_per_command']), 'Independent host oracle differs')
    if len(bytes.fromhex(oracle['activation_hex'])) != 2336:
        raise ValueError('Native activation length differs')
    expected_log = ['GAP105 command=0 checks=18 errors=0','GAP105 command=1 checks=18 errors=0',
        'GAP105 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
        'PASSED: '+NAME+' checks=44 errors=0']
    if (PRE/'host-app.log').read_text().splitlines() != expected_log:
        raise ValueError('Host complete checks differ')
    negatives = life.read_bound(PRE/'host-negative-tests.json',pins[str(PRE/'host-negative-tests.json')])
    mutations = {'dest','tail','register','initial','source','activation','descriptor',
                 'guard','sourceguard','csrguard','vl','vtype','vstart','frm','flags','vcsr','skip'}
    if (len(negatives) != 34 or {(r['command'],r['mutation']) for r in negatives} !=
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
        old_image_files_checked=66,baseline_tests=723,coverage_delta_requires_latest_formal_baseline=True,
        expected_dut_checks=41,expected_checks_per_command=17,expected_commands=2,
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
        print(json.dumps(dict(status='GAP105_PREPARED_NO_VCS',prepared=str(record),
                              seal=life.digest(record),pins_checked=len(manifest['pins']))))
    else:
        if life.read_bound(record,args.prepared_seal) != manifest:
            raise ValueError('Reviewed prepared contract differs')
        run(output,manifest)


if __name__ == '__main__':
    main()
