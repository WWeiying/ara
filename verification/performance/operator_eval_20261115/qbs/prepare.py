#!/usr/bin/env python3
"""Build-only current-SDK QBS/native and actual llama RVV projection slices."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
BASE = ROOT / 'verification/performance/chain_profile/q6_decode/build.py'
ROWS = OUT / 'stage2_qwen3_rows8_20261109_02'
ROWS_PINS = '8f8775bcccc4bc2da08d14fca7f554d66786fde4337650242453714d8422d2b0'
ROWS_RECEIPT = '8bcd4e59062b98d086bcf0aa11d30380269b4aa4b6b7695968619037376ca6c5'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
TOOLCHAIN = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')


def catalog():
    return json.loads((HERE / 'cases.json').read_text())


def helper():
    spec = importlib.util.spec_from_file_location('qbs_checked_build', BASE)
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    return b


def capture(case, b, base, data):
    if case['source'] == 'qwen3_rows8_q4k':
        receipt, pins = ROWS / 'result.json', ROWS / 'source-pins.json'
        base.require(base.digest(receipt) == ROWS_RECEIPT and base.digest(pins) == ROWS_PINS,
                     'Qwen3 eight-row capture receipt/inventory identity drift')
        record = json.loads(receipt.read_text())
        directory = ROWS / case['operator']
        meta = json.loads((directory / 'operator.json').read_text())
        base.require(record['state'] == 'CAPTURED_NOT_BENCHMARKED' and record['source_pins_match']
                     and record['rows'] == 8 and record['k'] == 2048 and meta in record['views']
                     and meta['distinct_rows'] == 8 and meta['activation_shape'] == [2048, 8]
                     and meta['captured_weight_shape'] == [2048, 128] and meta['profile'] == 'Q4_K',
                     'Not the reviewed eight-distinct-row full-K capture')
        a, w = directory / 'activation_f32.bin', directory / 'weight_q4_K.bin'
        base.require(base.digest(a) == meta['activation_sha256'] and
                     base.digest(w) == meta['weight_sha256'], 'Capture bytes changed')
        base.require(a.stat().st_size == 8*2048*4 and w.stat().st_size == 128*8*144,
                     'Capture bytes/geometry mismatch')
        for p in (receipt, pins, directory / 'operator.json', a, w):
            b.pin(p)
        activation = a.read_bytes()[:case['m']*2048*4]
        weights = w.read_bytes()[:case['n']*8*144]
        provenance = dict(capture=str(directory), original_inventory=str(pins),
                          metadata=meta, selection='first M distinct rows, first N weight rows, full K')
    else:
        b.pins.update(base.audit_capture(base.CAPTURE, base.OLD_BUILD))
        activation = (base.CAPTURE / 'attn_norm-0_f32.bin').read_bytes()
        weights = (base.CAPTURE / 'attn_v.bin').read_bytes()[:case['n']*8*210]
        provenance = dict(capture=str(base.CAPTURE), phase='decode', position=40,
                          audited_original_build=str(base.OLD_BUILD), selection='first N rows, full K')
    (data / 'input_f32.bin').write_bytes(activation)
    (data / 'weights_row.bin').write_bytes(weights)
    return provenance


def prepare(args):
    base = helper()
    cat = catalog()
    selected = [c for c in cat['cases'] if c['id'] == args.case]
    base.require(len(selected) == 1, 'Unknown/nonrunnable case; use --list')
    case = selected[0]
    out = args.output.resolve()
    base.require(out.parent == OUT.resolve() and
                 re.fullmatch(r'operator_qbs_prepare_20261115_[A-Za-z0-9_]+', out.name) and
                 not out.exists(), 'Fresh owned operator_qbs_prepare_20261115_* output required')
    out.mkdir()
    b = base.Builder(out)
    for p in sorted(HERE.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            b.pin(p)
    for p in (BASE, ROOT / 'AGENTS.md'):
        b.pin(p)
    sdk_commit = b.run('sdk-head', ['git', '-C', ROOT, 'rev-parse', 'HEAD']).decode().strip()
    base.require(sdk_commit == cat['sdk_policy']['commit'], 'Main workspace HEAD changed; review successor policy')
    llama_commit = b.run('llama-head', ['git', '-C', args.llama, 'rev-parse', 'HEAD']).decode().strip()
    sdk, llama = out / 'inputs/sdk', out / 'inputs/llama'
    b.archive(ROOT, sdk_commit, ['software/qbs', 'apps/common',
              'apps/llama_q4k_repack_bench', 'apps/llama_q4km_micro',
              'apps/llama_qwen25_real/common/generate_case.py',
              'verification/qbs/qbs_ref.c', 'verification/qbs/qbs_ref.h'], sdk)
    b.archive(args.llama, llama_commit, ['ggml/include', 'ggml/src'], llama)
    patch = sdk / cat['sdk_policy']['llama_registered_patch']
    patch_present = (llama / 'ggml/src/ggml-cpu/arch/riscv/q8_K-decode-sums.h').exists()
    if patch_present:
        b.run('llama-patch-already-present', ['git', 'apply', '--no-index', '--reverse', '--check', patch], cwd=llama)
    else:
        b.run('llama-patch-check', ['git', 'apply', '--no-index', '--check', patch], cwd=llama)
        b.run('llama-patch-apply', ['git', 'apply', '--no-index', patch], cwd=llama)
    for tree in (sdk, llama):
        for p in tree.rglob('*'):
            if p.is_file():
                b.pin(p)
    data = out / 'data'
    data.mkdir()
    provenance = capture(case, b, base, data)
    build_id = hashlib.sha256(json.dumps(dict(case=case, sources=b.pins, sdk=sdk_commit,
                                            llama=llama_commit), sort_keys=True).encode()).hexdigest()
    config = out / 'config.h'
    config.write_text(''.join(f'#define {key} {value}\n' for key, value in dict(
        EVAL_M=case['m'], EVAL_N=case['n'], EVAL_TILE=case['tile'],
        EVAL_PROFILE=case['profile'], EVAL_WB=144 if case['profile'] == 1 else 210,
        EVAL_STORAGE={1: 1, 4: 2, 8: 3}[case['tile']],
        EVAL_RVV=int(case['backend'] != 'native'), EVAL_X32=int(case['backend'] == 'rvv_x32'),
        EVAL_REUSE={'direct': 0, 'operation': 1, 'cross_call': 2}[case['reuse']],
        EVAL_DOT='ggml_vec_dot_q4_K_q8_K' if case['profile'] == 1 else 'ggml_vec_dot_q6_K_q8_K',
        EVAL_ID='"' + build_id + '"').items()))
    includes = ['-I' + str(p) for p in (out, sdk / 'software/qbs/include', sdk / 'verification/qbs')]
    host_flags = ['-std=c11', '-O2', '-fno-fast-math', '-ffp-contract=off', '-frounding-math',
                  '-Wall', '-Wextra', '-Werror', *includes]
    objs = []
    for src, name in ((HERE / 'oracle.c', 'oracle'), (sdk / 'verification/qbs/qbs_ref.c', 'ref'),
                      (sdk / 'software/qbs/src/qbs_runtime.c', 'host_runtime')):
        obj = out / (name + '.o')
        b.compile(args.host_cc, host_flags, src, obj)
        objs.append(obj)
    oracle = out / 'oracle'
    b.run('oracle-link', [args.host_cc, *objs, '-lm', '-o', oracle])
    plan = json.loads(b.run('oracle', [oracle, data / 'input_f32.bin', data / 'weights_row.bin', data]))
    base.write_json(data / 'plan.json', plan)
    packer = sdk / 'apps/llama_qwen25_real/common/generate_case.py'
    spec = importlib.util.spec_from_file_location('archived_x32_packer', packer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fmt = 'q4_K' if case['profile'] == 1 else 'q6_K'
    module.repack_fields_x32(data / 'weights_row.bin', data / 'weights_x32.bin',
                            2048, case['n'], 256, 144 if case['profile'] == 1 else 210,
                            module.RVV_X32_FIELDS[fmt])
    if case['source'] == 'qwen3_decode_q6k':
        expected = (base.OLD_BUILD / 'part_1_expected.bin').read_bytes()[:case['n']*4]
        base.require((data / 'expected.bin').read_bytes() == expected,
                     'New Q6 golden differs from audited captured original')
        base.require((data / 'expected_q8.bin').read_bytes() == (base.OLD_BUILD / 'activation_0.bin').read_bytes(),
                     'Complete independently quantized Q6 activation differs from original')
        base.require((data / 'weights_r4.bin').read_bytes() == base.crop_r4(
            (base.OLD_BUILD / 'part_1_r4.bin').read_bytes(), n=case['n']), 'Independent Q6 repack drift')
    assembly = out / 'data.S'
    assembly.write_text('.section .rodata\n' + ''.join(
        f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{data / name}"\n'
        for symbol, name in (('eval_input', 'input_f32.bin'), ('eval_weights', 'weights_r4.bin'),
                             ('eval_row_weights', 'weights_row.bin'), ('eval_x32_weights', 'weights_x32.bin'))))
    cc = args.toolchain / 'riscv64-unknown-elf-gcc'
    objdump = args.toolchain / 'riscv64-unknown-elf-objdump'
    for name in ('cc1', 'as', 'ld'):
        tool = b.run('locate-' + name, [cc, '-print-prog-name=' + name]).decode().strip()
        b.pin(Path(tool) if Path(tool).is_file() else shutil.which(tool))
    for name in ('libc.a', 'libm.a', 'libgcc.a', 'libnosys.a'):
        b.pin(b.run('locate-' + name, [cc, '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
                                     '-print-file-name=' + name]).decode().strip())
    common = sdk / 'apps/common'
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-O3',
             '-DNDEBUG', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
             '-ffunction-sections', '-fdata-sections', '-DNR_LANES=4', '-DVLEN=1024',
             *includes, '-I' + str(common)]
    ggml = llama / 'ggml'
    quant_flags = ['-I' + str(ggml / p) for p in ('include', 'src', 'src/ggml-cpu', 'src/ggml-cpu/arch/riscv')]
    sources = [(HERE / 'main.c', 'main'), (assembly, 'data'),
               (ggml / 'src/ggml-cpu/arch/riscv/quants.c', 'rvv_quant_dot')]
    sources += [(common / name, Path(name).stem) for name in
                ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    if case['backend'] != 'rvv':
        sources += [(sdk / 'software/qbs/src/qbs_runtime.c', 'qbs_runtime')]
    if case['backend'] == 'native':
        sources += [(sdk / 'software/qbs/src' / name, Path(name).stem)
                    for name in ('qbs_native_riscv.c',)]
    if case['backend'] == 'rvv_x32':
        sources += [(sdk / 'apps/llama_q4k_repack_bench/repack_kernels.c', 'x32_kernel')]
    objects = []
    for source, name in sources:
        extra = quant_flags if name == 'rvv_quant_dot' else []
        if name == 'main':
            extra += ['-Wall', '-Wextra', '-Werror', '-I' + str(sdk / 'apps/llama_q4k_repack_bench')]
        if name == 'string':
            extra += ['-fno-builtin']
        obj = out / (name + '.o')
        b.compile(cc, flags + extra, source, obj)
        objects.append(obj)
    link = out / 'link.ld'
    b.run('linker-script', [cc, '-E', '-P', '-x', 'c', '-DALIGNMENT=16', common / 'arch.link.ld', '-o', link])
    elf = out / 'operator.elf'
    b.run('link', [cc, *flags, '-static', '-nostartfiles', '-nostdlib', *objects,
                   '-Wl,--gc-sections', '-Wl,-Map=' + str(out / 'link.map'), '-T', link,
                   '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
    quant = b.run('quant-disassembly', [objdump, '-d', '--disassemble=quantize_row_q8_K', elf]).decode()
    base.require(all(op in quant for op in ('vle32.v', 'vse8.v', 'vwredsum.vs', 'vfcvt.x.f.v')),
                 'Actual RVV quantizer missing')
    if case['backend'] == 'rvv':
        symbol = 'ggml_vec_dot_q4_K_q8_K_vl1024' if case['profile'] == 1 else 'ggml_vec_dot_q6_K_q8_K'
        dot = b.run('dot-disassembly', [objdump, '-d', '--disassemble=' + symbol, elf]).decode()
        base.require('vwmul' in dot or 'vwmacc' in dot, 'Actual optimized RVV dot missing')
    if case['backend'] == 'rvv_x32':
        symbol = ('q4k_gemv_32' if case['m'] == 1 else 'q4k_gemm_32x4') if case['profile'] == 1 else 'q6k_gemv_32'
        dot = b.run('dot-disassembly', [objdump, '-d', '--disassemble=' + symbol, elf]).decode()
        base.require('vfmacc' in dot and ('vwmacc' in dot or 'vmacc' in dot) and 'vse32' in dot,
                     'Archived multi-output x32 RVV kernel missing')
    trial = b.run('trial-disassembly', [objdump, '-d', '--disassemble=eval_trial', elf]).decode()
    base.require('quantize_row_q8_K' in trial and len(re.findall(r'\bfence\b', trial)) == 1,
                 'Unexpected timing boundaries')
    base.require(('qbs_execute_with_options' in trial) == (case['backend'] == 'native'),
                 'Wrong execution backend')
    base.require(len(re.findall(r'rdcycle\s+zero', trial)) == 2, 'Missing commit-ROI marker pair')
    for p in (config, assembly, link, oracle, elf, *data.iterdir()):
        b.pin(p)
    for name, sha in b.pins.items():
        base.require(base.digest(name) == sha, 'Build-time source/artifact drift: ' + name)
    base.write_json(out / 'source-pins.json', b.pins)
    check_cmd = [sys.executable, '-B', str(HERE / 'check.py'), '--build', str(out),
                 '--log', '{log}', '--output', '{result}']
    receipt = dict(state='BUILT_NOT_EXECUTED', rtl_executed=False, performance_measured=False,
        build_id=build_id, case=case, elf=str(elf), elf_sha256=base.digest(elf),
        baseline_kind=case['baseline_kind'], primary_eligible=case['primary_eligible'],
        source_pins=str(out / 'source-pins.json'), source_pins_sha256=base.digest(out / 'source-pins.json'),
        sdk_commit=sdk_commit, llama_commit=llama_commit, sdk_policy=cat['sdk_policy'],
        registered_llama_patch='already_present_reverse_checked' if patch_present else 'applied_in_archive',
        provenance=provenance, plan=plan, checker=check_cmd, post_pins_match=True, reused_objects=0,
        numeric_contract=dict(native='bit-exact independent ordered qbs_ref',
            rvv='finite and abs(error)<=0.0002+0.0002*abs(independent qbs_ref); different reduction order',
            rvv_atol=0.0002, rvv_rtol=0.0002),
        flag_seeds=[0, 8], whole_model=False, full_output_width=False,
        source_policy='No production working files/AKV sources; no implicit overlay',
        image_contract='Externally pinned parent SoC; this prep neither compiles nor launches a simulator',
        timing_contract='Consecutive issue-side rdcycle; quant/pack/admit/execute/drain; one final fence; cold weight repack excluded')
    base.write_json(out / 'build.json', receipt)
    base.write_json(out / 'manifest.json', dict(cases=[dict(id=case['id'], category='qbs',
        elf=str(elf), elf_sha256=base.digest(elf), checker=check_cmd,
        source_pins=str(out / 'source-pins.json'), timeout_seconds=10800,
        baseline_kind=case['baseline_kind'], primary_eligible=case['primary_eligible'],
        plusargs=['+QBS_PERF'] if case['backend'] == 'native' else [])]))
    print(json.dumps(dict(state=receipt['state'], build=str(out / 'build.json'),
                          manifest=str(out / 'manifest.json'), elf=str(elf))))


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--list', action='store_true')
    p.add_argument('--case')
    p.add_argument('--output', type=Path)
    p.add_argument('--llama', type=Path, default=LLAMA)
    p.add_argument('--toolchain', type=Path, default=TOOLCHAIN)
    p.add_argument('--host-cc', default='/usr/bin/gcc')
    a = p.parse_args()
    if a.list:
        print(json.dumps(catalog(), indent=2)); return
    p.error('--case and --output are required') if not a.case or not a.output else None
    prepare(a)


if __name__ == '__main__':
    main()
