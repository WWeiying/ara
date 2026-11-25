#!/usr/bin/env python3
"""Bounded host + firmware preparation after a qualifying static review. No simulators."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile

sys.dont_write_bytecode=True
from contract import (HERE,SDK_COMMIT,LLAMA_COMMIT,TOOLCHAIN,PARENT,ATOL,RTOL,POLICY,
                      cases,owned_output,fnv,repack)
from check import require,digest
from build_support import Builder,firmware,write_json


def prepare(a):
    reviewed=json.loads(a.review.read_text())
    require(reviewed['state'] == 'STATIC_REVIEW_QUALIFIED_NOT_COMPILED' and reviewed['post_pins_match']
            and reviewed['cases'] == cases() and reviewed['sdk_commit'] == SDK_COMMIT and
            reviewed['llama_commit'] == LLAMA_COMMIT,'Qualifying static review required before compile')
    require(digest(reviewed['source_pins']) == reviewed['source_pins_sha256'],'Review inventory changed')
    pins=json.loads(Path(reviewed['source_pins']).read_text())
    for name,sha in pins.items():
        require(digest(name) == sha,'Static review input changed: '+name)
    out=owned_output(a.output); require(not out.exists(),'Fresh preparation directory required')
    out.mkdir(); b=Builder(out); b.pins.update(pins)
    b.pin(a.review); b.pin(reviewed['source_pins'])
    for p in HERE.iterdir():
        if p.is_file():
            b.pin(p)
    b.run('python-tests',[sys.executable,'-B','-m','unittest','discover','-s',HERE,'-p','test_projection.py','-v'])
    sdk,llama=Path(reviewed['sdk']),Path(reviewed['llama'])
    patch=sdk/'software/qbs/integrations/llama-decode-sums.patch'
    require((llama/'ggml/src/ggml-cpu/arch/riscv/q8_K-decode-sums.h').exists(),
            'Pinned llama must contain registered decode-sums patch')
    b.run('llama-patch-reverse-check',['git','apply','--no-index','--reverse','--check',patch],llama)
    includes=['-I'+str(p) for p in (sdk/'software/qbs/include',sdk/'verification/qbs',HERE)]
    ggml=llama/'ggml'
    quant_includes=['-I'+str(ggml/p) for p in ('include','src','src/ggml-cpu','src/ggml-cpu/arch/riscv')]
    host=out/'host'; host.mkdir()
    flags=['-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math',
           '-Wall','-Wextra','-Werror',*includes]
    for tool in ('cc1','as','ld'):
        name=b.run('host-locate-'+tool,[a.host_cc,'-print-prog-name='+tool]).decode().strip()
        b.pin(Path(name) if Path(name).is_file() else shutil.which(name))
    b.compile(a.host_cc,flags,HERE/'compare_test.c',host/'compare_test.o')
    b.run('comparator-link',[a.host_cc,host/'compare_test.o','-lm','-o',host/'compare_test'])
    b.run('comparator-mutations',[host/'compare_test'])
    b.pin(host/'compare_test')
    mutation=dict(state='PASS',test=str(host/'compare_test'),log=str(out/'comparator-mutations.log'),
        log_sha256=digest(out/'comparator-mutations.log'),byte_mutations=28032,output_mutations=256)
    objects=[]
    for source,name in ((HERE/'oracle.c','oracle'),(sdk/'verification/qbs/qbs_ref.c','ref'),
                        (sdk/'software/qbs/src/qbs_runtime.c','runtime')):
        obj=host/(name+'.o'); b.compile(a.host_cc,flags,source,obj); objects.append(obj)
    oracle=host/'oracle'
    b.run('oracle-link',[a.host_cc,*objects,'-lm','-o',oracle]); b.pin(oracle)
    libraries=b.run('host-runtime-libraries',['ldd',oracle,host/'compare_test']).decode()
    for name in re.findall(r'(/\S+)\s+\(',libraries):
        if Path(name).is_file():
            b.pin(name)
    builds=[]; case_root=out/'cases'; case_root.mkdir()
    selection={(s['operator'],s['phase']):s for s in reviewed['selections']}
    for c in cases():
        d=case_root/c['id']; d.mkdir()
        source=Path(selection[c['operator'],c['phase']]['selection'])
        (d/'input_f32.bin').write_bytes((source/'input_f32.bin').read_bytes())
        (d/'weights_row.bin').write_bytes((source/'weights_row.bin').read_bytes())
        plan=json.loads(b.run('oracle-'+c['id'],[oracle,c['profile'],c['m'],c['n'],c['k'],
            d/'input_f32.bin',d/'weights_row.bin',d]))
        require(plan['k_blocks'] == c['k_blocks'] and plan['outputs'] == c['m']*c['n'] and
            len(plan['commands']) == c['n']//32 and all(cmd['m'] == c['m'] and cmd['n'] == 32
            for cmd in plan['commands']),'Full-K plan/independent output extent')
        write_json(d/'plan.json',plan)
        (d/'weights_x32.bin').write_bytes(repack((d/'weights_row.bin').read_bytes(),c['format'],c['n'],c['k']))
        (d/'guard_golden.bin').write_bytes(bytes([0xa5])*640)
        pack=d/('expected_packed.bin' if c['backend'] == 'native' else 'expected_q8.bin')
        weights=d/('weights_r4.bin' if c['backend'] == 'native' else 'weights_x32.bin')
        comparisons={}
        for kind,path in (('Q8',d/'expected_q8.bin'),('PACK',pack),('OUT',d/'expected.bin'),('GUARD',d/'guard_golden.bin')):
            raw=path.read_bytes()
            comparisons[kind]=dict(path=str(path),count=len(raw)//(4 if kind == 'OUT' else 1),expected_hash=fnv(raw))
        identity=hashlib.sha256(json.dumps(dict(case=c,review=digest(a.review),comparisons=comparisons,
            sources=b.pins),sort_keys=True).encode()).hexdigest()
        build=dict(state='HOST_PREPARED_NOT_EXECUTED',case=c,build_id=identity,plan=plan,plan_path=str(d/'plan.json'),
            weights_path=str(weights),comparisons=comparisons,comparator_tests=mutation,output_policy=POLICY,
            diagnostic=a.diagnostic,numeric_contract=dict(native='bit_exact_ordered_qbs_ref',rvv_atol=ATOL,rvv_rtol=RTOL),
            flag_seeds=[0,8],sdk_commit=SDK_COMMIT,llama_commit=LLAMA_COMMIT,review=str(a.review.resolve()),
            review_sha256=digest(a.review),provenance=selection[c['operator'],c['phase']],requantized=False,
            baseline_kind=c['baseline_kind'],primary_eligible=True,native_format_model_capture=True,
            rtl_executed=False,performance_measured=False,whole_model=False,full_output_width=False,reused_objects=0,
            parent_image=str(PARENT),max_vcs_workers=4,
            timing_contract='quant/pack/admit/complete_execute/drain; one final fence; commit marker pair; all checks/UART outside ROI',
            memory_contract='Archived 1MiB linker, single guarded .data weight copy; parent 16MiB simulation RAM only, no FPGA admission')
        builds.append((d,build))
    archive=out/'goldens.tar'
    with tarfile.open(archive,'w') as tar:
        for d,_ in builds:
            for path in sorted(d.iterdir()):
                tar.add(path,arcname=str(path.relative_to(out)),recursive=False)
    b.pin(archive)
    if not a.host_only:
        firmware(a,b,sdk,ggml,includes,quant_includes,builds)
    for d,_ in builds:
        for path in d.iterdir():
            if path.is_file():
                b.pin(path)
    b.pin(out/'commands.json')
    for path in out.glob('*.log'):
        b.pin(path)
    require(all(digest(p) == sha for p,sha in b.pins.items()),'Build-time source drift')
    write_json(out/'source-pins.json',b.pins)
    manifests=[]
    for d,build in builds:
        build.update(source_pins=str(out/'source-pins.json'),source_pins_sha256=digest(out/'source-pins.json'),
            post_pins_match=True,golden_archive=str(archive),golden_archive_sha256=digest(archive))
        if not a.host_only:
            checker=[sys.executable,'-B',str(HERE/'check.py'),'--build',str(d),'--log','{log}','--output','{result}']
            build['checker']=checker
            manifests.append(dict(id=build['case']['id'],category='qbs',elf=build['elf'],elf_sha256=build['elf_sha256'],
                checker=checker,source_pins=str(out/'runner-source-pins.json'),timeout_seconds=10800,
                baseline_kind=build['baseline_kind'],primary_eligible=True,
                plusargs=['+QBS_PERF'] if build['case']['backend'] == 'native' else []))
        write_json(d/'build.json',build)
    if manifests:
        write_json(out/'manifest.json',dict(cases=manifests))
        for operator,phase in selection:
            ids={c['id'] for c in cases() if (c['operator'],c['phase']) == (operator,phase)}
            write_json(out/f'manifest_{phase}_{operator}.json',dict(cases=[c for c in manifests if c['id'] in ids]))
    summary=dict(state='HOST_PREPARED_NOT_EXECUTED' if a.host_only else 'BUILT_NOT_EXECUTED',
        cases=len(builds),pairs=len(builds)//2,rtl_executed=False,performance_measured=False,review=str(a.review.resolve()),
        source_pins_sha256=digest(out/'source-pins.json'),manifest=str(out/'manifest.json') if manifests else None,
        comparator_tests=mutation,parent_image=str(PARENT),sdk_commit=SDK_COMMIT,llama_commit=LLAMA_COMMIT)
    write_json(out/'build.json',summary)
    runner=dict(b.pins)
    for path in (out/'source-pins.json',out/'build.json',*(d/'build.json' for d,_ in builds),*out.glob('manifest*.json')):
        runner[str(path)]=digest(path)
    write_json(out/'runner-source-pins.json',runner)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--review',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--host-only',action='store_true')
    p.add_argument('--diagnostic',action='store_true')
    p.add_argument('--toolchain',type=Path,default=TOOLCHAIN)
    p.add_argument('--host-cc',default='/usr/bin/gcc')
    prepare(p.parse_args())
