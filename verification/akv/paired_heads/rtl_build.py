#!/usr/bin/env python3
"""Prepare and build only; never execute a simulator or modify canonical sources."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
from rtl_check import SHAPES, EXPECTED, require

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CAPTURE = Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252/kv128')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
HOST_FLAGS = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-fast-math',
              '-ffp-contract=off', '-frounding-math', '-fexcess-precision=standard',
              '-fno-builtin-fmaf', '-fno-tree-vectorize']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def gather(q, k, v, case):
    require(len(q) == 3072 and len(k) == len(v) == 131072, 'Capture length mismatch')
    head, d, t, stride = (case[n] for n in ('head', 'd', 'tokens', 'stride'))
    require(case in SHAPES, 'Unreviewed shape')
    query, key, value = bytearray(b'\xa5'*640), bytearray(b'\xa5'*16384), bytearray(b'\xa5'*16384)
    coeff, scales, acc = bytearray(b'\xa5'*512), bytearray(b'\xa5'*64), bytearray(b'\xa5'*1024)
    for row in range(2):
        start = (head*6+row)*256
        query[row*stride:row*stride+2*d] = q[start:start+2*d]
        for token in range(t):
            struct.pack_into('<f', coeff, row*256+token*4, .5 if (row+token)%2 == 0 else 1.)
        struct.pack_into('<f', scales, row*4, .5 if row == 0 else 1.)
        start = (head*256+row)*256
        acc[row*512:row*512+2*d] = v[start:start+2*d]
    for token in range(64):
        start = (head*256+token)*256
        key[token*2*d:(token+1)*2*d] = k[start:start+2*d]
        value[token*2*d:(token+1)*2*d] = v[start:start+2*d]
    # Coordinate check against original physical strides, including every byte.
    for token in range(64):
        for dim in range(d):
            offset = (head*256+token)*256+2*dim
            require(key[(token*d+dim)*2:(token*d+dim+1)*2] == k[offset:offset+2], 'K gather corruption')
            require(value[(token*d+dim)*2:(token*d+dim+1)*2] == v[offset:offset+2], 'V gather corruption')
    result = bytes(query+key+value+coeff+scales+acc)
    require(len(result) == 35008, 'Packed fixture layout mismatch')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT/'verification/out/akv-paired-heads-rtl-gate-build-20261023-01')
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []

    def pin(paths):
        for path in paths:
            path = Path(path).resolve(strict=True)
            digest = sha(path)
            require(str(path) not in pins or pins[str(path)] == digest, 'Input changed: '+str(path))
            pins[str(path)] = digest

    def run(argv, name):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        write_json(out/'commands.json', commands)
        with (out/(name+'.log')).open('x') as stream:
            subprocess.run(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=True)
        return (out/(name+'.log')).read_text()

    helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
    spec = importlib.util.spec_from_file_location('elf_tools', helper)
    elf_tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(elf_tools)
    common = ROOT/'apps/common'
    experimental = ROOT/'software/akv/experimental/paired_heads'
    hostcc = Path('/usr/bin/gcc')
    objdump, readelf = (CC.with_name('riscv64-unknown-elf-'+n) for n in ('objdump', 'readelf'))
    accepted = ROOT/'verification/out/akv-refill-attention-abba-20261023-01/manifest.json'
    simv = ROOT/'verification/out/qbacc-soc-20261023-02/build/sim/simv'
    pin([*HERE.glob('rtl_*'), helper, CC, hostcc, objdump, readelf, sys.executable,
         common/'arch.link.ld', accepted, experimental/'README.md',
         ROOT/'verification/akv/run_refill_overlap_probe.py'])
    acceptance_path = ROOT/'verification/qbs/results/qbacc-soc-20261023.json'
    acceptance = json.loads(acceptance_path.read_text())
    result_path = Path(acceptance['worker'])/'result.json'
    require(acceptance['state'] == 'PASS' and sha(result_path) == acceptance['result_sha256'], 'Image receipt mismatch')
    result = json.loads(result_path.read_text())
    require(result['state'] == 'PASS' and result['neighbors'] == 2, 'Image not accepted')
    pin([acceptance_path, result_path])
    for path, digest in result['evidence_sha256'].items():
        require(sha(path) == digest, 'Acceptance evidence drift')
        pin([path])
    image_pins_path = Path(acceptance['worker'])/'image-pins.json'
    require(str(image_pins_path) in result['evidence_sha256'], 'Missing accepted image pins')
    image_pins = json.loads(image_pins_path.read_text())
    require(str(simv) in image_pins, 'Wrong accepted image')
    actual_image = {str(simv), str(simv.parent/'simulator.conf'), str(simv.parent/'vcs_source_manifest.json')}
    actual_image.update(str(path) for path in simv.with_name('simv.daidir').rglob('*.so'))
    require(set(image_pins) == actual_image, 'Image component inventory drift')
    for path, digest in image_pins.items():
        require(sha(path) == digest, 'Actual image differs from acceptance')
        pin([path])
    config = dict(line.split('=', 1) for line in (simv.parent/'simulator.conf').read_text().splitlines())
    require(all(config.get(k) == v for k, v in dict(nr_lanes='4', vlen='1024', akv_enabled='1',
                akv_v2_enabled='1', sim_l2_mb='16', sim_l2_bytes='16777216', verify_axi_delay='0').items()), 'Incompatible image')
    manifest = json.loads((simv.parent/'vcs_source_manifest.json').read_text())
    require(manifest['schema_version'] == 1 and Path(manifest['repo_root']).resolve() == ROOT, 'Wrong image manifest')
    require(str(ROOT/'hardware/src/ara_sequencer.sv') in {item['path'] for item in manifest['files']}, 'Missing scalar-extract drain source')
    for item in manifest['files']:
        require(sha(item['path']) == item['sha256'], 'Image source drift: '+item['path'])
        pin([item['path']])
    original = json.loads(accepted.read_text())
    capture_files = [CAPTURE/'decode/block'/(n+s) for n in ('attn_q_input-0', 'attn_k_input-0',
                     'attn_v_input-0', 'attn_mask_input-0', 'kqv_out-0') for s in ('.bin', '.json')]
    capture_files += [CAPTURE/'replay/manifest.json', CAPTURE/'replay/cases/operator/decode/attention_core/case.json']
    require(all(original.get(str(f)) == sha(f) for f in capture_files), 'Accepted capture changed')
    pin(capture_files)
    for name, shape, stride, size, dtype in (
        ('attn_q_input-0', [128,1,12,1], [4,512,512,6144], 6144, 'f32'),
        ('attn_k_input-0', [128,256,2,1], [2,256,65536,131072], 131072, 'f16'),
        ('attn_v_input-0', [128,256,2,1], [2,256,65536,131072], 131072, 'f16')):
        meta = json.loads((CAPTURE/'decode/block'/(name+'.json')).read_text())
        require((meta['shape'],meta['strides'],meta['nbytes'],meta['type']) == (shape,stride,size,dtype), 'Capture geometry changed')
        require((CAPTURE/'decode/block'/(name+'.bin')).stat().st_size == size, 'Capture size changed')
    mask = list(struct.iter_unpack('<e', (CAPTURE/'decode/block/attn_mask_input-0.bin').read_bytes()))
    require(len(mask) == 256 and all(x[0] == (0. if i < 128 else -math.inf) for i, x in enumerate(mask)), 'Not genuine visible KV128 capture')
    q32 = (CAPTURE/'decode/block/attn_q_input-0.bin').read_bytes()
    require(all(math.isfinite(v) for (v,) in struct.iter_unpack('<f', q32)), 'Nonfinite Q')
    q = b''.join(struct.pack('<e', v) for (v,) in struct.iter_unpack('<f', q32))
    k, v = ((CAPTURE/'decode/block'/name).read_bytes() for name in ('attn_k_input-0.bin', 'attn_v_input-0.bin'))
    require(all(math.isfinite(x) for data in (q,k,v) for (x,) in struct.iter_unpack('<e', data)), 'Nonfinite F16 data')
    (out/'query_f16.bin').write_bytes(q)
    (out/'inputs.bin').write_bytes(b''.join(gather(q,k,v,c) for c in SHAPES))
    run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', HERE, '-p', 'rtl_test.py', '-v'], 'host-tests')
    for compiler in (hostcc, CC):
        run([compiler, '--version'], 'version-'+compiler.name)
        for tool in ('cc1', 'as', 'ld'):
            path = run([compiler, '-print-prog-name='+tool], compiler.name+'-'+tool).strip()
            pin([path if '/' in path else shutil.which(path)])
    pin([run([CC, '-print-libgcc-file-name'], 'libgcc-path').strip()])
    deps = run([hostcc, *HOST_FLAGS, '-M', '-MT', 'oracle', HERE/'rtl_oracle.c'], 'host-deps')
    pin(shlex.split(deps.replace('\\\n', ' ').split(':',1)[1]))
    oracle = out/'host_oracle'
    run([hostcc, *HOST_FLAGS, HERE/'rtl_oracle.c', '-lm', '-o', oracle], 'host-compile')
    dynamic = run(['/usr/bin/ldd', oracle], 'host-libraries')
    pin(re.findall(r'(/[^\s()]+)', dynamic))
    pin(['/usr/bin/ldd', '/usr/bin/objdump'])
    host_disasm = run(['/usr/bin/objdump', '-d', oracle], 'host-disassembly')
    require(re.search(r'call[^\n]*<fmaf@plt>', host_disasm), 'Host oracle must call actual libm fmaf')
    lines = run([oracle, out/'query_f16.bin', CAPTURE/'decode/block/attn_k_input-0.bin', out/'golden.bin'], 'host-oracle').splitlines()
    require(len(lines) == 3 and (out/'golden.bin').stat().st_size == 1536, 'Incomplete oracle')
    cases = []
    for c, line in zip(SHAPES, lines):
        prefix = f"ORACLE case={c['id']} head={c['head']} d={c['d']} tokens={c['tokens']} outputs={2*c['tokens']} fcsr="
        require(line.startswith(prefix) and line[len(prefix):].isdigit(), 'Oracle record mismatch')
        flags = int(line[len(prefix):])
        require(flags & ~31 == 0, 'Bad host flags')
        cases.append(dict(c, fcsr=flags|8))
    header = '#include <stdint.h>\nstatic const struct { unsigned head,d,tokens,stride,fcsr; } rtl_cases[3] = {\n'
    header += ''.join('{%d,%d,%d,%d,%d},\n' % tuple(c[k] for k in ('head','d','tokens','stride','fcsr')) for c in cases) + '};\n'
    (out/'rtl_data.h').write_text(header)
    blobs = {'rtl_inputs': out/'inputs.bin', 'rtl_golden': out/'golden.bin'}
    (out/'rtl_data.S').write_text('.section .rodata.rtl_inputs,"a",@progbits\n'+''.join(
        f'.balign 64\n.global {name}\n{name}:\n.incbin "{path}"\n' for name,path in blobs.items()))
    template = (common/'arch.link.ld').read_text()
    require(template.count('LENGTH = 0x00100000') == template.count('*(.bss)') == 1, 'Link template changed')
    (out/'rtl_link.ld').write_text(template.replace('ALIGNMENT','16').replace('LENGTH = 0x00100000','LENGTH = 0x01000000').replace('*(.bss)','*(.bss .bss.*)'))
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-O3',
             '-std=gnu11', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize', '-fno-common',
             '-ffunction-sections', '-fdata-sections', '-ffreestanding', '-fno-builtin',
             '-fno-tree-loop-distribute-patterns', '-DAKV_REFILL_OVERLAP=0', '-DNR_LANES=4', '-DVLEN=1024',
             '-Wno-unknown-pragmas', '-I'+str(ROOT), '-I'+str(out), '-I'+str(common),
             '-I'+str(ROOT/'software/akv/include'), '-I'+str(ROOT/'apps/include')]
    sources = [HERE/'rtl_main.c', HERE.parent/'qk_panel4_native/rtl_native.c',
               ROOT/'software/akv/src/akv_runtime.c', ROOT/'software/akv/src/akv_native_riscv.c',
               ROOT/'software/akv/src/akv_v2_attention_rvv.S', experimental/'attention_rvv.S',
               *[common/n for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')], out/'rtl_data.S']
    for i, source in enumerate(sources):
        deps = run([CC, *flags, '-M', '-MT', 'object', source], f'deps-{i}')
        pin(shlex.split(deps.replace('\\\n',' ').split(':',1)[1]))
    pin([out/'rtl_link.ld', out/'query_f16.bin', *blobs.values(), oracle])
    write_json(out/'source-pins.json', pins)
    objects = []
    for i, source in enumerate(sources):
        obj = out/f'{i}.o'
        extra = ['-Wall','-Wextra','-Werror'] if source == HERE/'rtl_main.c' else []
        run([CC, *flags, *extra, '-c', source, '-o', obj], f'compile-{i}')
        if source == common/'string.c':
            elf_tools.check_libc(run([objdump,'-dr',obj], 'libc-disassembly'))
        objects.append(obj)
    elf = out/'akv_paired_heads_rtl.elf'
    run([CC, *flags, '-static', '-nostdlib', '-nostartfiles', *objects, '-Wl,--gc-sections',
         '-Wl,-Map='+str(out/'link.map'), '-T', out/'rtl_link.ld', '-lgcc', '-o', elf], 'link')
    disasm = run([objdump,'-d',elf], 'disassembly')
    symbols = ('akv_device_query','akv_native_info','rtl_akv_full','rtl_akv_release',
               'akv_v2_compute_scores_f16_generic','akv_v2_update_outputs_f16_generic',
               'akv_experimental_qk_f16_pair_panel4','akv_experimental_pv_f16_pair')
    for name in symbols:
        require(f'<{name}>:' in disasm, 'Missing linked native symbol: '+name)
        if name != 'akv_native_info':
            require(re.search(r'\b(?:jalr?|jr?)\b[^\n]*<'+name+r'>',disasm), 'Missing real call: '+name)
    snapshot_pattern = r'vmv\.x\.s\s+\w+,\s*v12\n[^\n]*fence\s+rw,rw\n[^\n]*frcsr\s+\w+\n[^\n]*csrr\s+\w+,\s*vcsr'
    require(len(re.findall(snapshot_pattern, disasm)) == 2, 'Missing exact QK/PV drain+CSR snapshot instructions')
    sections = elf_tools.alloc_sections(elf)
    require(min(s['address'] for s in sections) >= 0x80000000 and
            max(s['address']+s['bytes'] for s in sections) < 0x81000000-65536, 'ELF memory bounds')
    run([readelf,'-lW',elf], 'elf-segments')
    require(all(sha(p) == digest for p,digest in pins.items()), 'Source/tool/input drift during build')
    artifacts = {str(f):sha(f) for f in sorted(out.iterdir()) if f.is_file()}
    write_json(out/'build.json', dict(state='BUILT_NOT_EXECUTED', execution='NOT_RUN',
        elf=str(elf), elf_sha256=sha(elf), source_pins=str(out/'source-pins.json'),
        source_pins_sha256=sha(out/'source-pins.json'), artifact_sha256=artifacts,
        post_pins_match=True, cases=cases, sections=sections, expected=EXPECTED,
        capture=str(CAPTURE), capture_provenance=str(accepted), simv=str(simv),
        accepted_image_receipt=str(acceptance_path), accepted_image_pins=image_pins,
        input_contract='Genuine KV128 first two Q heads of KV group; token0..63 and first D channels; derived subsets, not new model captures',
        qk_oracle='F32 Q converted via Python struct <e RNE; independent host libm fmaf d0..D-1; explicit FE-to-RISC-V flags OR sticky DZ8',
        pv_oracle='Canonical generic F16 regression only; NOT independent FP16 oracle. Real V token0/1 initial accumulators; alternating .5/1 coefficients; old scales .5/1. Not softmax/whole-Attention.',
        comparison='Full on-chip byte comparisons; compact UART hashes and first mismatch only; VCSR5 and RNE FCSR8 reset per phase',
        scope='Focused QK/PV correctness; requires numeric + hardware work + independent UVM and run pre/post pins; no execution/performance acceptance',
        suggested_timeout_seconds=10800, walltime_estimate='Unmeasured; compact UART targets lower overhead, no <30 minute guarantee'))
    print(json.dumps(dict(state='BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=sha(elf))))


if __name__ == '__main__':
    main()
