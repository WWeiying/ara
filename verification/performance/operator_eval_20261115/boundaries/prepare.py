#!/usr/bin/env python3
"""Build only two real QBS tail/segmentation boundary ELFs; no RTL launch."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import sys
sys.dont_write_bytecode=True
from build_support import Builder,digest,require,save,verify
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
ROWS=OUT/'stage2_qwen3_rows8_20261109_02'
LLAMA=Path('/home/wangwy/llama/llama.cpp')
TOOLCHAIN=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')

def catalog(): return json.loads((HERE/'cases.json').read_text())

def capture(b):
    receipt,pins=ROWS/'result.json',ROWS/'source-pins.json'
    require(digest(receipt)=='8bcd4e59062b98d086bcf0aa11d30380269b4aa4b6b7695968619037376ca6c5' and
        digest(pins)=='8f8775bcccc4bc2da08d14fca7f554d66786fde4337650242453714d8422d2b0','Capture inventory drift')
    record=json.loads(receipt.read_text()); directory=ROWS/'attn_q'
    meta_path=directory/'operator.json'; meta=json.loads(meta_path.read_text())
    require(record['state']=='CAPTURED_NOT_BENCHMARKED' and record['source_pins_match'] and
        record['rows']==8 and record['k']==2048 and meta in record['views'] and
        meta['activation_shape']==[2048,8] and meta['captured_weight_shape']==[2048,128] and
        meta['profile']=='Q4_K' and meta['distinct_rows']==8,'Wrong real capture scope')
    a,w=directory/'activation_f32.bin',directory/'weight_q4_K.bin'
    require(digest(a)==meta['activation_sha256'] and digest(w)==meta['weight_sha256'],'Capture changed')
    activation,weights=a.read_bytes(),w.read_bytes()
    require(len(activation)==8*8192 and len(weights)==128*8*144 and
        len({activation[i*8192:(i+1)*8192] for i in range(8)})==8 and
        all(math.isfinite(x[0]) for x in struct.iter_unpack('<f',activation)),'Capture bytes/rows')
    for p in (receipt,pins,meta_path,a,w): b.pin(p)
    return activation,weights,dict(source=str(directory),metadata=meta,selection='First M distinct prefill rows, N35; full K2048, no quantization-format conversion')

def prepare(a):
    cat=catalog(); out=a.output.resolve()
    require(out.parent==OUT.resolve() and not out.exists() and
        re.fullmatch(r'operator_boundaries_prepare_20261115_[A-Za-z0-9_]+',out.name),'Fresh owned output required')
    out.mkdir(); b=Builder(out)
    for p in HERE.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts: b.pin(p)
    b.pin(ROOT/'AGENTS.md')
    for origin in json.loads((HERE/'derivation.json').read_text())['sources']:
        path=ROOT/origin['path']; require(digest(path)==origin['sha256'],'Derivation drift'); b.pin(path)
    save(out/'prepare-source-pins.json',b.pins); b.pin(out/'prepare-source-pins.json')
    sdk,llama=out/'inputs/sdk',out/'inputs/llama'
    b.archive(ROOT,cat['sdk_commit'],['software/qbs','apps/common','verification/qbs/qbs_ref.c','verification/qbs/qbs_ref.h'],sdk)
    b.archive(a.llama,cat['llama_commit'],['ggml/include','ggml/src'],llama)
    b.run('registered-quant-patch',['git','apply','--no-index','--reverse','--check',sdk/'software/qbs/integrations/llama-decode-sums.patch'],cwd=llama)
    for tree in (sdk,llama):
        for path in tree.rglob('*'):
            if path.is_file(): b.pin(path)
    activation,weights,provenance=capture(b)
    gap=dict(cat['d256'])
    gemma=Path(gap['capture'])
    for path in (gemma/'replay/cases/operator/decode/attention_core/case.json',gemma/'decode/block/attention_params-0.json',
        ROOT/'verification/performance/operator_eval_20261115/attention_real/capture.py',
        ROOT/'verification/performance/operator_eval_20261115/attention_real/oracle.py'):
        b.pin(path)
    gap['evidence_pins']={p:h for p,h in b.pins.items() if 'gemma3-1b-' in p or '/attention_real/' in p}
    save(out/'d256-gap.json',gap); b.pin(out/'d256-gap.json')
    host=out/'host'; host.mkdir()
    hf=['-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math','-Wall','-Wextra','-Werror',
        '-I'+str(HERE),'-I'+str(sdk/'software/qbs/include'),'-I'+str(sdk/'verification/qbs')]
    for source,name in ((sdk/'verification/qbs/qbs_ref.c','reference'),(sdk/'software/qbs/src/qbs_runtime.c','runtime'),
                         (HERE/'verify_test.c','verify_test')):
        b.compile(a.host_cc,hf,source,host/(name+'.o'))
    b.run('host-comparator-link',[a.host_cc,host/'verify_test.o','-o',host/'verify_test'])
    b.run('host-comparator-tests',[host/'verify_test']); b.pin(host/'verify_test')
    items=[]
    for c in cat['cases']:
        d=out/c['id']; d.mkdir(); data=d/'data'; data.mkdir(); hd=host/c['id']; hd.mkdir()
        (hd/'config.h').write_text(f'#define E_M {c["m"]}\n#define E_SEG {c["segment"]}\n')
        (data/'input.bin').write_bytes(activation[:c['m']*8192]); (data/'weight_row.bin').write_bytes(weights[:35*8*144])
        b.compile(a.host_cc,hf+['-I'+str(hd)],HERE/'oracle.c',hd/'oracle.o')
        b.run('oracle-link-'+c['id'],[a.host_cc,hd/'oracle.o',host/'reference.o',host/'runtime.o','-lm','-o',hd/'oracle'])
        b.pin(hd/'oracle')
        plan=json.loads(b.run('oracle-'+c['id'],[hd/'oracle',data/'input.bin',data/'weight_row.bin',data]))
        require(len(plan['commands'])==(6 if c['segment'] else 2) and plan['sdk_host_calls']==2 and
            plan['rejected_executor_calls']==0,'Wrong host boundary coverage')
        save(data/'plan.json',plan)
        build_id=hashlib.sha256(json.dumps(dict(case=c,sources=b.pins,sdk=cat['sdk_commit']),sort_keys=True).encode()).hexdigest()
        values=dict(E_M=c['m'],E_SEG=c['segment'],E_WS=plan['workspace_bytes'],E_SNAP=plan['snapshot_bytes'],
                    E_COMMANDS=len(plan['commands']),E_FLAGS=plan['flags'],E_ID='"'+build_id+'"')
        (d/'config.h').write_text(''.join(f'#define {k} {v}\n' for k,v in values.items()))
        (d/'plan_config.h').write_text('typedef struct { unsigned m,n,kb,k0,col,wo,snapshot,snapshot_bytes; } boundary_command_t;\n'
            'static const boundary_command_t boundary_commands[E_COMMANDS]={\n'+''.join(
            '  {'+','.join(str(cmd[k]) for k in ('m','n','kb','k0','col','wo','snapshot','snapshot_bytes'))+'},\n'
            for cmd in plan['commands'])+'};\n')
        blobs=(('boundary_input','input.bin'),('boundary_weights','weights.bin'),('boundary_q8','q8.bin'),
               ('boundary_expected','expected.bin'),('boundary_ws','workspace.bin'),('boundary_acts','activations.bin'))
        (d/'data.S').write_text(''.join(f'.section .rodata.{sym},"a"\n.balign 64\n.global {sym}\n{sym}:\n.incbin "{data/name}"\n' for sym,name in blobs))
        items.append(dict(case=c,plan=plan,build_id=build_id,directory=d))
    fw=out/'firmware'; fw.mkdir(); common=sdk/'apps/common'; cc=a.toolchain/'riscv64-unknown-elf-gcc'
    objdump=a.toolchain/'riscv64-unknown-elf-objdump'
    for name in ('cc1','as','ld'):
        tool=b.run('locate-'+name,[cc,'-print-prog-name='+name]).decode().strip(); b.pin(Path(tool) if Path(tool).is_file() else shutil.which(tool))
    for name in ('libc.a','libm.a','libgcc.a','libnosys.a'):
        b.pin(b.run('locate-'+name,[cc,'-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-print-file-name='+name]).decode().strip())
    flags=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax','-O3','-DNDEBUG',
        '-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-ffunction-sections','-fdata-sections',
        '-DNR_LANES=4','-DVLEN=1024','-I'+str(common),'-I'+str(HERE),'-I'+str(sdk/'software/qbs/include')]
    ggml=llama/'ggml'; qf=['-I'+str(ggml/p) for p in ('include','src','src/ggml-cpu','src/ggml-cpu/arch/riscv')]
    sources=[(common/name,Path(name).stem) for name in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    sources += [(sdk/'software/qbs/src/qbs_runtime.c','qbs_runtime'),(sdk/'software/qbs/src/qbs_native_riscv.c','native'),
                (ggml/'src/ggml-cpu/arch/riscv/quants.c','quant')]
    objects=[]
    for source,name in sources:
        extra=qf if name=='quant' else (['-fno-builtin'] if name=='string' else [])
        obj=fw/(name+'.o'); b.compile(cc,flags+extra,source,obj); objects.append(obj)
    link=fw/'link.ld'; b.run('linker-script',[cc,'-E','-P','-x','c','-DALIGNMENT=16',common/'arch.link.ld','-o',link])
    for item in items:
        c,d=item['case'],item['directory']; cf=flags+['-I'+str(d),'-Wall','-Wextra','-Werror']
        for source,name in ((HERE/'main.c','main'),(d/'data.S','data')): b.compile(cc,cf,source,d/(name+'.o'))
        elf=d/'operator.elf'
        b.run('link-'+c['id'],[cc,*cf,'-static','-nostartfiles','-nostdlib',d/'main.o',d/'data.o',*objects,
            '-Wl,--gc-sections','-Wl,-Map='+str(d/'link.map'),'-T',link,'-Wl,--start-group','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf])
        trial=b.run('trial-'+c['id'],[objdump,'-d','--disassemble=boundary_trial',elf]).decode()
        require('quantize_row_q8_K' in trial and 'reuse_check_' not in trial and
            len(re.findall(r'rdcycle\s+zero',trial))==2 and len(re.findall(r'\bfence\b',trial))==1,'ROI/call contract drift')
        validation=b.run('validation-'+c['id'],[objdump,'-d','--disassemble=validate',elf]).decode()
        require(all(f in validation for f in ('reuse_check_bytes','reuse_check_output','reuse_check_guard')),'Full target checks absent')
        quant=b.run('quant-'+c['id'],[objdump,'-d','--disassemble=quantize_row_q8_K',elf]).decode()
        native=b.run('native-'+c['id'],[objdump,'-d','--disassemble=qbs_native_execute_command',elf]).decode()
        require('00a0d073' in quant and 'vwredsum.vs' in quant and
            ('02b5045b' if c['m']==2 else '04b5045b') in native,'Actual quantizer/native M2/M3 path missing')
        for p in d.rglob('*'):
            if p.is_file(): b.pin(p)
        item['elf']=elf
    b.run('python-host-tests',[sys.executable,'-B','-m','unittest','discover','-s',HERE,'-p','test_*.py','-v'])
    for p in (out/'commands.json',out/'python-host-tests.log',out/'host-comparator-tests.log',link): b.pin(p)
    verify(b.pins); save(out/'input-pins.json',b.pins)
    outer=dict(b.pins); outer[str(out/'input-pins.json')]=digest(out/'input-pins.json'); manifest=[]
    for item in items:
        c,d,elf=item['case'],item['directory'],item['elf']
        checker=[sys.executable,'-B',str(HERE/'check.py'),'--build',str(d),'--log','{log}','--output','{result}']
        save(d/'build.json',dict(state='BUILT_NOT_EXECUTED',rtl_executed=False,performance_measured=False,
            case=c,plan=item['plan'],build_id=item['build_id'],elf=str(elf),elf_sha256=digest(elf),
            input_pins=str(out/'input-pins.json'),input_pins_sha256=digest(out/'input-pins.json'),
            sdk_commit=cat['sdk_commit'],llama_commit=cat['llama_commit'],provenance=provenance,
            source_policy='Git archive only; registered quant patch reverse checked; no overlays or dirty AKV assembly',
            numeric='Independent ordered qbs_ref partials plus exact RNE FP32 SDK split-K add schedule; full bits and workspace checked',
            scope='M2/M3 + N-tail and explicit full-K software segmentation, not K beyond hardware maximum or full model',
            timing='Two calls, quant/pack/plan/execute/drain; snapshot-only callback overhead charged; full comparison/rejection outside ROI',checker=checker))
        outer[str(d/'build.json')]=digest(d/'build.json')
        manifest.append(dict(id='boundaries_'+c['id'],category='qbs',elf=str(elf),elf_sha256=digest(elf),
            source_pins=str(out/'source-pins.json'),checker=checker,timeout_seconds=10800,plusargs=['+QBS_PERF']))
    save(out/'manifest.json',dict(cases=manifest)); outer[str(out/'manifest.json')]=digest(out/'manifest.json')
    save(out/'source-pins.json',outer); verify(outer)
    print(json.dumps(dict(state='BUILT_NOT_EXECUTED',elf_count=2,manifest=str(out/'manifest.json'),d256_gap=str(out/'d256-gap.json'))))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--llama',type=Path,default=LLAMA); p.add_argument('--toolchain',type=Path,default=TOOLCHAIN)
    p.add_argument('--host-cc',default='/usr/bin/gcc'); prepare(p.parse_args())
