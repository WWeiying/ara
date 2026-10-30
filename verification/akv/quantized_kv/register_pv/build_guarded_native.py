#!/usr/bin/env python3
"""Fresh full-call Decode ABBA for the promoted kernel with early CSR guard."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREFILL = HERE.parent / 'prefill'
sys.path.insert(0, str(PREFILL))
sys.dont_write_bytecode = True
from run_replay import digest
from token_major import token_major
from build_production_native import capture_inputs
PRODUCTION = ROOT / 'software/akv/experimental/quantized_kv/prefill'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe-build', type=Path, required=True)
    parser.add_argument('--kind', choices=('q4_0', 'q8_0'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prior, out = args.recipe_build.resolve(strict=True), args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Independent fresh output required')
    report = json.loads((prior / 'build.json').read_text())
    records_path = prior / 'commands.json'
    old_pins_path = prior / 'source-pins.json'
    if (report['state'] != 'BUILT_NOT_EXECUTED' or report.get('token_major') is not True or
            digest(records_path) != report['artifacts'][str(records_path)] or
            digest(old_pins_path) != report['source_pins_sha256']):
        raise ValueError('Archived recipe identity')
    records = json.loads(records_path.read_text())
    compiles = [list(r['argv']) for r in records if r['label'].startswith('compile-')]
    if len(compiles) != 16:
        raise ValueError('Expected complete 16-object recipe')
    expected_sources = {0: 'quants.c', 1: 'native_strided_main.c', 2: 'qbs_runtime.c',
        3: 'qbs_native_riscv.c', 4: 'crt0.S', 5: 'printf.c', 6: 'string.c',
        7: 'serial.c', 8: 'util.c', 9: 'print_trap_cause.c', 10: 'data.S',
        11: 'ggml-quants.c', 12: 'pv_primitives.c', 13: 'runtime.c',
        14: 'mask.S', 15: 'runtime_strided.c'}
    for i, cmd in enumerate(compiles):
        if Path(cmd[cmd.index('-c') + 1]).name != expected_sources[i]:
            raise ValueError('Unexpected recipe source: ' + str(i))

    pins, commands = {}, []

    def pin(path):
        path = Path(path).resolve(strict=True)
        value = digest(path)
        if str(path) in pins and pins[str(path)] != value:
            raise ValueError('Input changed: ' + str(path))
        pins[str(path)] = value

    def run(argv, label):
        argv = list(map(str, argv))
        pin(argv[0])
        commands.append(dict(label=label, argv=argv))
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        with (out / (label + '.log')).open('w') as log:
            subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        return (out / (label + '.log')).read_text()

    audit = ROOT / 'verification/out/quant-prefill-capture-audit-20261028-01'
    audit_report = json.loads((audit / 'result.json').read_text())
    if audit_report['state'] != 'PASS':
        raise ValueError('Capture not audited')
    audited = json.loads((audit / 'manifest.json').read_text())
    capture = ROOT / 'verification/out/quant-prefill-capture-20261028-01' / args.kind / 'prefill/block'
    inputs = capture_inputs(capture, args.kind, audited)
    out.mkdir(parents=True)
    for path in (Path(__file__), PREFILL/'run_replay.py', PREFILL/'token_major.py', PREFILL/'build_production_native.py',
                 prior/'build.json', records_path, old_pins_path,
                 audit/'result.json', audit/'manifest.json', *inputs):
        pin(path)

    # Only physical byte coordinates change; no value is requantized.
    data = {}
    for name, width in (('attn_k_input-0', 72 if args.kind == 'q4_0' else 136),
                        ('attn_v_input-0', 136)):
        target = out / (name + '.bin')
        target.write_bytes(token_major((capture/(name+'.bin')).read_bytes(), width))
        pin(target)
        data[name] = target
    assembly = ['.section .rodata,"a",@progbits']
    for symbol, name in (('prefill_query', 'attn_q_input-0'), ('prefill_key', 'attn_k_input-0'),
                         ('prefill_value', 'attn_v_input-0'), ('prefill_golden', 'kqv_out-0')):
        payload = data.get(name, capture/(name+'.bin'))
        assembly.extend(['.balign 64', '.global '+symbol, symbol+':', f'.incbin "{payload}"'])
    assembly.extend(['.balign 4', '.global prefill_scale', 'prefill_scale:',
                     '.word 0x3db504f3', '.global prefill_q4', 'prefill_q4:',
                     '.word '+str(int(args.kind == 'q4_0'))])
    (out/'data.S').write_text('\n'.join(assembly)+'\n')
    (out/'mask.S').write_text('.section .rodata,"a",@progbits\n.balign 64\n'
        '.global prefill_mask\nprefill_mask:\n.incbin "'+str(capture/'attn_mask_input-0.bin')+'"\n')
    for index, source in ((1, HERE/'native_main.c'), (10, out/'data.S'), (14, out/'mask.S')):
        compiles[index][compiles[index].index('-c')+1] = str(source)
    candidate = list(compiles[15])
    candidate[candidate.index('-c')+1] = str(HERE/'runtime_entry_guard_candidate.c')
    compiles.append(candidate)
    objects = []
    for i, cmd in enumerate(compiles):
        obj = out / f'{i}.o'
        objects.append(str(obj))
        cmd[cmd.index('-o')+1] = str(obj)
        deps = [v for j, v in enumerate(cmd) if j not in
                (cmd.index('-c'), cmd.index('-o'), cmd.index('-o')+1)]
        text = run([*deps, '-M', '-MT', 'object'], 'deps-'+str(i))
        for path in shlex.split(text.replace('\\\n', ' ').split(':', 1)[1]):
            pin(path)
        run(cmd, 'compile-'+str(i))

    links = [r['argv'] for r in records if r['label'] == 'link']
    if len(links) != 1:
        raise ValueError('Ambiguous link recipe')
    link = [v for v in links[0] if not v.endswith('.o')]
    link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = objects
    elf = out/'register_pv.elf'
    link[link.index('-o')+1] = str(elf)
    link = ['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
    pin(link[link.index('-T')+1])
    for library in ('libm.a', 'libgcc.a'):
        pin(run([link[0], '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
                 '-print-file-name='+library], 'locate-'+library).strip())
    for program in ('cc1', 'as', 'ld'):
        pin(run([link[0], '-print-prog-name='+program], 'locate-'+program).strip())
    run(link, 'link')
    dis = run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
    for symbol in ('qbs_native_execute_command', 'akv_quant_strided_execute', 'quant_register_execute', 'main'):
        if '<'+symbol+'>:' not in dis:
            raise ValueError('Missing native execution: '+symbol)
    if '<dequantize_row_q8_0>:' in dis or '<qbs_ref_execute>:' in dis:
        raise ValueError('Scalar/reference binding drift')
    decoder = dis.split('<prefill_native_decode>:', 1)
    if len(decoder) != 2 or not all(op in decoder[1].split('\n\n', 1)[0]
                                   for op in ('vle8.v', 'vsext.vf4', 'vfcvt.f.x.v', 'vfmul.vf', 'vse32.v')):
        raise ValueError('Shared RVV V decode not present')
    for source in (HERE/'runtime_entry_guard_candidate.c',
                   PRODUCTION.parent/'register_pv/kernel.h',
                   PRODUCTION.parent/'register_pv/online.h',
                   PRODUCTION.parent/'register_pv/runtime.c'):
        if str(source) not in pins:
            raise ValueError('Register-PV dependency missing: '+str(source))
    if 'vfmacc.vf' not in dis or 'vle8.v' not in dis:
        raise ValueError('Candidate vector arithmetic missing')
    for path, expected in pins.items():
        if digest(path) != expected:
            raise ValueError('Input drift during build: '+path)
    (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
    result = dict(state='BUILT_NOT_EXECUTED', kind=args.kind, elf=str(elf), elf_sha256=digest(elf),
        source_pins_sha256=digest(out/'source-pins.json'), commands_per_trial=1, outputs_per_trial=256,
        value_decodes=[20,20,20,20], reused_objects=0, rebuilt_objects=17, whole_call=True,
        token_major=True, physical_kv_heads=8, value_binding='shared_rvv_q8_0',
        register_pv=True, early_entry_guard=True, recipe_only=str(prior),
        historical_source_identity_reused=False, capture_inputs_checked=10,
        scope='Qwen3 query19 GQA2 D128 visible20; shared RVV decode+PV versus register-PV; whole call, not whole model',
        performance_measured=False, artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file()})
    (out/'build.json').write_text(json.dumps(result, indent=2)+'\n')
    print('REGISTER_PV_BUILT_NOT_EXECUTED '+str(elf))


if __name__ == '__main__':
    main()
