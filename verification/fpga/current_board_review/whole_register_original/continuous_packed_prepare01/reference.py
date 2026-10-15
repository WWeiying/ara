"""Freeze once; one bounded complete reference only after independent entry review."""
import sys
from pathlib import Path
from prepare import HERE, OLD, CC, SPIKE, LIMIT, RAW_LIMIT, read, save, sha, require, pins_check, command


def freeze():
    host=read(HERE/'host02/result.json');entry=read(HERE/'host_entry01/result.json')
    require(host['run']['returncode']==0 and not host['run']['timeout'] and
            host['case_sha256']==sha(HERE/'case.c') and host['header_sha256']==sha(HERE/'packed.h'), 'Actual Host source binding')
    require(entry['actual_main']['returncode']==0 and entry['fresh_gate']['returncode']==0
            and entry['ub_trap']['returncode']<0,'Actual main/gates/UB trap')
    old=HERE.parent/'continuous_o2_prepare01/reference_bound01.json'
    pins=dict(read(old)['pins']);pins[str(old)]=sha(old);pins_check(pins)
    proof=read(HERE/'sourceproof.json');lower={}
    offsets={'table_ld':0x172,'input_sd':0x178,'output_sd':0x196,
             'current_input_ld':0x218,'output_ld_active':0x24a,'output_ld_inactive':0x78c}
    expected={'table_ld':0x639c,'input_sd':0xfef6bc23,'output_sd':0xe394,
              'current_input_ld':0xfe07b783,'output_ld_active':0x6210,'output_ld_inactive':0x639c}
    for backend,s in proof['backends'].items():
        require(sha(s['elf'])==s['sha256'],'Actual ELF unchanged')
        base=s['symbols']['whole_original_main'];pcs={}
        for name,offset in offsets.items():
            pc=base+offset;ins=s['code'][str(pc)]
            require(ins==expected[name],'Actual scalar lowering '+backend+' '+name)
            pcs[name]=dict(pc=pc,encoding=ins)
        lower[backend]=dict(pcs=pcs,elf_sha256=s['sha256'],bss_end=s['symbols']['__bss_end'],
                            stack_top=s['symbols']['__stack_top'])
    save(HERE/'lowering.json',dict(status='ACTUAL_LD_SD_NO_LIBCALL_NO_EXTRA_RVV',backends=lower,
                                  init_per_call=dict(input_sd=128,output_sd=136),output_words_per_call=136))
    for p in HERE.rglob('*'):
        if p.is_file():pins[str(p)]=sha(p)
    pins[str(HERE.parents[3]/'coverage/scoped_rv64c_memory.py')]=sha(HERE.parents[3]/'coverage/scoped_rv64c_memory.py')
    pins[str(CC)]=sha(CC);pins[str(SPIKE)]=sha(SPIKE)
    save(HERE/'reference_bound01.json',dict(pins=pins,steps=LIMIT,seconds=120,raw_bytes=RAW_LIMIT,
         parser_seconds=600,no_retries=True,scope='Full original1134 plus366 exclusions; scalar packed conversion; not original C byte identity',
         fresh_input_bytes_each_call=1024,fresh_output_bytes_each_call=1088,output_bytes_each_call=1088))
    print('FROZEN',sha(HERE/'reference_bound01.json'),flush=True)


def execute(digest,review_path,review_digest):
    require(sha(HERE/'reference_bound01.json')==digest,'Bound identity')
    require(sha(review_path)==review_digest,'Independent review identity')
    review=read(review_path)
    require(review['status']=='NO_BLOCKER_REFERENCE_ONLY' and review['bound_sha256']==digest,'Independent reference admission')
    bound=read(HERE/'reference_bound01.json');pins_check(bound['pins'])
    out=HERE/'reference01';out.mkdir()
    save(out/'admission.json',dict(bound_sha256=digest,review_path=str(review_path),review_sha256=review_digest,
                                 DUT_started=False,authorization='User single complete bounded packed reference'))
    try:
        execution=command([SPIKE,'--isa=rv64gcv_zvl1024b','-m2','--instructions='+str(LIMIT),
                           '--log-commits','--log='+str(out/'commits.log'),HERE/'spike/whole_all.elf'],
                          out/'spike.stdout',120,RAW_LIMIT)
        require((out/'commits.log').stat().st_size<=RAW_LIMIT,'4GiB raw bound')
        parser=command([sys.executable,'-B',HERE/'audit.py','--bound-sha256',digest],out/'audit.log',600)
        pins_check(bound['pins']);require(sha(review_path)==review_digest,'Late review identity')
        result=read(out/'reference.json')
        require(result['status']=='FULL1134_PACKED_REFERENCE_PASS_NOT_DUT','Full reference acceptance')
        save(HERE/'RESULT.json',dict(status='FULL1134_PACKED_REFERENCE_PASS_NOT_DUT',bound_sha256=digest,
             review_sha256=review_digest,reference_sha256=sha(out/'reference.json'),actual_spike=execution,
             actual_audit=parser,firmware_through_htif=result['firmware_through_htif'],DUT_started=False,retries=0))
        print('REFERENCE_PASS',result['firmware_through_htif'],flush=True)
    except BaseException as error:
        save(out/'NOT_ACCEPTED.json',dict(status='NOT_ACCEPTED_NO_RETRY',error=str(error),DUT_started=False))
        raise


if __name__=='__main__':
    if sys.argv[1:]==['freeze']:freeze()
    else:
        require(len(sys.argv)==5 and sys.argv[1]=='execute','Explicit bound and independent review')
        execute(sys.argv[2],Path(sys.argv[3]),sys.argv[4])
