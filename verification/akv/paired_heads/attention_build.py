#!/usr/bin/env python3
"""Build-only derived GQA2 Attention ABBA; no simulator or old object reuse."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/qbs'))
from run_half_scale_soc import digest, hashes, image_files

CAPTURE = Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252/kv128')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    def pin(paths):
        for name in paths:
            path = Path(name).resolve(strict=True)
            value = digest(path)
            require(str(path) not in pins or pins[str(path)] == value, 'Input drift: '+str(path))
            pins[str(path)] = value
    def write(name, value):
        (out/name).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    def run(argv, name, env=None):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        write('commands.json', commands)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(argv, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                           timeout=120, check=True)
        return (out/(name+'.log')).read_text()
    def load(path):
        return json.loads(Path(path).read_text())

    common = ROOT/'apps/common'
    experiment = ROOT/'software/akv/experimental/paired_heads'
    helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
    spec = importlib.util.spec_from_file_location('paired_attention_elf_tools', helper)
    elf_tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(elf_tools)
    generator = ROOT/'apps/llama_q4km_operator/script/gen_data.py'
    accepted_capture = ROOT/'verification/out/akv-refill-attention-abba-20261023-01/manifest.json'
    object_gate = ROOT/'verification/out/akv-paired-heads-object-20261023-01/result.json'
    proof = load(object_gate)
    require(proof['state'] == 'HOST_OBJECT_CHECK_PASS' and proof['mapped_matrix_cases'] == 768 and
            proof['rejected_mutations'] == 9, 'Wrong object gate')
    for group in ('sources', 'artifacts'):
        require(hashes(map(Path, proof[group])) == proof[group], 'Object gate drift')
    objdump = CC.with_name('riscv64-unknown-elf-objdump')
    readelf = CC.with_name('riscv64-unknown-elf-readelf')
    pin([Path(__file__), HERE/'attention_abba.c', HERE/'attention_README.md',
         experiment/'native_bench.c', experiment/'attention_rvv.S', experiment/'README.md',
         generator, helper, ROOT/'verification/qbs/run_half_scale_soc.py',
         object_gate, accepted_capture, common/'arch.link.ld', CC, objdump, readelf, sys.executable])

    acceptance = ROOT/'verification/out/qbacc-soc-accept-20261023-02'
    gate = load(acceptance/'result.json')
    require(gate['state'] == 'PASS' and gate['neighbors'] == 2 and gate['probe']['state'] == 'PASS', 'Image not accepted')
    require(hashes(map(Path, gate['evidence_sha256'])) == gate['evidence_sha256'], 'Image acceptance evidence drift')
    image_pin_path = acceptance/'image-pins.json'
    require(str(image_pin_path) in gate['evidence_sha256'], 'Missing image receipt')
    simv = ROOT/'verification/out/qbacc-soc-20261023-02/build/sim/simv'
    image = hashes(image_files(simv))
    require(image == load(image_pin_path), 'Accepted image inventory/hash mismatch')
    pin([acceptance/'result.json', *map(Path, gate['evidence_sha256']), *image_files(simv)])
    config = dict(line.split('=', 1) for line in (simv.parent/'simulator.conf').read_text().splitlines())
    require(all(config.get(k) == v for k, v in dict(nr_lanes='4', vlen='1024', akv_enabled='1',
        akv_v2_enabled='1', sim_l2_mb='16', sim_l2_bytes='16777216', verify_axi_delay='0').items()), 'Image configuration')
    manifest = load(simv.parent/'vcs_source_manifest.json')
    require(manifest['schema_version'] == 1 and Path(manifest['repo_root']).resolve() == ROOT, 'Image source root')
    for row in manifest['files']:
        require(digest(Path(row['path'])) == row['sha256'], 'Image/source mismatch: '+row['path'])
        pin([row['path']])

    names = ('attn_q_input-0', 'attn_k_input-0', 'attn_v_input-0', 'attn_mask_input-0', 'kqv_out-0')
    capture_files = [CAPTURE/'decode/block'/(n+s) for n in names for s in ('.json', '.bin')]
    case_path = CAPTURE/'replay/cases/operator/decode/attention_core/case.json'
    capture_files += [CAPTURE/'replay/manifest.json', case_path]
    original = load(accepted_capture)
    require(all(original.get(str(f)) == digest(f) for f in capture_files), 'Original capture drift')
    pin(capture_files)
    shapes = [('attn_q_input-0', 'f32', [128,1,12,1], [4,512,512,6144], 6144),
              ('attn_k_input-0', 'f16', [128,256,2,1], [2,256,65536,131072], 131072),
              ('attn_v_input-0', 'f16', [128,256,2,1], [2,256,65536,131072], 131072),
              ('kqv_out-0', 'f32', [1536,1,1,1], [4,6144,6144,6144], 6144)]
    for name, kind, shape, strides, nbytes in shapes:
        meta = load(CAPTURE/'decode/block'/(name+'.json'))
        require((meta['type'], meta['shape'], meta['strides'], meta['nbytes']) ==
                (kind, shape, strides, nbytes), 'Tensor geometry: '+name)
        data = (CAPTURE/'decode/block'/(name+'.bin')).read_bytes()
        require(len(data) == nbytes and all(math.isfinite(x) for (x,) in struct.iter_unpack(
                '<f' if kind == 'f32' else '<e', data)), 'Invalid finite data: '+name)
    mask = (CAPTURE/'decode/block/attn_mask_input-0.bin').read_bytes()
    require(len(mask) == 512 and all(x == (0.0 if i < 128 else -math.inf)
        for i, (x,) in enumerate(struct.iter_unpack('<e', mask))), 'Expected KV128 prefix')
    case = load(case_path)
    require(case['atol'] == .004 and case['rtol'] == .002 and case['max_bias'] == 0 and
            case.get('logit_softcap', 0) == 0 and not case['v_transposed'], 'Original tolerance/features')

    # Reuse the original full capture generator. Head selection is runtime work.
    env = dict(os.environ, Q4KM_CAPTURE_ROOT=str(CAPTURE), PYTHONDONTWRITEBYTECODE='1')
    data_source = run([sys.executable, '-B', generator, 'operator/decode/attention_core', 'akv_v2'], 'generate-data', env)
    (out/'data.S').write_text(data_source)
    template = (common/'arch.link.ld').read_text()
    require(template.count('LENGTH = 0x00100000') == template.count('*(.bss)') == 1, 'Linker template')
    (out/'link.ld').write_text(template.replace('ALIGNMENT', '16').replace(
        'LENGTH = 0x00100000', 'LENGTH = 0x01000000').replace('*(.bss)', '*(.bss .bss.*)'))
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
        '-O3', '-std=gnu11', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
        '-fno-common', '-ffunction-sections', '-fdata-sections', '-ffreestanding', '-fno-builtin',
        '-fno-tree-loop-distribute-patterns', '-DAKV_REFILL_OVERLAP=0', '-DNR_LANES=4', '-DVLEN=1024',
        '-Wno-unknown-pragmas', '-I'+str(ROOT), '-I'+str(common), '-I'+str(ROOT/'apps/include')]
    sources = [HERE/'attention_abba.c', experiment/'native_bench.c',
        *[ROOT/'software/akv/src'/n for n in ('akv_runtime.c', 'akv_native_riscv.c', 'akv_features.c',
                                            'akv_v2_attention_rvv.S')], experiment/'attention_rvv.S',
        *[common/n for n in ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')], out/'data.S']
    for i, source in enumerate(sources):
        dep = run([CC, *flags, '-M', '-MT', 'object', source], f'deps-{i}')
        pin(shlex.split(dep.replace('\\\n', ' ').split(':', 1)[1]))
    run([CC, '--version'], 'gcc-version')
    for tool in ('cc1', 'as', 'ld'):
        name = run([CC, '-print-prog-name='+tool], tool+'-path').strip()
        pin([name if '/' in name else shutil.which(name)])
    for lib in ('libm.a', 'libgcc.a'):
        pin([run([CC, '-print-file-name='+lib], lib+'-path').strip()])
    pin([out/'link.ld'])
    write('source-pins.json', pins)
    objects = []
    for i, source in enumerate(sources):
        obj = out/f'{i}.o'
        run([CC, *flags, '-c', source, '-o', obj], f'compile-{i}')
        if source == common/'string.c':
            elf_tools.check_libc(run([objdump, '-dr', obj], 'libc-disassembly'))
        objects.append(obj)
    elf = out/'akv_paired_heads_attention_abba.elf'
    run([CC, *flags, '-static', '-nostdlib', '-nostartfiles', *objects, '-Wl,--gc-sections',
         '-Wl,-Map='+str(out/'link.map'), '-T', out/'link.ld', '-lm', '-lgcc', '-o', elf], 'link')
    disassembly = run([objdump, '-d', elf], 'disassembly')
    # GCC inlines the canonical NULL-features convenience wrapper at -O3.
    symbols = ('akv_experimental_attention_pair_bench', 'akv_attention_execute_v2_with_features_native',
        'akv_v2_compute_scores_f16_generic', 'akv_v2_update_outputs_f16_generic',
        'akv_experimental_qk_f16_pair_panel4', 'akv_experimental_pv_f16_pair')
    for name in symbols:
        require('<'+name+'>:' in disassembly, 'Missing native symbol: '+name)
    for name in ('akv_experimental_attention_pair_bench', 'akv_attention_execute_v2_with_features_native',
                 'akv_v2_compute_scores_f16_generic', 'akv_v2_update_outputs_f16_generic',
                 'akv_experimental_qk_f16_pair_panel4', 'akv_experimental_pv_f16_pair'):
        require(re.search(r'\b(?:jalr?|jr?)\b[^\n]*<'+name+r'>', disassembly), 'Missing real call: '+name)
    require('vfncvt.f.f.w' in disassembly and 'vmv.x.s' in disassembly, 'Missing Q prep/drain')
    sections = elf_tools.alloc_sections(elf)
    require(min(s['address'] for s in sections) >= 0x80000000 and
        max(s['address']+s['bytes'] for s in sections) < 0x81000000-65536, '16MiB/stack capacity')
    run([readelf, '-lW', elf], 'elf-segments')
    require(hashes(map(Path, pins)) == pins and hashes(image_files(simv)) == image, 'Post-build pin drift')
    write('build.json', dict(state='BUILT_NOT_EXECUTED', execution='NOT_RUN',
        elf=str(elf), elf_sha256=digest(elf), source_pins_sha256=digest(out/'source-pins.json'),
        artifact_sha256={str(f): digest(f) for f in out.iterdir() if f.is_file()},
        post_pins_match=True, sections=sections, simv=str(simv), accepted_image_pins=image,
        capture=str(CAPTURE), source_heads=[0,1,6,7], source_kv_heads=[0,1],
        provenance='Derived GQA2 subset of genuine Qwen2.5 KV128 Decode capture; NOT a Qwen3 Decode capture',
        tolerance=dict(atol=case['atol'], rtol=case['rtol']), scale=case['scale'],
        expected=dict(trials=4, modes=[0,1,1,0], outputs_per_trial=512, commands=3864,
            off=dict(commands=1542, column_load=1024, column_panel=0, row_load=512, replay_bytes=262144),
            on=dict(commands=390, column_load=128, column_panel=128, row_load=256, replay_bytes=131072),
            per_trial=dict(v2_full=2, v2_refill=2, release=2, q_external_bytes=1024,
                           kv_external_bytes=131072, read_payload_bytes=132224, read_ranges=518)),
        scope='Complete plan/native execute including Q conversion, admission, softmax/normalization; checks excluded. Build-only; no numerical/performance PASS.',
        runtime_selection='Explicit benchmark-only per-call mode; no environment/canonical/runtime deployment changes; baseline original generics'))
    print(json.dumps(dict(state='BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=digest(elf))))


if __name__ == '__main__':
    main()
