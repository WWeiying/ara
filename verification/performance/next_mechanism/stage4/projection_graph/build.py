#!/usr/bin/env python3
"""Explicit frozen-candidate preparation and software-only GNU build. No VCS."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
_spec=importlib.util.spec_from_file_location('stage4_chain_build_contract',HERE/'contract.py')
c=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(c)

OWN=('contract.py','build.py','check.py','main.cpp','producer.cpp','oracle.c','test_projection.py','README.md')
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
CXX=CC.with_name(CC.name[:-3]+'g++')
BUILDER=c.ROOT/'verification/performance/chain_profile/q6_decode/build.py'
ENV=dict(PATH='/usr/bin:/bin',HOME='/home/wangwy',LC_ALL='C',PYTHONDONTWRITEBYTECODE='1')


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def out_path(path):
    path=Path(path).resolve()
    c.require(path.parent==c.OUT and re.fullmatch(r'stage4_projection_chain_[a-zA-Z0-9_]+',path.name),
              'Fresh direct signoff stage4_projection_chain_* output required')
    return path


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def located_path(name):
    return Path(shutil.which(name,path=ENV['PATH']) or name).resolve(strict=True)


def frozen_candidate(header,digest,receipt,receipt_sha):
    header,receipt=Path(header).resolve(strict=True),Path(receipt).resolve(strict=True)
    c.require(header.is_relative_to(c.OUT) and receipt.is_relative_to(c.OUT),
              'Only explicit frozen OUT snapshots, never the active ROOT helper')
    c.require(re.fullmatch('[0-9a-f]{64}',digest) and re.fullmatch('[0-9a-f]{64}',receipt_sha),
              'Explicit reviewed candidate/receipt SHAs required')
    c.require(c.sha(receipt)==receipt_sha,'Candidate freeze receipt identity')
    gate=json.loads(receipt.read_text())
    c.require(gate.get('state')=='PASS' and gate.get('post_pins_match') is True and
              gate.get('baseline_llama')==c.LLAMA_COMMIT and gate.get('sdk')==c.SDK_COMMIT,
              'Candidate correctness gate is not the reviewed terminal PASS')
    c.require(c.sha(header)==digest,'Candidate header identity')
    return {str(header):digest,str(receipt):receipt_sha}


def prepare(output,header,digest,receipt,receipt_sha):
    output=out_path(output)
    c.require(not output.exists(),'Preserve every previous output')
    candidate_pins=frozen_candidate(header,digest,receipt,receipt_sha)
    pins=c.data_contract()
    original_pins=dict(pins)
    pins.update(candidate_pins)
    output.mkdir();inputs=output/'inputs';inputs.mkdir()
    helper=module(BUILDER,'stage4_archive_builder');builder=helper.Builder(output)
    builder.pins.update(pins);builder.pin(BUILDER)
    for name in OWN:
        source=HERE/name;builder.pin(source);shutil.copyfile(source,inputs/name);builder.pin(inputs/name)
    c.require(c.sha(c.ELF_READER)==c.ELF_READER_SHA,'Frozen ELF reader changed')
    builder.pin(c.ELF_READER);shutil.copyfile(c.ELF_READER,inputs/'elf_reader.py')
    builder.archive(c.ROOT,c.SDK_COMMIT,['software/qbs','apps/common','verification/qbs/qbs_ref.c',
        'verification/qbs/qbs_ref.h'],inputs/'sdk')
    builder.archive(c.LLAMA,c.LLAMA_COMMIT,['ggml'],inputs/'llama')
    gate=json.loads(Path(receipt).read_text())
    for name,value in gate['accepted_dependencies'].items():
        c.require(c.sha(inputs/'llama/ggml/src/ggml-cpu/arch/riscv'/name)==value,
                  'Candidate/accepted GGML dependency mismatch: '+name)
    candidate=inputs/'candidate';candidate.mkdir()
    shutil.copyfile(header,candidate/'m4_preflight.h')
    c.require(c.sha(candidate/'m4_preflight.h')==digest,'Candidate snapshot copy changed')
    data=inputs/'data';data.mkdir()
    for name in c.FILES: shutil.copyfile(c.BASE/name,data/name)
    c.check_prepared_bytes((data/'activation_q8k_m4.bin').read_bytes())
    generic=c.GENERIC.read_text()
    body=generic.split('extern "C" {',1)[1].rsplit('}',1)[0].strip()
    production=(inputs/'llama/ggml/src/ggml-cpu/repack.cpp').read_text()
    c.require(body in production,'Accepted generic body is not exact da56 production source')
    (inputs/'generic.cpp').write_text(generic)
    link=(inputs/'sdk/apps/common/arch.link.ld').read_text()
    c.require(link.count('LENGTH = 0x00100000')==1,'Linker source drift')
    (inputs/'link.ld').write_text(link.replace('ALIGNMENT','16').replace(
        'LENGTH = 0x00100000','LENGTH = 0x01000000'))
    for p in inputs.rglob('*'):
        if p.is_file(): builder.pin(p)
    c.verify(builder.pins)
    save(output/'source-pins.json',builder.pins)
    save(output/'plan.json',dict(schema='stage4-qvk-chain-v1',state='PREPARED_NOT_BUILT',
        scope=c.SCOPE,llama_commit=c.LLAMA_COMMIT,sdk_commit=c.SDK_COMMIT,
        candidate_header_sha256=digest,candidate_gate_sha256=receipt_sha,
        candidate_provenance=candidate_pins,data_provenance=original_pins,
        baseline='da56 packed parallel-sums + exact-byte cache, tag3',
        candidate='new preflight cold producer only, tag4',order=list(c.ORDER),
        calls=4,commands_per_call=64,outputs_per_call=8192,commands=256,
        roi_included=c.ROI_INCLUDED,roi_excluded=c.ROI_EXCLUDED,
        full_ggml=False,simulator_launched=False,automatic_retry=False))
    return dict(state='PREPARED_NOT_BUILT',output=str(output),source_pins_sha256=c.sha(output/'source-pins.json'))


def assembly(output):
    data=output/'inputs/data'
    assets=[('projection_input','activation_f32.bin'),('projection_input_reference','activation_f32.bin'),
            ('projection_golden','activation_q8k_m4.bin')]
    for part in ('q','v','k'):
        assets.extend(((part+'_weights',part+'_r4.bin'),(part+'_weights_reference',part+'_r4.bin'),
                       (part+'_expected',part+'_oracle.bin')))
    paths=[(name,data/file) for name,file in assets]+[('ordered_golden',output/'ordered_golden.bin')]
    return '.section .rodata.stage4,"a",@progbits\n'+''.join(
        '.balign 64\n.global '+name+'\n'+name+':\n.incbin '+json.dumps(str(path))+'\n'
        for name,path in paths)+'.section .note.GNU-stack,"",@progbits\n'


def build(output):
    output=out_path(output)
    plan=json.loads((output/'plan.json').read_text())
    c.require(plan['state']=='PREPARED_NOT_BUILT' and plan['llama_commit']==c.LLAMA_COMMIT and
              plan['sdk_commit']==c.SDK_COMMIT and plan['scope']==c.SCOPE and
              plan['order']==list(c.ORDER) and not (output/'build.json').exists(),
              'One software build only; preserve previous result')
    pins=json.loads((output/'source-pins.json').read_text());c.verify(pins)
    pins[str(output/'plan.json')]=c.sha(output/'plan.json')
    inputs=output/'inputs';sdk=inputs/'sdk/software/qbs';common=inputs/'sdk/apps/common'
    ggml=inputs/'llama/ggml';arch=ggml/'src/ggml-cpu/arch/riscv'
    commands=[]

    def run(label,argv,limit=180):
        c.verify(pins)
        argv=list(map(str,argv));tool=Path(shutil.which(argv[0]) or argv[0]).resolve()
        pins[str(tool)]=c.sha(tool)
        commands.append(dict(label=label,argv=argv,cwd=str(output),environment=ENV,timeout=limit))
        save(output/'commands.json',commands)
        with (output/(label+'.log')).open('x') as log:
            proc=subprocess.run(argv,cwd=output,env=ENV,stdout=log,stderr=subprocess.STDOUT,timeout=limit)
        c.require(proc.returncode==0,'Software build failed: '+label)
        return (output/(label+'.log')).read_text().strip()

    report=dict(state='FAIL',scope=c.SCOPE,llama_commit=c.LLAMA_COMMIT,sdk_commit=c.SDK_COMMIT,
                baseline=plan['baseline'],candidate=plan['candidate'],target_executed=False,
                roi_included=c.ROI_INCLUDED,roi_excluded=c.ROI_EXCLUDED,
                simulator_launched=False,full_ggml=False)
    try:
        run('host-tests',[sys.executable,'-B',inputs/'test_projection.py','-v'])
        for name in ('cc1','as','ld'):
            p=located_path(run('locate-host-'+name,['/usr/bin/gcc','-print-prog-name='+name]))
            pins[str(p)]=c.sha(p)
        run('oracle-compile',['/usr/bin/gcc','-std=gnu11','-O2','-fno-fast-math','-ffp-contract=off',
            '-frounding-math','-I'+str(inputs/'sdk/verification/qbs'),'-MD','-MF',output/'oracle.d',
            inputs/'oracle.c',inputs/'sdk/verification/qbs/qbs_ref.c','-lm','-o',output/'oracle-host'])
        text=run('oracle-run',[output/'oracle-host',inputs/'data',output/'ordered_golden.bin'])
        c.require(text=='STAGE4_ORACLE commands=64 outputs=8192 flags=1','Independent oracle metadata')
        linked=run('oracle-runtime-libraries',['/usr/bin/ldd',output/'oracle-host'])
        c.require('not found' not in linked,'Missing host-oracle runtime library')
        for name in re.findall(r'(?:=>\s+|^\s*)(/[^\s()]+)',linked,re.M):
            p=Path(name).resolve(strict=True);pins[str(p)]=c.sha(p)
        (output/'data.S').write_text(assembly(output))
        for name in ('ordered_golden.bin','data.S'): pins[str(output/name)]=c.sha(output/name)
        flags=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax',
            '-O3','-DNDEBUG','-fno-fast-math','-fno-tree-vectorize','-ffunction-sections','-fdata-sections',
            '-DNR_LANES=4','-DVLEN=1024','-Wall','-Wextra','-Wno-unknown-pragmas',
            '-I'+str(sdk/'include'),'-I'+str(common),'-I'+str(inputs/'candidate')]
        flags += [flag for path in (ggml/'include',ggml/'src',ggml/'src/ggml-cpu',arch)
                  for flag in ('-isystem',str(path))]
        for library in ('libstdc++.a','libm.a','libc.a','libgcc.a','libnosys.a'):
            p=located_path(run('locate-'+library,[CXX,*flags[:2],'-print-file-name='+library]))
            pins[str(p)]=c.sha(p)
        for driver,names in ((CC,('cc1','as','ld')),(CXX,('cc1plus','collect2'))):
            for name in names:
                p=located_path(run('locate-'+name,[driver,'-print-prog-name='+name]))
                pins[str(p)]=c.sha(p)
        sources=[inputs/'main.cpp',inputs/'producer.cpp',inputs/'generic.cpp',output/'data.S',
            *[common/name for name in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')],
            sdk/'src/qbs_runtime.c',sdk/'src/qbs_native_riscv.c']
        objects=[]
        for index,source in enumerate(sources):
            cpp=source.suffix=='.cpp';driver=CXX if cpp else CC
            mode=['-std=gnu++17','-fno-exceptions','-fno-rtti','-ffp-contract=fast'] if cpp else ['-std=gnu11','-ffp-contract=off']
            if source.name=='string.c': mode+=['-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns']
            obj=output/('%02d_%s.o'%(index,source.stem));objects.append(obj)
            run('compile-'+obj.stem,[driver,*flags,*mode,'-MD','-MF',obj.with_suffix('.d'),'-c',source,'-o',obj])
        elf=output/'projection_chain.elf'
        run('link',[CXX,*flags[:4],'-static','-nostartfiles','-nostdlib',*objects,'-Wl,--gc-sections',
            '-Wl,-Map='+str(output/'link.map'),'-T',inputs/'link.ld','-Wl,--start-group',
            '-lstdc++','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf])
        listing=run('disassembly',[CC.with_name(CC.name[:-3]+'objdump'),'-d',elf])
        c.require(all('<'+name+'>:' in listing for name in
            ('stage4_baseline_produce','stage4_candidate_produce','qbs_execute','qbs_native_execute_command')) and
            '06b5045b' in listing and '__wrap_' not in listing,'Missing actual baseline/candidate/native path')
        entries=c.entry_contract(elf,inputs/'elf_reader.py')
        for dep in output.glob('*.d'):
            for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
                p=Path(name).resolve(strict=True)
                c.require(not p.is_relative_to(c.ROOT/'software') and not p.is_relative_to(c.LLAMA),
                          'Live SDK/llama compiler input forbidden')
                value=c.sha(p)
                c.require(str(p) not in pins or pins[str(p)]==value,'Compiler dependency drift')
                pins[str(p)]=value
        packed=(inputs/'data/activation_q8k_m4.bin').read_bytes()
        raw=(output/'ordered_golden.bin').read_bytes()
        c.require(len(raw)==32768,'Incomplete complete-output oracle')
        c.verify(pins);save(output/'source-pins.json',pins)
        report.update(state='BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=c.sha(elf),
            source_pins_sha256=c.sha(output/'source-pins.json'),post_pins_match=True,
            calls=4,commands=256,commands_per_call=64,outputs_per_call=8192,
            baseline_tag=3,candidate_tag=4,cache_both=True,parallel_sums_both=True,
            required_plusargs=['+QBS_PERF','+VECTOR_TRACE=<path>','+COMMIT_TRACE=<path>'],
            entry_contract=entries,expected_entries=dict(zip(c.ENTRIES,(2,2,256))),
            oracle=dict(output_hash=c.fnv(raw),packed_hash=c.fnv(packed),
                output_sha256=c.sha(output/'ordered_golden.bin'),packed_sha256=c.sha(inputs/'data/activation_q8k_m4.bin'),
                natural_matrix_flags=1,expected_fcsr=17))
    except Exception as exc:
        report['error']=str(exc)
    report['artifacts']={str(p):c.sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'build.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    sub=parser.add_subparsers(dest='action',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--output',type=Path,required=True)
    prep.add_argument('--candidate-header',type=Path,required=True);prep.add_argument('--candidate-sha256',required=True)
    prep.add_argument('--freeze-receipt',type=Path,required=True);prep.add_argument('--freeze-receipt-sha256',required=True)
    compile_parser=sub.add_parser('build');compile_parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=prepare(args.output,args.candidate_header,args.candidate_sha256,args.freeze_receipt,args.freeze_receipt_sha256) \
        if args.action=='prepare' else build(args.output)
    print(json.dumps({k:v for k,v in result.items() if k!='artifacts'},indent=2))
    raise SystemExit(int(result['state']=='FAIL'))
