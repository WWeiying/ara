#!/usr/bin/env python3
"""Build at most three compact group7 ELFs from archived sources. No RTL execution."""
import argparse
from collections import Counter
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
from contract import HERE,ROOT,OUT,REV,DELIVERY,CC,BASE,NARROW,WIDE,require,save,sha,verify,fnv
import oracle
import generate
import elf as reader

OWN=('contract.py','oracle.py','generate.py','main.c','handoff.c','elf.py','prepare.py','check.py',
     'test_coexist.py','README.md')


def archive(output):
    names=['apps/common','apps/qbs_akv_handoff_smoke/main.c',
        'verification/fpnew_upstream_20261009/oracle.py',
        *['apps/riscv-tests/isa/rv64uv/'+n+'.c' for n in (*NARROW,*WIDE,'vfmacc')],
        *['software/akv/experimental/resident_attention/'+n for n in ('qk.S','pv.S','pv_prepare.S')]]
    raw=subprocess.check_output(['git','-C',str(ROOT),'archive',REV,*names],timeout=60)
    (output/'source.tar').write_bytes(raw);dest=output/'archive';dest.mkdir()
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and
                    '..' not in Path(m.name).parts for m in tar.getmembers()),'Unsafe source archive')
        tar.extractall(dest)
    require(not list(dest.rglob('akv_v2_attention_rvv.S')),'Forbidden native AKV assembly imported')
    return dest


def handoff(output,reference):
    original=output.parent/'archive/apps/qbs_akv_handoff_smoke/main.c'
    text=original.read_text();derivation=[]
    for name,typ,n,label in (('qbs_observed','uint32_t',32,'qbs'),('akv_observed','uint16_t',64,'akv'),
            ('rvv_source','uint32_t',32,'rvv_source'),('rvv_observed','uint32_t',32,'rvv_observed')):
        pattern=r'static '+typ+' '+name+r'\['+str(n)+r'\]\s+__attribute__\(\(aligned\(64\)\)\);'
        matches=list(re.finditer(pattern,text));require(len(matches)==1,'Archived guard adapter anchor: '+name)
        replacement=('static struct __attribute__((aligned(64))) { unsigned char before[64]; '+
            typ+' value['+str(n)+']; unsigned char after[64]; } co_guard_'+label+';\n'+
            '#define '+name+' (co_guard_'+label+'.value)')
        derivation.append(dict(original=matches[0][0],replacement=replacement))
        text=text[:matches[0].start()]+replacement+text[matches[0].end():]
    (output/'archived_handoff.c').write_text(text)
    save(output/'handoff-derivation.json',dict(archive_source=str(original),sha256=sha(original),
        changes=derivation,main_not_called='archived_handoff_main; skip paths discarded by --gc-sections'))
    header=['#ifndef CO_HANDOFF_EXPECTED_H','#define CO_HANDOFF_EXPECTED_H']
    for name,width,values in (('qk',32,reference['qk']),('pv',16,reference['pv'])):
        header.append('static const uint%d_t handoff_%s_gold[%d] = {'%(width,name,len(values))+
                      ','.join('0x%x'%v for v in values)+'};')
    header.append('#endif');(output/'handoff_expected.h').write_text('\n'.join(header)+'\n')
    rows=[];flags=8
    def add(function,gold,width,vl,vtype,extra=0,native=0,qk=0,pv=0):
        nonlocal flags
        initial=flags;flags|=extra
        rows.append(dict(function=function,op=function,sew=width,width=width,gold=gold,
            initial_fcsr=initial,expected_fcsr=flags,expected_vl=vl,expected_vtype=vtype,
            expected_vcsr=5,native_fma_elements=native,qk_elements=qk,pv_elements=pv,
            provenance='Archived handoff data/issues plus explicit bounded Resident/RVV successor'))
    qbs=reference['qbs'];mul=[((0x80000003*0x7ffffffd)&0xffffffff)]*16
    fp=[0x40a00000]*16
    add('co_qbs',qbs,32,32,208)
    add('co_rvv_mul',mul,32,16,16)
    add('co_akv_begin',[0x2400+d for d in range(64)],16,64,200)
    add('co_resident_qk',reference['qk'],32,3,209,reference['qk_flags'],qk=384)
    add('co_rvv_fma',fp,32,16,16,native=16)
    add('co_resident_pv',reference['pv'],16,64,201,reference['pv_flags'],pv=384)
    add('co_rvv_fma',fp,32,16,16,native=16)
    add('co_akv_release',[],8,16,16)
    add('co_qbs',qbs,32,32,208)
    add('co_rvv_mul',mul,32,16,16)
    add('co_adjacent',[0x2200+d for d in range(64)],16,64,200)
    add('co_rvv_fma',fp,32,16,16,native=16)
    add('co_reverse',qbs,32,32,208)
    add('co_rvv_mul',mul,32,16,16)
    return rows


def build(output):
    output=output.absolute()
    require(output==output.resolve() and output.parent==OUT.resolve() and
        re.fullmatch(r'operator_coexist_prepare_20261115_[A-Za-z0-9_.-]+',output.name) and
        not output.exists(),'Fresh owned output required')
    for k in ('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','LIBRARY_PATH','LD_PRELOAD','LD_LIBRARY_PATH',
              'GCC_EXEC_PREFIX','COMPILER_PATH','CFLAGS','LDFLAGS'):
        require(not os.environ.get(k),'Compiler environment injection: '+k)
    output.mkdir();(output/'inputs').mkdir()
    pins={};commands=[]
    env=dict(PATH='/usr/bin:/bin',HOME=str(output),LC_ALL='C',TZ='UTC',PYTHONDONTWRITEBYTECODE='1')
    def pin(p):
        p=Path(p).resolve(strict=True);h=sha(p)
        require(str(p) not in pins or pins[str(p)]==h,'Input changed: '+str(p));pins[str(p)]=h
    def run(label,argv,cwd=output):
        argv=list(map(str,argv));p=subprocess.run(argv,cwd=cwd,env=env,stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,timeout=180)
        (output/(label+'.log')).write_bytes(p.stdout)
        commands.append(dict(label=label,argv=argv,cwd=str(cwd),returncode=p.returncode))
        require(p.returncode==0,'Command failed '+label+': '+p.stdout[-2000:].decode(errors='replace'))
        return p.stdout.decode().strip()
    report=dict(state='FAIL',schema='coexist-firmware-v1',target_executed=False,rtl_executed=False,
        hardware_compiled=False,performance_measured=False,programs={})
    try:
        for n in OWN:
            pin(HERE/n);shutil.copyfile(HERE/n,output/'inputs'/n)
        pin(CC);pin(Path(sys.executable).resolve())
        # Read the fixed current baseline only for ISA admission; the parent
        # independently binds actual same-source image parameters/protocol.
        bp=json.loads((BASE/'source-pins.json').read_text())
        soc=BASE/'source/hardware/src/ara_soc.sv';pkg=BASE/'source/hardware/include/ara_pkg.sv'
        tb=BASE/'source/hardware/tb/ara_tb.sv'
        require(all(bp.get(str(p))==sha(p) for p in (soc,pkg,tb)),'ISA source admission drift')
        require(re.search(r'FPUSupport\s*=\s*FPUSupportHalfSingleDouble',soc.read_text()) and
            not re.search(r'\.FPUSupport\s*\(',tb.read_text()) and
            re.search(r'ELEN\s*=\s*64\s*;',pkg.read_text()),
            'Baseline ISA configuration does not establish FP16/32/64 and ELEN64; preparation rejected')
        for p in (soc,pkg,tb,BASE/'source-pins.json'):pin(p)
        arch=archive(output);common=arch/'apps/common'
        integer=oracle.integer_cases(arch);floating,module=oracle.float_cases(arch)
        pin(module.LIB)
        reference=oracle.handoff_reference(module)
        allrows={'integer':integer,'fma':floating}
        d=output/'handoff';d.mkdir();allrows['handoff']=handoff(d,reference)
        for kind in ('integer','fma'):
            d=output/kind;d.mkdir()
        for kind,rows in allrows.items():
            generate.fixture(output/kind,rows,kind)
            if kind!='handoff':generate.kernels(output/kind,rows)
        link=(common/'arch.link.ld').read_text()
        require(link.count('LENGTH = 0x00100000')==1,'Archived linker capacity changed')
        (output/'link.ld').write_text(link.replace('ALIGNMENT','16'))
        for p in output.rglob('*'):
            if p.is_file():pin(p)
        flags=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax',
            '-O3','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-fno-ipa-cp',
            '-fno-optimize-sibling-calls','-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns',
            '-ffunction-sections','-fdata-sections','-std=gnu11','-Wall','-Wextra','-Wno-unused-function',
            '-DNR_LANES=4','-DVLEN=1024','-I'+str(common)]
        for lib in ('libc.a','libgcc.a','libnosys.a'):
            pin(Path(run('locate-'+lib,[CC,*flags[:2],'-print-file-name='+lib])))
        for tool in ('cc1','as','ld'):pin(Path(run('locate-'+tool,[CC,'-print-prog-name='+tool])))
        def compile_one(label,source,include):
            obj=output/(label+'.o');dep=output/(label+'.d')
            opts=[*flags,'-I'+str(include)]
            run('deps-'+label,[CC,*opts,'-M','-MF',dep,source])
            for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
                path=Path(name).resolve();require(not path.is_relative_to(ROOT/'software') and
                    not path.is_relative_to(ROOT/'apps'),'Live production compiler input');pin(path)
            run('compile-'+label,[CC,*opts,'-c',source,'-o',obj]);return obj
        verify(pins)
        shared=[compile_one('common_'+Path(n).stem,common/n,common) for n in
                ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
        plans=[]
        for kind,rows in allrows.items():
            d=output/kind
            sources=[output/'inputs/main.c',d/'data.S']
            if kind!='handoff':sources.append(d/'kernels.S')
            else:sources.extend([output/'inputs/handoff.c',
                arch/'software/akv/experimental/resident_attention/qk.S',
                arch/'software/akv/experimental/resident_attention/pv.S'])
            objects=[*shared,*[compile_one(kind+'_'+str(i),s,d) for i,s in enumerate(sources)]]
            elf=d/'coexist.elf'
            run('link-'+kind,[CC,*flags[:4],'-static','-nostdlib','-nostartfiles',*objects,
                '-Wl,--gc-sections','-Wl,-Map='+str(d/'link.map'),'-T',output/'link.ld',
                '-Wl,--start-group','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf])
            require(b'SKIP' not in elf.read_bytes(),'Skip-capable archived main survived garbage collection')
            dump=CC.with_name(CC.name.replace('gcc','objdump'));pin(dump)
            text=run('objdump-'+kind,[dump,'-d','-M','no-aliases,numeric',elf])
            symbols,word=reader.read(elf)
            names=Counter(r.get('function','co_kernel_%d'%i) for i,r in enumerate(rows))
            entries={name:dict(symbols[name],count=count,word=word(symbols[name]['address']))
                     for name,count in names.items()}
            tested=[]
            if kind!='handoff':
                tested=[dict(id=i,address=symbols['co_test_%d'%i]['address'],
                             word=word(symbols['co_test_%d'%i]['address'])) for i in range(len(rows))]
            else:
                for name,count in (('akv_experimental_resident_qk',1),('akv_experimental_resident_pv',1)):
                    entries[name]=dict(symbols[name],count=count,word=word(symbols[name]['address']))
            report['programs'][kind]=dict(elf=str(elf),elf_sha256=sha(elf),cases=len(rows),entries=entries,
                tested=tested,fixture=str(d/'fixture.json'),fixture_sha256=sha(d/'fixture.json'))
            plans.append(dict(id='coexist_'+kind,category='resource_coexistence',elf=str(elf),elf_sha256=sha(elf),
                source_pins=str(output/'source-pins.json'),timeout_seconds=1800,
                checker=[str(Path(sys.executable).resolve()),'-B',str(HERE/'check.py'),'--build',str(output),
                    '--kind',kind,'--log','{log}','--vector','{run}/vector.csv','--commit','{run}/commit.csv',
                    '--output','{result}'],plusargs=['+QBS_PERF','+AKV_PERF','+AKV_SUMMARY',
                    '+RESIDENT_QK_PERF','+RESIDENT_PV_PERF','+RESIDENT_PV_WATCHDOG']))
        require(len(report['programs'])==3,'At most three complete ELF contract')
        verify(pins)
        save(output/'commands.json',commands)
        save(output/'source-pins.json',pins)
        save(output/'run-plan.json',dict(cases=plans))
        report.update(state='BUILT_NOT_EXECUTED',source_pins_sha256=sha(output/'source-pins.json'),
            post_pins_match=True,archive_commit=REV,validated_delivery=DELIVERY,dirty_asm_excluded=True,
            imported_native_attention_assembly=False,source_archive_sha256=sha(output/'source.tar'),
            host_reference=dict(integer='Python arbitrary-precision signed/modular arithmetic; checked against archived literal gold',
                floating='Pinned Spike SoftFloat; checked against archived vfmacc literal gold',handoff=reference),
            isa_admission=dict(elen=64,sew=[8,16,32,64],widen_source_sew=[8,16,32],fp=[16,32,64],
                rejected='SEW64->128 widening is outside ELEN64, not emitted or skipped'),
            image_contract='Parent owns same-source all-on/shared_fma_off/other-switch expansion and strict protocol; same ELFs for all images')
    except Exception as exc:report['error']=repr(exc)
    if not (output/'commands.json').exists():save(output/'commands.json',commands)
    report['artifacts']={str(p):sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'build.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=build(a.output)
    print(json.dumps({k:r[k] for k in ('state','error') if k in r}),flush=True)
    return r['state']!='BUILT_NOT_EXECUTED'


if __name__=='__main__':raise SystemExit(main())
