"""Private software-case adapter; immutable UART lifecycle, one600s run then audit."""
import argparse
import json
from pathlib import Path
from types import FunctionType
import run_qbs_payload_matrix4_uart as frozen

life,reused=frozen.life,frozen.reused
PRE=life.OUT/'qbs-payload-residual4-preflight766-agent-20261007-01'
SEAL='ffefb83bab2d54898ad08c78bbd22e39d904661f601b3397e11cafcb33ea6ddd'
ELF_SHA='e9c4b78bcc74c32a94742501ed45f57ce6676dd7e00fcb0d43e0a9f9e78ecd64'
NAME='qbs_payload_residual4_766'
RUN=life.OUT/'qbs-payload-residual4-old-image766-agent-20261007-01'
QUAL=life.OUT/'qbs-payload-residual4-qualified766-agent-20261007-01'
FROZEN_SHA='11d3e3ec20ca070f925f5871270169a6739897e1f03c94dfde2fd7285b5489b7'


def validate(pre):
    reused.exact(pre,dict(status='MATRIX4_HOST_NATIVE_STATIC_ELF_READY_NOT_DUT_PASS',
        binary=str(PRE/(NAME+'.elf')),binary_sha256=ELF_SHA,baseline=766,
        commands=4,budget_s=600,host_checks=28,host_negative_tests=24,dut_checks=24,
        full_vrf_bytes=16384,source_readback_bytes=18176,csr_values=48,
        wp=[4,4,12,10],ap=[8,8,8,8],layout=[2,1,1,2],profile=[5,2,2,7],
        weight_block_bytes=[110,210,210,84],predicted_gain=504,measured_gain=None,
        coverage_admitted=False,vcs_launched=False,full_scalar_ISA_verified=False,rtl_changed=False),'Exact766 software')
    sites=pre['sites']
    if len(sites)!=4 or len({s['pc'] for s in sites})!=4 or any(s['word']!=0x0eb5045b for s in sites):
        raise ValueError('Exact four M8 sites')
    proof=life.read_bound(PRE/'uart-proof.json',pre['output_pins'][str(PRE/'uart-proof.json')])
    if proof!=pre['uart_proof'] or proof['status']!='ACTUAL_ELF_TWO_UART_PRINTF_CALLS_NO_NEWLIB_PRINT_SYSCALL' or len(proof['calls'])!=2:
        raise ValueError('Exact UART proof')


def prepare(output):
    if life.digest(Path(frozen.__file__))!=FROZEN_SHA or life.digest(Path(frozen.base.__file__))!=frozen.BASE_SHA:
        raise ValueError('Frozen UART runner drift')
    namespace=dict(vars(frozen.base),PRE=PRE,SEAL=SEAL,ELF_SHA=ELF_SHA,NAME=NAME,validate=validate)
    out,record=FunctionType(frozen.base.prepare.__code__,namespace)(output)
    extra={}
    for name in ('run_qbs_payload_residual4_766.py','qualify_qbs_payload_residual4_766.py','test_qbs_payload_residual4_runtime766.py',
        'qualify_qbs_payload_matrix4_uart.py','test_qualify_qbs_payload_matrix4_uart.py'):
        path=Path(__file__).with_name(name).resolve();extra[str(path)]=life.digest(path)
    for module in (frozen,):
        path=Path(module.__file__).resolve();extra[str(path)]=life.digest(path)
    record['pins']=life.merge_pins(record['pins'],extra)
    record.update(eventual_admission_base_required=766,automatic_postrun_qualification=True,
        software_change='Q3/Q6/Q2 fresh mapping4 only; frozen simv66/lifecycle/600s unchanged')
    life.check(record['pins'])
    return out,record


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('prepare','run'))
    parser.add_argument('--prepared-seal');a=parser.parse_args()
    if bool(a.prepared_seal)!=(a.mode=='run'):parser.error('Run requires seal')
    out,record=prepare(RUN);path=RUN.with_name(RUN.name+'.prepared.json')
    if a.mode=='prepare':
        if path.exists():raise ValueError('Preserve preparation')
        life.save(path,record);print(json.dumps(dict(path=str(path),seal=life.digest(path))),flush=True)
        return
    if life.read_bound(path,a.prepared_seal)!=record:raise ValueError('Prepared drift')
    reused.run(out,record)
    import qualify_qbs_payload_residual4_766 as qualifier
    try:
        result=qualifier.collect(QUAL,a.prepared_seal)
    except Exception as error:
        life.save(out/'postprocess-status.json',dict(status='HOLD_NOT_ADMITTED',reason=repr(error),coverage_admitted=False))
        raise
    life.save(out/'postprocess-status.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
