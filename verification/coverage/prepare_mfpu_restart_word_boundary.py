"""One fixed e16/m8 restart case: exact finite oracle and Spike preflight only."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys

from elftools.elf.elffile import ELFFile
import prepare_half_fma_finite as reused

life, require = reused.life, reused.require
HERE = Path(__file__).resolve().parent
APP = life.ROOT / 'apps/riscv-tests/isa/rv64uv/vgap_mfpu_restart_word_boundary.c'
OUT = life.OUT / 'mfpu-restart-word-boundary-preflight768-agent-20261007-01'
REVIEW = life.OUT / 'rvv-mfpu-restart-word-boundary768-static-agent-20261007-01.json'
REVIEW_SHA = '3f5d4743ab041e8b45162189095ab4b2e51bbe381d030e7a6412dccc365dc1fa'
STARTS = (508,) * 4 + (511,) * 4 + (0,) * 4
OPCODE = 0xb3041c57
CHECKS = 6264
GUARD = 0x5a3c719de4b208f6
NAMES = ('mr_target_fma', 'mr_vrf', 'mr_csr', 'mr_before', 'mr_source', 'mr_expected',
         'g75_result', 'num_failed', 'tohost', 'trap_fail')


def half_integer(value):
    require(isinstance(value, int) and 0 <= value <= 1024, 'Exact finite integer domain')
    if value == 0: return 0
    exponent = value.bit_length() - 1
    return ((exponent + 15) << 10) | ((value - (1 << exponent)) << (10 - exponent))


def decode(bits):
    require(0 <= bits < 0x7c00, 'Positive finite binary16 only')
    exponent, mantissa = bits >> 10, bits & 1023
    return Fraction(mantissa, 1 << 24) if not exponent else Fraction(1024 + mantissa, 1024) * Fraction(2) ** (exponent - 15)


def vector_state(destination):
    words = []
    for reg in range(32):
        for word in range(16):
            if reg < 8:
                value = 0x0101010101010101 * (0x40 + reg)
            else:
                elements = [0x4000] * 4 if reg < 16 else [0x4400] * 4 if reg < 24 else [
                    destination[(reg - 24) * 64 + word * 4 + k] for k in range(4)]
                value = sum(v << (16 * k) for k, v in enumerate(elements))
            words.append(value)
    return words


def gold():
    destination = [0x4800] * 512
    operations = []; snapshots = []
    for index, start in enumerate(STARTS):
        if index % 4 == 0: destination = [0x4800] * 512
        for element in range(start, 512):
            exact = decode(0x4000) * decode(0x4400) + decode(destination[element])
            require(exact.denominator == 1, 'Fixture unexpectedly inexact')
            destination[element] = half_integer(int(exact))
            require(decode(destination[element]) == exact, 'Not an exact RNE binary16 result')
        state = vector_state(destination)
        operations.append(state)
        if index % 4 == 3: snapshots.append(state)
    return operations, snapshots


def source_bytes():
    return b''.join(v.to_bytes(8, 'little') for v in [GUARD] * 8) + b''.join(
        v.to_bytes(2, 'little') for value in (0x4000, 0x4400, 0x4800) for v in [value] * 512) + b''.join(
        v.to_bytes(8, 'little') for v in [GUARD] * 8)


def header():
    array = lambda values: '{' + ','.join(hex(v) + 'ULL' for v in values) + '}'
    _, snapshots = gold()
    return ('#include <stdint.h>\nstatic const volatile struct { uint64_t before[8]; uint16_t a[512],b[512],c[512]; uint64_t after[8]; } '
            'mr_source __attribute__((aligned(128))) = {' + array([GUARD] * 8) + ',' +
            ','.join(array([v] * 512) for v in (0x4000, 0x4400, 0x4800)) + ',' + array([GUARD] * 8) + '};\n' +
            'static const uint64_t mr_expected[3][512] = {' + ','.join(array(s) for s in snapshots) + '};\n')


def oracle(value):
    require([value('g75_result', 0, 4), value('g75_result', 4, 4), value('num_failed', 0, 4),
             value('tohost')] == [CHECKS, 0, 0, 1], 'Terminal/check count failure')
    _, snapshots = gold()
    for phase, words in enumerate(snapshots):
        for word, expected in enumerate(words):
            require(value('mr_vrf', (phase * 512 + word) * 8) == expected, 'Complete VRF/source/prefix/destination mismatch')
    for index, start in enumerate(STARTS):
        require(value('mr_before', index * 8) == start, 'Requested restart missing or reordered')
        for k, expected in enumerate((512, 11, 0, 0, 0)):
            require(value('mr_csr', (index * 5 + k) * 8) == expected, 'Defined CSR/flags mismatch')


def validate_commits(commits, symbols, instruction):
    require(instruction == OPCODE, 'Exact FMA opcode/source/destination required')
    registers = {}; index = 0
    expected, _ = gold()
    for commit in commits:
        require(commit.pc != symbols['trap_fail'], 'Unexpected trap')
        registers.update(commit.vector_writes)
        if commit.pc != symbols['mr_target_fma']:
            require(commit.instruction != OPCODE, 'Foreign FMA site')
            continue
        require(index < 12 and commit.instruction == OPCODE, 'Extra or changed target instruction')
        require(set(registers) == set(range(32)), 'Missing full VRF architectural state')
        actual = [((registers[reg] >> (word * 64)) & ((1 << 64) - 1)) for reg in range(32) for word in range(16)]
        require(actual == expected[index], 'Independent per-instruction full VRF mismatch')
        index += 1
    require(index == 12, 'Missing target operations')
    writes = {address: data for commit in commits for address, data in commit.memory_accesses if data is not None}
    oracle(lambda name, offset=0, size=8: writes.get(symbols[name] + offset))
    source = range(symbols['mr_source'], symbols['mr_source'] + 3200)
    require(not any(address in source for address in writes), 'Source/guard memory modified')
    return dict(target_instructions=12, per_instruction_full_VRF_bytes=49152,
                memory_full_VRF_bytes=12288, per_instruction_CSR_words=60, requested_start_words=12)


def build():
    require(not OUT.exists(), 'Fresh independent preflight only')
    review = life.read_bound(REVIEW, REVIEW_SHA)
    life.check(review['pins'])
    require(review['population'] == 768 and review['target_objects'] == 76
            and review['exact_missing_serialized_positions'] == 726, 'Exact source candidate binding')
    prior = json.loads((reused.PRE / 'preflight.json').read_bytes())
    template = reused.PRE / 'compile-command.json'
    require(life.digest(template) == prior['pins'][str(template)], 'Consumed compiler template drift')
    command = json.loads(template.read_bytes())
    substitutions = {str(reused.APP): str(APP), str(reused.PRE / 'input.elf'): str(OUT / 'input.elf'),
                     '-I' + str(reused.PRE): '-I' + str(OUT)}
    command = [substitutions.get(arg, arg) for arg in command]
    require(all(flag in command for flag in ('-O2', '-fno-vectorize', '-fno-slp-vectorize', '-DVLEN=1024', '-DNR_LANES=4'))
            and 'ZCC' not in ' '.join(command) and str(APP) in command, 'Frozen compiler/fixture settings')
    compiler = Path(command[0]).resolve()
    require(life.digest(compiler) == prior['pins'][str(compiler)], 'Compiler identity drift')
    require(life.digest(reused.SPIKE) == prior['pins'][str(reused.SPIKE)], 'Spike identity drift')
    OUT.mkdir()
    (OUT / 'mfpu_restart_gold.h').write_text(header())
    life.save(OUT / 'compile-command.json', command)
    with (OUT / 'build.log').open('x') as log:
        subprocess.run(command, cwd=life.ROOT, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    with (OUT / 'input.elf').open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name in NAMES}
        segments = [(s['p_vaddr'], s.data()) for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    require(set(symbols) == set(NAMES), 'Missing required ELF symbols')
    def elfbytes(address, size):
        matches = [data[address-base:address-base+size] for base, data in segments if base <= address and address+size <= base+len(data)]
        require(len(matches) == 1, 'Unbound/ambiguous ELF range')
        return matches[0]
    require(elfbytes(symbols['mr_source'], 3200) == source_bytes(), 'ELF independent sources/guards differ')
    _, snapshots = gold()
    require(elfbytes(symbols['mr_expected'], 12288) == b''.join(v.to_bytes(8, 'little') for s in snapshots for v in s), 'ELF full VRF oracle differs')
    instruction = int.from_bytes(elfbytes(symbols['mr_target_fma'], 4), 'little')
    require(instruction == OPCODE, 'Exact assembled opcode differs')
    command = [str(reused.SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0', '-l', '--log-commits', str(OUT / 'input.elf')]
    life.save(OUT / 'spike-command.json', command)
    with (OUT / 'spike.trace').open('x') as log:
        subprocess.run(command, cwd=life.ROOT, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    require('exception ' not in (OUT / 'spike.trace').read_text(), 'Unexpected Spike exception')
    shared = reused.reused.old.shared.shared
    commits = shared.spike_trace.parse_spike_commits(OUT / 'spike.trace')
    checks = validate_commits(commits, symbols, instruction)
    counts = shared.reference_counts(commits, symbols)
    pins = {**review['pins'], str(REVIEW): REVIEW_SHA, str(template): life.digest(template),
            str(reused.PRE / 'preflight.json'): life.digest(reused.PRE / 'preflight.json')}
    for p in [APP, Path(__file__).resolve(), HERE / 'test_prepare_mfpu_restart_word_boundary.py', compiler,
              Path(reused.__file__), Path(reused.reused.__file__), Path(reused.reused.old.__file__),
              Path(reused.reused.old.shared.__file__),
              reused.SPIKE, life.ROOT / 'verification/tests/gap75_start.S', life.ROOT / 'verification/tests/gap75.ld',
              Path(shared.spike_trace.__file__), Path(shared.__file__), *OUT.iterdir()]:
        if p.is_file(): pins[str(p.resolve())] = life.digest(p)
    life.check(pins)
    record = dict(status='MFPU_RESTART768_SPIKE_FULL_VRF_CSR6264_PASS_NOT_DUT', source_review_sha256=REVIEW_SHA,
        source_bindings=review['source_producer_paths'], pins=pins, symbols=symbols, instruction=instruction,
        counts=counts, checks=checks, starts=list(STARTS), software_checks=CHECKS, source_guard_bytes=3200,
        numerical_domain='Exact finite binary16 integers; independent rational FMA, no IEEE certification claim',
        CSR_expected=[512, 11, 0, 0, 0], source_review_raw_candidate_positions=726,
        scope_constraints={'LMUL':8, 'nonoverlapping_aligned_groups':[8,16,24],
            'vstart_rewritten_before_every_FMA':True, 'destination_reinitialized_each_phase':8,
            'phase_final_active_value':40, 'phase_prefix_value':8,
            'primary_target':'vfu_operation_i.vstart[6]',
            'inactive_lane_bit7_valid_copy_not_guaranteed':True,
            'predicted_hits_or_percentage':None},
        simulation_launched=False, EDA_launched=False, coverage_admitted=False, intended_future_DUT_budget_seconds=600,
        DUT_requirements=['Same sealed ELF and frozen simulator/source manifest', 'Full scalar and vector Spike architectural comparison',
            'Independent full VRF/source/guards/CSR oracle', 'All defined bytes compared without blanket skip',
            'AXI request/response conservation and last-drain contract', 'Actual raw768 delta, no predicted-percent admission'])
    life.save(OUT / 'preflight.json', record)
    print(json.dumps(dict(output=str(OUT), seal=life.digest(OUT / 'preflight.json'), status=record['status'], counts=counts)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', required=True)
    parser.parse_args()
    build()
