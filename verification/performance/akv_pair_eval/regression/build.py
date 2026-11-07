#!/usr/bin/env python3
"""Prepare the frozen SmolLM2 GQA3 ABBA ELF, only after explicit seal-ready."""
import argparse
import hashlib
import io
import json
import math
import re
import shlex
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
DEFAULT_OUTPUT = OUT / 'akv_pair_smollm_build_20261107_01'
CAPTURE_ROOT = Path('/home/wangwy/llama/captures/smollm2-135m-q4_k_m-attention-gqa3-dag-probe')
CAPTURE = CAPTURE_ROOT / 'decode/block'
SDK_COMMIT = '785084122af984c1dd3fd6318efaf70cdcb017e8'
SDK_TREE = '099017ee4f6543417e4d666a5e0958ce175defe5'
COMMON_TREE = '027626ca2e2524cafbcb61b5b44b70fce9ec1cff'
ARCHIVE_SHA = 'c3d88d4d50151b7ba72801aef154549454585097e10285d1b6b31f8c0fe1d3dd'
REFERENCE_SOURCE = 'verification/performance/chain_profile/f16_decode/reference.c'
REFERENCE_SHA = '4580ef7695c4733ef4c243222ef4ed6d84a4d5d4bc0bd8863bc52915f2950819'
NATIVE_SHA = '016e0bf04e73a7a7f7ea92a84ef7834d5cb5b01f363d23ff5d132190f037549b'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
HOST_CC = Path('/usr/bin/clang')
OWN_FILES = ('build.py', 'main.c', 'check.py', 'test_regression.py', 'reference.c')
SCHEMA = 'akv-pair-smollm-regression-v1'
ORDER = [0, 1, 1, 0]
IMAGE = dict(NrLane=4, VLEN=1024, AXI=128, L2sim_bytes=16777216,
             shared_integer_multiply=True, EnableSharedFma=0)
FIXED_IMAGE_SHA = '3ed8bc6b761d49664162b9f3b45e525e5c051923618950cbdb2b38ea403486a6'
SHAPE = dict(batches=1, query_tokens=1, query_heads=3, kv_heads=1, head_dim=64,
             query_head_indices=[0, 1, 2], kv_head_index=0, valid_tokens=5,
             kv_capacity=256, tile_tokens=64, tile_lengths=[5], output_elements=192)
FILES = dict(decode_query=768, decode_query_f16=384, decode_key=32768,
             decode_value=32768, decode_mask=512, decode_golden=768)
MEMORY = dict(data_bytes=68736, data_hash=0xd636ad98f595076c,
              query_hash=0xc0c9c4d3e8675b8a, query_f32_hash=0x5da28c877da723c8,
              key_hash=0x9bdb4b2c075c7f44, value_hash=0xa85850eff7123637,
              mask_hash=0x2fdbebd65d54caf1, guard_bytes=6304, guard_hash=0xa177688d5985c405)
SOURCE_SHA = {
    'model.json': '6be826dfa37d8d72611a846e575628b4f72be22a332b8b5a20bd0ea010978045',
    'replay/manifest.json': '5d5ccc3d9ba93046a20816fb3fa1358588c7233e331e0b5255a2df1b611ddc5f',
    'replay/cases/operator/decode/attention_core/case.json':
        'd1c79769bc5a9c8725c029108d1ff7939b1e35f742fa2f11172b9c203e825433',
    'decode/block/attn_q_input-0.bin': '86f23dea566a6bb0b9c40ecbe6da3d8cc1b10bc067acc34d39687ca8d9721041',
    'decode/block/attn_q_input-0.json': 'b2602e3efc6ccfd70f0bf7bb308213d63a0ce49b21e5cc210be65821b384b5f9',
    'decode/block/attn_k_input-0.bin': 'd8c1342c7485cf163fb7fcdaf2f6b0cce5c9d81058421ffc32408ec4a31ea7ea',
    'decode/block/attn_k_input-0.json': '696275a48403a2be68b419acc2ec698c3012504297c3dd00f9ed238aeb7cdf32',
    'decode/block/attn_v_input-0.bin': '2ce51a2505a27fa00e8a41a0343c37745f11eaeb9db685837dfb1c05fbfaadd0',
    'decode/block/attn_v_input-0.json': '44382e936565ba2cd790826a1b8318b4692b93066b94c0f94847ca89407c0602',
    'decode/block/attn_mask_input-0.bin': '1820bc37f284a960b20f447ff6a49ba5f7a2119f31abe940d3b2508cf9e7b2a4',
    'decode/block/attn_mask_input-0.json': 'a79ddf137b48b41f581d65e5133e3c89727228cc88b4637906c3b864d65477ac',
    'decode/block/kqv_out-0.bin': 'f6c8d5c9dfc2659c744e15dc46a1260df519f8e7f544538c42d1daf67e0c09e4',
    'decode/block/kqv_out-0.json': 'a54e94b3a1f169e7f110b48a7f5d83d9c5b6d31850cfe7c9862e5b10896d43b6',
}
TARGET_SDK = ('akv_runtime.c', 'akv_decode.c', 'akv_features.c', 'akv_prefill_reference.c',
              'akv_native_riscv.c', 'akv_v2_native_riscv.c', 'akv_v2_attention_rvv.S', 'akv_attention_rvv.S')
COMMON = ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fnv64(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64)-1)
    return value


def mathematical_crosscheck(blobs):
    q = struct.unpack('<192f', blobs['decode_query'])
    k = struct.unpack('<16384e', blobs['decode_key'])
    v = struct.unpack('<16384e', blobs['decode_value'])
    golden = struct.unpack('<192f', blobs['decode_golden'])
    require(all(math.isfinite(x) for x in (*q, *k[:320], *v[:320], *golden)), 'Nonfinite input/golden')
    maximum_error = 0.0
    for h in range(3):
        scores = [math.fsum(q[h*64+d]*k[t*64+d] for d in range(64))*0.125 for t in range(5)]
        weights = [math.exp(s-max(scores)) for s in scores]
        denominator = math.fsum(weights)
        for d in range(64):
            actual = math.fsum(weights[t]*v[t*64+d] for t in range(5))/denominator
            expected = golden[h*64+d]
            error = abs(actual-expected)
            require(error <= 0.003+0.02*abs(expected), 'Independent F64 mapping/golden mismatch')
            maximum_error = max(maximum_error, error)
    return maximum_error


def read_capture(root=CAPTURE_ROOT):
    root = Path(root).resolve()
    pins = {}
    for relative, digest in SOURCE_SHA.items():
        p = root / relative
        require(p.is_file() and not p.is_symlink() and sha(p) == digest, 'Frozen capture drift: '+relative)
        pins[str(p)] = digest
    model = json.loads((root / 'model.json').read_text())
    require((model['n_embd'], model['n_head'], model['n_head_kv']) == (576, 9, 3) and
            model['metadata']['general.basename'] == 'smollm2', 'Not the original SmolLM2 topology')
    case = json.loads((root / 'replay/cases/operator/decode/attention_core/case.json').read_text())
    require(case['scale'] == 0.125 and case['max_bias'] == 0 and not case['v_transposed'], 'Attention parameters drift')
    roles = {
        'decode_query': ('attn_q_input', 'f32', [64, 1, 9, 1], [4, 256, 256, 2304], 2304),
        'decode_key': ('attn_k_input', 'f16', [64, 256, 3, 1], [2, 128, 32768, 98304], 98304),
        'decode_value': ('attn_v_input', 'f16', [64, 256, 3, 1], [2, 128, 32768, 98304], 98304),
        'decode_mask': ('attn_mask_input', 'f16', [256, 1, 1, 1], [2, 512, 512, 512], 512),
        'decode_golden': ('kqv_out', 'f32', [576, 1, 1, 1], [4, 2304, 2304, 2304], 2304),
    }
    blobs = {}
    for name, (role, dtype, shape, strides, size) in roles.items():
        p = root / 'decode/block' / (role+'-0')
        meta, raw = json.loads(p.with_suffix('.json').read_text()), p.with_suffix('.bin').read_bytes()
        require((meta['type'], meta['shape'], meta['strides'], meta['nbytes'], len(raw)) ==
                (dtype, shape, strides, size, size), 'Metadata/layout mismatch: '+role)
        # These exact contiguous metadata strides make KV0 and its own Q0/1/2 prefixes.
        blobs[name] = raw[:FILES[name]]
    mask = struct.unpack('<256H', blobs['decode_mask'])
    require(mask == (0,)*5+(0xfc00,)*251, 'Only the original visible-five mask is allowed')
    q = struct.unpack('<192f', blobs['decode_query'])
    blobs['decode_query_f16'] = b''.join(struct.pack('<e', x) for x in q)
    blobs = {name: blobs[name] for name in FILES}
    error = mathematical_crosscheck(blobs)
    provenance = dict(model='SmolLM2-135M-Instruct-Q4_K_M', source_receipt_verified=False,
        source_commit_claim=model.get('llama_commit'), model_json_sha256=SOURCE_SHA['model.json'],
        scope='Existing hashed capture/metadata, not a reproduced clean-checkout inference. '
              'KVhead0 and only its original Qheads0/1/2; original cap256 KV/mask and first192 F32 golden.',
        crosscheck='Independent F64 dot/stable-softmax/weighted-sum using original F32 Q and F16 KV',
        mapping_max_abs_error=error, source_hashes=SOURCE_SHA)
    return blobs, pins, provenance


def memory_expected(blobs, native):
    require(set(blobs) == set(FILES) and all(len(blobs[n]) == s for n, s in FILES.items()) and
            len(native) == 768, 'Wrong linked data sizes')
    data = b''.join(blobs[n] for n in FILES)+native
    # 8 outer guards + all inactive accumulator/score/state bytes + 32-byte ABI tail.
    guard_bytes = 8*64 + 3*(256-64)*2 + 5*256*2 + 3*(64-5)*4 + 5*64*4 + 5*12 + 32
    require(hashlib.sha256(native).hexdigest() == NATIVE_SHA, 'Frozen independent tile64 oracle drift')
    memory = dict(data_bytes=len(data), data_hash=fnv64(data),
        query_hash=fnv64(blobs['decode_query_f16']), query_f32_hash=fnv64(blobs['decode_query']),
        key_hash=fnv64(blobs['decode_key']), value_hash=fnv64(blobs['decode_value']),
        mask_hash=fnv64(blobs['decode_mask']), guard_bytes=guard_bytes,
        guard_hash=fnv64(bytes([0xa5])*guard_bytes))
    require(memory == MEMORY, 'Frozen host payload/query/guard FNV drift')
    return memory


def expected_header(memory):
    return ''.join('#define SMOL_EXPECT_'+k.upper()+' UINT64_C(0x%x)\n' % v for k, v in sorted(memory.items()))


def data_assembly(data):
    lines = ['.section .data.smol_capture,"aw",@progbits', '.balign 64',
             '.global data_guard_before', 'data_guard_before:', '.fill 64,1,0xa5',
             '.global data_begin', 'data_begin:']
    for name in [*FILES, 'native_golden']:
        lines += ['.balign 64', '.global '+name, name+':', '.incbin '+json.dumps(str(data/(name+'.bin')))]
    return '\n'.join(lines+['.global data_end', 'data_end:', '.global data_guard_after',
        'data_guard_after:', '.fill 64,1,0xa5', '.section .note.GNU-stack,"",@progbits'])+'\n'


def unpack_archive(archive, inputs):
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = tar.getmembers()
        require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and
                    '..' not in Path(m.name).parts for m in members), 'Unsafe archive member')
        tar.extractall(inputs, filter='data')


def build(output=DEFAULT_OUTPUT, seal_ready=False):
    require(seal_ready is True, 'No cross-build before explicit --seal-ready')
    output = Path(output).resolve()
    require(output == DEFAULT_OUTPUT.resolve() and not output.exists(), 'Use the agreed fresh output')
    blobs, pins, provenance = read_capture()
    pins.update({str(HERE/n): sha(HERE/n) for n in OWN_FILES})
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args])
    require(git('rev-parse', SDK_COMMIT+':software/akv').decode().strip() == SDK_TREE and
            git('rev-parse', SDK_COMMIT+':apps/common').decode().strip() == COMMON_TREE and
            hashlib.sha256(git('show', SDK_COMMIT+':'+REFERENCE_SOURCE)).hexdigest() == REFERENCE_SHA,
            'Frozen SDK/common/reference contract drift')
    output.mkdir()
    inputs, data = output/'inputs', output/'data'
    inputs.mkdir()
    data.mkdir()
    archive = git('archive', SDK_COMMIT, 'software/akv', 'apps/common')
    require(hashlib.sha256(archive).hexdigest() == ARCHIVE_SHA, 'Exact SDK archive identity mismatch')
    archive_file = inputs/'sdk-785084122.tar'
    archive_file.write_bytes(archive)
    unpack_archive(archive, inputs)
    for name, blob in blobs.items():
        (data/(name+'.bin')).write_bytes(blob)
    sdk, common = inputs/'software/akv', inputs/'apps/common'
    commands = []
    def run(label, argv):
        argv = list(map(str, argv))
        p = subprocess.run(argv, cwd=output, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=180)
        log = output/(label+'.log')
        log.write_text(p.stdout)
        commands.append(dict(label=label, argv=argv, cwd=str(output), returncode=p.returncode))
        (output/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        require(p.returncode == 0, label+' failed: '+p.stdout[-3000:])
        return p.stdout.strip()
    run('host-tests', [sys.executable, '-B', HERE/'test_regression.py', '-v'])
    run('host-reference-compile', [HOST_CC, '-std=gnu11', '-O2', '-fno-fast-math', '-ffp-contract=off',
        HERE/'reference.c', '-lm', '-o', output/'reference'])
    run('host-reference-run', [output/'reference', data, data/'native_golden.bin'])
    native = (data/'native_golden.bin').read_bytes()
    memory = memory_expected(blobs, native)
    (output/'expected.h').write_text(expected_header(memory))
    (output/'data.S').write_text(data_assembly(data))
    linker = (common/'arch.link.ld').read_text()
    require(linker.count('LENGTH = 0x00100000') == 1, 'Linker template changed')
    (output/'link.ld').write_text(linker.replace('ALIGNMENT', '16').replace(
        'LENGTH = 0x00100000', 'LENGTH = 0x01000000'))
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-O3',
        '-DNDEBUG', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize', '-ffunction-sections',
        '-fdata-sections', '-std=gnu11', '-Wall', '-Wextra', '-Wno-unknown-pragmas',
        '-DNR_LANES=4', '-DVLEN=1024', '-DAKV_REFILL_OVERLAP=0',
        '-I'+str(sdk/'include'), '-I'+str(common), '-I'+str(output)]
    sources = [HERE/'main.c', output/'data.S', *[common/n for n in COMMON], *[sdk/'src'/n for n in TARGET_SDK]]
    objects = []
    for i, src in enumerate(sources):
        obj = output/('%02d_%s.o' % (i, src.stem))
        require(not obj.exists(), 'No old runtime object reuse')
        extra = ['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns'] if src.name == 'string.c' else []
        run('compile-'+str(i), [CC, *flags, *extra, '-MMD', '-MF', obj.with_suffix('.d'), '-c', src, '-o', obj])
        objects.append(obj)
    elf = output/'akv_pair_smollm.elf'
    run('link', [CC, *flags[:4], '-static', '-nostdlib', '-nostartfiles', *objects,
        '-Wl,--gc-sections', '-Wl,-Map='+str(output/'link.map'), '-T', output/'link.ld',
        '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
    for label, name, options in [('disassembly', 'objdump', ['-d']), ('segments', 'readelf', ['-lW'])]:
        tool = CC.with_name(CC.name.replace('gcc', name))
        pins[str(tool.resolve())] = sha(tool.resolve())
        text = run(label, [tool, *options, elf])
        if label == 'disassembly':
            require(re.search(r'<full_call(?:\.[^>]*)?>:', text) is not None, 'Missing full-call symbol')
            for symbol in ('akv_decode_execute', 'akv_attention_execute_v2_native',
                           'akv_experimental_qk_f16_pair_panel4', 'akv_experimental_pv_f16_pair',
                           'akv_v2_compute_scores_f16_generic', 'akv_v2_update_outputs_f16_generic', 'getenv'):
                require('<'+symbol+'>:' in text, 'Missing target call graph symbol: '+symbol)
            require('bench_active' not in text and 'bench_pair_enabled' not in text,
                    'Experimental mutable wrapper leaked into ELF')
    for compiler in (CC, HOST_CC):
        pins[str(compiler.resolve())] = sha(compiler.resolve())
        run(compiler.name+'-version', [compiler, '--version'])
    for lib in ('libm.a', 'libc.a', 'libgcc.a', 'libnosys.a'):
        p = Path(run('locate-'+lib, [CC, *flags[:2], '-print-file-name='+lib])).resolve()
        pins[str(p)] = sha(p)
    for tool in ('cc1', 'as', 'ld'):
        p = Path(run('locate-'+tool, [CC, '-print-prog-name='+tool])).resolve()
        pins[str(p)] = sha(p)
    for obj in objects:
        deps = obj.with_suffix('.d').read_text().replace('\\\n', ' ').split(':', 1)[1]
        for name in shlex.split(deps):
            p = Path(name).resolve()
            pins[str(p)] = sha(p)
    for base in (inputs, data):
        pins.update({str(p): sha(p) for p in base.rglob('*') if p.is_file()})
    for name in ('expected.h', 'data.S', 'link.ld'):
        pins[str(output/name)] = sha(output/name)
    require(all(sha(p) == h for p, h in pins.items()), 'Source/input drift during build')
    pinfile = output/'source-pins.json'
    pinfile.write_text(json.dumps(pins, indent=2, sort_keys=True)+'\n')
    manifest = dict(schema=SCHEMA, state='BUILT_NOT_EXECUTED', target_executed=False,
        rtl_executed=False, performance_measured=False, hardware_changed=False,
        elf=str(elf), elf_sha256=sha(elf), sdk_head=SDK_COMMIT, sdk_tree=SDK_TREE, common_tree=COMMON_TREE,
        sdk_archive=str(archive_file), sdk_archive_sha256=sha(archive_file),
        SDKpins={str(p.relative_to(inputs)): sha(p) for p in sdk.rglob('*') if p.is_file()},
        source_pins=str(pinfile), source_pins_sha256=sha(pinfile),
        dirty_asm_excluded=True, sdk_unmodified=True, all_runtime_objects_recompiled=True,
        old_runtime_objects_reused=False, objects=list(map(str, objects)), objects_recompiled=len(objects),
        compile_commands=str(output/'commands.json'), data=str(data), capture=str(CAPTURE),
        provenance=provenance, shape=SHAPE, order=ORDER, image_contract=IMAGE,
        fixed_image_sha256=FIXED_IMAGE_SHA, memory_expected=memory,
        initial_csr=dict(fcsr=0, vcsr=0, vstart=0),
        environment=dict(AKV_PAIR_HEADS='0/1/1/0 local fixture; all other names NULL'),
        total_roi='Same F32->F16 conversion + device/capability query + decode validation/plan/native + final drain',
        toolchain=dict(target=str(CC.resolve()), host=str(HOST_CC.resolve()), zcc=False),
        native_reference=dict(source_origin=SDK_COMMIT+':'+REFERENCE_SOURCE, source_sha256=REFERENCE_SHA,
                              parameterization='D64/H3/T5/cap256/scale0.125; no backend linked'),
        golden=dict(captured=str(data/'decode_golden.bin'), captured_sha256=sha(data/'decode_golden.bin'),
            native_tile64=str(data/'native_golden.bin'), native_tile64_sha256=sha(data/'native_golden.bin'),
            capture_atol=0.003, capture_rtol=0.02, native_atol=0.0002, native_rtol=0.003),
        work=dict(per_call_commands=[209, 92, 92, 209], total_commands=602),
        checker=dict(entry=str(HERE/'check.py'), function='check_run(log_path, build_dir)',
                     vector_function='check_vector_workcounts(vector_path, build_dir)'),
        artifacts={str(p): sha(p) for p in output.rglob('*') if p.is_file()})
    (output/'build.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--seal-ready', action='store_true')
    args = parser.parse_args()
    result = build(args.output, args.seal_ready)
    print(json.dumps({k: result[k] for k in ('schema', 'state', 'elf', 'sdk_head')}))
