#!/usr/bin/env python3
"""Reuse checked common objects; compile only new GQA6 caller and real data."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from audit import digest, require, verify_pins
from build_output_native import ROOT, VERIFY, HERE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY/'verification/out'), 'Fresh verification output')
    prior = VERIFY/'verification/out/e2e_output_native_q8_20261106_02'
    report = json.loads((prior/'build.json').read_text())
    require(report['state'] == 'BUILT_NOT_EXECUTED' and report['kind'] == 'q8_0' and
            report['rebuilt_objects'] == 18 and digest(prior/'source-pins.json') == report['source_pins_sha256'], 'Program recipe')
    old = json.loads((prior/'source-pins.json').read_text()); verify_pins(old); verify_pins(report['artifacts'])
    out.mkdir(parents=True, exist_ok=False); pins = {}; commands = []
    state = dict(state='PREPARING', performance_measured=False, whole_model=False)
    def pin(path, expected=None):
        path = str(Path(path).resolve(strict=True)); sha = digest(path)
        require(expected is None or sha == expected, 'Input identity: '+path)
        require(path not in pins or pins[path] == sha, 'Input drift'); pins[path] = sha
    def run(argv, label):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv)); (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        result = subprocess.run(argv, cwd=out, capture_output=True, timeout=180)
        (out/(label+'.log')).write_bytes(result.stdout+result.stderr)
        require(result.returncode == 0, label+' failed'); return result.stdout.decode()
    try:
        for path in (Path(__file__), HERE/'audit.py', HERE/'output_gqa6_main.c', prior/'build.json', prior/'source-pins.json'):
            pin(path)
        pin(prior/'commands.json', report['artifacts'][str(prior/'commands.json')])
        capture = VERIFY/'verification/out/akv-quantkv-host-capture-20261024-01'
        accepted = json.loads((capture/'result.json').read_text())
        known = accepted['captures']['q8_0']['file_sha256']; pin(capture/'result.json')
        data_dir = capture/'capture-k-q8_0-v-q8_0/decode/block'
        import numpy as np
        data = {}
        names = ('attn_q_input-0', 'attn_k_input-0', 'attn_v_input-0', 'attn_mask_input-0', 'kqv_out-0')
        for name in names:
            source = data_dir/(name+'.bin'); pin(source, known[str(source)]); data[name] = source
        require(data[names[0]].stat().st_size == 6144 and data[names[4]].stat().st_size == 6144 and
                data[names[3]].stat().st_size == 512, 'Capture geometry')
        mask = np.frombuffer(data[names[3]].read_bytes(), dtype='<u2')
        require((mask[:128] == 0).all() and (mask[128:] == 0xfc00).all(), 'Not a genuine 128-token prefix')
        for name in names[1:3]:
            raw = np.frombuffer(data[name].read_bytes(), dtype=np.uint8)
            require(raw.size == 2*256*136, 'KV row geometry')
            source = raw.reshape(2, 256, 136)
            transformed = source.transpose(1, 0, 2).copy()
            require(np.array_equal(transformed.transpose(1, 0, 2), source), 'KV transpose inverse')
            target = out/(name+'-token-major.bin'); target.write_bytes(transformed.tobytes()); pin(target); data[name] = target
        symbols = dict(prefill_query=data[names[0]], prefill_key=data[names[1]], prefill_value=data[names[2]],
                       prefill_mask=data[names[3]], prefill_golden=data[names[4]])
        assembly = '.section .rodata\n'
        for name, path in symbols.items(): assembly += f'.balign 64\n.global {name}\n{name}:\n.incbin "{path}"\n'
        assembly += '.balign 4\n.global prefill_scale\nprefill_scale:\n.word 0x3db504f3\n.global prefill_q4\nprefill_q4:\n.word 0\n'
        (out/'data.S').write_text(assembly); pin(out/'data.S')
        records = json.loads((prior/'commands.json').read_text())
        compiles = {int(r['label'].split('-')[1]):list(r['argv']) for r in records if r['label'].startswith('compile-')}
        require(set(compiles) == set(range(18)), 'Common object inventory')
        objects = []
        for i in range(18):
            if i in (1, 10, 14): continue
            path = prior/f'{i}.o'; pin(path, report['artifacts'][str(path)]); objects.append(str(path))
        for i, source in ((1, HERE/'output_gqa6_main.c'), (10, out/'data.S')):
            cmd = compiles[i]; cmd[cmd.index('-c')+1] = str(source); obj = out/f'{i}.o'
            cmd[cmd.index('-o')+1] = str(obj); objects.append(str(obj))
            dep = [v for j, v in enumerate(cmd) if j not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
            text = run([*dep, '-M', '-MT', 'object'], 'deps-'+str(i))
            for name in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
                path = Path(name).resolve(strict=True)
                require(path in (source.resolve(), (out/'data.S').resolve()) or old.get(str(path)) == digest(path),
                        'New or changed common dependency: '+str(path)); pin(path)
            run(cmd, 'compile-'+str(i))
        link = [v for v in next(r['argv'] for r in records if r['label'] == 'link') if not v.endswith('.o')]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = objects
        elf = out/'output_gqa6.elf'; link[link.index('-o')+1] = str(elf)
        link = ['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        pin(link[link.index('-T')+1], old[str(Path(link[link.index('-T')+1]).resolve())])
        run(link, 'link'); pin(elf)
        dis = run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
        for symbol in ('quant_register_execute','quant_output_tile_execute','qbs_native_execute_command'):
            require('<'+symbol+'>:' in dis, 'Missing native runtime')
        require('<qbs_ref_execute>:' not in dis, 'Reference executor in measured image')
        verify_pins(old); verify_pins(pins); (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        state.update(state='GQA6_NATIVE_BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=digest(elf),
            source_pins_sha256=digest(out/'source-pins.json'), golden=str(symbols['prefill_golden']),
            kind='q8_0', heads=6, dim=128, visible=128, trials=4, commands_per_trial=8,
            reused_objects=15, rebuilt_objects=2, token_major=True,
            artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name != 'build.json'})
    except BaseException as exc: state.update(state='FAIL', error=repr(exc)); raise
    finally: (out/'build.json').write_text(json.dumps(state, indent=2)+'\n')


if __name__ == '__main__': main()
