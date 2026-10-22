#!/usr/bin/env python3
"""One complete offline parse per existing raw file; never executes an ELF."""
import time
import sys
sys.dont_write_bytecode=True
from prepare import HERE,SHAPES,read,save,sha,require,ISA,SPIKE
from reference_check02 import audit,console_store

def main():
    out=HERE/'offline02';out.mkdir(exist_ok=False)
    bound=read(HERE/'bound.json');require(sha(HERE/'bound.json')=='809f8fcb36a0f736c07c8104e7db0858793724ebdcf356cc4e342db4e26d583d','Bound drift')
    pins=dict(bound['pins']);pins[str(HERE/'bound.json')]=sha(HERE/'bound.json')
    for name in ('reference_check02.py','offline02.py','REFERENCE_ADMISSION.md'):pins[str(HERE/name)]=sha(HERE/name)
    for path,digest in pins.items():require(sha(path)==digest,'Input drift '+path)
    for p in SHAPES:
        root=HERE/p['id'];ref=root/'reference01'
        for n in ('execution.json','not_completed.json','command.json','spike.cmd','spike.stdout','commits.log'):
            pins[str(ref/n)]=sha(ref/n)
        execution=read(ref/'execution.json');command=read(ref/'command.json');proof=read(root/'sourceproof.json')
        require(type(execution['returncode']) is int and execution['returncode']==0 and
                execution['timeout'] is False and 0<execution['elapsed_s']<=120,'Actual reference child outcome')
        require(command['command']==[str(SPIKE),'-d','--debug-cmd='+str(ref/'spike.cmd'),'--isa='+ISA,'-m2',
                '--log-commits','--log='+str(ref/'commits.log'),proof['backends']['spike']['elf']] and
                command['steps']==p['steps'] and command['file_bytes']==p['raw_bytes'] and command['attempt']==1 and
                command['elf_sha256']==proof['backends']['spike']['sha256'] and command['spike_sha256']==sha(SPIKE),
                'Actual command/profile/one-attempt identity')
        require((ref/'commits.log').stat().st_size==execution['raw_bytes']<p['raw_bytes'],'Raw bound')
        require(read(ref/'not_completed.json')['reason']=='Runtime console scalar byte','Different first checker failure')
    save(out/'input_pins.json',pins)
    s=read(HERE/SHAPES[0]['id']/'spike/symbols.json')
    console_store(s['_start']+0x46,0x0002b023,s['replay_log'],0,8,s,0)
    rejected=0
    for pc,insn,val,n in [(s['main'],0x0002b023,0,0),(s['_start']+0x46,0x0002b023,1,0),
                        (s['_start']+0x46,0x0002b023,0,1),(s['_start']+0x46,0x0012b023,0,0)]:
        try:console_store(pc,insn,s['replay_log'],val,8,s,n)
        except ValueError:rejected+=1
    require(rejected==4,'Narrow startup compatibility negative controls')
    save(out/'host.json',dict(status='PASS_HOST_ONLY',positive=1,negative=4,
        checker_sha256=sha(HERE/'reference_check02.py'),scope='Only pinned startup zero-store may be console-width8'))
    results=[]
    for p in SHAPES:
        started=time.monotonic();root=HERE/p['id']
        try:
            result=audit(root,root/'reference01/commits.log')
            result.update(reference_execution=read(root/'reference01/execution.json'),
                raw_sha256=pins[str(root/'reference01/commits.log')],checker_sha256=sha(HERE/'reference_check02.py'),
                offline_seconds=time.monotonic()-started,whole_raw_parses=1)
            save(out/(p['id']+'.json'),result)
            results.append(dict(shape=p['id'],status=result['status'],calls=result['calls'],results=result['results'],
                guards=result['guards'],firmware_through_htif=result['firmware_through_htif'],
                retired_records=result['retired_records'],report_sha256=sha(out/(p['id']+'.json'))))
            print(results[-1],flush=True)
        except Exception as error:
            save(out/(p['id']+'.not_accepted.json'),dict(status='NOT_ACCEPTED_NO_RETRY',reason=str(error)))
            raise
    for path,digest in pins.items():require(sha(path)==digest,'Post-parse input drift '+path)
    save(out/'status.json',dict(status='FULL2_REFERENCE_ACCEPTED_WITH_OFFLINE_CHECKER_SUCCESSOR_NOT_DUT',results=results,
        pins_pre_post_unchanged=True,original_executor_postcheck_ERROR_preserved=True,reference_invocations=2,
        no_reference_retry=True,no_ELF_recompile=True,independent_agent_review_pending=True))

if __name__=='__main__':main()
