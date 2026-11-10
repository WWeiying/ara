#!/usr/bin/env python3
"""Fresh bounded GNU firmware build against target02. No VCS or RTL build."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('features_full_build_fixture',HERE/'fixture.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
BUILDER=f.ROOT/'verification/performance/chain_profile/q6_decode/build.py'
SUPPORT={
    'elf.py':f.ROOT/'verification/performance/resident_rvv/qk_shared/qk_boundary/elf.py',
    'geometry.py':f.ROOT/'verification/performance/resident_rvv/qk_shared/geometry.py',
    'legacy/check.py':f.ROOT/'verification/performance/akv_pair_eval/check.py',
    'legacy/build.py':f.ROOT/'verification/performance/akv_pair_eval/build.py'}
OWN=('fixture.py','main.c','build.py','check.py','test_full_call.py')


def write(path,value):Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def instruction(parsed,pc):
    word=parsed['words'][pc];return word if word&3==3 else word&65535


def branch_target(pc,w):
    f.require(w&127==0x63 and (w>>12)&7==1 and (w>>15)&31==31 and (w>>20)&31==0,
              'Not the wrapper selection bnez t6')
    offset=((w>>31)&1)<<12|((w>>7)&1)<<11|((w>>25)&63)<<5|((w>>8)&15)<<1
    if offset&4096:offset-=8192
    return pc+offset


def elf_check(path,reader_path):
    reader=f.load(reader_path,'features_elf_reader');raw=Path(path).read_bytes();parsed=reader.contract(raw)
    names=('feature_full_call','feature_terminal_marker','akv_decode_execute',
        'akv_experimental_attention_execute_features_v2_native','akv_experimental_qk_f16_pair_panel4',
        '__wrap_akv_experimental_pv_f16_pair','akv_experimental_resident_qk',
        'akv_experimental_resident_pv','akv_experimental_resident_pv_prepare')
    entries={}
    for name in names:
        lo,hi=reader.extent(parsed,name);entries[name]=dict(pc=lo,end=hi,insn=instruction(parsed,lo))
    wrapper=entries['__wrap_akv_experimental_pv_f16_pair'];branches=[]
    for pc in range(wrapper['pc'],min(wrapper['pc']+24,wrapper['end']),2):
        w=parsed['words'][pc]
        if w&127==0x63 and (w>>12)&7==1 and (w>>15)&31==31 and (w>>20)&31==0:
            branches.append((pc,w))
    f.require(len(branches)==1,'Wrapper branch binding missing/ambiguous')
    pc=branch_target(*branches[0]);f.require(wrapper['pc']<pc<wrapper['end'],'Rotation body branch escapes')
    entries['rotation_body']=dict(pc=pc,end=wrapper['end'],insn=instruction(parsed,pc))
    f.require({n for n in parsed['symbols'] if n.startswith('__wrap_')}=={'__wrap_akv_experimental_pv_f16_pair'},
              'Unexpected dispatch wrapping')
    for name,opcode in (('akv_experimental_qk_f16_pair_panel4',0x0205745b),
                        ('akv_experimental_resident_qk',0x0605705b),('akv_experimental_resident_pv',0x0485705b)):
        r=entries[name]
        f.require(sum(value==opcode for p,value in parsed['words'].items() if r['pc']<=p<r['end'])==1,
                  'Missing/duplicate actual arithmetic opcode')
    address=parsed['symbols']['resident_pv_rotation_selected']['address'];h=struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
    values=[]
    for i in range(h[12]):
        s=struct.unpack_from('<IIQQQQIIQQ',raw,h[6]+h[11]*i)
        if s[1]==1 and s[3]<=address and address+4<=s[3]+s[5]:
            values.append(struct.unpack_from('<I',raw,s[4]+address-s[3])[0])
    f.require(values==[1],'ELF does not select rotating baseline')
    return dict(entries=entries,rotation_selected=1,rotation_selection_branch_pc=branches[0][0],
                actual_resident_opcodes=True,only_pv_baseline_wrapped=True)


def build(output,kind):
    output=Path(output).resolve()
    f.require(output.parent==f.OUT and re.fullmatch(r'stage4_features_full_call_build_[A-Za-z0-9_]+',output.name)
              and not output.exists(),'Fresh owned signoff build output required')
    o,contract,target_pins=f.target();output.mkdir()
    helper=f.load(BUILDER,'features_common_builder');b=helper.Builder(output)
    report=dict(state='FAIL',schema='stage4-features-full-call-v1',kind=kind,sdk_revision=f.SDK,
        target_executed=False,rtl_executed=False,performance_measured=False,scope=f.SCOPE)
    try:
        b.pins.update(target_pins);b.pin(BUILDER);b.pin(Path(sys.executable).resolve())
        inputs=output/'inputs';inputs.mkdir()
        for name in OWN:
            b.pin(HERE/name);shutil.copyfile(HERE/name,inputs/name)
        for name,source in SUPPORT.items():
            dest=inputs/'support'/name;dest.parent.mkdir(parents=True,exist_ok=True)
            b.pin(source);shutil.copyfile(source,dest)
        target=inputs/'target';target.mkdir()
        for name in f.ANCHORS:shutil.copyfile(f.TARGET/name,target/name)
        b.archive(f.ROOT,f.SDK,['software/akv','apps/common',contract['wrapper']],inputs/'sdk')
        sdk=inputs/'sdk/software/akv';common=inputs/'sdk/apps/common'
        for p in sdk.rglob('*'):
            if p.is_file():
                frozen=f.TARGET/'inputs/software/akv'/p.relative_to(sdk)
                f.require(f.sha(p)==f.sha(frozen),'SDK differs from frozen B5 target: '+str(p))
        wrapper=inputs/'sdk'/contract['wrapper']
        f.require(f.sha(wrapper)==contract['wrapper_sha256'],'Unaccepted baseline wrapper')
        fixture=f.generate(output,kind,o);write(output/'fixture.json',fixture)
        for p in inputs.rglob('*'):
            if p.is_file():b.pin(p)
        for n in ('fixture.h','fixture.json','data.S','data.bin'):b.pin(output/n)
        b.run('host-tests',[sys.executable,'-B',inputs/'test_full_call.py','-v'])
        link=(common/'arch.link.ld').read_text()
        f.require(link.count('LENGTH = 0x00100000')==1,'Linker drift')
        (output/'link.ld').write_text(link.replace('ALIGNMENT','16').replace('LENGTH = 0x00100000','LENGTH = 0x01000000'))
        b.pin(output/'link.ld')
        flags=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax',
            '-O3','-DNDEBUG','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize',
            '-ffunction-sections','-fdata-sections','-std=gnu11','-Wall','-Wextra','-Wno-unknown-pragmas',
            '-DNR_LANES=4','-DVLEN=1024',*['-D'+k+'='+str(v) for k,v in contract['macros'].items()],
            '-I'+str(sdk/'include'),'-I'+str(sdk/'experimental'),'-I'+str(common),'-I'+str(output)]
        for name in ('libm.a','libc.a','libgcc.a','libnosys.a','cc1','as','ld'):
            option='-print-file-name=' if name.endswith('.a') else '-print-prog-name='
            value=b.run('locate-'+name,[CC,*flags[:2],option+name]).decode().strip()
            p=Path(shutil.which(value) or value).resolve(strict=True);b.pin(p)
            if name=='libm.a':f.require(f.sha(p)==f.LIBM_SHA,'Not the probed exact GNU newlib')
        sources=[inputs/'main.c',output/'data.S',
            *[common/n for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')],
            *[sdk/'src'/n for n in ('akv_runtime.c','akv_decode.c','akv_features.c','akv_prefill_reference.c',
                'akv_native_riscv.c','akv_v2_native_riscv.c','akv_v2_attention_rvv.S','akv_attention_rvv.S')],
            sdk/'experimental/resident_attention/qk.S',sdk/'experimental/resident_attention/pv.S',wrapper]
        objects=[]
        for i,source in enumerate(sources):
            f.verify(b.pins);obj=output/('%02d_%s.o'%(i,source.stem));objects.append(obj)
            extra=['-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns'] if source.name=='string.c' else []
            b.compile(CC,flags+extra,source,obj)
        elf=output/'attention_features.elf'
        b.run('link',[CC,*flags[:4],'-static','-nostdlib','-nostartfiles',*objects,
            '-Wl,--gc-sections','-Wl,-Map='+str(output/'link.map'),'-T',output/'link.ld',
            *contract['link_flags'],'-Wl,--start-group','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf])
        b.run('disassembly',[CC.with_name(CC.name[:-3]+'objdump'),'-d','-M','no-aliases,numeric',elf])
        binding=elf_check(elf,inputs/'support/elf.py')
        ck=f.load(inputs/'check.py','features_build_checker')
        expected_entries=Counter()
        for tr in fixture['trials']:expected_entries.update(ck.expected_entries(fixture,tr))
        expected_work=dict(calls=len(fixture['trials']),
            output_values=sum(o['cases'][tr['case']]['case']['heads']*o['cases'][tr['case']]['case']['dimension']
                              for tr in fixture['trials']),
            legacy_commands=len(fixture['work']['legacy']),legacy_per_call=fixture['work']['per_call'],
            resident_commands=len(fixture['work']['resident']),actual_entries=dict(expected_entries))
        f.require(not any(Path(p).is_relative_to(f.ROOT/'software') for p in b.pins),'Live SDK compiler input')
        f.verify(b.pins);write(output/'source-pins.json',b.pins)
        check_names=('check.py','fixture.py',*['support/'+n for n in SUPPORT])
        report.update(state='BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=f.sha(elf),
            source_pins_sha256=f.sha(output/'source-pins.json'),post_pins_match=True,
            target_receipt_sha256=f.ANCHORS['result.json'],target_libm_sha256=f.LIBM_SHA,
            elf_contract=binding,expected_work=expected_work,
            checker_dependencies={n:f.sha(inputs/n) for n in check_names},
            query_conversion_outside_roi=True,host_libm_used=False,
            required_plusargs=['+AKV_PERF','+AKV_SUMMARY','+RESIDENT_QK_PERF','+RESIDENT_PV_PERF',
                              '+RESIDENT_PV_WATCHDOG','+COMMIT_TRACE=<path>','+VECTOR_TRACE=<path>'],
            host_test_log=str(output/'host-tests.log'))
    except Exception as exc:report['error']=repr(exc)
    report['artifacts']={str(p):f.sha(p) for p in output.rglob('*') if p.is_file()}
    write(output/'build.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--kind',choices=('perf','functional'),required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=build(a.output,a.kind)
    print(json.dumps({k:v for k,v in result.items() if k!='artifacts'},indent=2))
    raise SystemExit(int(result['state']!='BUILT_NOT_EXECUTED'))
