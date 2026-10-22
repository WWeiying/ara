"""No-run final pin/ledger review, separate from immutable reference evidence."""
from common import *
from check_reference import specification, validate


def main():
    ready=read(HERE/'READY.json')
    require(ready['status']=='ALL9_EXECUTOR_REFERENCE_PASS_PENDING_INDEPENDENT_REVIEW','batch terminal')
    require(ready['shapes']==SHAPES and not (HERE/'STOPPED.json').exists(),'exact9/no stopped batch')
    checkpins(ready['case_ready_pins'])
    require(len(list(HERE.glob('*/reference01/ATTEMPT_STARTED.json')))==9,'nine unique attempts')
    rows=[];allpins={};inputpins={}
    for shape in SHAPES:
        dest=HERE/shape;ref=dest/'reference01'
        r=read(dest/'READY.json');a=read(ref/'admission.json');e=read(ref/'execution.json')
        checkpins(r['pins']);allpins.update(r['pins']);inputpins.update(a['pins'])
        require(a['limits']==LIMITS and a['profile']==ISA and e['profile']==ISA,'exact bounds/profile')
        require(a['command']==[str(SPIKE),'-d','--debug-cmd='+str(ref/'spike.cmd'),
            '--isa='+ISA,'-m2','--log-commits','--log='+str(ref/'commits.log'),str(dest/'spike/program.elf')],'actual command')
        require(e['returncode']==0 and e['error'] is None and e['elapsed_s']<120,'reference exit')
        require(e['admission_sha256']==sha(ref/'admission.json'),'used admission pin')
        for name,v in e['raw'].items():
            require(sha(ref/name)==v['sha256'] and (ref/name).stat().st_size==v['bytes']<=LIMITS['raw_bytes'],'actual raw pin/size')
        data=read(ref/'ledger.json');s=specification(dest);validate(s,data)
        require((ref/'console.log').read_text()==data['console'],'original full console')
        require(read(ref/'checker_host.json')['status']=='PASS_20_HOST_ONLY','raw mutation gate')
        result=read(ref/'result.json')
        require(result['firmware_retired']==data['terminal']['firmware_retired'],'result/ledger match')
        allpins[str(dest/'READY.json')]=sha(dest/'READY.json')
        rows.append({'shape':shape,'sew':s['config']['sew'],'cap':s['config']['cap'],'vl':s['config']['vl'],
            'soc_sha256':sha(dest/'soc/program.elf'),'spike_sha256':sha(dest/'spike/program.elf'),
            'firmware_retired':result['firmware_retired'],'retired_total':result['retired_total'],
            'elapsed_s':e['elapsed_s'],'raw_bytes':e['raw']['commits.log']['bytes'],
            'static_upper':a['static_upper'],'target_pc':hex(data['helper'][11]['pc']),
            'target_ordinal':data['helper'][11]['ordinal'],'result':result['result']})
    for p in (HERE/'READY.json',HERE/'manifest.json',HERE/'reference_plan.json',HERE/'terminal_check.py'):
        allpins[str(p)]=sha(p)
    save(HERE/'TERMINAL_CHECK.json',{'status':'ALL9_EXECUTOR_AND_PIN_CHECK_PASS_PENDING_INDEPENDENT_REVIEW',
        'shapes':SHAPES,'rows':rows,'exact_attempts':9,'input_pins_unique':len(inputpins),
        'evidence_pins_unique':len(allpins),'all_pins_unchanged':True,'evidence_pins':allpins,
        'native_host_tests':117,'preflight_ledger_tests':180,'preflight_raw_pc_negatives':558,
        'preflight_boot_negatives':27,'actual_raw_ledger_host_tests':180,
        'target_calls':9,'original_helper_instructions':189,'original_output_byte_checks':1296,
        'fixture_field_reads':60480,'profile':ISA,'DUT_run':False,'RTL_build':False,
        'Linux_run':False,'full6720_accepted':False,'independent_review':'pending'})
    for r in rows:print(r['shape'],r['firmware_retired'],f"{r['elapsed_s']:.3f}s",r['raw_bytes'],flush=True)
    print('READY_SHA256',sha(HERE/'READY.json'))
    print('TERMINAL_CHECK_SHA256',sha(HERE/'TERMINAL_CHECK.json'))


if __name__=='__main__':main()
