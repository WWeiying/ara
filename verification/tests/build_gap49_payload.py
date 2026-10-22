#!/usr/bin/env python3
"""Build one real-data Q5_K payload-skew case and seal host checks; never run VCS."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
import coverage_evidence as evidence
import run_gap49_payload_checked_extension as adapter
import analyze_gap49_payload as analysis
import build_gap38_i8_f16_lane3 as common

NAME = adapter.NAME
SCRIPT = Path(__file__).resolve()
APP = ROOT / 'apps' / NAME
REF = ROOT / 'verification/qbs/qbs_ref.c'
CAPTURE = Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q5_k_m-real-formats-v1')
OPERATOR = CAPTURE / 'decode/operators/blk_0_attn_q_weight'
BASELINE = ROOT / 'verification/out/gap37-control-current-20261004-01'
save, read, sha, pins, verify, require = (common.save, common.read, common.sha,
                                       common.pins, common.verify, common.require)


class Build(common.Build):
    def __init__(self, out):
        super().__init__(out)
        self.sources = pins([SCRIPT, Path(common.__file__), Path(analysis.__file__),
                             Path(adapter.__file__), APP / 'main.c', APP / 'execute.S',
                             APP / 'host_reference.c', REF])
        self.tools.update(pins([Path(shutil.which('as')).resolve(), Path(shutil.which('ld')).resolve()]))
        for program in ('cc1', 'collect2'):
            path = Path(self.run([self.host, '-print-prog-name=' + program], 'host-' + program).stdout.decode().strip()).resolve(strict=True)
            self.tools.update(pins([path]))


def captured_slice(out):
    paths = [OPERATOR / n for n in ('operator.json', 'weight_q5_K.json', 'weight_q5_K.bin',
             'activation_f32.json', 'activation_f32.bin')]
    paths += [CAPTURE / 'model.json', ROOT / 'apps/llama_qwen25_q5k_decode_attn_q_qbs/case.json',
              ROOT / 'apps/common/qbs_abi.h', ROOT / 'verification/qbs/qbs_ref.h']
    frozen = pins(paths)
    wmeta, ameta, op = read(paths[1]), read(paths[3]), read(paths[0])
    require(op['op'] == 'GGML_OP_MUL_MAT' and op['weight_type'] == 'q5_K' and
            op['activation_quantization'] == 'Q8_K', 'wrong captured operator')
    require(wmeta['shape'] == [1536, 1536, 1, 1] and wmeta['strides'][:2] == [176, 1056] and
            wmeta['type'] == 'q5_K', 'wrong weight ABI/strides')
    require(ameta['type'] == 'f32' and ameta['shape'] == [1536, 1, 1, 1] and
            ameta['strides'][:2] == [4, 6144], 'wrong activation ABI/strides')
    weights, activation = paths[2].read_bytes(), paths[4].read_bytes()
    require(len(weights) == wmeta['nbytes'] == 1622016 and len(activation) == ameta['nbytes'] == 6144,
            'captured size differs')
    sliced = b''.join(weights[row * 1056:row * 1056 + 176] for row in range(7))
    (out / 'weight-slice.bin').write_bytes(sliced)
    (out / 'activation-f32-slice.bin').write_bytes(activation[:1024])
    verify(frozen)
    record = {'status': 'REAL_CAPTURE_SLICE_NOT_FULL_OPERATOR_OUTPUT',
              'operator': op, 'weight_metadata': wmeta, 'activation_metadata': ameta,
              'source_files': frozen, 'weight_row_indices': list(range(7)), 'k_block_indices': [0],
              'original_k_blocks': 6, 'selected_k_elements': 256,
              'weight_byte_ranges': [[r * 1056, r * 1056 + 176] for r in range(7)],
              'activation_byte_range': [0, 1024],
              'slices': pins([out / 'weight-slice.bin', out / 'activation-f32-slice.bin']),
              'full_capture_output_used_as_golden': False}
    save(out / 'capture-slice.json', record)
    return frozen, sliced


def emit_header(out, weights, oracle):
    activation = bytes.fromhex(oracle['activation_hex'])
    require(len(weights) == 1232 and len(activation) == 292 and len(oracle['expected_bits']) == 7,
            'oracle shape differs')
    require(oracle['scope'] == 'host-reference-only' and
            oracle['custom_instruction_execution_prechecked'] is False and
            isinstance(oracle['fflags'], int) and 0 <= oracle['fflags'] < 32, 'wrong oracle scope')
    lines = ['#ifndef GAP49_DATA_H', '#define GAP49_DATA_H', '#include <stdint.h>',
             '#define GAP49_FFLAGS ' + str(oracle['fflags']) + 'u']
    for name, values, ctype in [('weights', weights, 'uint8_t'), ('activation', activation, 'uint8_t'),
                               ('expected', oracle['expected_bits'], 'uint32_t')]:
        lines.append('static const ' + ctype + ' gap49_' + name + '[] = {')
        for i in range(0, len(values), 16):
            lines.append('  ' + ', '.join(hex(v) for v in values[i:i + 16]) + ',')
        lines.append('};')
    lines.append('#endif')
    (out / 'gap49_data.h').write_text('\n'.join(lines) + '\n')


def instruction_proof(b, elf):
    b.run([b.llvm / 'bin/llvm-objdump', '-d', elf], 'dut.disassembly')
    result = b.run([b.llvm / 'bin/llvm-readobj', '--elf-output-style=JSON',
                    '--sections', '--symbols', '--program-headers', elf], 'dut.metadata')
    metadata = json.loads(result.stdout)[0]
    symbols = {r['Symbol']['Name']['Name']: r['Symbol'] for r in metadata['Symbols']}
    address = symbols['gap49_qbexec_site']['Value']
    blob, matches = elf.read_bytes(), []
    for row in metadata['Sections']:
        sec = row['Section']
        if sec['Flags']['Value'] & 4 and sec['Address'] <= address and address + 4 <= sec['Address'] + sec['Size']:
            offset = sec['Offset'] + address - sec['Address']
            matches.append(int.from_bytes(blob[offset:offset + 4], 'little'))
    require(matches == [0x00b5045b], 'wrong M1 v8 QBS instruction')
    require(symbols['weights']['Value'] % 64 == 0 and symbols['activation']['Value'] % 64 == 0 and
            symbols['descriptor_packet']['Value'] % 64 == 0, 'ELF buffer alignment differs')
    proof = {'status': 'STATIC_ELF_SITE_VERIFIED_NOT_EXECUTED', 'elf': str(elf),
             'elf_sha256': sha(elf), 'site': {'pc': address, 'word': 0x00b5045b},
             'descriptor_address': symbols['descriptor_packet']['Value'] + 64,
             'weight_address': symbols['weights']['Value'] + 66,
             'activation_address': symbols['activation']['Value'] + 64,
             'custom_commands': 1, 'm': 1, 'n': 7, 'k_blocks': 1,
             'descriptor_packet_bytes': symbols['descriptor_packet']['Size'],
             'fflags_seed': 8, 'frm': 2, 'vl': 7, 'vtype': 16, 'vstart': 0, 'vcsr': 5,
             'full_vrf_words_checked': 1024, 'vcs_launched': False}
    save(b.out / 'elf-proof.json', proof)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(ROOT == Path('/home/wangwy/openproject/ara_dsa_signoff_integration'), 'wrong worktree')
    out = args.output.resolve()
    require(out.parent == ROOT / 'verification/out' and out.name.startswith('gap49-payload-') and
            not out.exists(), 'new independent gap49-payload output required')
    legality = analysis.analyze()
    out.mkdir()
    save(out / 'min-cover.json', legality)
    protected, weights = captured_slice(out)
    protected.update(legality['source_hashes'])
    b = Build(out)
    inc = [f'-I{out}', '-Wall', '-Wextra']
    ref_obj = b.compile(REF, 'host-qbs-ref', host=True)
    oracle_obj = b.compile(APP / 'host_reference.c', 'host-independent', host=True)
    oracle_exe = out / 'host-reference'
    b.link([b.host, oracle_obj, ref_obj, '-lm', '-o', oracle_exe], 'host-reference.link')
    oracle = json.loads(b.run([oracle_exe, out / 'weight-slice.bin', out / 'activation-f32-slice.bin'],
                             'host-reference', timeout=30).stdout)
    save(out / 'oracle.json', oracle)
    emit_header(out, weights, oracle)
    host_obj = b.compile(APP / 'main.c', 'host-app', [*inc, '-DGAP49_HOST=1'], host=True)
    host = out / 'host-app'
    b.link([b.host, host_obj, ref_obj, '-lm', '-o', host], 'host-app.link')
    host_result = b.run([host], 'host-app', timeout=30).stdout.decode().strip()
    match = re.fullmatch(r'PASSED: ' + NAME + r' checks=([1-9][0-9]*) errors=0', host_result)
    require(match, 'missing complete host selfcheck')
    negatives = []
    for mutation in ('dest', 'tail', 'register', 'source', 'activation', 'descriptor', 'guard', 'flags', 'frm'):
        result = subprocess.run([str(host), mutation], cwd=ROOT, capture_output=True, timeout=30)
        log = out / ('negative-' + mutation + '.log')
        log.write_bytes(result.stdout + result.stderr)
        require(result.returncode == 1 and b'FAILED: ' + NAME.encode() in result.stdout and
                b'PASSED:' not in result.stdout, 'negative guard escaped: ' + mutation)
        negatives.append({'mutation': mutation, 'command': [str(host), mutation],
                          'returncode': result.returncode, 'expected': 'REJECTED',
                          'log': str(log), 'log_sha256': sha(log)})
    save(out / 'host-negative-tests.json', negatives)
    objects = [b.compile(b.common / n, 'dut-' + n) for n in
               ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    objects += [b.compile(APP / 'main.c', 'dut-main', inc), b.compile(APP / 'execute.S', 'dut-execute')]
    elf = out / (NAME + '.elf')
    b.bind_sources([b.common / 'link.ld', ROOT / 'verification/coverage/check_elf_fit.py'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostartfiles', '-Wl,--gc-sections',
            f'-Wl,-Map={out / (NAME + ".map")}', f'-T{b.common / "link.ld"}', *objects,
            '-lm', f'-L{b.llvm / "lib/generic"}', '-lclang_rt.builtins-riscv64', '-o', elf], 'dut.link')
    proof = instruction_proof(b, elf)
    fit_python = ROOT / 'verification/tools/soc-venv/bin/python'
    b.tools.update(pins([fit_python.resolve()]))
    b.run([fit_python, ROOT / 'verification/coverage/check_elf_fit.py', '--elf', elf,
           '--ram-bytes', '0x200000', '--output', out / 'elf-fit.json'], 'elf-fit')
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values())
                    if getattr(m, '__file__', None) and
                    Path(m.__file__).resolve().is_relative_to(ROOT / 'verification')])
    for bound in (b.sources, b.tools, b.link_inputs, protected):
        verify(bound)
    save(out / 'source_hashes.json', b.sources)
    save(out / 'tool_hashes.json', b.tools)
    save(out / 'link-inputs.json', b.link_inputs)
    save(out / 'protected-inputs.json', protected)
    record = {'name': NAME, 'binary': str(elf), 'binary_sha256': sha(elf),
              'sources': sorted(b.sources), 'source_hashes': b.sources,
              'host_reference': str(APP / 'host_reference.c'), 'host_result': host_result,
              'host_log': str(out / 'host-app.log'), 'host_log_sha256': sha(out / 'host-app.log'),
              'host_checks': int(match[1]), 'dut_checks': int(match[1]) - 2,
              'oracle': str(out / 'oracle.json'), 'elf_proof': proof,
              'custom_instruction_execution_prechecked': False, 'vcs_launched': False}
    record_path = out / (NAME + '.precheck.json')
    save(record_path, record)
    artifacts = pins(p for p in out.iterdir() if p.is_file())
    save(out / 'artifact_hashes.json', artifacts)
    targets = sorted({legality['points'][i]['scope'] for i in legality['selected']['point_ids']})
    item = {'name': adapter.CASE, 'binary': str(elf), 'binary_sha256': sha(elf),
            'sources': sorted(b.sources), 'evidence': sorted([*artifacts, str(out / 'artifact_hashes.json')]),
            'source_audit': 'Real llama Qwen2.5 native Q5_K row0..6/block0 and captured activation '
                            'slice, existing QBS ABI/ref quantization, independent byte-decode dot/flags '
                            'crosscheck. One M1 N7 K1 DIRECT command at Wmod16=2. Complete 1024-word '
                            'VRF image, sources/descriptor/guards, narrow zero tail, and immediate '
                            'flags/frm/vl/vtype/vstart/vcsr. Host-only, no custom ISA preexecution.',
            'rationale': 'Legal Q5_K high-plane pending suffix in both weight banks; N7 is the '
                         'minimum second-tile local-row2 realization. Sixteen potential gap40 '
                         'branch positions, not measured gains; no context/AKV or wide-M claim.',
            'targets': targets, 'timeout_s': 600,
            'precheck': {'format': 'accel-host-v1', 'record': str(record_path),
                         'log': str(out / 'host-app.log')}}
    draft = out / 'selection.checked-draft.json'
    save(draft, {'status': 'CHECKED_DRAFT_HOST_ONLY_NOT_SUBMITTED', 'baseline': str(BASELINE),
                 'baseline_bits': str(BASELINE / 'combined-bits.json'), 'cases': [item],
                 'vcs_launched': False, 'measured_candidate_gain': None})
    checked = evidence.Evidence()
    checked.pin(draft)
    for name in adapter.MANIFESTS:
        checked.hashes(checked.read(out / name))
    result = evidence.precheck(read(draft)['cases'][0], checked)
    require(json.loads(json.dumps(result)) == result, 'precheck is not JSON stable')
    save(out / 'checked-precheck.json', {'status': 'PASS', 'scope': 'host-reference-only',
         'read_only_validation': True, 'result': result, 'checked_files': checked.files,
         'vcs_launched': False, 'baseline_full_reaudit_performed': False})
    save(out / 'draft.sha256.json', pins([draft, out / 'checked-precheck.json', out / 'artifact_hashes.json']))
    replay = adapter.precheck(read(draft)['cases'][0], evidence.Evidence(), evidence.precheck)
    require(replay == result, 'final sealed replay differs')
    print('HOST PRECHECK ONLY: ' + host_result, flush=True)
    print('One custom command statically encoded; no VCS or Spike execution.', flush=True)
    print(draft, flush=True)


if __name__ == '__main__':
    main()
