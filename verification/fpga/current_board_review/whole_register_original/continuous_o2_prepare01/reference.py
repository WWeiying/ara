"""Exclusive one-shot bounded reference and parser. No DUT path."""
import sys
from prepare import HERE, SPIKE, LIMIT, RAW_LIMIT, read, save, sha, require, pins_check, command

def freeze():
    b=read(HERE/'bound.json');pins_check(b['pins']);pins=dict(b['pins'])
    for p in (HERE/'bound.json',HERE/'audit.py',HERE/'reference.py',
              HERE.parents[3]/'coverage/scoped_rv64c_memory.py'):
        pins[str(p)]=sha(p)
    save(HERE/'reference_bound01.json',dict(pins=pins,steps=LIMIT,seconds=120,raw_bytes=RAW_LIMIT,
        parser_seconds=600,no_retries=True,authorization='User single full1134 O2 reference; no DUT'))
    print(sha(HERE/'reference_bound01.json'))

def execute(digest):
    require(sha(HERE/'reference_bound01.json')==digest,'Actual frozen audit/compile inputs')
    b=read(HERE/'reference_bound01.json');pins_check(b['pins']);out=HERE/'reference01';out.mkdir()
    try:
        command([SPIKE,'--isa=rv64gcv_zvl1024b','-m2','--instructions='+str(LIMIT),
                 '--log-commits','--log='+str(out/'commits.log'),HERE/'spike/whole_all.elf'],out/'spike.stdout',120,RAW_LIMIT)
        require((out/'commits.log').stat().st_size<=RAW_LIMIT,'Raw4GiB bound')
        command([sys.executable,'-B',HERE/'audit.py','--bound-sha256',digest],out/'audit.log',600)
        pins_check(b['pins']);r=read(out/'reference.json')
        save(HERE/'RESULT.json',dict(status='FULL1134_O2_REFERENCE_PASS_NOT_DUT',firmware_through_htif=r['firmware_through_htif'],
            reference_sha256=sha(out/'reference.json'),actual_reference=read(str(out/'spike.stdout')+'.exit.json'),
            actual_audit=read(str(out/'audit.log')+'.exit.json'),bound_sha256=digest,DUT_started=False,retries=0))
        print('REFERENCE_PASS',r['firmware_through_htif'],flush=True)
    except BaseException as error:
        save(out/'NOT_ACCEPTED.json',dict(status='NOT_ACCEPTED_NO_RETRY',error=str(error),DUT_started=False))
        raise

if __name__=='__main__':
    if sys.argv[1:] == ['freeze']:freeze()
    else:
        require(len(sys.argv)==3 and sys.argv[1]=='execute','Explicit bound required')
        execute(sys.argv[2])
