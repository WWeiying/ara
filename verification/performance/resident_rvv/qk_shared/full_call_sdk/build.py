#!/usr/bin/env python3
"""Archive + two reviewed overlays; fresh GNU firmware, never simulation."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import fixture as f

ROOT, OUT = f.ROOT, f.OUT
SDK_COMMIT = '8dc915db8689d801af991676c25b75093bec9a4b'
FROZEN = OUT/'stage3_resident_executor_host_20261110_02/inputs'
OVERLAYS = {
    'software/akv/src/akv_v2_native_riscv.c':
        '78872026dd5377469a0c991564456b8550763ba170999302b5c7b774d35294ee',
    'software/akv/experimental/resident_attention/executor.h':
        '6db8864e09e2c6a6bf003c5bd94b900b7c18bd12a13326f2c8ae3d4c0fbc9016',
}
ASM_SHA = '0e90dccf193c43bcda367fa18813bedb1077e9790795635f9efa993871a20061'
LEAVES = {
    'qk.S':'3def49b4e6a76d32c178363a9ddd31f092a6158253844b771efef13d8f62056f',
    'pv.S':'8f7ff657d608c4d3f71f0b17250936094390c3abdb79717db3a023a3f1426ccf',
    'pv_prepare.S':'8d039dd90da0b00497429be90483d0ed9f3576c1400f458889e9e8cd380968be',
}
OWN = ('main.c','fixture.py','build.py','check.py','test_sdk.py','README.md')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
BUILDER = ROOT/'verification/performance/chain_profile/q6_decode/build.py'
ELF_READER = ROOT/'verification/performance/resident_rvv/qk_shared/qk_boundary/elf.py'


def verify(pins):
    for path,digest in pins.items():
        f.require(f.sha(path) == digest,'Input drift: '+path)


def elf_check(path):
    reader = f.load(ELF_READER,'sdk_elf_reader')
    elf = reader.contract(Path(path).read_bytes())
    required = ('akv_decode_execute','akv_experimental_attention_execute_v2_native',
                'akv_experimental_resident_qk','akv_experimental_resident_pv')
    ranges = {name:reader.extent(elf,name) for name in required}
    f.require(not any(name.startswith('__wrap_') for name in elf['symbols']),
              'Wrapped dispatch forbidden')
    for name,opcode in (('akv_experimental_resident_qk',0x0605705b),
                        ('akv_experimental_resident_pv',0x0485705b)):
        lo,hi = ranges[name]
        f.require(sum(value == opcode for pc,value in elf['words'].items()
                      if lo <= pc < hi) == 1,'Missing/duplicate real leaf opcode')
    return dict(ranges=ranges,wrapped=False)


def build(output):
    output = Path(output).resolve()
    f.require(output.parent == OUT and re.fullmatch(r'stage3_attention_sdk_build_\d{8}_\w+',output.name)
              and not output.exists(),'Fresh owned output required')
    for rel,digest in OVERLAYS.items():
        f.require(f.sha(FROZEN/rel) == digest,'Reviewed SDK overlay changed')
    output.mkdir()
    helper = f.load(BUILDER,'sdk_common_builder')
    builder = helper.Builder(output)
    report = dict(state='FAIL',schema='resident-sdk-three-call-v1',
                  target_executed=False,rtl_executed=False,performance_measured=False)
    try:
        builder.pin(BUILDER)
        builder.pin(ELF_READER)
        for path in (ROOT/'verification/performance/akv_pair_eval/check.py',
                     ROOT/'verification/performance/resident_rvv/qk_shared/full_call/check_work.py',
                     ROOT/'verification/performance/resident_rvv/qk_shared/geometry.py',
                     Path(sys.executable).resolve()):
            builder.pin(path)
        f.require(not any(os.environ.get(name) for name in ('CPATH','C_INCLUDE_PATH',
            'CPLUS_INCLUDE_PATH','LIBRARY_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LD_PRELOAD')),
            'Compiler environment injection forbidden')
        for name in OWN:
            builder.pin(HERE/name)
        builder.pin(ROOT/'verification/performance/akv_pair_eval/build.py')
        inputs = output/'inputs'
        builder.archive(ROOT,SDK_COMMIT,['software/akv','apps/common'],inputs)
        for rel,digest in OVERLAYS.items():
            source,dest = FROZEN/rel,inputs/rel
            builder.pin(source)
            shutil.copyfile(source,dest)
            f.require(f.sha(dest) == digest,'Overlay copy changed')
        sdk,common = inputs/'software/akv',inputs/'apps/common'
        f.require(f.sha(sdk/'src/akv_v2_attention_rvv.S') == ASM_SHA,'Dirty/unreviewed assembly')
        for name,digest in LEAVES.items():
            f.require(f.sha(sdk/'experimental/resident_attention'/name) == digest,'Leaf changed')
        (inputs/'fixture').mkdir()
        for name in OWN:
            shutil.copyfile(HERE/name,inputs/'fixture'/name)
        builder.run('hosttests',[sys.executable,'-B',inputs/'fixture/test_sdk.py','-v'])
        fixture,pins = f.generate(output)
        builder.pins.update(pins)
        for p in inputs.rglob('*'):
            if p.is_file():
                builder.pin(p)
        for p in output.glob('fixture*'):
            builder.pin(p)
        for p in output.glob('*.bin'):
            builder.pin(p)
        builder.pin(output/'data.S')
        linker = (common/'arch.link.ld').read_text()
        f.require(linker.count('LENGTH = 0x00100000') == 1,'Linker drift')
        (output/'link.ld').write_text(linker.replace('ALIGNMENT','16').replace(
            'LENGTH = 0x00100000','LENGTH = 0x01000000'))
        builder.pin(output/'link.ld')
        flags = ['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax',
            '-O3','-DNDEBUG','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize',
            '-ffunction-sections','-fdata-sections','-std=gnu11','-Wall','-Wextra',
            '-Wno-unknown-pragmas','-DNR_LANES=4','-DVLEN=1024','-DAKV_REFILL_OVERLAP=0',
            '-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1','-I'+str(sdk/'include'),
            '-I'+str(sdk/'experimental'),'-I'+str(common),'-I'+str(output)]
        for library in ('libm.a','libc.a','libgcc.a','libnosys.a'):
            path = Path(builder.run('locate-'+library,[CC,*flags[:2],'-print-file-name='+library])
                        .decode().strip()).resolve()
            builder.pin(path)
        for tool in ('cc1','as','ld'):
            path = Path(builder.run('locate-'+tool,[CC,'-print-prog-name='+tool])
                        .decode().strip()).resolve()
            builder.pin(path)
        sources = [inputs/'fixture/main.c',output/'data.S',
            *[common/n for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')],
            *[sdk/'src'/n for n in ('akv_runtime.c','akv_decode.c','akv_features.c',
                'akv_prefill_reference.c','akv_native_riscv.c','akv_v2_native_riscv.c',
                'akv_v2_attention_rvv.S','akv_attention_rvv.S')],
            sdk/'experimental/resident_attention/qk.S',sdk/'experimental/resident_attention/pv.S']
        objects = []
        for index,source in enumerate(sources):
            verify(builder.pins)
            obj = output/('%02d_%s.o' % (index,source.stem))
            extra = ['-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns'] if source.name == 'string.c' else []
            builder.compile(CC,flags+extra,source,obj)
            objects.append(obj)
        elf = output/'attention_sdk.elf'
        builder.run('link',[CC,*flags[:4],'-static','-nostdlib','-nostartfiles',*objects,
            '-Wl,--gc-sections','-Wl,-Map='+str(output/'link.map'),'-T',output/'link.ld',
            '-Wl,--start-group','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf])
        for label,tool,args in (('disassembly','objdump',['-d','-M','no-aliases,numeric']),
                                ('segments','readelf',['-lW'])):
            builder.run(label,[CC.with_name(CC.name[:-3]+tool),*args,elf])
        linked = elf_check(elf)
        f.require(not any('--wrap' in arg for command in builder.commands for arg in command['argv']),
                  'Link wrapper forbidden')
        f.require(all(not Path(p).is_relative_to(ROOT/'software') for p in builder.pins),
                  'Live SDK input forbidden')
        verify(builder.pins)
        (output/'source-pins.json').write_text(json.dumps(builder.pins,indent=2,sort_keys=True)+'\n')
        report.update(state='BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=f.sha(elf),
            sdk_commit=SDK_COMMIT,sdk_overlays=OVERLAYS,archived_native_assembly_sha256=ASM_SHA,
            source_pins_sha256=f.sha(output/'source-pins.json'),post_pins_match=True,
            objects=list(map(str,objects)),elf_contract=linked,fixture=fixture,
            host_tests=15,host_tests_log=str(output/'hosttests.log'),
            cases=list(f.CASES),required_plusargs=['+AKV_PERF','+AKV_SUMMARY',
                '+RESIDENT_QK_PERF','+RESIDENT_PV_PERF','+RESIDENT_PV_WATCHDOG'],
            scope='Three functional SDK calls, same enabled entry requested=0/1; '
                  'OFF timing is NOT a performance baseline; no GGML/default deployment acceptance')
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p):f.sha(p) for p in output.rglob('*') if p.is_file()}
    (output/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = build(args.output)
    print(json.dumps({k:result[k] for k in ('state','error','elf','elf_sha256') if k in result}))
    return int(result['state'] != 'BUILT_NOT_EXECUTED')


if __name__ == '__main__':
    raise SystemExit(main())
