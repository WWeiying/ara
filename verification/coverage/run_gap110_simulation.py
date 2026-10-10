"""Reviewed GAP110 old-image lifecycle, hard600 seconds; exit0 is not admission."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import run_gap95_simulation as life

PRE=life.OUT/'gap110-q3-r4-preflight-732-20261006-01'
PRE_SEAL='dcaaf03b88d1cbf516e2bbe1466e1790ff52098646d585ae81af17bba2bb37eb'
NAME='qbs_gap110_q3_r4_tail'
ELF=PRE/(NAME+'.elf')
ELF_SEAL='7ea085af09625a504bc99999c862c98a6324cebbba598bd95c7858964ad29df3'
TARGET_SEAL='d7a9d6e8724f9a5c9888c08d2cc760a3f898ea92d74e0f2ed5119c6954518b64'
BASE=life.OUT/'gap109-offline-admitted-732-parent-20261006-01'
BASE_SEAL='badbcc7aad21ce6dab6c8c0eeabc7f85b2c13226bbe893a56c88995eab149794'
LIFE_SEAL='1e8b9f269fefd86e095c01d08bcff0be0fc52dd567273de26aafdebe7233d3d8'
IMAGE_SEAL='2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
BUDGET=600


def exact(actual,expected,label):
    for k,v in expected.items():
        if k not in actual or type(actual[k]) is not type(v) or actual[k]!=v:raise ValueError(label+': '+k)


def oracle_expected(phase):
    if type(phase) is not int or phase not in (0,1):raise ValueError('Only two commands')
    n=7 if phase==0 else 5
    return dict(phase=phase,flags=0,bits=[v for v in (0x43800000,0x44000000,0x44400000,0x44800000,0x44a00000) for _ in range(n)])


def validate(pre):
    exact(pre,dict(status='GAP110_HOST_NATIVE_STATIC_ELF_READY_NOT_RTL_PASS',name=NAME,
        binary=str(ELF),binary_sha256=ELF_SEAL,baseline=str(BASE),baseline_seal=BASE_SEAL,
        commands=2,host_checks=44,dut_checks=41,host_negative_tests=42,budget_s=600,
        expected_fflags=[0,0],expected_csr_fflags=[8,8],full_vrf_words_per_command=1024,
        expected_bits_per_command=[oracle_expected(i)['bits'] for i in (0,1)],
        native_runtime_qualification_required=True,measured_gain=None,vcs_launched=False,
        rtl_changed=False,coverage_admitted=False),'Exact preflight')
    exact(pre['spike'],dict(status='NOT_EXECUTED_CUSTOM_UNSUPPORTED',custom_isa_pass=False,
        full_scalar_isa_verified=False),'No custom Spike claim')
    exact(pre['elf_proof'],dict(status='STATIC_ELF_VERIFIED_NOT_EXECUTED',elf=str(ELF),elf_sha256=ELF_SEAL,
        m=5,n=[7,5],k_blocks=1,vl=[7,5],weight_profile='Q3_K',weight_layout='R4_BLOCK_MAJOR',
        activation_layout='M8_INTERLEAVED',activation_mod16=[4,4],weight_mod16=[0,12],
        active_outputs_per_command=[35,25],full_vrf_words_checked=2048,initial_words_checked=2048,
        source_bytes_checked=7328,csr_words_checked=24,dut_checks=41,vtype=16,vstart=0,frm=2,
        expected_fflags_after=[8,8],fflags_seed=8,vcsr=5,full_scalar_isa_verified=False,
        custom_spike_pass=False,vcs_launched=False,exact_seed_and_snapshot_instructions=True,
        immediate_pre_post_CSR_instructions_verified=True,
        sites=[dict(symbol='gap110_qbexec_site0',pc=0x8000017a,word=0x08b5045b),
               dict(symbol='gap110_qbexec_site1',pc=0x80000252,word=0x08b5045b)]),'Exact ELF')
    targets=pre['targets']
    wanted=[(0,11128+8*j,4628+3*j,3,2+j) for j in range(14)]+[(1,10348+8*j,4336+3*j,1,2+j) for j in range(12)]
    if len(targets)!=26:raise ValueError('Exact26 targets required')
    for t,(phase,raw,native,row,byte) in zip(targets,wanted):
        exact(t,dict(phase=phase,metric='cond',width=21503,checksum='2947893042',
            compiled_definition_checksum='2947893042',before_hit=False,measured_hit=None),'Target identity')
        exact(t['point'],dict(raw_index=raw,native_id=str(native),line='223',vector='011'),'Target leaf')
        if t['point']['spec']['generate_info']!='slot=1,p=1,r=%d,b=%d'%(row,byte):raise ValueError('Target generate coordinate')


def command(output):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(ELF),'+TESTCASE='+NAME,'+COMMIT_TRACE='+str(output/'commit_trace.csv'),
        '+VECTOR_TRACE='+str(output/'vector_trace.csv'),'+QBS_PERF',
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),'-cm_name',NAME]


def prepare(output):
    output=Path(output).absolute()
    if output.parent!=life.OUT or output.resolve()!=output or output.exists():raise ValueError('Fresh independent output')
    helper=Path(life.__file__).resolve()
    if life.digest(helper)!=LIFE_SEAL:raise ValueError('Frozen lifecycle drift')
    pre=life.read_bound(PRE/'preflight-manifest.json',PRE_SEAL);validate(pre)
    pins=life.merge_pins(pre['input_pins'],pre['output_pins'])
    artifacts=life.read_bound(PRE/'artifact_hashes.json',pins[str(PRE/'artifact_hashes.json')])
    pins=life.merge_pins(pins,artifacts)
    if len(pins)!=298 or pins.get(str(ELF))!=ELF_SEAL or pins.get(str(PRE/'target-static-contract.json'))!=TARGET_SEAL:
        raise ValueError('Exact298 preflight identities differ')
    static=life.read_bound(PRE/'target-static-contract.json',TARGET_SEAL)
    if static['targets']!=pre['targets'] or static['baseline_seal']!=BASE_SEAL:raise ValueError('Static target contract differs')
    for name in ('elf-proof.json','elf-fit.json','host-app.log','host-reference.log','host-negative-tests.json',
                 'host-oracle-tests.log','weight-native0.bin','weight-native1.bin','activation-native0.bin','activation-native1.bin'):
        if str(PRE/name) not in artifacts:raise ValueError('Missing preflight artifact: '+name)
    for phase in (0,1):
        record=life.read_bound(PRE/('oracle-command%d.json'%phase),pins[str(PRE/('oracle-command%d.json'%phase))])
        if record!=oracle_expected(phase):raise ValueError('Independent native reference differs')
    if (PRE/'host-app.log').read_text().splitlines()!=['GAP110 command=0 checks=18 errors=0',
        'GAP110 command=1 checks=18 errors=0','GAP110 inspected vrf_words=2048 initial_words=2048 source_bytes=7328 csr_words=24',
        'PASSED: '+NAME+' checks=44 errors=0']:raise ValueError('Full host contract differs')
    if (PRE/'host-oracle-tests.log').read_text().strip()!='GAP110 independent native tests=12 PASS':raise ValueError('Native negative oracle tests differ')
    negatives=life.read_bound(PRE/'host-negative-tests.json',pins[str(PRE/'host-negative-tests.json')])
    mutations={'dest','tail','register','unused','initial','source','activation','padding','descriptor','guard',
        'sourceguard','csrguard','vl','vtype','vstart','frm','flags','vcsr','skip','cancel','sourcecancel'}
    if len(negatives)!=42 or {(r['phase'],r['mutation']) for r in negatives}!={(p,m) for p in (0,1) for m in mutations}:raise ValueError('Negative population differs')
    for row in negatives:
        if pins.get(row['log'])!=row['sha256']:raise ValueError('Negative log identity')
        text=Path(row['log']).read_text()
        if 'FAILED: '+NAME not in text or 'PASSED:' in text or 'unknown fault' in text:raise ValueError('Negative failed to reject')
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    if plan['simv']!=str(life.IMAGE) or len(plan['image'])!=66 or plan['image'].get(str(life.IMAGE))!=IMAGE_SEAL:
        raise ValueError('Exact old66 image differs')
    pins=life.merge_pins(pins,plan['image'])
    pins=life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL,str(helper):LIFE_SEAL,str(PRE/'preflight-manifest.json'):PRE_SEAL})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_run_gap110_simulation.py')):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    return output,dict(case=NAME,preflight=pre,pins=pins,command=command(output),timeout_s=BUDGET,
        old_image_files_checked=66,preflight_files_checked=298,baseline_tests=732,
        coverage_delta_requires_latest_formal_baseline=True,expected_dut_checks=41,expected_checks_per_command=17,
        expected_commands=2,expected_external_request_count=None,expected_backend_vl=[160,160],
        expected_software_vl=[7,5],expected_active_output_bytes=[140,100],expected_csr_fflags=[8,8],
        qualification_required='Complete independent software/native VRF/CSR/source/lifecycle before admission',
        spike_custom_isa_pass=False,full_scalar_isa_verified=False,simulator_exit_is_not_functional_pass=True,
        coverage_admitted=False,admission_performed=False,rtl_changed=False,automatic_retry=False)


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
        print(json.dumps(dict(status='GAP110_PREPARED_NO_VCS',prepared=str(record),
                              seal=life.digest(record),pins_checked=len(manifest['pins']))))
    else:
        if life.read_bound(record,args.prepared_seal) != manifest:
            raise ValueError('Reviewed prepared contract differs')
        run(output,manifest)


if __name__ == '__main__':
    main()

