#!/usr/bin/env python3
"""Integrate Norm by replacing only ops.cpp.o in the latest accepted model archive."""
import argparse
import json
from pathlib import Path
import re
import shlex
import shutil
import sys

from audit import digest, require
from build_trace_context_library import Build, archive_members, dependencies, exports, write
from build_sdk_dispatch_library import compare_member_archives
from rms_ggml_source import MAIN, LIVE, OPS, ARCH, ORIGINAL_SHA, MEMBER, transform, header_inventory

RUNS=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
GRAPH=RUNS/'e2e_output_graph_20261106_01'
MODEL=RUNS/'e2e_output_model_20261106_01'
PRIOR=RUNS/'e2e_sdk_dispatch_library_20261106_01/attempt-02'
BASE_SHA='d335a23205c19f0f4e4e8e77b4160812a925b3e848cb967b4479b0a6f4d29c5f'
OBJECT_SHA='297273cf9d004c829e1584852d25ee393a55cc157871058ace3892c4528d22a7'
MODEL_RECEIPT=MAIN/'verification/performance/evidence/sdk_dispatch_model_20261106_01/result.json'
MODEL_RECEIPT_SHA='5e24427b0d8e8510259d5771f2fd169034f738b8fdd131aef0e9d8ac1f925dcd'
NORM_RECEIPT=MAIN/'verification/performance/evidence/rms_vector_output_20261106_01/result.json'
TOOLCHAIN=Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host')


def remap(original, source, obj, inputs=None):
    argv=list(original)
    if inputs is not None:
        for i,value in enumerate(argv):
            if value.startswith('-I'):
                path=Path(value[2:]).resolve(strict=True)
                require(path.is_relative_to(GRAPH),'Unexpected include outside frozen graph')
                argv[i]='-I'+str(inputs/path.relative_to(GRAPH))
    argv[argv.index('-c')+1]=str(source);argv[argv.index('-o')+1]=str(obj)
    return argv


def build(output):
    out=output.absolute();require(out==out.resolve() and out.is_relative_to(RUNS),'Fresh sole-verification output required')
    out.mkdir(parents=True,exist_ok=False);b=Build(out)
    report=dict(state='PREPARING',target_executed=False,performance_measured=False,
        rtl_changed=False,production_library_promoted=False,default_enabled=False)
    try:
        for path in (Path(__file__),MAIN/'verification/performance/end_to_end_baseline/rms_ggml_source.py',
                     MAIN/'verification/performance/end_to_end_baseline/test_rms_ggml_source.py'):b.pin(path)
        b.pin(MODEL_RECEIPT,MODEL_RECEIPT_SHA);accepted=json.loads(MODEL_RECEIPT.read_text())
        require(accepted['state']=='SDK_DISPATCH_QWEN3_MODEL_PAIR_REAUDITED' and
                accepted['candidate_library_sha256']==BASE_SHA and accepted['identical_full_logits'] and
                accepted['identical_tokens_and_csr'] and accepted['identical_native_work'],'Latest model library acceptance differs')
        b.pin(Path(accepted['run'])/'result.json',accepted['result_sha256'])
        b.pin(NORM_RECEIPT);norm=json.loads(NORM_RECEIPT.read_text())
        require(norm['state']=='REAL_FUSED_RMS_VECTOR_OUTPUT_SCOPED_ACCEPTANCE_INDEPENDENTLY_REPLAYED' and
                norm['outputs_checked']==40960 and norm['output_boundary_cases']==155 and
                norm['independent_protocol_checked'],'Measured Norm acceptance required')
        b.pin(Path(norm['collector']),norm['collector_sha256'])
        b.pin(PRIOR/'result.json');library=json.loads((PRIOR/'result.json').read_text())
        require(library['state']=='SDK_DISPATCH_LIBRARY_BUILT_ARCHIVE_VERIFIED' and
                library['candidate_library_sha256']==BASE_SHA,'Baseline SDK library identity')
        base=Path(library['candidate_library']);b.pin(base,BASE_SHA)
        old_path=MODEL/'source-pins.json';b.pin(old_path);old=json.loads(old_path.read_text())
        # The earlier model inventory sealed the graph database, not this
        # second CMake database. Bind it now and require exact object replay.
        database=MODEL/'build/compile_commands.json';b.pin(database)
        matches=[e for e in json.loads(database.read_text()) if e['file']==str(GRAPH/'llama'/OPS)]
        require(len(matches)==1,'Unique frozen ops compile recipe required')
        entry=matches[0];original=list(entry.get('arguments') or shlex.split(entry['command']))
        require(original.count('-c')==original.count('-o')==1 and '-fno-fast-math' not in original and
                '-ffast-math' not in original,'Original compile options changed; reassess numerical contract')
        cwd=Path(entry['directory']);obj=cwd/original[original.index('-o')+1]
        b.pin(obj,OBJECT_SHA);before=archive_members(base.read_bytes())
        require([payload for name,payload in before if name==MEMBER]==[obj.read_bytes()],
                'Accepted library member is not the original ops object')
        depfile=Path(str(obj)+'.d');b.pin(depfile)
        deps=dependencies(depfile.read_text(),cwd);origins={}
        for path in sorted(deps):
            require(path.is_relative_to(GRAPH) or path.is_relative_to(TOOLCHAIN),'Unreviewed dependency')
            b.pin(path,old.get(str(path)))
            if path.is_relative_to(GRAPH):
                require(str(path) in old,'Unpinned frozen project source/header')
                dest=out/'inputs'/path.relative_to(GRAPH);dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(path,dest);origins[str(dest)]=dict(source=str(path),sha256=digest(path))
        original_source=GRAPH/'llama'/OPS;b.pin(original_source,ORIGINAL_SHA)
        generated,changes=transform(original_source.read_text())
        require(generated==(LIVE/OPS).read_text(),'Live Norm change differs from registered full-source transform')
        b.pin(LIVE/OPS)
        source=out/'inputs/llama'/OPS;source.write_text(generated)
        # New project dependencies are limited to the three reviewed headers.
        headers=header_inventory()
        for path,sha in headers.items():
            path=Path(path);b.pin(path,sha)
            dest=out/'inputs/llama'/path.relative_to(LIVE);dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,dest);b.pin(dest,sha)
        for path,identity in origins.items():
            b.pin(path,digest(source) if Path(path)==source else identity['sha256'])
        write(out/'transform.json',changes);b.pin(out/'transform.json')
        compiler=Path(original[0]);require(compiler.is_relative_to(TOOLCHAIN/'bin'),'Compiler outside fixed toolchain')
        b.pin(compiler,old[str(compiler.resolve())]);b.tool_libraries(compiler,'compiler-wrapper')
        real=compiler.with_name('riscv64-buildroot-linux-gnu-g++.br_real');b.tool_libraries(real,'compiler-real')
        tools={}
        for name in ('cc1plus','as','ar','nm','objdump'):
            tool=Path(b.run([compiler,'-print-prog-name='+name],'locate-'+name).strip())
            require(tool.is_absolute() and tool.resolve().is_relative_to(TOOLCHAIN),'Tool outside fixed toolchain')
            b.pin(tool,old.get(str(tool.resolve())));b.tool_libraries(tool,name);tools[name]=tool
        # Use the unchanged original path/flags first, proving reproduction
        # before the one-member replacement. No model/QEMU tree is rehashed here.
        original_copy=out/'objects/original-ops.cpp.o'
        b.run(remap(original,original_source,original_copy),'compile-original',cwd=cwd,bound=600)
        b.pin(original_copy,OBJECT_SHA)
        replacement=out/'objects'/MEMBER;command=remap(original,source,replacement,out/'inputs')
        for value in command:
            if value.startswith('-I'):Path(value[2:]).mkdir(parents=True,exist_ok=True)
        base_command=[v for i,v in enumerate(command) if i not in (command.index('-c'),command.index('-o'),command.index('-o')+1)]
        resolved=dependencies(b.run([*base_command,'-M','-MT','object'],'candidate-dependencies'),out)
        expected={out/'inputs'/p.relative_to(GRAPH) if p.is_relative_to(GRAPH) else p for p in deps}
        expected|={out/'inputs/llama'/Path(p).relative_to(LIVE) for p in headers}
        # The wrapper adds these two C++ standard forwarding headers; their
        # underlying C headers already belong to the original dependency set.
        extra_headers={TOOLCHAIN/'riscv64-buildroot-linux-gnu/include/c++/14.3.0'/name
                       for name in ('cstdint','cstdio')}
        expected|=extra_headers
        require(resolved==expected,'Norm header closure differs from exact registered dependencies')
        for path in resolved:b.pin(path)
        b.run(command,'compile-candidate',bound=600);b.pin(replacement)
        candidate=out/'lib/libggml-cpu.a';shutil.copyfile(base,candidate)
        b.run([tools['ar'],'rD',candidate,replacement],'replace-ops');b.run([tools['ar'],'sD',candidate],'index-library')
        comparison=compare_member_archives(before,archive_members(candidate.read_bytes()),MEMBER,replacement.read_bytes())
        defined=[]
        for label,path in (('before',base),('after',candidate)):
            defined.append(exports(b.run([tools['nm'],'-g','--defined-only','--format=posix',path],'exports-'+label)))
        require(defined[0]==defined[1],'Public defined symbols changed')
        dis=b.run([tools['objdump'],'-d',replacement],'candidate-disassembly')
        before_dis=b.run([tools['objdump'],'-d',obj],'original-disassembly')
        require('vfwredosum.vs' in before_dis and 'vfwredosum.vs' in dis and
                re.search(r'\bvset(?:i)?vli\b[^\n]*e32,\s*m4\b',dis) and
                b'GGML_RISCV_ORDERED_RMS\0' in replacement.read_bytes(),
                'Ordered RVV and actual runtime selection absent from full GGML object')
        write(out/'archive-members.json',comparison);b.pin(out/'archive-members.json');b.pin(candidate)
        b.verify();write(out/'source-pins.json',b.pins);write(out/'path-identities.json',b.identities)
        report.update(state='RMS_GGML_LIBRARY_BUILT_ARCHIVE_VERIFIED',member=MEMBER,
            baseline_library=str(base),baseline_library_sha256=BASE_SHA,candidate_library=str(candidate),
            candidate_library_sha256=digest(candidate),candidate_object=str(replacement),
            candidate_object_sha256=digest(replacement),original_object_reproduced_exactly=True,
            original_object_sha256=OBJECT_SHA,public_exports_unchanged=True,
            unchanged_other_members=len(comparison)-1,members=len(comparison),inventory_and_order_unchanged=True,
            compiled_translation_units=2,original_library_unchanged=True,source_pins_sha256=digest(out/'source-pins.json'),
            baseline_already_uses_ordered_rvv=True,
            new_standard_forwarding_headers=sorted(map(str,extra_headers)),
            ordered_reduction_sites=dict(baseline=before_dis.count('vfwredosum.vs'),
                                         candidate=dis.count('vfwredosum.vs')),
            post_pins_match=True,helpers_identical_to_measured_sources=True,
            source_before_sha256=ORIGINAL_SHA,source_after_sha256=digest(source),header_pins=headers,
            selection='GGML_RISCV_ORDERED_RMS=1, RV64/V/FP64, entry vstart0/valid FRM',
            limitations=['Archive and source acceptance only, not a complete model execution or new RTL timing',
                         'Production baseline already auto-vectorizes; isolated scalar-baseline speedups do not apply',
                         'Only the ops member changes; existing QBS/AKV members remain byte-identical',
                         'Runtime flag defaults off; no production build/library is overwritten'])
    except BaseException as exc:
        report.update(state='FAIL',error=repr(exc));raise
    finally:
        write(out/'source-pins.json',b.pins);write(out/'path-identities.json',b.identities)
        write(out/'commands.json',b.commands)
        report['artifacts']={str(p):digest(p) for p in out.rglob('*') if p.is_file() and p.name!='result.json' and
                             'tmp' not in p.relative_to(out).parts}
        write(out/'result.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    build(p.parse_args().output)
