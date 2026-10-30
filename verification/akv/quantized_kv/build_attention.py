#!/usr/bin/env python3
"""Build a complete real six-head quantized-KV Attention ABBA inquiry."""
import argparse
import importlib.util
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/akv/paired_heads'))
import attention_run as s
from capture_host import validate_capture


def scale_source_checks(model, graph, parameters):
    s.require('1.0f/sqrtf(float(n_embd_head)), il);' in model and
              'GGML_ASSERT(n_embd_head == hparams.n_embd_head_k());' in model,
              'Qwen2 scale expression/shape contract changed')
    s.require('build_attn_mha(q, k, v, kq_b, kq_mask, sinks, v_mla, kq_scale, il)' in graph and
              'ggml_flash_attn_ext(ctx0, q, k, v, kq_mask, kq_scale, hparams.f_max_alibi_bias,' in graph,
              'Graph scale forwarding changed')
    s.require(parameters.get('op') == 'FLASH_ATTN_EXT' and parameters.get('scale') == 0.0883883 and
              parameters.get('max_bias') == parameters.get('logit_softcap') == 0,
              'Only frozen zero-bias/zero-softcap Qwen2 capture admitted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('q8_0', 'q4_0'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    old = ROOT/'verification/out/akv-quantkv-rvv-qbs-build-20261024-01'
    pv = ROOT/'verification/out/akv-quantkv-pv-primitives-20261024-01'
    capture = ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'
    commands = []

    def execute(argv, label):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        s.atomic_json(out/'commands.json', commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        return (out/(label+'.log')).read_text()

    try:
        report = s.read_json(old/'build.json')
        s.require(report['state'] == 'BUILT_NOT_EXECUTED' and report['post_pins_match'] is True,
                  'Wrong original primitive/data build')
        s.require(s.digest(old/'source-pins.json') == report['source_pins_sha256'], 'Original receipt drift')
        pins = s.read_json(old/'source-pins.json')
        s.merge_pins(pins, report['artifact_sha256'])
        primitive = s.read_json(pv/'result.json')
        s.require(primitive['state'] == 'ACTUAL_GGML_QUANTIZED_V_PRIMITIVES_COMPILED' and
                  s.digest(pv/'source-pins.json') == primitive['source_pins_sha256'], 'PV primitive receipt drift')
        s.merge_pins(pins, s.read_json(pv/'source-pins.json'))
        s.merge_pins(pins, primitive['artifact_sha256'])
        s.verify_pins(pins)
        captured = s.read_json(capture/'result.json')
        directory = capture/('capture-k-'+a.kind+'-v-q8_0')
        checked = validate_capture(directory, a.kind)
        s.require(checked == captured['captures'][a.kind] and checked['visible_tokens'] == 128,
                  'Real capture drift')
        s.merge_pins(pins, checked['file_sha256'])
        data = directory/'decode/block'
        qmeta = s.read_json(data/'attn_q_input-0.json')
        vmeta = s.read_json(data/'attn_v_input-0.json')
        gmeta = s.read_json(data/'kqv_out-0.json')
        s.require(qmeta['type'] == 'f32' and qmeta['shape'] == [128, 1, 12, 1] and
                  qmeta['strides'] == [4, 512, 512, 6144] and
                  vmeta['type'] == 'q8_0' and vmeta['shape'] == [128, 256, 2, 1] and
                  vmeta['strides'] == [34, 136, 34816, 69632] and
                  gmeta['type'] == 'f32' and gmeta['shape'] == [1536, 1, 1, 1], 'Unexpected tensor layout')
        model = Path('/home/wangwy/llama/llama-q4km-extract/src/models/qwen2.cpp')
        graph = model.parent.parent/'llama-graph.cpp'
        for path in (model, graph):
            s.require(pins.get(str(path)) == s.digest(path), 'Scale source not pinned by original capture')
        scale_source_checks(model.read_text(), graph.read_text(), s.read_json(data/'attention_params-0.json'))
        host_cc = Path(shutil.which('gcc')).absolute()
        scale_probe = out/'scale-probe'
        execute([host_cc, '-std=c11', '-O0', '-fno-fast-math', '-fno-builtin', HERE/'attention_scale.c',
                 '-lm', '-o', scale_probe], 'compile-scale')
        scale_bits = execute([scale_probe], 'exact-scale').strip()
        s.require(scale_bits == '3db504f3', 'Exact Qwen2 FP32 scale differs')
        # Emit words, not decimal text; both the scale and provenance remain auditable.
        assembly = out/'attention-data.S'
        blobs = [('attention_query', 'attn_q_input-0.bin'), ('attention_key', 'attn_k_input-0.bin'),
                 ('attention_value', 'attn_v_input-0.bin'), ('attention_golden', 'kqv_out-0.bin')]
        assembly.write_text('.section .rodata,"a",@progbits\n'+''.join(
            f'.balign 64\n.global {name}\n{name}:\n.incbin "{data/file}"\n' for name, file in blobs)+
            f'.balign 4\n.global attention_scale\nattention_scale: .word 0x{scale_bits}\n'+
            f'.global attention_key_kind\nattention_key_kind: .word {int(a.kind == "q4_0")}\n')
        previous = s.read_json(old/'commands.json')
        compiles = [r['argv'] for r in previous if '-c' in r['argv'] and str(HERE/'rvv_qbs_main.c') in r['argv']]
        links = [r['argv'] for r in previous if '-nostdlib' in r['argv']]
        s.require(len(compiles) == len(links) == 1, 'Original compile/link ambiguity')
        main = list(compiles[0])
        main[main.index(str(HERE/'rvv_qbs_main.c'))] = str(HERE/'attention_main.c')
        main[main.index('-ffp-contract=off')] = '-ffp-contract=fast'
        main[main.index('-o')+1] = str(out/'attention-main.o')
        deps = [x for i, x in enumerate(main) if i not in
                (main.index('-c'), main.index('-o'), main.index('-o')+1)] + ['-M', '-MT', 'object']
        text = execute(deps, 'deps-main')
        s.merge_pins(pins, s.hashes(Path(x).resolve(strict=True) for x in
            shlex.split(text.replace('\\\n', ' ').split(':', 1)[1])))
        execute(main, 'compile-main')
        data_command = [str(assembly) if x == str(HERE/'attention_main.c') else x for x in main]
        data_command[data_command.index('-o')+1] = str(out/'attention-data.o')
        execute(data_command, 'compile-data')
        elf = out/'quantized_attention.elf'
        link = [str(out/'attention-main.o') if x == str(old/'0.o') else
                '-Wl,-Map='+str(out/'link.map') if x == '-Wl,-Map='+str(old/'link.map') else x
                for x in links[0] if x not in (str(old/'3.o'), str(old/'10.o'))]
        s.require(str(old/'10.o') in links[0] and str(old/'0.o') not in link, 'Object replacement failed')
        link[link.index('-o')+1] = str(elf)
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = [
            str(out/'attention-data.o'), str(pv/'0.o'), str(pv/'1.o')]
        execute(link, 'link')
        cc = Path(main[0])
        disassembly = execute([cc.with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
        for symbol in ('quantize_row_q8_0', 'dequantize_row_q8_0', 'quant_kv_ggml_mad_f32',
                       'quant_kv_ggml_scale_f32', 'qbs_native_execute_command'):
            s.require('<'+symbol+'>:' in disassembly, 'Missing actual primitive '+symbol)
        s.require('<qbs_ref_execute>:' not in disassembly, 'On-target scalar oracle retained')
        helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
        spec = importlib.util.spec_from_file_location('quant_attention_elf', helper)
        elf_tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(elf_tools)
        sections = elf_tools.alloc_sections(elf)
        s.require(min(x['address'] for x in sections) >= 0x80000000 and
                  max(x['address']+x['bytes'] for x in sections) < 0x81000000-65536, 'ELF bounds')
        s.merge_pins(pins, s.hashes([Path(__file__), HERE/'attention_scale.c', host_cc.resolve(), scale_probe,
            helper, old/'build.json', old/'source-pins.json', pv/'result.json', pv/'source-pins.json']))
        s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json', pins)
        s.atomic_json(out/'build.json', dict(state='BUILT_NOT_EXECUTED', execution='NOT_RUN',
            kind=a.kind, elf=str(elf), elf_sha256=s.digest(elf), simv=report['simv'],
            accepted_image_pins=report['accepted_image_pins'], post_pins_match=True,
            source_pins_sha256=s.digest(out/'source-pins.json'),
            artifact_sha256=s.hashes(x for x in out.iterdir() if x.is_file()), sections=sections,
            trials=4, heads=6, head_dim=128, visible_tokens=128, kv_head=0, outputs_per_trial=768,
            expected_commands=16, exact_scale_bits=scale_bits, scale_origin='Derived from pinned Qwen2 graph expression; JSON is rounded',
            baseline='Reconstructed GGML head-major online schedule with original RVV primitives, not untouched GGML operator',
            fp_contract='No fast-math; explicit contraction-fast for both schedules and production primitives',
            scope='Complete original KV-head-0 GQA group, both schedules include Query quantization, QK, online softmax, V decode, PV and drain; not whole model'))
        print('BUILT_NOT_EXECUTED '+a.kind+' heads=6 tokens=128 commands=16')
    except BaseException as exc:
        s.atomic_json(out/'build.json', dict(state='FAIL', execution='NOT_RUN', error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
