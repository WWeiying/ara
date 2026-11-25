#!/usr/bin/env python3
"""Archive, prove real D256 numerics, compile one small ELF; never execute RTL."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
sys.dont_write_bytecode=True
from contract import HERE,ROOT,OUT,REV,OLD,CC,ANCHOR,require,save,sha,verify,load,fnv
import oracle
import elf as reader
from expf_audit import audit

OWN=('contract.py','arithmetic.py','oracle.py','elf.py','expf_audit.py','main.c','rvv.c',
     'prepare.py','check.py','test_d256.py','README.md')


def extract(output,revision,names,label):
    raw=subprocess.check_output(['git','-C',str(ROOT),'archive',revision,*names],timeout=60)
    (output/(label+'.tar')).write_bytes(raw);dest=output/label;dest.mkdir()
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and
                    '..' not in Path(m.name).parts for m in tar.getmembers()),'Unsafe archived source')
        tar.extractall(dest)
    return dest


def sources(output):
    arch=extract(output,REV,['software/akv','apps/common','verification/fpnew_upstream_20261009/oracle.py',
        'hardware/scripts/akv/model-generality-manifest.json'],'archive')
    names=('akv_v2_attention_rvv.S','akv_v2_native_riscv.c','akv_online_internal.h')
    old=extract(output,OLD,['software/akv/src/'+n for n in names],'historical-source-only')
    rules={
        'akv_v2_attention_rvv.S':('    .globl  akv_v2_compute_scores_f16_d256_generic','#ifdef AKV_D256_TEST_REFERENCE'),
        'akv_v2_native_riscv.c':('static __attribute__((noinline)) void prepare_d256_online_softmax(','\n#endif'),
    }
    comparisons=[]
    for name in names:
        a=(old/'software/akv/src'/name).read_text();b=(arch/'software/akv/src'/name).read_text()
        if name in rules:
            start,end=rules[name]
            a=a[a.index(start):a.index(end,a.index(start))];b=b[b.index(start):b.index(end,b.index(start))]
        require(a==b,'Historical/current D256 numerical schedule mismatch: '+name)
        comparisons.append(dict(file=name,scope='D256 numerical functions only' if name in rules else 'whole header',
            old_commit=OLD,current_commit=REV,identical=True,sha256=hashlib.sha256(a.encode()).hexdigest()))
    save(output/'compatibility.json',dict(state='NUMERICAL_SOURCE_IDENTICAL_NOT_RTL_ACCEPTED',
        comparisons=comparisons,old_rtl_pass_reused=False))
    return arch


def reference(output,arch):
    data,pins=oracle.capture()
    module=load(arch/'verification/fpnew_upstream_20261009/oracle.py','d256_softfloat')
    result=oracle.reference(data,module.SoftFloat());pins[str(module.LIB)]=sha(module.LIB)
    specification=json.loads((arch/'hardware/scripts/akv/model-generality-manifest.json').read_text())
    model=next(m for m in specification['models'] if m['id']=='gemma3_1b_q4km')
    require(sha(model['model'])==model['expected_sha256'],'Captured model identity differs from archived contract')
    pins[str(Path(model['model']).resolve())]=model['expected_sha256']
    require(result['pv_fmas']==17408 and all(s.get('weight_zero_tokens',0)==0 for s in result['stages']),
            'Real 17KV PV work changed; do not assume skipped weights')
    receipt=dict(model=model['name'],model_sha256=model['expected_sha256'],dimension=256,
        query_heads=4,kv_heads=1,query_head_indices=[0,1,2,3],kv_head_index=0,layer=0,
        tokens=17,capacity=256,scale_bits=0x3f800000,scale_source='Captured exact scale1, NOT 1/sqrt(D)',
        original_atol=0.004,original_rtol=0.002,kv_repetition=False,full_mask_retained=True,
        result=result,source_pins=pins)
    save(output/'reference.json',receipt)
    return data,result,pins,receipt


def fixture(output,data,result):
    assembly=['.section .rodata.d256,"a",@progbits','.balign 64','.global data_guard_before',
        'data_guard_before:','.fill 64,1,0xa5','.global data_begin','data_begin:']
    header=['#ifndef REAL_D256_FIXTURE_H','#define REAL_D256_FIXTURE_H']
    payload=bytearray()
    for role,width in (('query',32),('key',16),('value',16),('mask',16),('model',32),('exact',32)):
        raw=oracle.pack(result['bits'],32) if role=='exact' else data[role]
        path=output/(role+'.bin');path.write_bytes(raw)
        payload+=bytes(-len(payload)%64)+raw
        assembly+=['.balign 64','.global fixture_'+role,'fixture_'+role+':','.incbin '+json.dumps(str(path))]
        typ='float' if role in ('query','model') else 'uint%d_t'%width
        header.append('extern const %s fixture_%s[%d];'%(typ,role,len(raw)//(width//8)))
    assembly+=['.global data_end','data_end:','.global data_guard_after','data_guard_after:',
        '.fill 64,1,0xa5','.section .note.GNU-stack,"",@progbits']
    values=dict(EXPECT_FCSR=result['expected_fcsr'],QUERY_HASH=fnv(bytes.fromhex(result['query_half'])),
                OUTPUT_HASH=result['output_hash'],DATA_BYTES=len(payload),DATA_HASH=fnv(payload))
    header+=['#define D256_SCALE 0x1p0f',*['#define D256_%s UINT64_C(0x%x)'%v for v in values.items()],'#endif']
    (output/'fixture.h').write_text('\n'.join(header)+'\n');(output/'data.S').write_text('\n'.join(assembly)+'\n')
    return dict(data_bytes=len(payload),data_hash=fnv(payload),query_hash=values['QUERY_HASH'])


def build(output):
    output=output.absolute()
    require(output==output.resolve() and output.parent==OUT.resolve() and
        re.fullmatch(r'operator_d256_prepare_20261115_[A-Za-z0-9_.-]+',output.name) and not output.exists(),
        'Fresh owned D256 output required')
    for key in ('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','LIBRARY_PATH','LD_PRELOAD','LD_LIBRARY_PATH',
                'GCC_EXEC_PREFIX','COMPILER_PATH','CFLAGS','LDFLAGS'):
        require(not os.environ.get(key),'Compiler environment injection: '+key)
    output.mkdir();inputs=output/'inputs';inputs.mkdir();pins={};commands=[]
    report=dict(state='FAIL',schema='real-d256-firmware-v1',target_executed=False,rtl_executed=False,
        performance_measured=False,hardware_compiled=False,old_rtl_pass_reused=False)
    env=dict(PATH='/usr/bin:/bin',HOME=str(output),LC_ALL='C',TZ='UTC',PYTHONDONTWRITEBYTECODE='1')
    def pin(p):
        p=Path(p).resolve(strict=True);h=sha(p)
        require(str(p) not in pins or pins[str(p)]==h,'Input changed: '+str(p));pins[str(p)]=h
    def run(label,argv):
        argv=list(map(str,argv));p=subprocess.run(argv,cwd=output,env=env,stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,timeout=180)
        (output/(label+'.log')).write_bytes(p.stdout)
        commands.append(dict(label=label,argv=argv,returncode=p.returncode))
        require(p.returncode==0,'Command failed '+label+': '+p.stdout[-2000:].decode(errors='replace'))
        return p.stdout.decode().strip()
    try:
        for n in OWN:pin(HERE/n);shutil.copyfile(HERE/n,inputs/n)
        arch=sources(output);data,result,refpins,receipt=reference(output,arch);pins.update(refpins)
        memory=fixture(inputs,data,result)
        sdk=arch/'software/akv';common=arch/'apps/common'
        link=(common/'arch.link.ld').read_text();require(link.count('LENGTH = 0x00100000')==1,'Linker template drift')
        (inputs/'link.ld').write_text(link.replace('ALIGNMENT','16'))
        for p in output.rglob('*'):
            if p.is_file():pin(p)
        for p in (CC,Path(sys.executable).resolve(),ANCHOR/'objdump.log',ANCHOR/'attention.elf'):pin(p)
        flags=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax','-O3',
            '-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-fno-ipa-cp',
            '-fno-optimize-sibling-calls','-ffunction-sections','-fdata-sections',
            '-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns','-std=gnu11',
            '-Wall','-Wextra','-Wno-unknown-pragmas','-DNR_LANES=4','-DVLEN=1024',
            '-DAKV_REFILL_OVERLAP=0','-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=0',
            '-I'+str(sdk/'include'),'-I'+str(sdk/'src'),'-I'+str(common),'-I'+str(inputs)]
        for name in ('libm.a','libc.a','libgcc.a','libnosys.a'):
            pin(Path(run('locate-'+name,[CC,*flags[:2],'-print-file-name='+name])))
        for tool in ('cc1','as','ld'):pin(Path(run('locate-'+tool,[CC,'-print-prog-name='+tool])))
        srcs=[inputs/'main.c',inputs/'rvv.c',inputs/'data.S',
            *[common/n for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')],
            *[sdk/'src'/n for n in ('akv_runtime.c','akv_decode.c','akv_features.c','akv_prefill_reference.c',
                'akv_native_riscv.c','akv_v2_attention_rvv.S','akv_attention_rvv.S')]]
        objects=[];verify(pins)
        for i,source in enumerate(srcs):
            dep=output/('%02d.d'%i);obj=output/('%02d_%s.o'%(i,source.stem))
            run('deps-%02d'%i,[CC,*flags,'-M','-MF',dep,source])
            for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
                path=Path(name).resolve();require(not path.is_relative_to(ROOT/'software') and
                    not path.is_relative_to(ROOT/'apps'),'Live SDK/compiler input');pin(path)
            run('compile-%02d'%i,[CC,*flags,'-c',source,'-o',obj]);objects.append(obj)
        image=output/'d256.elf'
        run('link',[CC,*flags[:4],'-static','-nostdlib','-nostartfiles',*objects,'-Wl,--gc-sections',
            '-Wl,-Map='+str(output/'link.map'),'-T',inputs/'link.ld','-Wl,--start-group',
            '-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',image])
        dump=CC.with_name(CC.name.replace('gcc','objdump'));pin(dump)
        run('objdump',[dump,'-d','-M','no-aliases,numeric',image])
        symbols,mem=reader.read(image)
        names=dict(d256_full_call=2,akv_device_query=2,akv_decode_execute=2,
            d256_memory_group=1,d256_memory_pack=1,d256_memory_qk=1,d256_memory_pv=1,
            akv_attention_execute_v2_native_auto=1,execute_segmented_d256=1,
            akv_v2_compute_scores_f16_d256_panel4=1,akv_v2_update_outputs_f16_d256_online=1,
            prepare_d256_online_softmax=2,store_outputs=2)
        entries={name:dict(symbols[name],count=count,word=int.from_bytes(mem(symbols[name]['address'],4),'little'))
                 for name,count in names.items()}
        exp_contract=audit(output);verify(pins)
        save(output/'commands.json',commands);save(output/'source-pins.json',pins)
        save(output/'run-plan.json',dict(cases=[dict(id='gemma3_d256_h4_kv17_segmented_memory',
            category='attention_boundary',elf=str(image),elf_sha256=sha(image),
            source_pins=str(output/'source-pins.json'),timeout_seconds=10800,
            checker=[str(Path(sys.executable).resolve()),'-B',str(HERE/'check.py'),'--build',str(output),
                '--log','{log}','--vector','{run}/vector.csv','--commit','{run}/commit.csv','--output','{result}'],
            plusargs=['+AKV_PERF','+AKV_SUMMARY'])]))
        report.update(state='BUILT_NOT_EXECUTED',sdk_commit=REV,source_pins_sha256=sha(output/'source-pins.json'),
            elf=str(image),elf_sha256=sha(image),post_pins_match=True,entries=entries,reference=receipt,memory=memory,
            scalar_expf_audit=exp_contract,archive_native_assembly_sha256=sha(sdk/'src/akv_v2_attention_rvv.S'),
            dirty_asm_excluded=True,modes=['same_schedule_memory_rvv','current_sdk_segmented_akv'],
            primary_speedup_eligible=False,scope='Real D256 numerical/shape/path boundary only; no Resident or old RTL acceptance')
    except Exception as exc:report['error']=repr(exc)
    if not (output/'commands.json').exists():save(output/'commands.json',commands)
    report['artifacts']={str(p):sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'build.json',report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=build(a.output);print(json.dumps({k:r[k] for k in ('state','error','elf','elf_sha256') if k in r}),flush=True)
    return r['state']!='BUILT_NOT_EXECUTED'


if __name__=='__main__':raise SystemExit(main())
