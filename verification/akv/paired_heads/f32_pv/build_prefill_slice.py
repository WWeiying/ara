#!/usr/bin/env python3
"""Build complete real Prefill-slice OFF/ON comparison, without execution."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
from prefill_slice_data import load, require
from prepare_prefill_candidate import transform, SOURCE

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0,str(HERE.parent))
import attention_run as s


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--base',type=Path,default=ROOT/'verification/out/akv-f32-pv-rtl-build-20261024-02')
    p.add_argument('--candidate',type=Path,default=ROOT/'verification/out/akv-prefill-pv-candidate-20261024-01')
    a = p.parse_args()
    base,candidate = a.base.resolve(strict=True),a.candidate.resolve(strict=True)
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
        data,capture_pins = load()
        s.merge_pins(pins,capture_pins)
        c = s.read_json(candidate/'result.json')
        require(c['state'] == 'PREFILL_CANDIDATE_COMPILED_NOT_EXECUTED' and c['canonical_modified'] is False,
                'Wrong Prefill candidate')
        source = candidate/'akv_prefill_pv_candidate.c'
        require(source.read_text() == transform(SOURCE.read_text()) and s.digest(source) == c['candidate_sha256'],
                'Candidate source changed')
        s.merge_pins(pins,c['source_pins'])
        base_report = s.read_json(base/'build.json')
        require(base_report['state'] == 'BUILT_NOT_EXECUTED' and base_report['post_pins_match'],
                'Invalid base flags receipt')
        require(s.digest(base/'commands.json') == base_report['artifact_sha256'][str(base/'commands.json')],
                'Base command identity')
        image,accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',Path(base_report['simv']))
        require(image == base_report['accepted_image_pins'],'Wrong image')
        s.merge_pins(pins,accepted)
        for name,blob in data.items():
            (out/(name+'.bin')).write_bytes(blob)
        assembly = out/'data.S'
        assembly.write_text('.section .rodata,"a",@progbits\n'+''.join(
            f'.balign 64\n.global prefill_{name}\nprefill_{name}:\n.incbin "{out/(name+".bin")}"\n' for name in data))
        compiles = [row['argv'] for row in s.read_json(base/'commands.json') if '-c' in row['argv']]
        require(len(compiles) == 13,'Base compile structure changed')
        replacements = {str(HERE/'rtl_main.c'):str(HERE/'prefill_slice_main.c'),
            str(ROOT/'verification/akv/qk_panel4_native/rtl_native.c'):str(source),
            str(base/'rtl_data.S'):str(assembly)}
        objects,used = [],set()
        for i,original in enumerate(compiles):
            argv = list(original)
            si,oi = argv.index('-c')+1,argv.index('-o')+1
            if argv[si] in replacements:
                used.add(argv[si])
                argv[si] = replacements[argv[si]]
            argv[oi] = str(out/f'{i}.o')
            argv += ['-iquote',str(SOURCE.parent)]
            dep = [x for j,x in enumerate(argv) if j not in (si-1,oi-1,oi)]+['-M','-MT','object']
            deps = execute(dep,f'deps-{i}')
            s.merge_pins(pins,s.hashes([Path(x).resolve(strict=True) for x in
                shlex.split(deps.replace('\\\n',' ').split(':',1)[1])]))
            execute(argv,f'compile-{i}')
            objects.append(Path(argv[oi]))
        require(used == set(replacements),'Missing source substitution')
        cc = compiles[0][0]
        flags = compiles[0][1:compiles[0].index('-c')]
        for name in ('akv_features.c','akv_prefill_reference.c'):
            path = ROOT/'software/akv/src'/name
            deps = execute([cc,*flags,'-M','-MT','object',path],name+'-deps')
            s.merge_pins(pins,s.hashes([Path(x).resolve(strict=True) for x in
                shlex.split(deps.replace('\\\n',' ').split(':',1)[1])]))
            obj = out/(name+'.o')
            execute([cc,*flags,'-c',path,'-o',obj],name+'-compile')
            objects.append(obj)
        libm = Path(execute([cc,*flags,'-print-file-name=libm.a'],'libm-path').strip()).resolve(strict=True)
        elf = out/'akv_prefill_pv_slice.elf'
        execute([cc,*flags,'-static','-nostdlib','-nostartfiles',*objects,'-Wl,--gc-sections',
                 '-Wl,-Map='+str(out/'link.map'),'-T',base/'link.ld','-lm','-lgcc','-o',elf],'link')
        disasm = execute([Path(cc).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        for name in ('akv_attention_execute_v2_prefill_native','akv_experimental_pv_f32_pair',
                     'akv_v2_update_outputs_f32_generic','akv_attention_v2_prefill_validate'):
            require(f'<{name}>:' in disasm,'Missing actual symbol '+name)
        helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
        spec = importlib.util.spec_from_file_location('prefill_pv_elf_tools',helper)
        elf_tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(elf_tools)
        sections = elf_tools.alloc_sections(elf)
        require(min(x['address'] for x in sections) >= 0x80000000 and
                max(x['address']+x['bytes'] for x in sections) < 0x81000000-65536,'ELF bounds')
        s.merge_pins(pins,s.hashes([Path(__file__),HERE/'prefill_slice_data.py',HERE/'test_prefill_slice_data.py',
            HERE/'prepare_prefill_candidate.py',base/'build.json',base/'commands.json',base/'link.ld',
            candidate/'result.json',candidate/'candidate.patch',helper,libm,
            *[out/(name+'.bin') for name in data]]))
        s.verify_pins(pins)
        save('source-pins.json',pins)
        save('build.json',dict(state='BUILT_NOT_EXECUTED',execution='NOT_RUN',elf=str(elf),
            elf_sha256=s.digest(elf),simv=base_report['simv'],accepted_image_pins=image,
            source_pins_sha256=s.digest(out/'source-pins.json'),post_pins_match=True,
            artifact_sha256=s.hashes([x for x in out.iterdir() if x.is_file()]),sections=sections,
            expected_commands=[3552,3138,3138,3552],trials=4,outputs_per_trial=2304,
            provenance='Real SmolLM2 M64 positions32--35, all9 Query/3 KV heads; derived M4 slice not full M64 dispatch',
            numerical='Original golden atol.004/rtol.002; generic/pair exact all9216 bytes and FCSR',
            scope='Complete original Prefill native API candidate; performance not yet accepted'))
        print(json.dumps(dict(state='BUILT_NOT_EXECUTED',elf=str(elf))))
    except BaseException as exc:
        save('build.json',dict(state='FAIL',execution='NOT_RUN',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
