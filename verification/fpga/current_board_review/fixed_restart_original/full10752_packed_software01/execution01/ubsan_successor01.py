"""Complete only the missing UBSan check, preserving the failed linker attempt."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
OLD=HERE/'host01'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def save(p,d):
    with p.open('x') as f: json.dump(d,f,indent=2); f.write('\n')
def require(c,s):
    if not c: raise ValueError(s)
def run(stem,command,expected=0):
    rc=subprocess.run([sys.executable,str(HERE/'run_bound.py'),'--stem',str(stem),
        '--timeout','120','--expected',str(expected),'--',*map(str,command)],check=False).returncode
    require(rc==0,'Missing-stage successor failed; stop '+str(stem))

def main():
    failure=OLD/'ubsan_compile.wait.json'
    require(read(failure)['actual_wait_exit']==1 and not read(failure)['timed_out'],'Original real link failure')
    require('/usr/bin/ld: cannot find /usr/lib64/libubsan.so.1.0.0' in (OLD/'ubsan_compile.log').read_text(), 'Exact diagnosed environmental cause')
    require(read(HERE/'ubsan_trap_preflight.wait.json')['actual_wait_exit']==0,'Compiler dryrun')
    dry=(HERE/'ubsan_trap_preflight.log').read_text()
    require('-fsanitize-undefined-trap-on-error' in dry and '-lubsan' not in dry,'Trap sanitizer has no missing runtime dependency')
    inputs=read(OLD/'inputs_before.json')
    for p,h in inputs.items(): require(sha(Path(p))==h,'Reviewed Host/source drift '+p)
    rejection={
        'missing_same_value_source_run':'condition=e.bank==bank && e.offset==off && e.value==load_value(src,n) calls=0',
        'missing_mask_SB_run':'condition=off==e.offset && load_value(src,n)==e.value calls=0',
        'missing_same_value_init_run':'condition=off==(init_index<64 ? init_index*8:512) calls=1',
        'missing_actual_read_run':'condition=off==(read_index<64 ? read_index*8:512) calls=1',
    }
    accepted={}
    for p in OLD.glob('*.wait.json'):
        if p==failure: continue
        w=read(p)
        require(type(w['actual_wait_exit']) is int and w['actual_wait_exit']==w['expected_exit'] and
            not w['timed_out'] and w['error'] is None,'Prior actual child '+str(p))
        log=p.with_name(p.name.replace('.wait.json','.log'))
        require(sha(log)==w['log_sha256'],'Receipt log binding')
        accepted[str(p)]=w
    require(len(accepted)==14,'No replay or omitted predecessor test')
    for name,reason in rejection.items():
        require(read(OLD/(name+'.wait.json'))['actual_wait_exit']==90,'Rejection code')
        require(reason in (OLD/(name+'.log')).read_text(),'Exact first rejection '+name)
    out=HERE/'ubsan_trap01'; out.mkdir(exist_ok=False)
    save(out/'inputs_before.json',inputs)
    try:
        command=read(OLD/'ubsan_compile.command.json')['command'][:]
        require(command[-2]=='-o','Exact prior compile output option')
        command[-1]=str(out/'host_ubsan')
        command.insert(1,'-fsanitize-undefined-trap-on-error')
        run(out/'compile',command)
        run(out/'control_compile',['/usr/bin/cc','-O2','-fsanitize=undefined',
            '-fno-sanitize-recover=all','-fsanitize-undefined-trap-on-error',
            HERE/'ubsan_control.c','-o',out/'ubsan_control'])
        run(out/'control_run',[out/'ubsan_control'],expected=-4)
        target=out/'positive'; target.mkdir()
        run(out/'positive_run',[out/'host_ubsan','0','0',target])
        for p,h in inputs.items(): require(sha(Path(p))==h,'Source changed '+p)
        for p in out.glob('*.wait.json'): accepted[str(p)]=read(p)
        require(len(accepted)==18,'Full original requested coverage plus compile/run UB trap control')
        pins={str(p):sha(p) for p in list(OLD.glob('*.json'))+list(OLD.glob('*.log'))+
            list(OLD.glob('*/*.uart'))+list(out.glob('*.json'))+list(out.glob('*.log'))+
            list(out.glob('*/*.uart'))+[HERE/'ubsan_successor01.py',HERE/'ubsan_control.c',HERE/'ubsan_trap_preflight.command.json',
                HERE/'ubsan_trap_preflight.wait.json',HERE/'ubsan_trap_preflight.log']}
        save(out/'inputs_after.json',inputs)
        save(out/'HOST_COMPOSITE.json',dict(status='ORIGINAL_C_FULL10752_HOST_COMPOSITE_ACCEPTED',
            accepted_receipts=accepted,original_link_failure=dict(path=str(failure),sha256=sha(failure),
                reason='Missing libubsan.so.1.0.0; not a numeric failure. Original rc1 assets retained.'),
            sanitizer='Same GCC undefined instrumentation with trap-on-error, no absent runtime library',
            explicit_UB_control=read(out/'control_run.wait.json'),
            exact_rejections=rejection,input_pins=inputs,evidence_pins=pins,pins_unchanged=True,
            full_calls=10752,original_C_gold_bytes=5526528,original_C_sat=10752,
            source_SB=4416,mask_epochs=336,mask_SB=70644,actual_reads=698880,fresh_stores=698880,
            ordinary_suite_repeated=False,reference=False,DUT=False))
    except Exception as exc:
        save(out/'FIRST_FAILURE.json',dict(status='STOPPED',error=repr(exc))); raise

if __name__=='__main__': main()
