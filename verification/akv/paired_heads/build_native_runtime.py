#!/usr/bin/env python3
"""Fresh complete-call candidate ELF using reviewed structured GNU build flags."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
import attention_run as s
import prepare_native_candidate as candidate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--base',type=Path,default=ROOT/'verification/out/akv-f32-pv-rtl-build-20261024-02')
    p.add_argument('--candidate',type=Path,default=ROOT/'verification/out/akv-paired-native-candidate-20261024-01')
    a = p.parse_args()
    base, prepared = a.base.resolve(strict=True),a.candidate.resolve(strict=True)
    out = a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        (out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    commands = []
    def execute(argv,name):
        argv = list(map(str,argv))
        commands.append(dict(argv=argv,cwd=str(out)))
        save('commands.json',commands)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(name+'.log')).read_text()
    try:
        report = s.read_json(base/'build.json')
        s.require(report['state'] == 'BUILT_NOT_EXECUTED' and report['post_pins_match'] is True,
                  'Unreviewed base build')
        s.require(s.digest(base/'source-pins.json') == report['source_pins_sha256'],'Base pin receipt drift')
        pins = s.read_json(base/'source-pins.json')
        s.merge_pins(pins,report['artifact_sha256'])
        c = s.read_json(prepared/'result.json')
        s.require(c['state'] == 'CANDIDATE_COMPILED_NOT_EXECUTED' and c['canonical_modified'] is False,
                  'Invalid candidate preparation')
        s.merge_pins(pins,c['source_pins'])
        s.require(s.digest(prepared/'akv_v2_native_candidate.c') == c['candidate_sha256'], 'Candidate drift')
        source = (prepared/'akv_v2_native_candidate.c').read_text()
        s.require(source == candidate.transform(candidate.SOURCE.read_text()), 'Candidate substitution drift')
        image,accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',Path(report['simv']))
        s.require(image == report['accepted_image_pins'],'Wrong accepted image')
        s.merge_pins(pins,accepted)
        capture = Path(report['capture'])/'decode/block'
        blobs = dict(candidate_query_f32=capture/'attn_q_input-0.bin',
                     candidate_key=capture/'attn_k_input-0.bin',candidate_value=capture/'attn_v_input-0.bin')
        s.require([p.stat().st_size for p in blobs.values()] == [6144,131072,131072], 'Capture extents')
        for file in blobs.values():
            s.require(pins.get(str(file)) == s.digest(file), 'Missing capture identity')
        data = out/'data.S'
        data.write_text('.section .rodata,"a",@progbits\n'+''.join(
            f'.balign 64\n.global {name}\n{name}:\n.incbin "{file}"\n' for name,file in blobs.items()))
        compiles = [entry['argv'] for entry in s.read_json(base/'commands.json') if '-c' in entry['argv']]
        s.require(len(compiles) == 13,'Base compiler inventory changed')
        oldroot = ROOT/'verification/akv/paired_heads/f32_pv'
        replacements = {
            str(oldroot/'rtl_main.c'):str(HERE/'native_runtime_main.c'),
            str(ROOT/'verification/akv/qk_panel4_native/rtl_native.c'):str(prepared/'akv_v2_native_candidate.c'),
            str(ROOT/'software/akv/experimental/paired_heads/f32_pv/attention_rvv.S'):
                str(ROOT/'software/akv/experimental/paired_heads/attention_rvv.S'),
            str(base/'rtl_data.S'):str(data)}
        used,objects = set(),[]
        for i,original in enumerate(compiles):
            argv = list(original)
            source_index,output_index = argv.index('-c')+1,argv.index('-o')+1
            old = argv[source_index]
            if old in replacements:
                used.add(old)
                argv[source_index] = replacements[old]
            argv[output_index] = str(out/f'{i}.o')
            argv += ['-iquote',str(candidate.SOURCE.parent)]
            depflags = [arg for j,arg in enumerate(argv) if j not in
                        (source_index-1,output_index-1,output_index)]
            # Preserve the structured invocation, replacing compile/output with
            # dependency-only mode; include quoted headers from the original TU.
            depflags += ['-M','-MT','object']
            deps = execute(depflags,f'deps-{i}')
            dep_paths = [Path(x).resolve(strict=True) for x in shlex.split(deps.replace('\\\n',' ').split(':',1)[1])]
            s.merge_pins(pins,s.hashes(dep_paths))
            execute(argv,f'compile-{i}')
            objects.append(Path(argv[output_index]))
        s.require(used == set(replacements),'Missing replacement source')
        compiler = compiles[0][0]
        flags = compiles[0][1:compiles[0].index('-c')]
        feature_source = ROOT/'software/akv/src/akv_features.c'
        deps = execute([compiler,*flags,'-M','-MT','features',feature_source],'features-deps')
        s.merge_pins(pins,s.hashes([Path(x).resolve(strict=True) for x in
            shlex.split(deps.replace('\\\n',' ').split(':',1)[1])]))
        features = out/'features.o'
        execute([compiler,*flags,'-c',feature_source,'-o',features],'features-compile')
        objects.append(features)
        libm = Path(execute([compiler,*flags,'-print-file-name=libm.a'],'libm-path').strip()).resolve(strict=True)
        s.merge_pins(pins,s.hashes([libm]))
        elf = out/'akv_native_pair_runtime.elf'
        execute([compiler,*flags,'-static','-nostdlib','-nostartfiles',*objects,'-Wl,--gc-sections',
            '-Wl,-Map='+str(out/'link.map'),'-T',base/'link.ld','-lm','-lgcc','-o',elf],'link')
        objdump = Path(compiler).with_name('riscv64-unknown-elf-objdump')
        disasm = execute([objdump,'-d',elf],'disassembly')
        for name in ('akv_attention_execute_v2_native','akv_experimental_qk_f16_pair_panel4',
                     'akv_experimental_pv_f16_pair','akv_v2_compute_scores_f16_generic',
                     'akv_v2_update_outputs_f16_generic','getenv'):
            s.require(f'<{name}>:' in disasm,'Missing real candidate call graph '+name)
        s.require('bench_pair_enabled' not in disasm and 'bench_active' not in disasm,'Benchmark dispatch leaked')
        helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
        spec = importlib.util.spec_from_file_location('native_pair_elf_tools',helper)
        elf_tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(elf_tools)
        sections = elf_tools.alloc_sections(elf)
        s.require(min(section['address'] for section in sections) >= 0x80000000 and
            max(section['address']+section['bytes'] for section in sections) < 0x81000000-65536,
            'Candidate ELF outside accepted memory map')
        s.merge_pins(pins,s.hashes([Path(__file__),HERE/'native_runtime_main.c',
            base/'build.json',base/'source-pins.json',prepared/'result.json',prepared/'candidate.patch',
            data,candidate.SOURCE,Path(candidate.__file__).resolve(),helper]))
        s.verify_pins(pins)
        save('source-pins.json',pins)
        save('build.json',dict(state='BUILT_NOT_EXECUTED',execution='NOT_RUN',
            elf=str(elf),elf_sha256=s.digest(elf),simv=report['simv'],accepted_image_pins=image,
            source_pins_sha256=s.digest(out/'source-pins.json'),post_pins_match=True,
            artifact_sha256=s.hashes([f for f in out.iterdir() if f.is_file()]),
            canonical_modified=False,runs=12,expected_commands=3680,sections=sections,
            cases=[dict(d=64,heads=3,kv=1),dict(d=96,heads=3,kv=65),
                   dict(d=128,heads=6,kv=7),dict(d=128,heads=2,kv=64)],
            numerical='Original generic OFF / candidate ON / OFF full-output and FCSR comparison; no independent full Attention oracle',
            scope='Complete native calls on derived real capture data, not model measurement or performance acceptance'))
        print(json.dumps(dict(state='BUILT_NOT_EXECUTED',elf=str(elf))))
    except BaseException as exc:
        save('build.json',dict(state='FAIL',execution='NOT_RUN',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
