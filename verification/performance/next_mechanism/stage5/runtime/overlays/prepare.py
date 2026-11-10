#!/usr/bin/env python3
"""Materialize reviewed da56 overlays in a fresh build input; never edit llama."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

HERE=Path(__file__).resolve().parent
RUNTIME=HERE.parent
ROOT=Path('/home/wangwy/openproject/ara_dsa')
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
LLAMA=Path('/home/wangwy/llama/llama.cpp')
REV='da56aa750559c180d631b466de983ff2bb5d54d9'
AUTO_REV='06d046324e1dde07d3d6f8625843b2b8858a1a06'
AKV='ggml/src/ggml-cpu/arch/riscv/akv.cpp'
CMAKE='ggml/src/ggml-cpu/CMakeLists.txt'
BASE_AKV='a2382b3a19a9c035428181c22a131ca18aaa466c153d9dc8006d7b43a75f97fb'
BASE_CMAKE='2168ddbf805dc048b86d868468b4793f8998d635bd55cfa9d247bef4e375275f'
AUTO_AKV='40e41f2ac210c8c1eeb0ad3149734e47a12044fa17fe4d30797b75a23320544f'
SEALED=('platform.c','platform.h','read_state.S')
OWN=('prepare.py','auto_pair.patch','entry.c','entry.h','resident.inc','resident.cmake',
     'host_control.cpp','test_overlay.py','CONTRACT.md')

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def replace(text,old,new):
    if text.count(old)!=1: raise ValueError('Nonunique/missing overlay anchor: '+old[:80])
    return text.replace(old,new)

def materialize(output):
    output=Path(output)
    output.mkdir()
    raw=subprocess.check_output(['git','-C',str(LLAMA),'archive',REV])
    (output/'llama.tar').write_bytes(raw)
    tree=output/'llama'
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        if any('..' in Path(m.name).parts or Path(m.name).is_absolute() or
               not (m.isfile() or m.isdir() or m.issym()) for m in archive.getmembers()):
            raise ValueError('Unsafe archive')
        archive.extractall(tree,filter='data')
    if sha(tree/AKV)!=BASE_AKV or sha(tree/CMAKE)!=BASE_CMAKE:
        raise ValueError('da56 source identity')
    # Signoff output itself lives inside another Git worktree. Prevent git apply
    # from silently ignoring paths outside that ancestor repository's prefix.
    env=dict(os.environ,GIT_CEILING_DIRECTORIES=str(output.absolute()))
    subprocess.run(['git','apply','--check',str(HERE/'auto_pair.patch')],cwd=tree,env=env,check=True)
    subprocess.run(['git','apply',str(HERE/'auto_pair.patch')],cwd=tree,env=env,check=True)
    if sha(tree/AKV)!=AUTO_AKV: raise ValueError('Reviewed adapted06 result identity')
    shutil.copytree(tree/'ggml/src/ggml-cpu/arch/riscv',output/'auto_reference')
    text=(tree/AKV).read_text()
    include_next=text[:text.index('#include <mutex>')].count('\n')+2
    namespace_line=text[:text.index('}  // namespace')].count('\n')+1
    entry_line=text[:text.index('bool ggml_riscv_akv_flash_attn(')].count('\n')+1
    quant_if='    if (env_true("GGML_RISCV_AKV_QUANT_KV")) {'
    quant_next=text[:text.index(quant_if)].count('\n')+2
    trace_line=text[:text.index('    register_trace();')].count('\n')+1
    # Emulation must not bypass provider denial through the native quantKV
    # branch that precedes ordinary AKV's emulation dispatch in the old body.
    text=replace(text,quant_if,'#if defined(GGML_AKV_RESIDENT) && GGML_AKV_RESIDENT\n'
        '    if (!emulation_enabled() && env_true("GGML_RISCV_AKV_QUANT_KV")) {\n'
        '#else\n'+quant_if+'\n#endif\n#line '+str(quant_next))
    text=replace(text,'#endif\n    register_trace();',
        '#endif\n#line '+str(trace_line)+'\n    register_trace();')
    # Preserve default-OFF __LINE__ diagnostics as well as executable semantics.
    text=replace(text,'#include <mutex>','#include <mutex>\n#if defined(GGML_AKV_RESIDENT) && GGML_AKV_RESIDENT\n#include <vector>\n#include "entry.h"\n#include "resident_attention/executor.h"\nstatic bool stage5_legacy_body(const ggml_compute_params *,ggml_tensor *);\n#endif\n#line '+str(include_next))
    text=replace(text,'}  // namespace\n\nbool ggml_riscv_akv_flash_attn',
        '#if defined(GGML_AKV_RESIDENT) && GGML_AKV_RESIDENT\n#include "resident.inc"\n#endif\n#line '+str(namespace_line)+'\n}  // namespace\n\n'
        '#if defined(GGML_AKV_RESIDENT) && GGML_AKV_RESIDENT\n'
        'extern "C" void ggml_akv_resident_snapshot_v1(ggml_akv_resident_counters_v1 *out) {\n'
        '    *out={resident_counts.denied.load(),resident_counts.unsupported.load(),resident_counts.lease_denied.load(),\n'
        '        resident_counts.resident_calls.load(),resident_counts.native_calls.load(),resident_counts.resident_groups.load(),\n'
        '        resident_counts.native_groups.load(),resident_counts.completed.load(),resident_counts.failed.load(),\n'
        '        resident_counts.legacy_calls.load(),resident_counts.legacy_completed.load(),resident_counts.legacy_fallback.load()};\n}\n#endif\n\n'
        '#line '+str(entry_line)+'\nbool ggml_riscv_akv_flash_attn')
    text=replace(text,'bool ggml_riscv_akv_flash_attn(const ggml_compute_params * params, ggml_tensor * dst) {',
        '#if defined(GGML_AKV_RESIDENT) && GGML_AKV_RESIDENT\n'
        'bool ggml_riscv_akv_flash_attn(const ggml_compute_params * params, ggml_tensor * dst) {\n'
        '    const auto *provider=akv_resident_platform_current_v1();\n'
        '    const auto gate=ggml_akv_platform_entry_v1(provider);\n'
        '    if (gate<0) GGML_ABORT("AKV entry VSTART/state violation: %d",int(gate));\n'
        '    if (!emulation_enabled()) {\n'
        '        if (gate!=AKV_PLATFORM_READY) {\n'
        '            resident_counts.denied.fetch_add(1,std::memory_order_relaxed);\n'
        '            return false; // no INFO, native or resident opcode\n'
        '        }\n'
        '        return stage5_native(params,dst,provider);\n'
        '    }\n    return stage5_legacy_body(params,dst);\n}\n'
        'static bool stage5_legacy_body(const ggml_compute_params *params,ggml_tensor *dst) {\n'
        '#else\n#line '+str(entry_line)+'\n'
        'bool ggml_riscv_akv_flash_attn(const ggml_compute_params * params, ggml_tensor * dst) {\n'
        '#endif\n#line '+str(entry_line+1))
    (tree/AKV).write_text(text)
    cmake=(tree/CMAKE).read_text()
    cmake='option(GGML_RISCV_AKV_RESIDENT "Experimental trusted-provider resident Decode (default deny)" OFF)\n'+cmake
    cmake=replace(cmake,'            enable_language(ASM)\n            target_compile_definitions(${GGML_CPU_NAME} PRIVATE GGML_USE_RISCV_AKV)',
        '            enable_language(ASM)\n'+(HERE/'resident.cmake').read_text()+
        '            target_compile_definitions(${GGML_CPU_NAME} PRIVATE GGML_USE_RISCV_AKV)')
    (tree/CMAKE).write_text(cmake)
    dest=tree/AKV;dest=dest.parent
    for name in ('entry.h','entry.c','resident.inc'):
        shutil.copyfile(HERE/name,dest/name)
    for name in SEALED: shutil.copyfile(RUNTIME/name,dest/name)
    pins={str(p):sha(p) for p in sorted(tree.rglob('*')) if p.is_file()}
    for p in (output/'auto_reference').rglob('*'):
        if p.is_file(): pins[str(p)]=sha(p)
    for name in OWN: pins[str(HERE/name)]=sha(HERE/name)
    for name in SEALED: pins[str(RUNTIME/name)]=sha(RUNTIME/name)
    pins[str(output/'llama.tar')]=sha(output/'llama.tar')
    (output/'source-pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
    report=dict(state='PREPARED_NOT_BUILT',schema='stage5-ggml-overlay-v1',llama_revision=REV,
        adapted_auto_pair_revision=AUTO_REV,base_akv_sha256=BASE_AKV,base_cmake_sha256=BASE_CMAKE,
        auto_akv_sha256=AUTO_AKV,akv_sha256=sha(tree/AKV),cmake_sha256=sha(tree/CMAKE),
        source_pins_sha256=sha(output/'source-pins.json'),provider_registered=False,
        native_execution=False,production_capability_changed=False)
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return tree,report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.absolute()
    if out!=out.resolve() or out.parent!=OUT or not out.name.startswith('stage5_ggml_overlay_') or out.exists():
        raise ValueError('Fresh direct signoff stage5_ggml_overlay_* output required')
    _,report=materialize(out)
    print(json.dumps(report,sort_keys=True))
