"""Compact independent whole-VRF integer oracle and Spike preflight; no VCS."""
import argparse
import json
from pathlib import Path
import subprocess

import build_tlb_asid_matrix as shared
from admit_stride_metadata768 import dedup
import scoped_rv64c_memory as rvc

life, build, require = shared.life, shared.build, shared.require
ROOT, OUT = life.ROOT, life.OUT
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/vmacc_c_fifo_length_ring.c'
BASE = OUT / 'sv39-fault-alternating-offline-admitted-773-agent-20261007-01'
SEAL = '65710f130e698571f9e17800e57361b0baa2a9d407a02287409797de64f64060'
STATIC = OUT / 'vmacc-C-fifo-toggle773-static-agent-20261007-02.json'
STATIC_SHA = '34058f97f312f0e8046afd98a46925d910af6113548fe62195315554fcc73628'
GUARD = 0x9696969696969696
SYMBOLS = ('tohost', 'num_failed', 'g75_result', 'trap_fail', 'vmacc_ring_checks',
           'vmacc_ring_source', 'vmacc_ring_vrf', 'vmacc_ring_csr', 'vmacc_ring_op', 'vmacc_ring_recovery')


def golden():
    a = bytes((i ^ 0xa5) & 255 for i in range(1024))
    b = bytes((2 * i + 1) & 255 for i in range(1024))
    source = GUARD.to_bytes(8, 'little') * 2 + a + b + GUARD.to_bytes(8, 'little') * 2
    phases = []
    for phase in range(4):
        count = [4, 8, 12, 12][phase]
        c = bytes((0x5a + (count if i < 1020 or phase == 0 else count - 4) * a[i] * b[i]
                   + (1 if phase == 3 and i < 4 else 0)) & 255 for i in range(1024))
        phases.append(bytes([0x5a]) * 1024 + a + b + c)
    return source, phases


def validate(path, symbols):
    commits = build.parse_spike_commits(path)
    require(not any(c.pc == symbols['trap_fail'] for c in commits) and
            'exception ' not in path.read_text(), 'Unexpected trap')
    writes = {a: v for c in commits for a, v in c.memory_accesses if v is not None}
    source, phases = golden()
    readback, snapshot_bytes, memory = set(), {}, {}
    for c in commits:
        for a, v in c.memory_accesses:
            if v is not None:
                decoded = rvc.decode(c.instruction)
                if decoded:
                    require(decoded['kind'] == 'write', 'Read carrying store effect')
                    width = decoded['size']
                elif c.instruction & 0x7f == 0x23:
                    require((c.instruction >> 12 & 7) <= 3, 'Unsupported scalar store width')
                    width = 1 << (c.instruction >> 12 & 7)
                else:
                    require(c.instruction & 0x7f == 0x27, 'Unknown memory writer')
                    width = 1
                for i in range(width):
                    memory[a + i] = (v >> (8 * i)) & 255
            if v is not None and c.instruction & 0x7f == 0x27 and \
                    symbols['vmacc_ring_vrf'] <= a < symbols['vmacc_ring_vrf'] + 4 * 4128:
                require(a not in snapshot_bytes, 'Duplicate snapshot byte')
                snapshot_bytes[a] = v
            if v is None and symbols['vmacc_ring_source'] <= a < symbols['vmacc_ring_source'] + len(source):
                if c.instruction & 0x7f == 3:
                    require(c.instruction >> 12 & 7 == 3 and len(c.gpr_writes) == 1, 'Full source word read')
                    offset = a - symbols['vmacc_ring_source']
                    require(offset % 8 == 0 and list(c.gpr_writes.values()) ==
                            [int.from_bytes(source[offset:offset + 8], 'little')], 'Immutable source value')
                    readback.add(offset)
    require(readback == set(range(0, len(source), 8)), 'Complete immutable source readback')
    for phase, vrf in enumerate(phases):
        image = GUARD.to_bytes(8, 'little') * 2 + vrf + GUARD.to_bytes(8, 'little') * 2
        start = symbols['vmacc_ring_vrf'] + phase * len(image)
        require(all(snapshot_bytes.get(start + 16 + i) == v for i, v in enumerate(vrf)),
                'Full VRF phase%d' % phase)
        require(all(writes.get(start + i) == GUARD for i in (0, 8, 4112, 4120)),
                'Every snapshot guard')
        csrs = ([1024, 1020, 1024, 4][phase], 3, 0, 0, 0)
        require([writes.get(symbols['vmacc_ring_csr'] + 40 * phase + 8 * i)
                 for i in range(5)] == list(csrs), 'Every phase CSR')
    require(len(snapshot_bytes) == 16384, 'No extra or missing snapshot byte')
    macc = [c for c in commits if c.pc == symbols['vmacc_ring_op']]
    require(len(macc) == 12, 'Exactly twelve target operations')
    for index, c in enumerate(macc):
        insn = c.instruction
        require(insn & 0x7f == 0x57 and insn >> 26 == 0x2d and (insn >> 25) & 1 == 1 and
                (insn >> 7) & 31 == 24 and (insn >> 15) & 31 == 8 and (insn >> 20) & 31 == 16,
                'Exact unmasked VMACC tuple')
        require(c.vector_vl == [1024, 1020, 1024][index // 4] and c.vector_sew == 8 and
                set(c.vector_writes) == set(range(24, 32)), 'Exact m8 target shape')
    require(sum(c.pc == symbols['vmacc_ring_recovery'] for c in commits) == 1, 'One recovery')
    def observed(name, offset=0, size=4):
        values = [memory.get(symbols[name] + offset + i) for i in range(size)]
        require(all(v is not None for v in values), 'Missing terminal bytes')
        return int.from_bytes(bytes(values), 'little')
    require([observed('g75_result'), observed('g75_result', 4),
             observed('num_failed'), observed('tohost', size=8)] == [2344, 0, 0, 1],
            '2344-check terminal')
    return dict(retirements=len(commits), checks=2344, target_VMACC=12, full_VRF_bytes=16384,
                source_guard_bytes=len(source), exact_phase_CSRs=20, recovery=1)


def prepare(out, existing=None):
    require(not out.exists() and out.parent == OUT, 'Fresh preflight output')
    base = life.read_bound(BASE / 'admission-manifest.json', SEAL)
    require(base['coverage_admitted'] is True, 'Not admitted773')
    ledger = BASE / 'combined-inputs.txt'
    require(life.digest(ledger) == base['output_pins'][str(ledger)] and
            len(ledger.read_text().splitlines()) == 774, 'Exact773 ledger')
    static = life.read_bound(STATIC, STATIC_SHA)
    life.check(static['pins'])
    source, phases = golden()
    words = lambda data: [int.from_bytes(data[i:i + 8], 'little') for i in range(0, len(data), 8)]
    text = '#define RING_GUARD 0x9696969696969696ULL\n'
    for name, qualifier in (('vmacc_ring_source', 'volatile'), ('vmacc_ring_source_gold', 'static const')):
        text += '%s uint64_t %s[260] __attribute__((aligned(128))) = {%s};\n' % (
            qualifier, name, ','.join('0x%xULL' % v for v in words(source)))
    text += 'static const uint64_t vmacc_ring_gold[4][512] = {%s};\n' % ','.join(
        '{' + ','.join('0x%xULL' % v for v in words(p)) + '}' for p in phases)
    out.mkdir()
    artifact = existing or out
    if existing:
        require((artifact / 'vmacc_c_fifo_gold.h').read_text() == text, 'Existing independent golden header')
    else:
        (artifact / 'vmacc_c_fifo_gold.h').write_text(text)
    command = json.loads(shared.TEMPLATE.read_bytes())
    command = [str(APP) if a.endswith('/vgap99_csr_satp_mprv.c') else
               str(artifact / 'input.elf') if a.endswith('/input.elf') else a for a in command]
    command += ['-I' + str(artifact), '-fno-unroll-loops']
    require(not any('Terapines' in a or 'ZCC' in a for a in command), 'Non-ZCC LLVM')
    pins = dict(static['pins'])
    for p in (APP, shared.TEMPLATE, Path(__file__).resolve(), Path(build.__file__).resolve(),
              Path(command[0]), build.SPIKE, build.LLVM / 'llvm-readelf',
              ROOT / 'verification/tests/gap75_start.S', ROOT / 'verification/tests/gap75.ld',
              artifact / 'vmacc_c_fifo_gold.h', Path(rvc.__file__).resolve()):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    if existing:
        require(json.loads((artifact / 'compile-command.json').read_bytes()) == command, 'Existing actual compile command')
    else:
        life.save(out / 'compile-command.json', command)
        with (out / 'build.log').open('x') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=True)
    from elftools.elf.elffile import ELFFile
    with (artifact / 'input.elf').open('rb') as stream:
        elf = ELFFile(stream)
        require(all(0x80000000 <= p['p_paddr'] and p['p_paddr'] + p['p_memsz'] <= 0x80040000
                    for p in elf.iter_segments() if p['p_type'] == 'PT_LOAD'), 'Frozen image L2 fit')
    symbols = {n: build._elf_symbol(artifact / 'input.elf', build.LLVM / 'llvm-readelf', n) for n in SYMBOLS}
    require(symbols['tohost'] == 0x80001000, 'Frozen image tohost ABI')
    duplicate = dedup(ledger.read_text().splitlines(), life.digest(artifact / 'input.elf'), base['input_pins'])
    life.save(out / 'elf-dedup.json', duplicate)
    spike = [str(build.SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
             '-l', '--log-commits', str(artifact / 'input.elf')]
    if existing:
        require(json.loads((artifact / 'spike-command.json').read_bytes()) == spike, 'Existing actual Spike command')
    else:
        life.save(out / 'spike-command.json', spike)
        with (out / 'spike.trace').open('x') as stream:
            subprocess.run(spike, stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=True)
    counts = validate(artifact / 'spike.trace', symbols)
    life.check(pins)
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in artifact.iterdir() if p.is_file()})
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in out.iterdir() if p.is_file()})
    life.save(out / 'preflight.json', dict(status='VMACC_RING_SPIKE_FULL_REGION_ORACLE_PASS_NOT_DUT',
        baseline=773, baseline_seal=SEAL, expected_new_slots_upper_bound=144, measured_gain=None,
        symbols=symbols, counts=counts, input_pins=pins, budget_seconds=600,
        ELF=str(artifact / 'input.elf'), reference=str(artifact / 'spike.trace'),
        coverage_admitted=False, VCS_started=False, RTL_modified=False))
    print('PREFLIGHT_PASS', life.digest(out / 'preflight.json'), counts, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--existing-build', type=Path)
    args = parser.parse_args()
    prepare(args.output.resolve(), args.existing_build.resolve() if args.existing_build else None)
