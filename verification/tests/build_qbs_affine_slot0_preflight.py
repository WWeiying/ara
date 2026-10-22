"""Affine Full8 host/native-gold and ELF preflight only; never starts VCS."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

import build_gap38_i8_f16_lane3 as common
from build_gap110_q3_r4 import MUTATIONS
import audit_gap110_q3_r4 as audit

ROOT = common.ROOT
APP = ROOT / 'apps/qbs_affine_slot0_cancel'
OLD = ROOT / 'apps/qbs_gap110_q3_r4_tail'
REVIEW = ROOT / 'verification/out/qbs-accumulator48-static-review744-agent-20261007-01.json'
REVIEW_SHA = 'dd32fde7ca87178405af5d2f6f9375c7371697daaa152b72bfb911de248af108'
NAME = 'qbs_affine_slot0_cancel'


def replace_one(text, before, after):
    common.require(text.count(before) == 1, 'Nonunique template anchor: ' + before)
    return text.replace(before, after)


def fixture(phase):
    common.require(type(phase) is int and phase in (0, 1), 'Exact phase required')
    w, a = bytearray([0xa5] * 1280), bytearray([0x5a] * 2496)
    q = phase + 2
    for r in range(8):
        b = bytearray(144)
        struct.pack_into('<e', b, 0, r + 1 + phase)
        struct.pack_into('<e', b, 2, r + 2 - phase)
        b[4:12] = bytes([1] * 8)
        b[12:16] = bytes([0x11] * 4)
        b[16:] = bytes([q | q << 4] * 128)
        w[64 + 144*r:64 + 144*(r+1)] = b
    for c in range(8):
        struct.pack_into('<f', a, 68 + 4*c, c+1)
        for i in range(256):
            a[68 + 32 + 8*i + c] = 1
        for g in range(16):
            struct.pack_into('<h', a, 68 + 2080 + 16*g + 2*c, 16)
    # Analytic independent gold, not unpacked by the C oracle and not DUT-derived.
    gold = [struct.unpack('<I', struct.pack('<f',
            256 * (c+1) * (q * (r+1+phase) - (r+2-phase))))[0]
            for c in range(8) for r in range(8)]
    return bytes(w), bytes(a), gold


def templates():
    body = (OLD / 'main.c').read_text()
    for before, after in [
        ('sizeof(weights_t) == 1024', 'sizeof(weights_t) == 1280'),
        ('c->m == 5 && c->n == (current == 0 ? 7u : 5u)', 'c->m == 8 && c->n == 8'),
        ('c->weight_profile == QBS_WEIGHT_PROFILE_Q3_K', 'c->weight_profile == QBS_WEIGHT_PROFILE_Q4_K'),
        ('c->weight_skew == (current == 0 ? 0u : 12u)', 'c->weight_skew == 0'),
        ('{0x08b5045bu, 0x08b5045bu}', '{0x0eb5045bu, 0x0eb5045bu}'),
        ('source_bytes == 7328', 'source_bytes == 7840')]:
        body = replace_one(body, before, after)
    assembly = (OLD / 'execute.S').read_text()
    for phase, n in enumerate((7, 5)):
        assembly = replace_one(assembly, 'MATRIX_EXEC %d, %d, 0x08b5045b' % (phase, n),
                               'MATRIX_EXEC %d, 8, 0x0eb5045b' % phase)
    return body, assembly


def build(out):
    common.require(out.parent == ROOT / 'verification/out' and not out.exists(), 'Fresh direct output only')
    common.require(common.sha(REVIEW) == REVIEW_SHA, 'Frozen source review drift')
    review = json.loads(REVIEW.read_bytes())
    common.verify(review['input_pins'])
    common.require(review['status'] == 'NORMAL_REUSE_UNREACHABLE_RESET_REUSE_REACHABLE_KEEP_COVERAGE',
                   'Wrong cancellation source contract')
    out.mkdir()
    b = common.Build(out)
    b.bind_sources([Path(__file__), Path(__file__).with_name('test_qbs_affine_slot0_preflight.py'),
                    APP/'main.c', APP/'native_oracle.h', OLD/'main.c', OLD/'execute.S',
                    OLD/'contract.h', Path(audit.__file__), Path(common.__file__), REVIEW])
    body, assembly = templates()
    (out/'affine_checked_body.inc').write_text(body)
    (out/'execute.S').write_text(assembly)
    inputs, gold_lines, expected_dump = [], [], b''
    for phase in (0, 1):
        w, a, gold = fixture(phase)
        expected_dump += w+a
        for name, blob in [('weights', w), ('activation', a)]:
            words = [int.from_bytes(blob[i:i+8], 'little') for i in range(0, len(blob), 8)]
            inputs.append('static const uint64_t gap110_%s%d[%d]={%s};' %
                          (name, phase, len(words), ','.join('UINT64_C(%s)' % hex(x) for x in words)))
        gold_lines.append('static const uint32_t affine_gold%d[64]={%s};' %
                          (phase, ','.join(hex(x) for x in gold)))
        common.save(out/('gold%d.json' % phase), dict(bits=gold, flags=0))
    (out/'affine_inputs.h').write_text('\n'.join(inputs)+'\n')
    (out/'affine_gold.h').write_text('\n'.join(gold_lines)+'\n')
    inc = ['-I'+str(out), '-I'+str(APP), '-I'+str(OLD)]
    obj = b.compile(APP/'main.c', 'host-main', [*inc, '-DGAP110_HOST=1'], host=True)
    host = out/'host'
    b.link([b.host, obj, '-o', host], 'host.link')
    common.require(b.run([host, '--dump'], 'host-dump').stdout == expected_dump, 'Native bytes differ')
    result = b.run([host], 'host-checks').stdout
    common.require(b'PASSED: qbs_affine_slot0_cancel checks=44 errors=0' in result and
                   b'vrf_words=2048 initial_words=2048 source_bytes=7840 csr_words=24' in result and
                   b'FAIL' not in result, 'Full independent affine host oracle failed')
    for phase in (0, 1):
        for mutation in MUTATIONS:
            r = subprocess.run([host, mutation, str(phase)], capture_output=True, timeout=10)
            common.require(r.returncode == 1 and b'FAIL' in r.stdout, 'Mutation escaped: '+mutation)
            (out/('negative-%d-%s.log' % (phase, mutation))).write_bytes(r.stdout+r.stderr)
    objects = [b.compile(b.common/name, 'dut-'+name) for name in
               ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    objects += [b.compile(APP/'main.c', 'dut-main', inc), b.compile(out/'execute.S', 'dut-execute')]
    elf = out/(NAME+'.elf')
    b.bind_sources([b.common/'link.ld'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostartfiles', '-Wl,--gc-sections',
            '-T'+str(b.common/'link.ld'), *objects, '-lm', '-L'+str(b.llvm/'lib/generic'),
            '-lclang_rt.builtins-riscv64', '-o', elf], 'dut.link')
    metadata = json.loads(b.run([b.llvm/'bin/llvm-readobj', '--elf-output-style=JSON',
                                '--sections', '--symbols', elf], 'dut.metadata').stdout)[0]
    symbols = {r['Symbol']['Name']['Name']: r['Symbol'] for r in metadata['Symbols']}
    blob, sites = elf.read_bytes(), []
    for phase in (0, 1):
        fn = symbols['gap110_exec%d' % phase]
        pc = symbols['gap110_qbexec_site%d' % phase]['Value']
        sections = [r['Section'] for r in metadata['Sections'] if r['Section']['Type']['Name'] != 'SHT_NOBITS'
                    and r['Section']['Address'] <= fn['Value'] and
                    fn['Value']+fn['Size'] <= r['Section']['Address']+r['Section']['Size']]
        common.require(len(sections) == 1, 'Ambiguous execution section')
        start = sections[0]['Offset']+fn['Value']-sections[0]['Address']
        code, words, pcs, i = blob[start:start+fn['Size']], [], [], 0
        while i < len(code):
            length = 4 if int.from_bytes(code[i:i+2], 'little') & 3 == 3 else 2
            common.require(i+length <= len(code), 'Truncated opcode')
            words.append(int.from_bytes(code[i:i+length], 'little')); pcs.append(fn['Value']+i); i += length
        common.require(words[pcs.index(pc)] == 0x0eb5045b and any(
            words[j] in (0x42a1, 0x00800293) and words[j+1] == 0x0102f057 for j in range(len(words)-1)),
            'Exact M8 opcode/VL8 differs')
        normalized = list(words); normalized[pcs.index(pc)] = 0x08b5045b
        audit.audit_execution(normalized, pcs, pc)
        sites.append(dict(pc=pc, word=0x0eb5045b))
    fit = ROOT/'verification/coverage/check_elf_fit.py'
    b.bind_sources([fit])
    b.run([ROOT/'verification/tools/soc-venv/bin/python', fit, '--elf', elf, '--ram-bytes',
           '0x200000', '--output', out/'elf-fit.json'], 'elf-fit')
    pins = {**review['input_pins'], **b.sources, **b.tools, **b.link_inputs}
    common.verify(pins)
    record = dict(status='AFFINE_FULL8_HOST_ELF_PREFLIGHT_NOT_DUT', binary=str(elf), binary_sha256=common.sha(elf),
                  input_pins=pins, output_pins=common.pins(p for p in out.iterdir() if p.is_file()),
                  m=8, n=8, k_blocks=1, weight_profile=1, commands=2, sites=sites,
                  host_checks=44, host_negative_tests=2*len(MUTATIONS), dut_checks=41,
                  full_vrf_words=2048, initial_words=2048, source_guard_bytes=7840, csr_words=24,
                  spike='NOT_EXECUTED_CUSTOM_QBS_UNSUPPORTED', full_scalar_isa_verified=False,
                  slot=0, target_stages={'AUX': 1, 'SCALE': 2, 'MIN_SCALE': 3}, target_raw_indices=[9,16,14],
                  rst_pin='ara_tb.rst_n', reset_hold_complete_clocks=4,
                  ucli_syntax_qualified=False, vcs_launched=False, coverage_admitted=False,
                  rtl_modified=False, native_dut_oracle_verified=False, measured_FSM_gain=None)
    common.save(out/'preflight-manifest.json', record)
    return dict(output=str(out), seal=common.sha(out/'preflight-manifest.json'), elf_sha256=common.sha(elf),
                host_checks=44, host_negative_tests=2*len(MUTATIONS), VCS_started=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    print(json.dumps(build(p.parse_args().output.absolute())))
