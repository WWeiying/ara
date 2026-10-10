#!/usr/bin/env python3
"""Build and seal four short native-model payload commands; no VCS or Spike."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
import coverage_evidence as evidence
import run_gap51_payload_checked_extension as adapter
import analyze_gap51_payload as analysis
import build_gap38_i8_f16_lane3 as common

NAME, SCRIPT = adapter.NAME, Path(__file__).resolve()
APP = ROOT / 'apps' / NAME
REF = ROOT / 'verification/qbs/qbs_ref.c'
BASELINE = ROOT / 'verification/out/gap37-control-current-20261004-01'
CAPTURES = {
    'Q5_K': dict(root=Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q5_k_m-real-formats-v1'),
                 phase='prefill', operator='blk_0_attn_q_weight', weight='q5_K', k=1536, n=1536, m=15),
    'Q2_K': dict(root=Path('/home/wangwy/openproject/ara_verification_archive/captures/qbs-format-closure-q2k-20260923-03/capture'),
                 phase='decode', operator='blk_0_ffn_down_weight', weight='q2_K', k=4864, n=896, m=1),
}
save, read, sha, pins, verify, require = (common.save, common.read, common.sha,
                                       common.pins, common.verify, common.require)


class Build(common.Build):
    def __init__(self, out):
        super().__init__(out)
        self.sources = pins([SCRIPT, Path(common.__file__), Path(analysis.__file__),
                             Path(adapter.__file__), APP / 'main.c', APP / 'execute.S',
                             APP / 'contract.h', APP / 'host_reference.c', REF])
        self.tools.update(pins([Path(shutil.which('as')).resolve(), Path(shutil.which('ld')).resolve()]))
        for program in ('cc1', 'collect2'):
            result = self.run([self.host, '-print-prog-name=' + program], 'host-' + program)
            self.tools.update(pins([Path(result.stdout.decode().strip()).resolve(strict=True)]))


def captured_slices(out, commands):
    frozen, captures = {}, {}
    for profile, capture in CAPTURES.items():
        root, kind = capture['root'], capture['weight']
        directory = root / capture['phase'] / 'operators' / capture['operator']
        paths = [directory / name for name in ('operator.json', 'weight_' + kind + '.json',
                 'weight_' + kind + '.bin', 'activation_f32.json', 'activation_f32.bin')]
        frozen.update(pins([root / 'model.json', *paths]))
        op, wmeta, ameta = read(paths[0]), read(paths[1]), read(paths[3])
        size = 176 if profile == 'Q5_K' else 84
        k, n, m = (capture[key] for key in ('k', 'n', 'm'))
        stride = k // 256 * size
        require(op['op'] == 'GGML_OP_MUL_MAT' and op['phase'] == capture['phase'] and
                op['weight_type'] == kind and op['activation_quantization'] == 'Q8_K', 'wrong operator')
        require(wmeta['type'] == kind and wmeta['shape'] == [k, n, 1, 1] and
                wmeta['strides'][:2] == [size, stride], 'wrong native weight ABI')
        require(ameta['type'] == 'f32' and ameta['shape'] == [k, m, 1, 1] and
                ameta['strides'][:2] == [4, k * 4], 'wrong captured activation ABI')
        weights, activation = paths[2].read_bytes(), paths[4].read_bytes()
        require(len(weights) == wmeta['nbytes'] == n * stride and
                len(activation) == ameta['nbytes'] == k * m * 4, 'wrong captured file size')
        captures[profile] = dict(weights=weights, activation=activation, wmeta=wmeta, ameta=ameta,
                                 operator=op, paths=paths, block_bytes=size, row_stride=stride)
    results, records = [], []
    for c in commands:
        data = captures[c['weight']]
        wb, stride = data['block_bytes'], data['row_stride']
        rows = list(range(c['weight_row'], c['weight_row'] + c['n']))
        require(rows[-1] < data['wmeta']['shape'][1] and
                c['k_block'] < data['wmeta']['shape'][0] // 256 and
                all(0 <= ctx < data['ameta']['shape'][1] for ctx in c['contexts']), 'slice outside capture')
        wranges = [[row * stride + c['k_block'] * wb, row * stride + (c['k_block'] + 1) * wb] for row in rows]
        aranges = [[ctx * data['ameta']['strides'][1] + c['k_block'] * 1024,
                    ctx * data['ameta']['strides'][1] + (c['k_block'] + 1) * 1024] for ctx in c['contexts']]
        weights = b''.join(data['weights'][a:b] for a, b in wranges)
        activation = b''.join(data['activation'][a:b] for a, b in aranges)
        wp, ap = (out / f'command{c["id"]}-{name}.bin' for name in ('weight-slice', 'activation-f32-slice'))
        wp.write_bytes(weights)
        ap.write_bytes(activation)
        records.append(dict(command=c['id'], operator=data['operator'], weight_metadata=data['wmeta'],
            activation_metadata=data['ameta'], weight_source=str(data['paths'][2]),
            activation_source=str(data['paths'][4]), weight_row_indices=rows, k_block=c['k_block'],
            activation_context_indices=c['contexts'], weight_byte_ranges=wranges, activation_byte_ranges=aranges,
            replicated_single_captured_token=c['weight'] == 'Q2_K', slices=pins([wp, ap]),
            full_capture_output_used_as_golden=False))
        results.append((weights, wp, ap))
    verify(frozen)
    save(out / 'capture-slices.json', dict(status='REAL_NATIVE_SLICES_NOT_FULL_OPERATOR_OUTPUT',
        source_files=frozen, commands=records))
    return frozen, results


def emit_header(out, commands, slices, oracles):
    lines = ['#ifndef GAP51_DATA_H', '#define GAP51_DATA_H', '#include "contract.h"',
             '_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "native little endian ABI");']
    for c, (weights, _, _), oracle in zip(commands, slices, oracles):
        activation = bytes.fromhex(oracle['activation_hex'])
        require(len(weights) == c['weight_bytes'] and len(activation) == c['activation_bytes'] and
                len(oracle['expected_bits']) == c['m'] * c['n'], 'oracle size differs')
        require(oracle['scope'] == 'host-reference-only' and
                oracle['custom_instruction_execution_prechecked'] is False and
                oracle['independent_native_decode'] is True and
                oracle['m8_padding_checked'] == (c['m'] == 5) and
                type(oracle['fflags']) is int and 0 <= oracle['fflags'] < 32, 'wrong oracle scope')
        weight_image, activation_image = bytearray([0xa5] * 800), bytearray([0x5a] * 2496)
        weight_image[64:64 + len(weights)] = weights
        start = 64 + c['a_mod16']
        activation_image[start:start + len(activation)] = activation
        require(len(weight_image) == 800 and len(activation_image) == 2496, 'source image overflow')
        qwords = lambda blob: [int.from_bytes(blob[i:i + 8], 'little') for i in range(0, len(blob), 8)]
        for name, values, ctype in [('weights', qwords(weight_image), 'uint64_t'),
                                   ('activation', qwords(activation_image), 'uint64_t'),
                                   ('expected', oracle['expected_bits'], 'uint32_t')]:
            lines.append(f'static const {ctype} gap51_{name}{c["id"]}[] = {{')
            for i in range(0, len(values), 16):
                lines.append('  ' + ', '.join(hex(v) for v in values[i:i + 16]) + ',')
            lines.append('};')
    lines.append('static const gap51_case_t gap51_cases[GAP51_COMMANDS] = {')
    for c, oracle in zip(commands, oracles):
        profile, layout = (4 if c['weight'] == 'Q5_K' else 7), (3 if c['activation_layout'] == 'M8' else 1)
        numbers = [c['m'], c['n'], profile, layout, c['a_mod16'], c['weight_bytes'], c['activation_bytes'], oracle['fflags']]
        names = [f'gap51_{name}{c["id"]}' for name in ('weights', 'activation', 'expected')]
        lines.append('  {' + ', '.join([*map(str, numbers), *names]) + '},')
    lines += ['};', '#endif']
    (out / 'gap51_data.h').write_text('\n'.join(lines) + '\n')


def instruction_proof(b, elf, commands):
    b.run([b.llvm / 'bin/llvm-objdump', '-d', elf], 'dut.disassembly')
    result = b.run([b.llvm / 'bin/llvm-readobj', '--elf-output-style=JSON',
                    '--sections', '--symbols', '--program-headers', elf], 'dut.metadata')
    metadata = json.loads(result.stdout)[0]
    symbols = {r['Symbol']['Name']['Name']: r['Symbol'] for r in metadata['Symbols']}
    blob, sites = elf.read_bytes(), []
    for c in commands:
        symbol = 'gap51_qbexec_site' + str(c['id'])
        address = symbols[symbol]['Value']
        expected = ((c['m'] - 1) << 25) | 0x00b5045b
        matches = []
        for row in metadata['Sections']:
            s = row['Section']
            if s['Flags']['Value'] & 4 and s['Address'] <= address and address + 4 <= s['Address'] + s['Size']:
                offset = s['Offset'] + address - s['Address']
                matches.append(int.from_bytes(blob[offset:offset + 4], 'little'))
        require(matches == [expected], 'wrong QBS command at ' + symbol)
        sites.append(dict(command=c['id'], symbol=symbol, pc=address, word=expected,
                          m=c['m'], n=c['n'], k_blocks=1,
                          weight_address=symbols['weights']['Value'] + 64,
                          activation_address=symbols['activation']['Value'] + 64 + c['a_mod16']))
    require(len({s['pc'] for s in sites}) == 4, 'instruction sites alias')
    for name in ('weights', 'activation', 'descriptor_packet', 'initial', 'actual', 'csr_packet'):
        require(symbols[name]['Value'] % 64 == 0, 'ELF allocation alignment differs: ' + name)
    require(symbols['weights']['Size'] == 800 and symbols['activation']['Size'] == 2496,
            'source guard allocation changed')
    image_proofs = []
    for c in commands:
        for kind, capacity, prefix, length in [('weights', 800, 64, c['weight_bytes']),
                ('activation', 2496, 64 + c['a_mod16'], c['activation_bytes'])]:
            s = symbols[f'gap51_{kind}{c["id"]}']
            require(s['Value'] % 8 == 0 and s['Size'] == capacity, 'template alignment/size differs')
            section = next(row['Section'] for row in metadata['Sections'] if
                row['Section']['Address'] <= s['Value'] < row['Section']['Address'] + row['Section']['Size'])
            offset = section['Offset'] + s['Value'] - section['Address']
            image = blob[offset:offset + capacity]
            expected_native = ((b.out / f'command{c["id"]}-weight-slice.bin').read_bytes() if kind == 'weights'
                else bytes.fromhex(read(b.out / f'oracle-command{c["id"]}.json')['activation_hex']))
            guard = bytes([0xa5 if kind == 'weights' else 0x5a])
            require(image[:prefix] == guard * prefix and image[prefix:prefix + length] == expected_native and
                    image[prefix + length:] == guard * (capacity - prefix - length), 'ELF source image differs')
            image_proofs.append(dict(symbol=f'gap51_{kind}{c["id"]}', address=s['Value'],
                bytes=capacity, native_start=prefix, native_bytes=length, alignment=8))
    proof = dict(status='STATIC_ELF_SITES_VERIFIED_NOT_EXECUTED', elf=str(elf), elf_sha256=sha(elf),
        sites=sites, custom_commands=4, active_outputs=28,
        descriptor_address=symbols['descriptor_packet']['Value'] + 64,
        full_vrf_words_checked_per_command=1024, fflags_seed=8, frm=2, vtype=16, vstart=0, vcsr=5,
        narrow_zero_tail=True, wide_preserved_tail=True, capability_queries=5,
        source_templates=image_proofs, vcs_launched=False)
    save(b.out / 'elf-proof.json', proof)
    return proof


def host_negatives(out, host):
    negatives = []
    faults = ('dest', 'tail', 'register', 'initial', 'source', 'activation', 'descriptor', 'guard',
              'sourceguard', 'csrguard', 'vl', 'vtype', 'vstart', 'frm', 'flags', 'vcsr', 'skip',
              'cancel', 'sourcecancel')
    pairs = [(i, f) for i in range(4) for f in faults] + [(1, 'unused'), (3, 'unused'), (3, 'padding')]
    pairs += [(0, fault) for fault in ('caps-vlen', 'caps-abi', 'caps-q2')]
    regions = dict(weights=800, activation=2496, descriptor=144, initial=4224, actual=4224, csr=160)
    for command in range(4):
        for region, size in regions.items():
            for offset in (0, 7, size // 2, size - 8, size - 1):
                pairs.append((command, f'byte:{region}:{offset}'))
    for command, fault in pairs:
        argv = [str(host), fault, str(command)]
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=30)
        log = out / f'negative-command{command}-{fault.replace(":", "-")}.log'
        log.write_bytes(result.stdout + result.stderr)
        require(result.returncode == 1 and b'FAILED: ' + NAME.encode() in result.stdout and
                b'PASSED:' not in result.stdout, f'guard escaped: command{command}/{fault}')
        require(not any(message in result.stdout for message in
                        (b'mutation syntax', b'mutation range', b'unknown fault injection')),
                'fault did not exercise a real checker: ' + fault)
        negatives.append(dict(command=argv, command_id=command, mutation=fault, returncode=result.returncode,
                              expected='REJECTED', log=str(log), log_sha256=sha(log)))
    save(out / 'host-negative-tests.json', negatives)
    return len(negatives)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(ROOT == Path('/home/wangwy/openproject/ara_dsa_signoff_integration'), 'wrong worktree')
    out = args.output.resolve()
    require(out.parent == ROOT / 'verification/out' and out.name.startswith('gap51-payload-') and
            not out.exists(), 'new independent gap51-payload output required')
    legality = analysis.analyze()
    out.mkdir()
    save(out / 'static-plan.json', legality)
    commands = legality['commands']
    protected, slices = captured_slices(out, commands)
    protected.update(legality['source_hashes'])
    b = Build(out)
    inc = [f'-I{out}', f'-I{APP}', '-Wall', '-Wextra']
    ref_obj = b.compile(REF, 'host-qbs-ref', host=True)
    oracle_obj = b.compile(APP / 'host_reference.c', 'host-independent', host=True)
    oracle_exe = out / 'host-reference'
    b.link([b.host, oracle_obj, ref_obj, '-lm', '-o', oracle_exe], 'host-reference.link')
    oracles = []
    for c, (_, wp, ap) in zip(commands, slices):
        argv = [oracle_exe, 4 if c['weight'] == 'Q5_K' else 7, c['m'], c['n'],
                3 if c['activation_layout'] == 'M8' else 1, wp, ap]
        oracle = json.loads(b.run(argv, f'host-reference-command{c["id"]}', timeout=30).stdout)
        save(out / f'oracle-command{c["id"]}.json', oracle)
        oracles.append(oracle)
    emit_header(out, commands, slices, oracles)
    host_obj = b.compile(APP / 'main.c', 'host-app', [*inc, '-DGAP51_HOST=1'], host=True)
    host = out / 'host-app'
    b.link([b.host, host_obj, ref_obj, '-lm', '-o', host], 'host-app.link')
    host_lines = b.run([host], 'host-app', timeout=30).stdout.decode().splitlines()
    require(len(host_lines) == 6, 'missing/extra host command records')
    for i, line in enumerate(host_lines[:4]):
        require(re.fullmatch(rf'GAP51 command={i} checks=[1-9][0-9]* errors=0', line), 'host command incomplete')
    require(host_lines[4] == 'GAP51 inspected vrf_words=4096 initial_words=4096 source_bytes=13760 csr_words=48',
            'incomplete inspection counts')
    match = re.fullmatch(r'PASSED: ' + NAME + r' checks=([1-9][0-9]*) errors=0', host_lines[-1])
    require(match, 'missing complete host selfcheck')
    negative_count = host_negatives(out, host)
    objects = [b.compile(b.common / name, 'dut-' + name) for name in
               ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    objects += [b.compile(APP / 'main.c', 'dut-main', inc), b.compile(APP / 'execute.S', 'dut-execute')]
    elf = out / (NAME + '.elf')
    b.bind_sources([b.common / 'link.ld', ROOT / 'verification/coverage/check_elf_fit.py'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostartfiles', '-Wl,--gc-sections',
            f'-Wl,-Map={out / (NAME + ".map")}', f'-T{b.common / "link.ld"}', *objects,
            '-lm', f'-L{b.llvm / "lib/generic"}', '-lclang_rt.builtins-riscv64', '-o', elf], 'dut.link')
    proof = instruction_proof(b, elf, commands)
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
    record = dict(name=NAME, binary=str(elf), binary_sha256=sha(elf), sources=sorted(b.sources),
        source_hashes=b.sources, host_reference=str(APP / 'host_reference.c'), host_result='\n'.join(host_lines),
        host_log=str(out / 'host-app.log'), host_log_sha256=sha(out / 'host-app.log'),
        host_checks=int(match[1]), dut_checks=int(match[1]) - 5, host_fault_injections_rejected=negative_count,
        oracles=[str(out / f'oracle-command{i}.json') for i in range(4)], elf_proof=proof,
        custom_instruction_execution_prechecked=False, vcs_launched=False)
    record_path = out / (NAME + '.precheck.json')
    save(record_path, record)
    artifacts = pins(p for p in out.iterdir() if p.is_file())
    save(out / 'artifact_hashes.json', artifacts)
    targets = sorted({p['scope'] for p in legality['points'] if p['id'] in legality['remaining_target_ids']})
    item = dict(name=adapter.CASE, binary=str(elf), binary_sha256=sha(elf), sources=sorted(b.sources),
        evidence=sorted([*artifacts, str(out / 'artifact_hashes.json')]),
        source_audit='Real llama native Q5_K prefill distinct context/block slices and Q2_K decode '
            'rows8..15/block0; Q2_K deliberately replays one captured token twice. Existing native '
            'Q8_K quantization/M8 packing crosschecked by independent packing and raw-byte integer '
            'dots, exact float bits/flags. Four K1 DIRECT commands, 28 outputs. Full 1024-word VRF, '
            'sources/descriptor/guards and immediate six CSRs per command; narrow zero tail and '
            'wide preserved tail/unused groups. Host reference only, no custom ISA preexecution.',
        rationale='Other 36 gap40 reachable targets, excluding gap49 predicted16: row-major Q8_K '
            'M4/A4, M3/A8, M2/A12; M5 M8/A4 physical bank1, plus Q2_K N8 side metadata in second '
            'weight tile. Four commands, one ELF/admission, 600s fixed budget; predictions not VDB hits.',
        targets=targets, timeout_s=600,
        precheck=dict(format='accel-host-v1', record=str(record_path), log=str(out / 'host-app.log')))
    draft = out / 'selection.checked-draft.json'
    save(draft, dict(status='CHECKED_DRAFT_HOST_ONLY_NOT_SUBMITTED', baseline=str(BASELINE),
        baseline_bits=str(BASELINE / 'combined-bits.json'), cases=[item], vcs_launched=False,
        measured_candidate_gain=None))
    checked = evidence.Evidence()
    checked.pin(draft)
    for name in adapter.MANIFESTS:
        checked.hashes(checked.read(out / name))
    result = evidence.precheck(read(draft)['cases'][0], checked)
    require(json.loads(json.dumps(result)) == result, 'precheck is not JSON stable')
    save(out / 'checked-precheck.json', dict(status='PASS', scope='host-reference-only',
        read_only_validation=True, result=result, checked_files=checked.files,
        vcs_launched=False, baseline_full_reaudit_performed=False))
    save(out / 'draft.sha256.json', pins([draft, out / 'checked-precheck.json', out / 'artifact_hashes.json']))
    replay = adapter.precheck(read(draft)['cases'][0], evidence.Evidence(), evidence.precheck)
    require(replay == result, 'final sealed replay differs')
    print('HOST PRECHECK ONLY: ' + host_lines[-1], flush=True)
    print(f'{negative_count} fault injections rejected; four static command sites; no VCS or Spike.', flush=True)
    print(draft, flush=True)


if __name__ == '__main__':
    main()
