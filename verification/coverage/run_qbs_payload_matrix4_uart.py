"""Exact UART-only matrix4 successor, same frozen lifecycle and 600s bound."""
import argparse
import json
from pathlib import Path
from types import FunctionType
import run_qbs_payload_matrix4 as base

life,reused=base.life,base.reused
PRE=life.OUT/'qbs-payload-matrix4-uart-preflight764-agent-20261007-01'
SEAL='be1c95d80a1758e36cba8d34fc9c5ba651b8d3627e9433a553bb4c866d718848'
ELF_SHA='dca509eca477b2087bb7ecb2df3a879e37f7fed28fdbae3757f4bc2487c98285'
NAME='qbs_payload_matrix4_uart'
BASE_SHA='534e2a21159d63151a9f4e98a1e50eba41d983fae5ccfe722ca004d12333ec50'


def validate(pre):
    ns=dict(vars(base),PRE=PRE,SEAL=SEAL,ELF_SHA=ELF_SHA,NAME=NAME)
    FunctionType(base.validate.__code__,ns)(pre)
    proof=life.read_bound(PRE/'uart-binding-proof.json',pre['uart_binding_proof_sha256'])
    if proof['status']!='ACTUAL_ELF_TWO_UART_PRINTF_CALLS_NO_NEWLIB_PRINT_SYSCALL' or len(proof['calls'])!=2:
        raise ValueError('Actual UART ELF proof differs')


def prepare(output):
    if life.digest(Path(base.__file__))!=BASE_SHA:
        raise ValueError('Sealed predecessor runner drift')
    ns=dict(vars(base),PRE=PRE,SEAL=SEAL,ELF_SHA=ELF_SHA,NAME=NAME,
            validate=validate,__file__=__file__)
    out,record=FunctionType(base.prepare.__code__,ns)(output)
    extra={}
    for path in (Path(base.__file__),Path(__file__).with_name('test_run_qbs_payload_matrix4_uart.py')):
        extra[str(path.resolve())]=life.digest(path)
    record['pins']=life.merge_pins(record['pins'],extra)
    life.check(record['pins'])
    record['software_change']='UART printf_ binding only, no RTL/workload/oracle/budget changes'
    return out,record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','run'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepared-seal');a=p.parse_args()
    if bool(a.prepared_seal)!=(a.mode=='run'):p.error('Run requires prepared seal')
    out,record=prepare(a.output);path=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        if path.exists():raise ValueError('Preserve existing preparation')
        life.save(path,record)
        print(json.dumps(dict(prepared=str(path),seal=life.digest(path),pins=len(record['pins']))),flush=True)
    else:
        if life.read_bound(path,a.prepared_seal)!=record:raise ValueError('Prepared drift')
        reused.run(out,record)


if __name__=='__main__':main()
