#!/usr/bin/env python3
"""Build one immutable real Qwen3 QKV SDK workload for two SoC configurations."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess

from audit import digest, require, verify_pins
from check_projection_capture import check
from run_projection_capture_v3 import VERIFY, GRAPH, HERE, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); capture = args.capture.resolve(strict=True); out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY/'verification/out'), 'Fresh verification output')
    report = json.loads((capture/'result.json').read_text())
    require(report['state'] == 'REAL_QWEN3_PROJECTION_CAPTURED_NOT_BENCHMARKED' and report['post_pins_match'],
            'Capture not accepted')
    require(digest(capture/'source-pins.json') == report['source_pins_sha256'], 'Capture pin map')
    capture_pins = json.loads((capture/'source-pins.json').read_text())
    verify_pins(capture_pins); verify_pins(report['artifacts'])
    payload, metadata = check((capture/'qemu.log').read_text())
    require(payload == (capture/'activation_f32.bin').read_bytes() and metadata == report['activation'], 'Capture replay')
    out.mkdir(parents=True, exist_ok=False); pins = {}; commands = []
    state = dict(state='PREPARING', performance_measured=False, whole_model=False)
    def pin(path):
        path = str(Path(path).resolve(strict=True)); value = digest(path)
        require(path not in pins or pins[path] == value, 'Build input drift'); pins[path] = value
    def run(argv, label):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv)); (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        state['state'] = label.upper(); (out/'status.json').write_text(json.dumps(state, indent=2)+'\n')
        result = subprocess.run(argv, cwd=out, capture_output=True, timeout=180)
        (out/(label+'.log')).write_bytes(result.stdout+result.stderr)
        require(result.returncode == 0, label+' failed')
        return result.stdout.decode()
    try:
        for path in (Path(__file__), HERE/'projection_golden.c', HERE/'projection_native.cpp',
                     HERE/'audit.py', HERE/'check_projection_capture.py', capture/'result.json', capture/'source-pins.json'):
            pin(path)
        for name in ('activation_f32.bin', 'attn_q.bin', 'attn_k.bin', 'attn_v.bin'): pin(capture/name)
        host = ['/usr/bin/gcc', '-std=c11', '-O2', '-fno-fast-math', '-ffp-contract=off', '-frounding-math',
                '-Wall', '-Wextra', '-Werror', HERE/'projection_golden.c', ROOT/'verification/qbs/qbs_ref.c',
                '-lm', '-o', out/'golden']
        deps = [v for i, v in enumerate(host) if i not in (host.index('-o'), host.index('-o')+1) and v != '-lm']
        text = run([*deps, '-M', '-MT', 'object'], 'host-deps')
        for path in shlex.split(text.replace('\\\n', ' ').replace('object:', ' ')): pin(path)
        run(host, 'host-build'); run([out/'golden', capture, out], 'host-golden')
        symbols = {'projection_input':capture/'activation_f32.bin', 'projection_golden':out/'activation_q8k_m4.bin'}
        for short, name in (('q','attn_q'), ('k','attn_k'), ('v','attn_v')):
            for suffix, artifact in (('weights','r4'), ('expected','expected'), ('flags','fflags')):
                symbols[short+'_'+suffix] = out/(name+'_'+artifact+'.bin')
        assembly = '.section .rodata\n'
        for symbol, path in symbols.items():
            pin(path); assembly += f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{path}"\n'
        (out/'data.S').write_text(assembly); pin(out/'data.S')
        prior = VERIFY/'verification/out/m4-prepared-qkv-build-20261027-02'
        prior_report = json.loads((prior/'build.json').read_text())
        require(digest(prior/'manifest.json') == prior_report['manifest_sha256'], 'Archived compiler recipe')
        old = json.loads((prior/'manifest.json').read_text()); pin(prior/'manifest.json')
        archive_pins = json.loads((GRAPH/'source-pins.json').read_text())
        pin(GRAPH/'source-pins.json')
        require(old[str(prior/'commands.json')] == digest(prior/'commands.json'), 'Recipe identity')
        pin(prior/'commands.json')
        records = json.loads((prior/'commands.json').read_text())
        first_link = next(i for i, c in enumerate(records) if '-c' not in c and '-o' in c and
                          c[c.index('-o')+1] == str(prior/'qbs_current_projection_soc'))
        require(first_link == 12 and all('-c' in c for c in records[:first_link]),
                'Unexpected bare-metal compilation recipe')
        compiles = [list(c) for c in records[:first_link]]
        compiles[0][compiles[0].index('-c')+1] = str(HERE/'projection_native.cpp')
        compiles[3][compiles[3].index('-c')+1] = str(out/'data.S')
        compiles.pop(1)  # The new main calls the production header directly.
        objects = []
        for i, cmd in enumerate(compiles):
            adjusted = []
            for word in cmd:
                word = word.replace('/home/wangwy/llama/llama.cpp/ggml/', str(GRAPH/'llama/ggml')+'/')
                word = word.replace(str(VERIFY/'software/qbs'), str(GRAPH/'sdk/software/qbs'))
                adjusted.append(word)
            cmd = adjusted
            # The runtime uses this framework header, not the older SDK copy.
            cmd[1:1] = ['-I'+str(GRAPH/'llama/ggml/src/ggml-cpu/arch/riscv')]
            obj = out/f'{i}.o'; objects.append(str(obj)); cmd[cmd.index('-o')+1] = str(obj)
            dep = [v for j, v in enumerate(cmd) if j not in (cmd.index('-c'), cmd.index('-o'), cmd.index('-o')+1)]
            text = run([*dep, '-M', '-MT', 'object'], 'deps-'+str(i))
            for name in shlex.split(text.replace('\\\n', ' ').split(':',1)[1]):
                path = Path(name).resolve(strict=True)
                # All framework and SDK code comes from the accepted isolated archive.
                if path.is_relative_to(GRAPH):
                    require(capture_pins.get(str(path), archive_pins.get(str(path))) == digest(path),
                            'Archived SDK/GGML drift: '+str(path))
                elif not path.is_relative_to(ROOT/'verification/performance/end_to_end_baseline') and not path.is_relative_to(out):
                    if str(path) in old:
                        require(old[str(path)] == digest(path), 'Archived tool/startup dependency drift: '+str(path))
                    else:
                        require(any(path.is_relative_to(root) for root in
                            (Path('/home/wangwy/openproject/ara/install/riscv-gcc'), VERIFY/'apps/common', VERIFY/'apps/include')),
                            'Unreviewed new compile dependency: '+str(path))
                pin(path)
            run(cmd, 'compile-'+str(i))
        link = list(next(c for c in records if '-c' not in c and '-o' in c and
                         c[c.index('-o')+1] == str(prior/'qbs_current_projection_soc')))
        link = [v for v in link if not v.endswith('.o')]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = objects
        elf = out/'matrix_projection.elf'; link[link.index('-o')+1] = str(elf)
        link = ['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        pin(link[link.index('-T')+1])
        for name in ('libstdc++.a','libm.a','libc.a','libgcc.a','libnosys.a'):
            pin(run([link[0], '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-print-file-name='+name], 'locate-'+name).strip())
        run(link, 'link'); pin(elf)
        dis = run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
        require('<qbs_native_execute_command>:' in dis and '<qbs_ref_execute>:' not in dis and
                'vsse16.v' in dis, 'Native production quantizer/executor missing or oracle leaked')
        verify_pins(pins); (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        state.update(state='REAL_QWEN3_SDK_BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=digest(elf),
            source_pins_sha256=digest(out/'source-pins.json'), m=4, n=128, k=2048,
            trials=2, commands=24, outputs=3072, capture=str(capture), full_ggml=False,
            preparation_included=True, cold_weight_repack_included=False,
            artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('status.json','build.json')})
    except BaseException as exc: state.update(state='FAIL', error=repr(exc)); raise
    finally: (out/'status.json').write_text(json.dumps(state, indent=2)+'\n'); (out/'build.json').write_text(json.dumps(state, indent=2)+'\n')


if __name__ == '__main__': main()
