"""One independent original-C Host campaign; no target compiler/reference/DUT."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
GEN=ROOT/'generated01'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def save(p,d):
    with p.open('x') as f: json.dump(d,f,indent=2); f.write('\n')
def require(c,s):
    if not c: raise ValueError(s)
def run(stem,args,expected=0):
    rc=subprocess.run([sys.executable,str(HERE/'run_bound.py'),'--stem',str(stem),
        '--timeout','120','--expected',str(expected),'--',*map(str,args)],check=False).returncode
    require(rc==0,'Bounded Host child failed: '+str(stem))

def static_source_gate():
    status=read(ROOT/'SOURCE_STATUS.json')
    for n,h in status['source_files'].items(): require(sha(ROOT/n)==h,'Sealed source drift '+n)
    generation=read(GEN/'GENERATED.json')
    require(generation['status']=='SOURCE_GENERATED_UNTESTED_NO_COMPILE_REFERENCE_DUT','Generation status')
    for p,h in generation['input_pins'].items(): require(sha(Path(p))==h,'Generation input '+p)
    for p,h in generation['artifacts'].items(): require(sha(Path(p))==h,'Generation artifact '+p)
    original=(ROOT.parent/'recovery01/successor_oracle.c').read_text()
    ported=(GEN/'original_port.c').read_text()
    first='#if !defined(INTEGER_MACC_SUITE) && !defined(INTEGER_CARRY_SUITE)'
    require(original[original.index(first):original.index('void probe_main(void)')]==
            ported[ported.index(first):ported.index('int fixed_full_main(void)')],
            'Original signed_word/selected/rounded/extra_value/failure byte identity')
    wrapper=(HERE/'original_wrapper.c').read_text()
    cleaned=re.sub(r"source_note\('[abzm]',[^;]+\);",'',wrapper)
    seed=original[original.index('        uint64_t random='):original.index('#ifdef FIXED_SCALAR_SUITE',original.index('        uint64_t random='))]
    require(seed in cleaned,'Original RNG/override statements unchanged after removing event recording')
    mask=('                for(unsigned i=0;i<128;++i)mask[i]=0;\n'
          '                for(unsigned i=0;i<cap;++i)\n'
          '                    if(selected(mode,i))mask[i/8]|=1u<<(i%8);')
    cleaned=cleaned.replace('{mask[i]=0;}','mask[i]=0;').replace('{mask[i/8]|=1u<<(i%8);}','mask[i/8]|=1u<<(i%8);')
    require(mask in original and mask in cleaned,'Original mask loop plus after-store recording only')
    require('#define __builtin_memcpy host_copy' in (HERE/'packed_wrapper.c').read_text(), 'Actual packed operation interception')
    admission=ROOT.parent/'full10752_numeric_admission01.json'
    require(read(admission)['source_review_sha256']=='5112e80f98a9dff638e1012662ee4e1f79617eb49d3b6fc75bfaee2349b622e9','Admission')
    pins={str(p):sha(p) for p in [admission,ROOT/'SOURCE_STATUS.json',GEN/'GENERATED.json',
        HERE/'host_api.h',HERE/'host.c',HERE/'original_wrapper.c',HERE/'packed_wrapper.c',HERE/'host_stage.py',HERE/'run_bound.py']}
    pins.update(generation['input_pins']); pins.update(generation['artifacts'])
    return pins

def main():
    out=HERE/'host01'; out.mkdir(exist_ok=False)
    try:
        pins=static_source_gate(); save(out/'inputs_before.json',pins)
        flags=['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror','-DSEW=8','-DFRACTIONAL_SUITE=1',
               '-I'+str(GEN),'-I'+str(HERE)]
        sources=[HERE/'host.c',HERE/'original_wrapper.c',HERE/'packed_wrapper.c']
        run(out/'compile',flags+list(map(str,sources))+['-o',str(out/'host')])
        positive=out/'positive'; positive.mkdir()
        run(out/'positive_run',[out/'host','0','0',positive])
        for mutation,name in enumerate(('first','middle','last','front_guard','rear_guard','vstart_full32','sat_full32','mixed_first20'),1):
            dest=out/name; dest.mkdir()
            run(out/(name+'_run'),[out/'host',str(mutation),'0',dest])
        for mutation,name in enumerate(('missing_same_value_source','missing_mask_SB','missing_same_value_init','missing_actual_read'),1):
            dest=out/name; dest.mkdir()
            run(out/(name+'_run'),[out/'host','0',str(mutation),dest],expected=90)
        run(out/'ubsan_compile',flags+['-fsanitize=undefined','-fno-sanitize-recover=all']+
            list(map(str,sources))+['-o',str(out/'host_ubsan')])
        dest=out/'ubsan'; dest.mkdir()
        run(out/'ubsan_run',[out/'host_ubsan','0','0',dest])
        for p,h in pins.items(): require(sha(Path(p))==h,'Input changed '+p)
        save(out/'inputs_after.json',pins)
        receipts={str(p):read(p) for p in out.glob('*.wait.json')}
        require(len(receipts)==16,'Two Host compiles, ten positive/diagnostic runs, four rejection runs')
        save(out/'complete.json',dict(status='ORIGINAL_C_FULL10752_HOST_ACCEPTED_NOT_REFERENCE_OR_DUT',
            receipts=receipts,pins_unchanged=True,full_calls=10752,bytes_per_call=514,
            independent_original_C_oracle=True,Python_expected_supplies_helper=False,
            diagnostics_compared='Whole UART and all checks/elements/errors, mixed35 errors with first20 print limit',
            source_SB=4416,mask_epochs=336,mask_SB=70644,actual_reads=698880,fresh_stores=698880))
    except Exception as exc:
        save(out/'FIRST_FAILURE.json',dict(status='STOPPED',error=repr(exc))); raise

if __name__=='__main__': main()
