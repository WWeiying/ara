#!/usr/bin/env python3
"""Build-only ordinary RVV / generic AKV / paired AKV, with offline head crops."""
import argparse
from contextlib import redirect_stdout
import importlib.util
import io
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
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/qbs'))
from run_half_scale_soc import digest, hashes, image_files

CAPTURE = Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252/kv128')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
HEADS = (0, 1, 6, 7)
ORDER = ('rvv', 'generic', 'paired', 'paired', 'generic', 'rvv')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_crop(original, cropped):
    require(len(original) == 6144 and len(cropped) == 2048, 'Crop byte extent')
    for head, source_head in enumerate(HEADS):
        for dim in range(128):
            for byte in range(4):
                require(cropped[(head*128+dim)*4+byte] == original[(source_head*128+dim)*4+byte],
                        'Head/dimension/byte crop mismatch')


def crop_heads(data):
    cropped = b''.join(data[head*512:(head+1)*512] for head in HEADS)
    validate_crop(data, cropped)
    return cropped


def self_test():
    data = b''.join(struct.pack('<I', 0x41000000+head*128+dim) for head in range(12) for dim in range(128))
    cropped = crop_heads(data)
    require(list(struct.unpack('<512I', cropped)) ==
            [0x41000000+head*128+dim for head in HEADS for dim in range(128)], 'Independent coordinate fixture')
    rejected = 0
    for bad in (cropped[:-1], bytes([cropped[0]^1])+cropped[1:], data[:2048]):
        try:
            validate_crop(data, bad)
        except ValueError:
            rejected += 1
    require(rejected == 3, 'Crop mutations accepted')
    return dict(coordinate_words=512, coordinate_bytes=2048, rejected_mutations=3)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def elf_bytes(elf, address, size):
    data = elf.read_bytes()
    require(data[:6] == b'\x7fELF\x02\x01', 'Expected little-endian ELF64')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    for i in range(header[10]):
        ph = struct.unpack_from('<IIQQQQQQ', data, header[5]+i*header[9])
        if ph[0] == 1 and ph[3] <= address and address+size <= ph[3]+ph[5]:
            offset = ph[2]+address-ph[3]
            return data[offset:offset+size]
    raise ValueError('No file-backed ELF segment for data assertion')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT/'verification/out/akv-paired-heads-threeway-build-20261023-01')
    p.add_argument('--self-test', action='store_true')
    a = p.parse_args()
    tests = self_test()
    if a.self_test:
        print(json.dumps(dict(state='HOST_SELF_TEST_PASS', **tests)))
        return
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []

    def pin(paths):
        for path in paths:
            path = Path(path).resolve(strict=True)
            value = digest(path)
            require(str(path) not in pins or pins[str(path)] == value, 'Input drift: '+str(path))
            pins[str(path)] = value

    def write(name, value):
        (out/name).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')

    def run(argv, name):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        write('commands.json', commands)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
        return (out/(name+'.log')).read_text()

    def load(path):
        return json.loads(Path(path).read_text())

    common = ROOT/'apps/common'
    experiment = ROOT/'software/akv/experimental/paired_heads'
    helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
    generator = ROOT/'apps/llama_q4km_operator/script/gen_data.py'
    elf_tools = load_module('threeway_elf_tools', helper)
    gen = load_module('threeway_capture_generator', generator)
    gen.CAPTURE_ROOT = CAPTURE
    accepted_capture = ROOT/'verification/out/akv-refill-attention-abba-20261023-01/manifest.json'
    objdump, readelf, nm = (CC.with_name('riscv64-unknown-elf-'+tool) for tool in ('objdump','readelf','nm'))
    pin([HERE/'threeway_main.c', Path(__file__), HERE/'threeway_README.md', helper, generator,
         ROOT/'verification/qbs/run_half_scale_soc.py', experiment/'native_bench.c',
         experiment/'attention_rvv.S', experiment/'README.md', accepted_capture,
         common/'arch.link.ld', CC, objdump, readelf, nm, sys.executable])

    accepted_receipt = ROOT/'verification/qbs/results/qbacc-soc-20261023.json'
    receipt = load(accepted_receipt)
    acceptance = Path(receipt['worker'])
    require(receipt['state'] == 'PASS' and digest(acceptance/'result.json') == receipt['result_sha256'], 'Image receipt chain')
    gate = load(acceptance/'result.json')
    require(gate['state'] == 'PASS' and gate['neighbors'] == 2 and gate['probe']['state'] == 'PASS', 'Image not accepted')
    require(hashes(map(Path, gate['evidence_sha256'])) == gate['evidence_sha256'], 'Image acceptance drift')
    require(str(acceptance/'image-pins.json') in gate['evidence_sha256'], 'Missing accepted image inventory')
    simv = ROOT/'verification/out/qbacc-soc-20261023-02/build/sim/simv'
    image = hashes(image_files(simv))
    require(image == load(acceptance/'image-pins.json'), 'Image inventory/hash mismatch')
    pin([accepted_receipt, acceptance/'result.json', *gate['evidence_sha256'], *image_files(simv)])
    config = dict(line.split('=',1) for line in (simv.parent/'simulator.conf').read_text().splitlines())
    require(all(config.get(k) == v for k,v in dict(nr_lanes='4',vlen='1024',akv_enabled='1',akv_v2_enabled='1',
                sim_l2_mb='16',sim_l2_bytes='16777216',verify_axi_delay='0').items()), 'Incompatible image')
    manifest = load(simv.parent/'vcs_source_manifest.json')
    require(manifest['schema_version'] == 1 and Path(manifest['repo_root']).resolve() == ROOT, 'Image source root')
    require(str(ROOT/'hardware/src/ara_sequencer.sv') in {r['path'] for r in manifest['files']}, 'Missing drain source')
    for row in manifest['files']:
        require(digest(Path(row['path'])) == row['sha256'], 'Image source drift: '+row['path'])
        pin([row['path']])

    names = ('attn_q_input-0','attn_k_input-0','attn_v_input-0','attn_mask_input-0','kqv_out-0')
    case_path = CAPTURE/'replay/cases/operator/decode/attention_core/case.json'
    capture_files = [CAPTURE/'decode/block'/(name+suffix) for name in names for suffix in ('.json','.bin')]
    capture_files += [CAPTURE/'replay/manifest.json',case_path]
    original = load(accepted_capture)
    require(all(original.get(str(f)) == digest(f) for f in capture_files), 'Accepted capture drift')
    pin(capture_files)
    for name, kind, shape, strides, size in (
        ('attn_q_input-0','f32',[128,1,12,1],[4,512,512,6144],6144),
        ('attn_k_input-0','f16',[128,256,2,1],[2,256,65536,131072],131072),
        ('attn_v_input-0','f16',[128,256,2,1],[2,256,65536,131072],131072),
        ('kqv_out-0','f32',[1536,1,1,1],[4,6144,6144,6144],6144)):
        meta = load(CAPTURE/'decode/block'/(name+'.json'))
        data = (CAPTURE/'decode/block'/(name+'.bin')).read_bytes()
        require((meta['type'],meta['shape'],meta['strides'],meta['nbytes']) == (kind,shape,strides,size), 'Tensor geometry: '+name)
        require(len(data) == size and all(math.isfinite(x) for (x,) in struct.iter_unpack('<f' if kind == 'f32' else '<e',data)), 'Invalid finite data')
    mask = (CAPTURE/'decode/block/attn_mask_input-0.bin').read_bytes()
    require(len(mask) == 512 and all(x == (0. if i < 128 else -math.inf)
            for i,(x,) in enumerate(struct.iter_unpack('<e',mask))), 'Not genuine KV128 mask')
    case = load(case_path)
    require(case['atol'] == .004 and case['rtol'] == .002 and case['max_bias'] == 0 and
            case.get('logit_softcap',0) == 0 and not case['v_transposed'], 'Capture feature/tolerance mismatch')
    kind, flag, args, params, blobs = gen.make_spec('operator/decode/attention_core','rvv')
    require(kind == 'attention_core' and flag == gen.ATTENTION_RVV and args[:5] == [128,1,12,256,2], 'Original generator spec')
    for name, original_name in zip(('input_a','input_b','input_c','input_d','golden'), names):
        require(blobs[name]['data'] == CAPTURE/'decode/block'/(original_name+'.bin'), 'Generator resolves unexpected capture')
    crop_report = []
    for name, source_name, shape, strides in (
        ('input_a','attn_q_input-0',[128,1,4,1],[4,512,512,2048]),
        ('golden','kqv_out-0',[512,1,1,1],[4,2048,2048,2048])):
        source = CAPTURE/'decode/block'/(source_name+'.bin')
        cropped = crop_heads(source.read_bytes())
        data_path = out/(name+'.bin')
        data_path.write_bytes(cropped)
        meta = dict(load(source.with_suffix('.json')), shape=shape, strides=strides, nbytes=2048)
        meta.update(derived=True, source=str(source), source_heads=list(HEADS))
        write(name+'.json',meta)
        blobs[name] = gen.tensor(out/(name+'.json'))
        crop_report.append(dict(name=name, source=str(source), source_sha256=digest(source),
            output=str(data_path), sha256=digest(data_path), verified_bytes=2048, source_heads=list(HEADS)))
    args[2] = 4
    require(blobs['input_a']['shape'] == [128,1,4,1] and blobs['golden']['shape'] == [512,1,1,1], 'Cropped tensor shapes')
    words = [gen.MAGIC,1,gen.KIND[kind],flag,*args,*map(gen.f32_bits,params)]
    for name in ('input_a','input_b','input_c','input_d','golden'):
        words.extend([*blobs[name]['shape'],blobs[name]['nbytes']])
    require(len(words) == 45, 'Original case_config_t ABI extent')
    config_bytes = struct.pack('<45I',*words)
    (out/'config.bin').write_bytes(config_bytes)
    stream = io.StringIO()
    with redirect_stdout(stream):
        print('.section .rodata,"a",@progbits\n.balign 64\n.global llama_case_config\nllama_case_config:')
        for word in words:
            print(f'.long 0x{word:08x}')
        print('.balign 8\n.global llama_case_name\nllama_case_name:\n.asciz "qwen25_kv128/derived_heads_0_1_6_7/threeway"')
        for name,value in blobs.items():
            gen.emit_blob('llama_'+name,value)
        print('.section .bss,"aw",@nobits\n.balign 64\n.global threeway_output_before\nthreeway_output_before:\n.zero 64')
        print('.global llama_attention_output_start\nllama_attention_output_start:\n.zero 2048')
        print('.global llama_attention_output_end\nllama_attention_output_end:')
        print('.global threeway_output_after\nthreeway_output_after:\n.zero 64')
    (out/'data.S').write_text(stream.getvalue())
    write('data-proof.json',dict(state='HOST_DATA_CHECK_PASS',self_test=tests,crops=crop_report,
        args=args, params=params, flag=flag, config_sha256=digest(out/'config.bin'),
        unchanged={name:dict(path=str(blobs[name]['data']),sha256=digest(blobs[name]['data'])) for name in ('input_b','input_c','input_d')}))
    template = (common/'arch.link.ld').read_text()
    require(template.count('LENGTH = 0x00100000') == template.count('*(.bss)') == 1, 'Link template changed')
    (out/'link.ld').write_text(template.replace('ALIGNMENT','16').replace('LENGTH = 0x00100000','LENGTH = 0x01000000').replace('*(.bss)','*(.bss .bss.*)'))
    flags = ['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax',
        '-O3','-std=gnu11','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize',
        '-fno-common','-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin',
        '-fno-tree-loop-distribute-patterns','-DAKV_REFILL_OVERLAP=0','-DNR_LANES=4','-DVLEN=1024',
        '-Wno-unknown-pragmas','-I'+str(ROOT),'-I'+str(common),'-I'+str(ROOT/'apps/include')]
    sources = [HERE/'threeway_main.c',experiment/'native_bench.c',
        *[ROOT/'software/akv/src'/name for name in ('akv_runtime.c','akv_native_riscv.c','akv_features.c','akv_v2_attention_rvv.S')],
        experiment/'attention_rvv.S', *[common/name for name in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')], out/'data.S']
    for i,source in enumerate(sources):
        dep = run([CC,*flags,'-M','-MT','object',source],f'deps-{i}')
        pin(shlex.split(dep.replace('\\\n',' ').split(':',1)[1]))
    run([CC,'--version'],'gcc-version')
    for tool in ('cc1','as','ld'):
        path = run([CC,'-print-prog-name='+tool],tool+'-path').strip()
        pin([path if '/' in path else shutil.which(path)])
    for lib in ('libm.a','libgcc.a'):
        pin([run([CC,'-print-file-name='+lib],lib+'-path').strip()])
    pin([out/'link.ld',out/'config.bin',out/'input_a.json',out/'golden.json',*[b['data'] for b in blobs.values()]])
    write('source-pins.json',pins)
    objects = []
    for i,source in enumerate(sources):
        obj = out/f'{i}.o'
        run([CC,*flags,'-c',source,'-o',obj],f'compile-{i}')
        if source == common/'string.c':
            elf_tools.check_libc(run([objdump,'-dr',obj],'libc-disassembly'))
        objects.append(obj)
    elf = out/'akv_paired_heads_threeway.elf'
    run([CC,*flags,'-static','-nostdlib','-nostartfiles',*objects,'-Wl,--gc-sections',
         '-Wl,-Map='+str(out/'link.map'),'-T',out/'link.ld','-lm','-lgcc','-o',elf],'link')
    disasm = run([objdump,'-d',elf],'disassembly')
    required = ('threeway_ordinary_rvv','threeway_native','akv_experimental_attention_pair_bench',
        'akv_attention_execute_v2_with_features_native','akv_v2_compute_scores_f16_generic',
        'akv_v2_update_outputs_f16_generic','akv_experimental_qk_f16_pair_panel4','akv_experimental_pv_f16_pair')
    for name in required:
        require('<'+name+'>:' in disasm and re.search(r'\b(?:jalr?|jr?)\b[^\n]*<'+name+r'>',disasm), 'Missing actual call: '+name)
    require('run_attention_tiled_rvv' not in disasm and 'captured_operator_main' not in disasm, 'Unintended app/tiled path linked')
    require('vfncvt.f.f.w' in disasm and re.search(r'vmv\.x\.s\s+\w+,v0\n[^\n]*fence\s+rw,rw',disasm), 'Missing conversion/drain')
    require('frcsr' in disasm and re.search(r'csrr\s+\w+,vcsr',disasm), 'Missing CSR snapshots')
    symbol_text = run([nm,'-n','--defined-only',elf],'symbols')
    symbols = {m[3]:int(m[1],16) for line in symbol_text.splitlines()
               if (m := re.fullmatch(r'([0-9a-fA-F]+)\s+(\S)\s+(\S+)',line))}
    start,end = (symbols['llama_attention_output_'+s] for s in ('start','end'))
    require(end-start == 2048 and symbols['threeway_output_before']+64 == start and
            symbols['threeway_output_after'] == end, 'Output guards contaminate ABI capacity')
    require(elf_bytes(elf,symbols['llama_case_config'],180) == config_bytes, 'Linked config ABI mismatch')
    for name,value in blobs.items():
        begin,finish = (symbols['llama_'+name+'_'+s] for s in ('start','end'))
        require(finish-begin == value['nbytes'] and elf_bytes(elf,begin,value['nbytes']) == value['data'].read_bytes(), 'Linked blob bytes differ: '+name)
    sections = elf_tools.alloc_sections(elf)
    require(min(s['address'] for s in sections) >= 0x80000000 and
        max(s['address']+s['bytes'] for s in sections) < 0x81000000-65536,'Image/stack bounds')
    run([readelf,'-lW',elf],'elf-segments')
    require(hashes(map(Path,pins)) == pins and hashes(image_files(simv)) == image,'Post-build pin drift')
    write('build.json',dict(state='BUILT_NOT_EXECUTED',execution='NOT_RUN',elf=str(elf),elf_sha256=digest(elf),
        source_pins=str(out/'source-pins.json'),source_pins_sha256=digest(out/'source-pins.json'),post_pins_match=True,
        artifact_sha256={str(f):digest(f) for f in out.iterdir() if f.is_file()},simv=str(simv),accepted_image_pins=image,
        sections=sections, output_address=start,output_capacity=end-start,shared_output_all_paths=True,
        capture=str(CAPTURE),source_heads=list(HEADS),source_kv_heads=[0,1],tolerance=dict(atol=.004,rtol=.002),
        scale=case['scale'],host_self_tests=tests,linked_abi_and_all_blob_bytes_verified=True,
        expected=dict(trials=6,order=list(ORDER),outputs_per_trial=512,commands=3864,
            rvv=dict(commands=0),generic=dict(commands=1542,column_load=1024,column_panel=0,row_load=512,replay_bytes=262144),
            paired=dict(commands=390,column_load=128,column_panel=128,row_load=256,replay_bytes=131072),
            per_native_trial=dict(v2_full=2,v2_refill=2,release=2,q_external_bytes=1024,kv_external_bytes=131072,
                                  read_payload_bytes=132224,read_ranges=518)),
        provenance='Offline Q/golden heads0,1,6,7 subset of Qwen2.5 KV128; K/V/mask untouched; NOT Qwen3 capture',
        numerical='All512 finite and original tolerance; rawbits/FCSR exact repeats within each variant; generic/paired exact; RVV may differ bits/flags',
        timing='Common output address; real Q conversion, AKV query/plan/admission, complete execute/stores/drain; no artificial RVV cap queries; poison/check/crop excluded',
        scope='Preparation only. Later requires actual per-trial commands, mandatory raw hardware summary, independent UVM, source/image/artifact pre/post pins; no runtime PASS or benefit claim'))
    print(json.dumps(dict(state='BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=digest(elf))))


if __name__ == '__main__':
    main()
