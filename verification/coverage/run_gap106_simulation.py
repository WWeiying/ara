"""One reviewed GAP106 old-image run; raw evidence only, never admission."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import run_gap95_simulation as life

PRE = life.OUT/'gap106-positive-inf-preflight-725-20261006-01'
PRE_SEAL = 'd217e69408396c536987b08d8b35f628cfae972b8e1d7a4c1c7ffeba8afeefc0'
NAME = 'qbs_gap106_positive_inf'
ELF = PRE/(NAME+'.elf')
ELF_SEAL = '26e5a60abb383f4a2b0acff13574789a994e64010ae347642bca95a3d1889781'
LIFE_SEAL = '1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8'
IMAGE_SEAL = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
BASE_SEAL = '0f49638e8cea36b28b5832e7eaeea39ee9b5249a162de3f3732c0fcd13a5a397'
BUDGET = 600


def exact(actual, expected, label):
    for key, value in expected.items():
        if key not in actual or type(actual[key]) is not type(value) or actual[key] != value:
            raise ValueError(label+': '+key)


def validate(pre):
    exact(pre, dict(status='HOST_ORACLE_ELF_READY_SPIKE_CUSTOM_ISA_UNSUPPORTED_NOT_RTL_PASS',
        name=NAME, binary=str(ELF), binary_sha256=ELF_SEAL, baseline_seal=BASE_SEAL,
        host_checks=44, dut_checks=41, commands=2, phase_order=[0,0], host_negative_tests=34,
        full_vrf_words_per_command=1024, measured_gain=None, vcs_launched=False,
        rtl_changed=False, coverage_admitted=False), 'Exact preflight differs')
    exact(pre['spike'], dict(status='QBS_CUSTOM_ISA_UNSUPPORTED_NOT_FUNCTIONAL_PASS',
        capability_probe_completed=True, custom_isa_pass=False, qbs_app_spike_executed=False),
        'Unsupported custom ISA boundary differs')
    exact(pre['elf_proof'], dict(status='STATIC_ELF_VERIFIED_NOT_EXECUTED', elf=str(ELF),
        elf_sha256=ELF_SEAL, m=1, n=1, k_blocks=1, weight_profile='Q5_K',
        activation_mod16=[0,0], custom_commands=2, active_outputs_per_command=1,
        full_vrf_words_checked=2048, initial_words_checked=2048, source_bytes_checked=6880,
        csr_words_checked=24, dut_checks=41, vl=1, vtype=16, vstart=0, frm=2,
        fflags_seed=8, vcsr=5, vcs_launched=False,
        sites=[dict(pc=0x8000017a,symbol='gap106_qbexec_site0',word=0x00b5045b),
               dict(pc=0x80000252,symbol='gap106_qbexec_site1',word=0x00b5045b)]),
        'ELF contract differs')
    if [(p['raw_index'],p['native_id'],p['vector'],p['file_id']) for p in pre['targets']] != [(4,'3','1','574'),(7,'4','0','574')]:
        raise ValueError('Exact Inf conversion targets required')


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
    for name in ('host-app.log','host-reference0.log','host-reference1.log','oracle-command0.json','oracle-command1.json','numeric-proof.json',
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
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_run_gap106_simulation.py'),
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
    for c in (0,1):
        oracle = life.read_bound(PRE/('oracle-command%d.json'%c),pins[str(PRE/('oracle-command%d.json'%c))])
        exact(oracle, dict(scope='host-reference-only', independent_native_decode=True,
            row_major_bytes_checked=True, m=1, n=1, fflags=0,
            custom_instruction_execution_prechecked=False,
            integer_dot=[256],integer_correction=[0],
            expected_bits=pre['expected_bits_per_command'][c]), 'Independent host oracle differs')
        if len(bytes.fromhex(oracle['activation_hex'])) != 292:
            raise ValueError('Native activation length differs')
    exact(pre['numeric_proof'],dict(weight_d=[0x3c00,0x7c00],activation_d=0x3f800000,
        dot=256,correction=0,dmin=0,first_block_accumulator=0,
        expected_bits=[0x43800000,0x7f800000],generated_fflags=0,
        architectural_fflags_seed=8,architectural_fflags_after=8,
        inf_times_zero=False,inf_minus_inf=False,spike_custom_pass=False),'Numeric prerequisites differ')
    numeric = life.read_bound(PRE/'numeric-proof.json',pins[str(PRE/'numeric-proof.json')])
    if numeric != pre['numeric_proof']:
        raise ValueError('Numeric evidence differs')
    expected_log = ['GAP106 command=0 checks=18 errors=0','GAP106 command=1 checks=18 errors=0',
        'GAP106 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
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
        old_image_files_checked=66,baseline_tests=725,coverage_delta_requires_latest_formal_baseline=True,
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
        print(json.dumps(dict(status='GAP106_PREPARED_NO_VCS',prepared=str(record),
                              seal=life.digest(record),pins_checked=len(manifest['pins']))))
    else:
        if life.read_bound(record,args.prepared_seal) != manifest:
            raise ValueError('Reviewed prepared contract differs')
        run(output,manifest)


if __name__ == '__main__':
    main()
