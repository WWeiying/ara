#!/usr/bin/env python3
"""V2: resolve the actual GCC validation symbol; all firmware logic unchanged."""
import argparse
import hashlib
import importlib.util
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
ROWS_RECEIPT='8bcd4e59062b98d086bcf0aa11d30380269b4aa4b6b7695968619037376ca6c5'
ROWS_PINS='8f8775bcccc4bc2da08d14fca7f554d66786fde4337650242453714d8422d2b0'
LLAMA=Path('/home/wangwy/llama/llama.cpp')
TOOLCHAIN=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')


def catalog():
    return json.loads((HERE/'cases.json').read_text())


def capture(b):
    receipt,pins=ROWS/'result.json',ROWS/'source-pins.json'
    require(digest(receipt)==ROWS_RECEIPT and digest(pins)==ROWS_PINS,'Capture receipt/inventory drift')
    record=json.loads(receipt.read_text()); directory=ROWS/'attn_q'
    meta_path=directory/'operator.json'; meta=json.loads(meta_path.read_text())
    require(record['state']=='CAPTURED_NOT_BENCHMARKED' and record['source_pins_match'] and
        record['rows']==8 and record['k']==2048 and meta in record['views'] and
        meta['profile']=='Q4_K' and meta['distinct_rows']==8 and
        meta['activation_shape']==[2048,8] and meta['captured_weight_shape']==[2048,128],
        'Not the reviewed distinct-row full-K Qwen3 capture')
    a,w=directory/'activation_f32.bin',directory/'weight_q4_K.bin'
    require(digest(a)==meta['activation_sha256'] and digest(w)==meta['weight_sha256'],'Capture bytes drift')
    activation,weights=a.read_bytes(),w.read_bytes()
    require(len(activation)==8*2048*4 and len(weights)==128*8*144,'Capture dimensions')
    require(len({activation[i*8192:(i+1)*8192] for i in range(8)})==8,'Repeated activation rows')
    require(all(math.isfinite(v[0]) for v in struct.iter_unpack('<f',activation)),'Nonfinite activation')
    for p in (receipt,pins,meta_path,a,w): b.pin(p)
    return activation,weights,dict(capture=str(directory),metadata=meta,
        selection='First M genuinely distinct prefill rows, first N output channels, full K2048; M1 is not decode')


def audit_x32(original,packed,n):
    require(len(original)==len(packed)==n*8*144,'x32 lengths')
    recovered=bytearray(len(original)); cursor=0
    for group in range(0,n,32):
        for block in range(8):
            for offset,size,width in ((0,2,2),(2,2,2),(4,12,1),(16,128,1)):
                for item in range(0,size,width):
                    for row in range(group,group+32):
                        start=(row*8+block)*144+offset+item
                        recovered[start:start+width]=packed[cursor:cursor+width]; cursor+=width
    require(recovered==original,'x32 C ABI field layout does not recover original bytes')


def macros(case,build_id=None,flags=None):
    values=dict(EVAL_M=case['m'],EVAL_N=case['n'],EVAL_TILE=case['tile'],EVAL_PROFILE=1,EVAL_WB=144,
        EVAL_STORAGE={1:1,4:2,8:3}[case['tile']],EVAL_X32=int(case['backend']=='rvv_x32'),
        EVAL_REUSE={'direct':0,'operation':1,'cross_call':2}[case['reuse']])
    if build_id is not None:
        values.update(EVAL_ID='"'+build_id+'"',EVAL_GOLD_FLAGS=flags)
    return ''.join(f'#define {key} {value}\n' for key,value in values.items())


def prepare(args):
    cat=catalog(); selected=[c for c in cat['cases'] if args.suite=='all' or
        (c['backend']=='native')==(args.suite=='native')]
    if args.case:
        require(set(args.case)<={c['id'] for c in cat['cases']},'Unknown case')
        selected=[c for c in cat['cases'] if c['id'] in args.case]
    out=args.output.resolve()
    require(out.parent==OUT.resolve() and not out.exists() and
        re.fullmatch(r'operator_qbs_reuse_prepare_20261115_[A-Za-z0-9_]+',out.name),'Fresh owned output required')
    out.mkdir(); b=Builder(out)
    for p in sorted(HERE.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts: b.pin(p)
    b.pin(ROOT/'AGENTS.md')
    for origin in json.loads((HERE/'derivation.json').read_text())['sources']:
        p=ROOT/origin['path']; require(digest(p)==origin['sha256'],'Derivation identity drift: '+str(p)); b.pin(p)
    save(out/'prepare-source-pins.json',b.pins)
    b.pin(out/'prepare-source-pins.json')
    sdk,llama=out/'inputs/sdk',out/'inputs/llama'
    b.archive(ROOT,cat['sdk_commit'],['software/qbs','apps/common','verification/qbs/qbs_ref.c',
        'verification/qbs/qbs_ref.h','apps/llama_q4k_repack_bench','apps/llama_q4km_micro',
        'apps/llama_qwen25_real/common/generate_case.py'],sdk)
    b.archive(args.llama,cat['llama_commit'],['ggml/include','ggml/src'],llama)
    patch=sdk/'software/qbs/integrations/llama-decode-sums.patch'
    b.run('registered-llama-patch-present',['git','apply','--no-index','--reverse','--check',patch],cwd=llama)
    for tree in (sdk,llama):
        for p in tree.rglob('*'):
            if p.is_file(): b.pin(p)
    activation,weights,provenance=capture(b)
    host=out/'host'; host.mkdir()
    host_flags=['-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math',
        '-Wall','-Wextra','-Werror','-I'+str(HERE),'-I'+str(sdk/'software/qbs/include'),
        '-I'+str(sdk/'verification/qbs')]
    for src,name in ((sdk/'verification/qbs/qbs_ref.c','reference'),
                     (sdk/'software/qbs/src/qbs_runtime.c','runtime'),(HERE/'verify_test.c','verify_test')):
        b.compile(args.host_cc,host_flags,src,host/(name+'.o'))
    b.run('host-compare-link',[args.host_cc,host/'verify_test.o','-o',host/'verify_test'])
    b.run('host-compare-tests',[host/'verify_test'])
    b.pin(host/'verify_test')
    packer_path=sdk/'apps/llama_qwen25_real/common/generate_case.py'
    spec=importlib.util.spec_from_file_location('reuse_archived_x32_packer',packer_path)
    packer=importlib.util.module_from_spec(spec); spec.loader.exec_module(packer)
    case_data={}; receipts=[]
    for c in selected:
        directory=out/c['id']; directory.mkdir(); data=directory/'data'; data.mkdir()
        hd=host/c['id']; hd.mkdir()
        (hd/'config.h').write_text(macros(c))
        (data/'input_f32.bin').write_bytes(activation[:c['m']*8192])
        (data/'weights_row.bin').write_bytes(weights[:c['n']*8*144])
        b.compile(args.host_cc,host_flags+['-I'+str(hd)],HERE/'oracle.c',hd/'oracle.o')
        b.run('oracle-link-'+c['id'],[args.host_cc,hd/'oracle.o',host/'reference.o',host/'runtime.o','-lm','-o',hd/'oracle'])
        b.pin(hd/'oracle')
        plan=json.loads(b.run('oracle-'+c['id'],[hd/'oracle',data/'input_f32.bin',data/'weights_row.bin',data]))
        require(plan['context_eligible']==int(c['m']==1),'Host full-K context admission differs')
        save(data/'plan.json',plan)
        packer.repack_fields_x32(data/'weights_row.bin',data/'weights_x32.bin',2048,c['n'],256,144,
                                packer.RVV_X32_FIELDS['q4_K'])
        audit_x32((data/'weights_row.bin').read_bytes(),(data/'weights_x32.bin').read_bytes(),c['n'])
        build_id=hashlib.sha256(json.dumps(dict(case=c,sources=b.pins,source_policy=cat),sort_keys=True).encode()).hexdigest()
        (directory/'config.h').write_text(macros(c,build_id,plan['flags']))
        command_header=('typedef struct { unsigned m,n,row,col,layout; } reuse_expected_command_t;\n'
            f'#define EVAL_COMMANDS {len(plan["commands"])}\n'
            'static const reuse_expected_command_t reuse_expected_commands[EVAL_COMMANDS] __attribute__((unused))={\n'+
            ''.join('  {'+','.join(str(cmd[k]) for k in ('m','n','row','col','layout'))+'},\n' for cmd in plan['commands'])+'};\n')
        (directory/'plan_config.h').write_text(command_header)
        active_weight='weights_x32.bin' if c['backend']=='rvv_x32' else 'weights_r4.bin'
        blobs=(('reuse_input','input_f32.bin'),('reuse_weights',active_weight),
               ('reuse_expected_q8','expected_q8.bin'),('reuse_expected_packed','expected_packed.bin'),
               ('reuse_expected','expected.bin'))
        (directory/'data.S').write_text(''.join(f'.section .rodata.{sym},"a"\n.balign 64\n.global {sym}\n{sym}:\n.incbin "{data/name}"\n' for sym,name in blobs))
        case_data[c['id']]=data
        receipts.append(dict(case=c,plan=plan,build_id=build_id,directory=directory))
    n128=next((data for cid,data in case_data.items() if next(c for c in selected if c['id']==cid)['m']==1),None)
    if n128:
        b.compile(args.host_cc,host_flags,HERE/'context_test.c',host/'context_test.o')
        b.run('host-context-link',[args.host_cc,host/'context_test.o',host/'runtime.o',host/'reference.o','-lm','-o',host/'context_test'])
        b.run('host-real-context-tests',[host/'context_test',n128]); b.pin(host/'context_test')
    comparisons=[]
    for lhs in receipts:
        for rhs in receipts:
            a,z=lhs['case'],rhs['case']
            if a['id']<z['id'] and (a['m'],a['n'])==(z['m'],z['n']):
                x,y=case_data[a['id']],case_data[z['id']]
                for name in ('input_f32.bin','expected_q8.bin','expected.bin'):
                    xb,yb=(x/name).read_bytes(),(y/name).read_bytes()
                    require(xb==yb,'Matched schedule/backend golden drift')
                    comparisons.append(dict(lhs=a['id'],rhs=z['id'],artifact=name,bytes_compared=len(xb)))
    save(out/'host-data-checks.json',dict(state='HOST_FULL_DATA_CHECKS_PASS_NOT_EXECUTED',
        pairwise_full_byte_comparisons=comparisons,x32_full_byte_inverse_audited=True,
        rtl_executed=False,provenance=provenance))
    cc=args.toolchain/'riscv64-unknown-elf-gcc'; objdump=args.toolchain/'riscv64-unknown-elf-objdump'
    for name in ('cc1','as','ld'):
        tool=b.run('locate-'+name,[cc,'-print-prog-name='+name]).decode().strip()
        b.pin(Path(tool) if Path(tool).is_file() else shutil.which(tool))
    for name in ('libc.a','libm.a','libgcc.a','libnosys.a'):
        b.pin(b.run('locate-'+name,[cc,'-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-print-file-name='+name]).decode().strip())
    common=sdk/'apps/common'; fw=out/'firmware'; fw.mkdir()
    flags=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax','-O3','-DNDEBUG',
        '-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-ffunction-sections','-fdata-sections',
        '-DNR_LANES=4','-DVLEN=1024','-I'+str(common),'-I'+str(HERE),'-I'+str(sdk/'software/qbs/include'),
        '-I'+str(sdk/'apps/llama_q4k_repack_bench')]
    ggml=llama/'ggml'
    quant_flags=['-I'+str(ggml/p) for p in ('include','src','src/ggml-cpu','src/ggml-cpu/arch/riscv')]
    common_sources=[(common/name,Path(name).stem) for name in
        ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    common_sources += [(sdk/'software/qbs/src/qbs_runtime.c','qbs_runtime'),
                       (ggml/'src/ggml-cpu/arch/riscv/quants.c','quant')]
    if any(c['backend']=='native' for c in selected):
        common_sources.append((sdk/'software/qbs/src/qbs_native_riscv.c','qbs_native'))
    if any(c['backend']=='rvv_x32' for c in selected):
        common_sources.append((sdk/'apps/llama_q4k_repack_bench/repack_kernels.c','x32'))
    common_objects=[]
    for source,name in common_sources:
        extra=quant_flags if name=='quant' else (['-fno-builtin'] if name=='string' else [])
        obj=fw/(name+'.o'); b.compile(cc,flags+extra,source,obj); common_objects.append(obj)
    link=fw/'link.ld'
    b.run('linker-script',[cc,'-E','-P','-x','c','-DALIGNMENT=16',common/'arch.link.ld','-o',link])
    for item in receipts:
        c,d=item['case'],item['directory']; per_flags=flags+['-I'+str(d)]
        for src,name in ((HERE/'main.c','main'),(d/'data.S','data')):
            b.compile(cc,per_flags+['-Wall','-Wextra','-Werror'],src,d/(name+'.o'))
        elf=d/'operator.elf'
        b.run('link-'+c['id'],[cc,*per_flags,'-static','-nostartfiles','-nostdlib',d/'main.o',d/'data.o',
            *common_objects,'-Wl,--gc-sections','-Wl,-Map='+str(d/'link.map'),'-T',link,
            '-Wl,--start-group','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf])
        quant=b.run('quant-'+c['id'],[objdump,'-d','--disassemble=quantize_row_q8_K',elf]).decode()
        require('00a0d073' in quant and all(op in quant for op in ('vle32.v','vse8.v','vwredsum.vs')),
                'Actual quantizer/VCSR=2 lineage missing')
        trial=b.run('trial-'+c['id'],[objdump,'-d','--disassemble=reuse_trial',elf]).decode()
        require(len(re.findall(r'rdcycle\s+zero',trial))==2 and len(re.findall(r'\bfence\b',trial))==1,
                'Commit ROI markers/fence changed')
        require('quantize_row_q8_K' in trial and 'reuse_check_' not in trial,'Quant missing or comparisons inside ROI')
        table=b.run('symbols-'+c['id'],[objdump,'-t',elf]).decode()
        validate_symbols=[]
        for line in table.splitlines():
            match=re.search(r'\bF\s+\.text(?:\.\S+)?\s+[0-9a-f]+\s+(validate(?:\.\S+)?)$',line)
            if match: validate_symbols.append(match[1])
        require(len(validate_symbols)==1,'Missing/ambiguous actual target validation function')
        validate=b.run('validate-'+c['id'],
            [objdump,'-d','--disassemble='+validate_symbols[0],elf]).decode()
        require(all(name in validate for name in ('reuse_check_bytes','reuse_check_output','reuse_check_guard')),
                'Full target comparison calls missing')
        if c['backend']=='rvv_x32':
            symbol='q4k_gemv_32' if c['m']==1 else 'q4k_gemm_32x4'
            dot=b.run('x32-'+c['id'],[objdump,'-d','--disassemble='+symbol,elf]).decode()
            require('vfmacc' in dot and 'vwmacc' in dot and 'vse32' in dot,'Established x32 vector kernel missing')
        for p in d.rglob('*'):
            if p.is_file(): b.pin(p)
        item['elf']=elf
    b.run('python-host-tests',[sys.executable,'-B','-m','unittest','discover','-s',HERE,'-p','test_*.py','-v'])
    for p in (link,out/'host-data-checks.json',out/'host-compare-tests.log',out/'python-host-tests.log',
              out/'commands.json'):
        b.pin(p)
    if n128: b.pin(out/'host-real-context-tests.log')
    verify(b.pins); save(out/'input-pins.json',b.pins)
    outer=dict(b.pins); outer[str(out/'input-pins.json')]=digest(out/'input-pins.json')
    manifest=[]
    for item in receipts:
        c,d,elf=item['case'],item['directory'],item['elf']
        command=[sys.executable,'-B',str(HERE/'check.py'),'--build',str(d),'--log','{log}','--output','{result}']
        record=dict(state='BUILT_NOT_EXECUTED',rtl_executed=False,performance_measured=False,
            case=c,plan=item['plan'],build_id=item['build_id'],elf=str(elf),elf_sha256=digest(elf),
            input_pins=str(out/'input-pins.json'),input_pins_sha256=digest(out/'input-pins.json'),
            sdk_commit=cat['sdk_commit'],llama_commit=cat['llama_commit'],provenance=provenance,
            source_policy='Pinned git archives only, registered llama patch reverse-checked; zero SDK overlays, zero dirty AKV sources',
            validation='Full target element/byte comparisons outside both ROIs, host-mutated comparator; no hashes substitute for numeric checks',
            timing='Two full calls; quant/pack/plan/execute/drain; record-only native callback overhead retained; one final fence; two commit markers per call',
            numerical=dict(native='bit-exact independent qbs_ref',rvv='finite, abs(error)<=0.0002+0.0002*abs(reference)'),
            baseline_kind=c['baseline_kind'],primary_eligible=True,checker=command,reused_old_objects=0)
        save(d/'build.json',record); outer[str(d/'build.json')]=digest(d/'build.json')
        manifest.append(dict(id='qbs_reuse_'+c['id'],category='qbs',elf=str(elf),elf_sha256=digest(elf),
            checker=command,source_pins=str(out/'source-pins.json'),timeout_seconds=10800,
            plusargs=['+QBS_PERF'] if c['backend']=='native' else [],baseline_kind=c['baseline_kind'],primary_eligible=True))
    save(out/'manifest.json',dict(cases=manifest)); outer[str(out/'manifest.json')]=digest(out/'manifest.json')
    save(out/'source-pins.json',outer); verify(outer)
    print(json.dumps(dict(state='BUILT_NOT_EXECUTED',cases=len(manifest),manifest=str(out/'manifest.json'))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--suite',choices=('native','rvv','all'),default='native')
    p.add_argument('--case',action='append')
    p.add_argument('--llama',type=Path,default=LLAMA)
    p.add_argument('--toolchain',type=Path,default=TOOLCHAIN)
    p.add_argument('--host-cc',default='/usr/bin/gcc')
    prepare(p.parse_args())
