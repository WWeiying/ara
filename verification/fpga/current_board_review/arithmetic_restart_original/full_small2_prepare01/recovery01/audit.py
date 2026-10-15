#!/usr/bin/env python3
"""Explicitly admitted full offline audit only; no ELF execution or compilation."""
import argparse
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
from prepare import read,save,sha,require,SHAPES,ISA,SPIKE
sys.path.insert(0,str(HERE))
from checker import audit

def main():
    p=argparse.ArgumentParser();p.add_argument('--authorize-full-parse',action='store_true')
    p.add_argument('--approved-checker-sha256',required=True);p.add_argument('--approved-host-sha256',required=True)
    a=p.parse_args()
    require(a.authorize_full_parse and sha(HERE/'checker.py')==a.approved_checker_sha256 and
            sha(HERE/'host.json')==a.approved_host_sha256,'Explicit post-review full-parse gate')
    out=HERE/'fullparse01';require(not out.exists(),'No automatic parse retry/overwrite')
    bound=read(ROOT/'bound.json');require(sha(ROOT/'bound.json')=='809f8fcb36a0f736c07c8104e7db0858793724ebdcf356cc4e342db4e26d583d','Original bound drift')
    host=read(HERE/'host.json');pins={**bound['pins'],**host['pins']}
    for path,digest in pins.items():require(sha(path)==digest,'Pre-audit input drift '+path)
    for path in HERE.iterdir():
        if path.is_file():pins[str(path)]=sha(path)
    pins[str(ROOT/'bound.json')]=sha(ROOT/'bound.json')
    for shape in SHAPES:
        root=ROOT/shape['id'];ref=root/'reference01';execution=read(ref/'execution.json');command=read(ref/'command.json')
        proof=read(root/'sourceproof.json');elf=proof['backends']['spike']
        require(type(execution['returncode']) is int and execution['returncode']==0 and not execution['timeout'] and
            0<execution['elapsed_s']<=120 and execution['raw_bytes']==(ref/'commits.log').stat().st_size<shape['raw_bytes'],
            'Actual child outcome and original file/time bounds')
        require(command['command']==[str(SPIKE),'-d','--debug-cmd='+str(ref/'spike.cmd'),'--isa='+ISA,'-m2',
            '--log-commits','--log='+str(ref/'commits.log'),elf['elf']] and command['elf_sha256']==elf['sha256'] and
            command['attempt']==1 and command['steps']==shape['steps'] and command['file_bytes']==shape['raw_bytes'] and
            command['spike_sha256']==sha(SPIKE),'Actual pinned command/profile')
        for n in ('execution.json','not_completed.json','command.json','spike.cmd','spike.stdout','commits.log'):
            pins[str(ref/n)]=sha(ref/n)
    out.mkdir();save(out/'input_pins.json',pins);results=[]
    for shape in SHAPES:
        root=ROOT/shape['id'];start=time.monotonic()
        try:
            result=audit(root,root/'reference01/commits.log')
            result.update(actual_execution=read(root/'reference01/execution.json'),offline_seconds=time.monotonic()-start,
                raw_sha256=pins[str(root/'reference01/commits.log')],checker_sha256=a.approved_checker_sha256,
                host_sha256=a.approved_host_sha256)
            save(out/(shape['id']+'.json'),result)
            summary={k:result[k] for k in ('shape','status','calls','results','guards','firmware_through_htif','retired_records')}
            summary['report_sha256']=sha(out/(shape['id']+'.json'));results.append(summary);print(summary,flush=True)
        except Exception as error:
            save(out/(shape['id']+'.not_accepted.json'),dict(status='NOT_ACCEPTED_NO_RETRY',reason=str(error)));raise
    for path,digest in pins.items():require(sha(path)==digest,'Post-audit input drift '+path)
    save(out/'status.json',dict(status='FULL2_REFERENCE_ACCEPTED_BY_RECOVERY01_NOT_DUT',results=results,
        pins_pre_post_unchanged=True,actual_Spike_invocations=2,reference_retries=0,
        original_postcheck_ERROR_preserved=True,prior_offline02_INTERRUPTED_notaccepted=True,
        independent_agent_review_pending=True))

if __name__=='__main__':main()
