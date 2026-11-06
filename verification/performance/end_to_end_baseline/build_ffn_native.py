#!/usr/bin/env python3
"""Build a full-K FFN SDK triplet with real inputs and an independent oracle."""
import argparse
import json
from pathlib import Path
import shlex
import struct
import subprocess

from audit import digest, require, verify_pins
from ffn_capture import check
from run_projection_capture_v3 import HERE, ROOT, VERIFY

PREFIX = VERIFY/'verification/out/e2e_qwen3_projection_native_build_20261106_03'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); capture = args.capture.resolve(strict=True); out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY/'verification/out'), 'Fresh verification output')
    out.mkdir(parents=True, exist_ok=False); pins = {}; commands = []
    state = dict(state='PREPARING', performance_measured=False, whole_model=False, full_ggml=False)
    def pin(path, expected=None):
        path = str(Path(path).resolve(strict=True)); sha = digest(path)
        require(expected is None or expected == sha, 'Input identity: '+path)
        require(path not in pins or pins[path] == sha, 'Input changed'); pins[path] = sha
    def run(argv, label):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv)); (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        state['state'] = label.upper(); (out/'status.json').write_text(json.dumps(state, indent=2)+'\n')
        result = subprocess.run(argv, cwd=out, capture_output=True, timeout=180)
        (out/(label+'.log')).write_bytes(result.stdout+result.stderr)
        require(result.returncode == 0, label+' failed'); return result.stdout.decode()
    try:
        report = json.loads((capture/'result.json').read_text())
        require(report['state'] == 'REAL_QWEN3_FFN_CAPTURED_NOT_BENCHMARKED' and report['post_pins_match'] and
                digest(capture/'source-pins.json') == report['source_pins_sha256'], 'Capture identity')
        cpins = json.loads((capture/'source-pins.json').read_text()); verify_pins(cpins); verify_pins(report['artifacts'])
        prior_capture = VERIFY/'verification/out/e2e_qwen3_projection_capture_20261106_03'
        require(cpins.get(str(prior_capture/'qemu.log')) == digest(prior_capture/'qemu.log'), 'QKV control capture')
        payloads, metadata = check((capture/'qemu.log').read_text(), (prior_capture/'qemu.log').read_text())
        require(metadata == report['activation'] and all((capture/(key+'_f32.bin')).read_bytes() == value
                for key,value in payloads.items()), 'Capture replay')
        before = json.loads((PREFIX/'build.json').read_text())
        require(before['state'] == 'REAL_QWEN3_SDK_BUILT_NOT_EXECUTED' and
                digest(PREFIX/'source-pins.json') == before['source_pins_sha256'], 'Common object build')
        old = json.loads((PREFIX/'source-pins.json').read_text()); verify_pins(old); verify_pins(before['artifacts'])
        for path in (Path(__file__), HERE/'audit.py', HERE/'ffn_capture.py', HERE/'ffn_native.cpp', HERE/'ffn_golden.c',
                     capture/'result.json', capture/'source-pins.json', PREFIX/'build.json', PREFIX/'source-pins.json', PREFIX/'commands.json'):
            pin(path)
        for path in report['artifacts']: pin(path, report['artifacts'][path])
        require([(w['tensor'],w['k'],w['full_n'],w['captured_n']) for w in report['weights']] ==
                [('blk.0.ffn_gate.weight',2048,6144,128),('blk.0.ffn_up.weight',2048,6144,128),
                 ('blk.0.ffn_down.weight',6144,2048,128)], 'FFN weight scope')
        profiles = [dict(Q4_K=1,Q6_K=2)[w['type']] for w in report['weights']]
        (out/'profiles.bin').write_bytes(struct.pack('<3I',*profiles)); pin(out/'profiles.bin')
        host = ['/usr/bin/gcc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math',
                '-Wall','-Wextra','-Werror',HERE/'ffn_golden.c',ROOT/'verification/qbs/qbs_ref.c','-lm','-o',out/'golden']
        dep = [v for i,v in enumerate(host) if i not in (host.index('-o'),host.index('-o')+1) and v != '-lm']
        text = run([*dep,'-M','-MT','object'],'host-deps')
        for path in shlex.split(text.replace('\\\n',' ').replace('object:',' ')): pin(path)
        run(host,'host-build'); run([out/'golden',capture,out],'host-golden')
        symbols = dict(ffn_input=capture/'ffn_norm-0_f32.bin',down_input=capture/'ffn_swiglu-0_f32.bin',
                       ffn_quantized=out/'ffn_quantized.bin',down_quantized=out/'down_quantized.bin',ffn_profiles=out/'profiles.bin')
        for part in range(3):
            for symbol, artifact in (('weights','r4'),('expected','expected'),('flags','flags')):
                symbols[f'ffn_{part}_{symbol}'] = out/f'ffn_{part}_{artifact}.bin'
        assembly = '.section .rodata\n'
        for symbol,path in symbols.items():
            pin(path); assembly += f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{path}"\n'
        (out/'data.S').write_text(assembly); pin(out/'data.S')
        records = json.loads((PREFIX/'commands.json').read_text())
        recipes = {int(r['label'].split('-')[1]): list(r['argv']) for r in records if r['label'].startswith('compile-')}
        require(set(recipes) == set(range(11)), 'Common object inventory')
        objects = []
        for i in range(11):
            if i in (0,2): continue
            path = PREFIX/f'{i}.o'; pin(path,before['artifacts'][str(path)]); objects.append(str(path))
        for i,source in ((0,HERE/'ffn_native.cpp'),(2,out/'data.S')):
            cmd = recipes[i]; cmd[cmd.index('-c')+1] = str(source); obj = out/f'{i}.o'
            cmd[cmd.index('-o')+1] = str(obj); objects.append(str(obj))
            dep = [v for j,v in enumerate(cmd) if j not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
            text = run([*dep,'-M','-MT','object'],'deps-'+str(i))
            for name in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
                path = Path(name).resolve(strict=True)
                require(path in (source.resolve(),(out/'data.S').resolve()) or old.get(str(path)) == digest(path),
                        'Unreviewed compile dependency: '+str(path)); pin(path)
            run(cmd,'compile-'+str(i))
        link = [v for v in next(r['argv'] for r in records if r['label'] == 'link') if not v.endswith('.o')]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = objects
        elf = out/'ffn_projection.elf'; link[link.index('-o')+1] = str(elf)
        link = ['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        pin(link[link.index('-T')+1],old[str(Path(link[link.index('-T')+1]).resolve())]); run(link,'link'); pin(elf)
        dis = run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        require('<qbs_native_execute_command>:' in dis and '<qbs_ref_execute>:' not in dis and 'vsse16.v' in dis,
                'Production quantizer/executor missing or oracle leaked')
        for mode in ('base','wide'):
            sim = VERIFY/'verification/out'/('e2e_matrix_soc_'+mode+'_20261106_01/sim')
            run(['/usr/bin/bash',VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',sim,elf],'l2-'+mode)
        verify_pins(old); verify_pins(cpins); verify_pins(pins)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        state.update(state='REAL_QWEN3_FFN_SDK_BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=digest(elf),
                     source_pins_sha256=digest(out/'source-pins.json'),capture=str(capture),profiles=profiles,
                     m=4,n=128,k=[2048,2048,6144],trials=1,commands=12,outputs=1536,
                     preparation_included=True,shared_gate_up_preparation=True,cold_weight_repack_included=False,
                     reused_objects=9,rebuilt_objects=2,
                     artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('status.json','build.json')})
    except BaseException as exc: state.update(state='FAIL',error=repr(exc)); raise
    finally:
        (out/'status.json').write_text(json.dumps(state,indent=2)+'\n'); (out/'build.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__ == '__main__': main()
