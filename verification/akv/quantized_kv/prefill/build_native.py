#!/usr/bin/env python3
"""Fresh native QBS Prefill ABBA build from reviewed recipes and real captures."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
from run_replay import digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--kind', choices=('q4_0', 'q8_0'), required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    prior = ROOT / 'verification/out/grouped-pv-fresh-build-20261027-01'
    audit = ROOT / 'verification/out/quant-prefill-capture-audit-20261028-01'
    pins = json.loads((audit / 'manifest.json').read_text())
    assert json.loads((audit / 'result.json').read_text())['state'] == 'PASS'
    for name, sha in pins.items():
        assert digest(name) == sha, name
    commands = []
    def save(name, value):
        (out / name).write_text(json.dumps(value, indent=2) + '\n')
    def pin(path):
        p = Path(path).resolve(strict=True)
        h = digest(p)
        assert str(p) not in pins or pins[str(p)] == h, str(p)
        pins[str(p)] = h
    def execute(argv, label):
        argv = list(map(str, argv))
        pin(argv[0])
        commands.append(dict(label=label, argv=argv))
        save('commands.json', commands)
        with (out / (label + '.log')).open('w') as log:
            subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        return (out / (label + '.log')).read_text()
    pin(__file__); pin(HERE / 'run_replay.py'); pin(prior / 'commands.json')
    capture = ROOT / 'verification/out/quant-prefill-capture-20261028-01' / args.kind / 'prefill/block'
    model = Path('/home/wangwy/llama/llama-q4km-extract/src/models/qwen3.cpp')
    assert '1.0f/sqrtf(float(n_embd_head)), il);' in model.read_text()
    pin(model)
    params = json.loads((capture / 'attention_params-0.json').read_text())
    assert params['scale'] == 0.0883883 and params['max_bias'] == params['logit_softcap'] == 0
    assembly = out / 'data.S'
    blobs = [('prefill_query', 'attn_q_input-0.bin'), ('prefill_key', 'attn_k_input-0.bin'),
             ('prefill_value', 'attn_v_input-0.bin'), ('prefill_golden', 'kqv_out-0.bin')]
    assembly.write_text('.section .rodata,"a",@progbits\n' + ''.join(
        f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{capture / name}"\n'
        for symbol, name in blobs) + '.balign 4\n.global prefill_scale\nprefill_scale: .word 0x3db504f3\n'
        + f'.global prefill_q4\nprefill_q4: .word {int(args.kind == "q4_0")}\n')
    records = json.loads((prior / 'commands.json').read_text())
    objects = []
    for record in records:
        if not record['label'].startswith('compile-'):
            continue
        index = int(record['label'].split('-')[-1])
        if index > 12:
            continue
        cmd = list(record['argv'])
        if index == 1: cmd[cmd.index('-c') + 1] = str(HERE / 'native_main.c')
        if index == 10: cmd[cmd.index('-c') + 1] = str(assembly)
        source = Path(cmd[cmd.index('-c') + 1]); pin(source)
        obj = out / f'{index}.o'; objects.append(str(obj))
        cmd[cmd.index('-o') + 1] = str(obj)
        dep = [x for i, x in enumerate(cmd) if i not in
               (cmd.index('-c'), cmd.index('-o'), cmd.index('-o') + 1)] + ['-M', '-MT', 'object']
        text = execute(dep, 'deps-' + str(index))
        for p in shlex.split(text.replace('\\\n', ' ').split(':', 1)[1]): pin(p)
        execute(cmd, 'compile-' + str(index))
    assert len(objects) == 13
    original = next(r['argv'] for r in records if r['label'] == 'link')
    link = [x for x in original if not x.endswith('.o')]
    link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = objects
    elf = out / 'prefill.elf'
    link[link.index('-o') + 1] = str(elf)
    link = ['-Wl,-Map=' + str(out / 'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
    pin(link[link.index('-T') + 1])
    cc = Path(link[0])
    for lib in ('libm.a', 'libgcc.a', 'libc.a', 'libnosys.a'):
        pin(subprocess.check_output([cc, '-print-file-name=' + lib], text=True).strip())
    execute(link, 'link')
    dis = execute([cc.with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
    for symbol in ('qbs_native_execute_command', 'quantize_row_q8_0', 'dequantize_row_q8_0'):
        assert '<' + symbol + '>:' in dis, symbol
    assert '<qbs_ref_execute>:' not in dis
    for name, sha in pins.items(): assert digest(name) == sha, name
    save('source-pins.json', pins)
    save('build.json', dict(state='BUILT_NOT_EXECUTED', kind=args.kind, elf=str(elf),
         elf_sha256=digest(elf), source_pins_sha256=digest(out / 'source-pins.json'),
         scope='Real Qwen3 KV-head0 queries16..19, QBS on both sides, complete call ABBA',
         commands_per_trial=4, value_decodes=[74,20,20,74], outputs_per_trial=1024,
         performance_measured=False, reused_objects=0,
         artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file()}))
    print('BUILT_NOT_EXECUTED ' + str(elf))


if __name__ == '__main__': main()
