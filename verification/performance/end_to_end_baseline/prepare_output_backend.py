#!/usr/bin/env python3
"""Generate a default-OFF llama.cpp adapter from the pinned delivery sources."""
import argparse
import difflib
import json
from pathlib import Path
import subprocess

from audit import digest,require

DELIVERY='da56aa750559c180d631b466de983ff2bb5d54d9'
CPU='ggml/src/ggml-cpu/'
ADAPTER=CPU+'arch/riscv/quant-kv.cpp'
CMAKE=CPU+'CMakeLists.txt'
CHANGES={
 ADAPTER:[
  ('#include "q8_0_value.h"\n', '#include "q8_0_value.h"\n#ifdef GGML_USE_RISCV_OUTPUT_TILE\n#include "output_tile/ggml_entry.h"\n#endif\n'),
  ('    bool register_pv;\n','    bool register_pv;\n    bool output_tile;\n'),
  ('    call.bindings.execute = executor;\n#ifdef GGML_USE_RISCV_REGISTER_PV','    call.bindings.execute = executor;\n#ifdef GGML_USE_RISCV_OUTPUT_TILE\n    if (call.output_tile) {\n        return quant_output_tile_ggml_execute(call.dst, &call.context, &call.bindings,\n            call.workspace, call.workspace_bytes, &call.report);\n    }\n#endif\n#ifdef GGML_USE_RISCV_REGISTER_PV'),
  ('    const int status = ggml_riscv_qbs_direct_run(execute, &call);', '''#ifdef GGML_USE_RISCV_OUTPUT_TILE
    call.output_tile = enabled("GGML_RISCV_AKV_OUTPUT_TILE");
    if (call.output_tile && (call.register_pv || call.grouped_pv)) {
        return ggml_riscv_quant_kv_status::fallback;
    }
#endif
    const int status = ggml_riscv_qbs_direct_run(execute, &call);'''),
  ('        std::fprintf(stderr, "GGML_RISCV_QUANT_KV_REGISTER_PV enabled=%u status=%d completed_groups=%u\\n", unsigned(call.register_pv), status, native.completed_groups);', '''        std::fprintf(stderr, "GGML_RISCV_QUANT_KV_REGISTER_PV enabled=%u status=%d completed_groups=%u\\n", unsigned(call.register_pv), status, native.completed_groups);
#ifdef GGML_USE_RISCV_OUTPUT_TILE
        std::fprintf(stderr, "GGML_RISCV_QUANT_KV_OUTPUT_TILE enabled=%u status=%d completed_groups=%u\\n", unsigned(call.output_tile), status, native.completed_groups);
#endif'''),
 ],
 CMAKE:[
  ('                if (GGML_RISCV_AKV_REGISTER_PV)\n', '''                option(GGML_RISCV_AKV_OUTPUT_TILE "Opt-in output-resident quantized Decode PV" OFF)
                if (GGML_RISCV_AKV_OUTPUT_TILE)
                    if (NOT EXISTS "${GGML_QUANT_KV_DIR}/output_tile/ggml_entry.h")
                        message(FATAL_ERROR "Output-tile requires the reviewed runtime")
                    endif()
                    get_filename_component(GGML_OUTPUT_TILE_ROOT "${GGML_QUANT_KV_DIR}/../../../.." ABSOLUTE)
                    target_include_directories(${GGML_CPU_NAME} PRIVATE "${GGML_OUTPUT_TILE_ROOT}")
                    target_compile_definitions(${GGML_CPU_NAME} PRIVATE GGML_USE_RISCV_OUTPUT_TILE)
                    list(APPEND GGML_CPU_SOURCES "${GGML_QUANT_KV_DIR}/output_tile/runtime.c")
                    if (CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
                        set_property(SOURCE "${GGML_QUANT_KV_DIR}/output_tile/runtime.c"
                            APPEND PROPERTY COMPILE_OPTIONS -fno-fast-math -ffp-contract=fast)
                    endif()
                endif()
                if (GGML_RISCV_AKV_REGISTER_PV)
'''),
 ]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--llama',type=Path,default=Path('/home/wangwy/llama/llama.cpp'))
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    files={};patch=[]
    for name,changes in CHANGES.items():
        before=subprocess.check_output(['git','-C',str(a.llama),'show',DELIVERY+':'+name]).decode()
        after=before
        for old,new in changes:
            require(after.count(old)==1,'Ambiguous delivery anchor: '+name)
            after=after.replace(old,new,1)
        path=out/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(after)
        original=out/'baseline'/name;original.parent.mkdir(parents=True,exist_ok=True);original.write_text(before)
        files[name]=dict(before_sha256=digest(original),after_sha256=digest(path))
        patch.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
                     fromfile='a/'+name,tofile='b/'+name))
    (out/'output-tile.patch').write_text(''.join(patch))
    subprocess.run(['patch','--batch','--fuzz=0','--dry-run','-p1','-i',str(out/'output-tile.patch')],
                   cwd=out/'baseline',check=True,capture_output=True,timeout=30)
    result=dict(state='ADAPTER_PREPARED_NOT_COMPILED_OR_EXECUTED',delivery=DELIVERY,
        checkout_changed=False,production_enabled=False,files=files,
        generator_sha256=digest(__file__),patch_sha256=digest(out/'output-tile.patch'))
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['state'])


if __name__=='__main__':main()
