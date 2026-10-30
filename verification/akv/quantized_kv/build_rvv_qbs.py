#!/usr/bin/env python3
"""Link real cached K and untouched GGML RVV primitives with actual QBS calls."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/akv/paired_heads'))
import attention_run as s
from capture_host import validate_capture


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--primitives',type=Path,default=ROOT/'verification/out/akv-quantkv-rvv-primitives-20261024-01')
    p.add_argument('--capture',type=Path,default=ROOT/'verification/out/akv-quantkv-host-capture-20261024-01')
    a = p.parse_args()
    primitives,capture = a.primitives.resolve(strict=True),a.capture.resolve(strict=True)
    out = a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    commands,pins = [],{}
    def save(name,value):
        (out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    def execute(argv,name):
        argv = list(map(str,argv))
        commands.append(dict(argv=argv,cwd=str(out)))
        save('commands.json',commands)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(name+'.log')).read_text()
    try:
        prim = s.read_json(primitives/'result.json')
        s.require(prim['state'] == 'ACTUAL_GGML_RVV_PRIMITIVES_COMPILED' and
            s.digest(primitives/'source-pins.json') == prim['source_pins_sha256'] and
            s.digest(primitives/'ggml_rvv_quants.o') == prim['object_sha256'],'Primitive identity')
        s.merge_pins(pins,s.read_json(primitives/'source-pins.json'))
        captured = s.read_json(capture/'result.json')
        s.require(captured['state'] == 'REAL_HOST_QUANTIZED_KV_CAPTURED' and captured['source_unchanged'] and
            s.digest(capture/'source-pins.json') == captured['source_pins_sha256'],'Capture identity')
        s.merge_pins(pins,s.read_json(capture/'source-pins.json'))
        artifacts = s.read_json(capture/'build-artifacts.json')
        s.require(s.digest(capture/'build-artifacts.json') == captured['build_artifacts_sha256'],'Capture binary identity')
        s.merge_pins(pins,artifacts)
        blobs = {}
        for index,kind in enumerate(('q8_0','q4_0')):
            directory = capture/('capture-k-'+kind+'-v-q8_0')
            checked = validate_capture(directory,kind)
            s.require(checked == captured['captures'][kind] and checked['visible_tokens'] == 128,
                      'Real tensor/capture drift')
            s.merge_pins(pins,checked['file_sha256'])
            for role,name in (('query','attn_q_input-0'),('key','attn_k_input-0')):
                blobs[f'quant_{role}{index}'+('_f32' if role == 'query' else '')] = directory/'decode/block'/(name+'.bin')
        simv = ROOT/'verification/out/qbacc-soc-20261023-02/build/sim/simv'
        image,accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',simv)
        s.merge_pins(pins,accepted)
        assembly = out/'data.S'
        assembly.write_text('.section .rodata,"a",@progbits\n'+''.join(
            f'.balign 64\n.global {name}\n{name}:\n.incbin "{path}"\n' for name,path in blobs.items()))
        cc = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
        common = ROOT/'apps/common'
        flags = ['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax','-O3',
            '-std=gnu11','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-fno-common',
            '-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin',
            '-fno-tree-loop-distribute-patterns','-DNR_LANES=4','-DVLEN=1024',
            '-I'+str(ROOT),'-I'+str(common),'-I'+str(ROOT/'apps/include'),'-I'+str(ROOT/'software/qbs/include')]
        template = (common/'arch.link.ld').read_text()
        s.require(template.count('LENGTH = 0x00100000') == template.count('*(.bss)') == 1,'Link template drift')
        linker = out/'link.ld'
        linker.write_text(template.replace('ALIGNMENT','16').replace('LENGTH = 0x00100000',
            'LENGTH = 0x01000000').replace('*(.bss)','*(.bss .bss.*)'))
        sources = [HERE/'rvv_qbs_main.c',ROOT/'software/qbs/src/qbs_runtime.c',
            ROOT/'software/qbs/src/qbs_native_riscv.c',ROOT/'verification/qbs/qbs_ref.c',
            *[common/name for name in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')],assembly]
        helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
        spec = importlib.util.spec_from_file_location('quant_kv_elf_tools',helper)
        elf_tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(elf_tools)
        objects = [primitives/'ggml_rvv_quants.o']
        for index,source in enumerate(sources):
            extra = ['-Dcalloc=quant_ref_calloc','-Dfree=quant_ref_free'] if source.name == 'qbs_ref.c' else []
            deps = execute([cc,*flags,*extra,'-M','-MT','object',source],f'deps-{index}')
            s.merge_pins(pins,s.hashes([Path(x).resolve(strict=True) for x in
                shlex.split(deps.replace('\\\n',' ').split(':',1)[1])]))
            obj = out/f'{index}.o'
            warnings = ['-Wall','-Wextra','-Werror'] if source.name == 'rvv_qbs_main.c' else []
            execute([cc,*flags,*extra,*warnings,'-c',source,'-o',obj],f'compile-{index}')
            if source == common/'string.c':
                elf_tools.check_libc(execute([cc.with_name('riscv64-unknown-elf-objdump'),'-dr',obj],'libc-disassembly'))
            objects.append(obj)
        libs = [Path(execute([cc,'-print-file-name='+name],name+'-path').strip()).resolve(strict=True)
                for name in ('libm.a','libgcc.a')]
        elf = out/'quantized_kv_rvv_qbs.elf'
        execute([cc,*flags,'-static','-nostdlib','-nostartfiles',*objects,'-Wl,--gc-sections',
            '-Wl,-Map='+str(out/'link.map'),'-T',linker,'-lm','-lgcc','-o',elf],'link')
        disasm = execute([cc.with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        for name in ('quantize_row_q8_0','ggml_vec_dot_q4_0_q8_0','ggml_vec_dot_q8_0_q8_0',
                     'qbs_native_execute_command','qbs_ref_execute','quant_ref_calloc','quant_ref_free'):
            s.require(f'<{name}>:' in disasm,'Missing actual primitive/reference '+name)
        sections = elf_tools.alloc_sections(elf)
        s.require(min(x['address'] for x in sections) >= 0x80000000 and
            max(x['address']+x['bytes'] for x in sections) < 0x81000000-65536,'ELF bounds')
        s.merge_pins(pins,s.hashes([Path(__file__),HERE/'capture_host.py',HERE/'layout.py',
            primitives/'result.json',primitives/'source-pins.json',primitives/'ggml_rvv_quants.o',
            capture/'result.json',capture/'source-pins.json',capture/'build-artifacts.json',
            common/'arch.link.ld',linker,helper,*libs,cc.resolve()]))
        s.verify_pins(pins)
        save('source-pins.json',pins)
        save('build.json',dict(state='BUILT_NOT_EXECUTED',execution='NOT_RUN',elf=str(elf),
            elf_sha256=s.digest(elf),simv=str(simv),accepted_image_pins=image,
            source_pins_sha256=s.digest(out/'source-pins.json'),post_pins_match=True,
            artifact_sha256=s.hashes([x for x in out.iterdir() if x.is_file()]),sections=sections,
            profiles=['q8_0','q4_0'],heads=[0,1],query_heads=[0,6],tokens=[0,63,64,127],
            expected_commands=16,query_exports=4,query_bytes_per_export=136,
            baseline='Untouched production RVV TU compiled with explicit contraction-fast; QBS reference contraction-off',
            scope='Numerical inquiry and actual Query byte export only; no performance or full Attention/model acceptance'))
        print(json.dumps(dict(state='BUILT_NOT_EXECUTED',elf=str(elf))))
    except BaseException as exc:
        save('build.json',dict(state='FAIL',execution='NOT_RUN',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
