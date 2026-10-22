"""One finite binary16 fused-FMA fixture, exact rational gold and Spike preflight."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import re
import subprocess
from elftools.elf.elffile import ELFFile
import prepare_fpu_half_reset744 as reused

life, require = reused.life, reused.require
HERE = Path(__file__).resolve().parent
APP = life.ROOT/'apps/riscv-tests/isa/rv64uv/vgap_half_fma_finite.c'
PRE = life.OUT/'half-fma-finite-preflight-agent-20261007-01'
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
PATTERNS = ((0x3c01, 0x3bfe, 0xbc00), (0x3c00, 0x3c00, 0x1000),
            (0x3e00, 0x4000, 0xbc00), (0xbc01, 0x3bfe, 0x3c00),
            (0x3400, 0x4400, 0x3800), (0xbc00, 0x4000, 0xc000),
            (0x4000, 0x3800, 0xb400), (0x3c00, 0xbc00, 0x9000))


def decode(bits):
    require(0 <= bits < 65536 and (bits >> 10 & 31) != 31, 'Finite binary16 only')
    sign, exp, mant = bits >> 15, bits >> 10 & 31, bits & 1023
    value = Fraction(mant, 1 << 24) if exp == 0 else Fraction(1024+mant, 1024)*Fraction(2)**(exp-15)
    return -value if sign else value


def fused(a, b, c, rm):
    require(rm in (0, 1), 'Fixture supports RNE/RTZ')
    exact = decode(a)*decode(b)+decode(c)
    sign, value = (0x8000 if exact < 0 else 0), abs(exact)
    require(value <= decode(0x7bff), 'Fixture finite result bound')
    lo, hi = 0, 0x7bff
    while lo < hi:
        mid = (lo+hi+1)//2
        if decode(mid) <= value: lo = mid
        else: hi = mid-1
    selected = lo
    if rm == 0 and decode(lo) != value:
        upper = lo+1
        dl, du = value-decode(lo), decode(upper)-value
        if du < dl or (du == dl and upper % 2 == 0): selected = upper
    inexact = decode(selected) != value
    flags = int(inexact) | (2 if inexact and selected >> 10 == 0 else 0)
    return selected | sign, flags


def gold():
    inputs = [[PATTERNS[i % 8][j] for i in range(64)] for j in range(3)]
    snapshots, csrs = [], []
    for phase in range(4):
        rm, vl = int(phase == 1), 31 if phase == 3 else 64
        result, flags = list(inputs[2]), 0
        for i in range(vl):
            if phase == 2 and i % 2 == 0: continue
            result[i], f = fused(*(inputs[j][i] for j in range(3)), rm)
            flags |= f
        words = []
        for reg in range(32):
            half = inputs[0] if reg == 8 else inputs[1] if reg == 16 else result if reg == 24 else None
            for word in range(16):
                words.append(sum(half[word*4+k] << (16*k) for k in range(4)) if half else
                             0xaaaaaaaaaaaaaaaa if reg == 0 else 0x0101010101010101*(0x40+reg))
        snapshots.append(words); csrs.append([vl, 8, 0, 0, (rm << 5)|flags])
    return inputs, snapshots, csrs


def oracle(value):
    _, snapshots, csrs = gold()
    require([value('g75_result', 0, 4), value('g75_result', 4, 4), value('num_failed', 0, 4),
             value('tohost')] == [2900, 0, 0, 1], 'Terminal/full check count')
    for phase in range(4):
        for i, expected in enumerate(snapshots[phase]):
            require(value('hfm_vrf', (phase*512+i)*8) == expected, 'Full VRF/active/mask/tail differs')
        for i, expected in enumerate(csrs[phase]):
            require(value('hfm_csr', (phase*5+i)*8) == expected, 'Phase flags/frm/CSR differs')


def header():
    inputs, snapshots, csrs = gold()
    array = lambda data: '{'+','.join(hex(x)+'ULL' for x in data)+'}'
    return ('#include <stdint.h>\nstatic const uint16_t hfm_inputs[3][64] = {'+
            ','.join(array(x) for x in inputs)+'};\n'+
            'static const volatile struct { uint64_t before[8]; uint16_t a[64],b[64],c[64]; uint64_t after[8]; } '+
            'hfm_source __attribute__((aligned(128))) = {'+array([0x5a3c719de4b208f6]*8)+','+
            ','.join(array(x) for x in inputs)+','+array([0x5a3c719de4b208f6]*8)+'};\n'+
            'static const uint64_t hfm_expected[4][512] = {'+','.join(array(x) for x in snapshots)+'};\n'+
            'static const uint64_t hfm_expected_csr[4][5] = {'+','.join(array(x) for x in csrs)+'};\n')


def build():
    require(not PRE.exists(), 'Fresh preflight only')
    PRE.mkdir()
    (PRE/'half_fma_gold.h').write_text(header())
    old = json.loads((reused.OUT/'compile-command.json').read_bytes())
    command = [str(APP) if x == str(reused.APP) else str(PRE/'input.elf') if x == str(reused.OUT/'input.elf') else x for x in old]
    command.insert(1, '-I'+str(PRE))
    require('-O2' in command and 'ZCC' not in ' '.join(command), 'Non-ZCC O2 toolchain')
    life.save(PRE/'compile-command.json', command)
    with (PRE/'build.log').open('x') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    names = ('hfm_unmasked', 'hfm_masked', 'hfm_vrf', 'hfm_csr', 'hfm_source', 'hfm_expected',
             'hfm_inputs', 'g75_result', 'num_failed', 'tohost', 'trap_fail')
    with (PRE/'input.elf').open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name in names}
        segments = [(s['p_vaddr'], s.data()) for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
    require(set(symbols) == set(names), 'Required ELF symbols')
    def elfbytes(address, size):
        matches = [data[address-start:address-start+size] for start,data in segments if start <= address and address+size <= start+len(data)]
        require(len(matches) == 1, 'ELF object unbound'); return matches[0]
    inputs, snapshots, csrs = gold()
    source = b''.join(x.to_bytes(8,'little') for x in [0x5a3c719de4b208f6]*8)+b''.join(x.to_bytes(2,'little') for row in inputs for x in row)+b''.join(x.to_bytes(8,'little') for x in [0x5a3c719de4b208f6]*8)
    require(elfbytes(symbols['hfm_source'], len(source)) == source, 'ELF independent input/guards')
    require(elfbytes(symbols['hfm_expected'], 16384) == b''.join(x.to_bytes(8,'little') for row in snapshots for x in row), 'ELF full independent gold')
    words = {k: int.from_bytes(elfbytes(symbols[k],4),'little') for k in ('hfm_unmasked','hfm_masked')}
    require(words == {'hfm_unmasked':0xb3041c57,'hfm_masked':0xb1041c57}, 'Exact fused opcode/operand/mask')
    sc = [str(SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(PRE/'input.elf')]
    life.save(PRE/'spike-command.json', sc)
    with (PRE/'spike.trace').open('x') as log:
        subprocess.run(sc, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    commits = reused.old.shared.shared.spike_trace.parse_spike_commits(PRE/'spike.trace')
    writes = {a:v for c in commits for a,v in c.memory_accesses if v is not None}
    oracle(lambda n,o=0,size=8:writes.get(symbols[n]+o))
    operations = [c for c in commits if c.instruction in words.values()]
    require([c.instruction for c in operations] == [words['hfm_unmasked']]*2+[words['hfm_masked'],words['hfm_unmasked']], 'Exact four FMA phases')
    require(not any(c.pc==symbols['trap_fail'] for c in commits) and 'exception ' not in (PRE/'spike.trace').read_text(), 'No Spike traps')
    counts = reused.old.shared.shared.reference_counts(commits, symbols)
    pins = {str(p):life.digest(p) for p in PRE.iterdir() if p.is_file()}
    for p in (APP, Path(__file__).resolve(), HERE/'test_half_fma_finite.py', Path(reused.__file__),
              Path(reused.old.shared.shared.__file__), Path(command[0]).resolve(), SPIKE,
              life.ROOT/'verification/tests/gap75_start.S', life.ROOT/'verification/tests/gap75.ld'):
        pins[str(p)] = life.digest(p)
    frozen = json.loads((life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
    for rel in ('hardware/src/lane/vmfpu.sv','hardware/deps/fpnew/src/fpnew_fma.sv',
                'hardware/deps/fpnew/src/fpnew_top.sv','hardware/deps/fpnew/src/fpnew_opgroup_block.sv',
                'hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv','hardware/deps/fpnew/src/fpnew_pkg.sv'):
        p=life.ROOT/rel; pins[str(p)]=frozen[str(p)]
    life.check(pins)
    record = dict(status='FOUR_PHASE_RATIONAL_SPIKE_FULL_VRF_CSR_PASS_NO_DUT', pins=pins,
        symbols=symbols, words=words, counts=counts, software_checks=2900, phases=4,
        full_vrf_bytes=16384, csr_words=20, expected_csr=csrs, source_bytes=512,
        ELF_sha256=life.digest(PRE/'input.elf'), EDA_launched=False, coverage_admitted=False,
        reference='Exact integer/rational binary16 fused single rounding, independently cross-checked with Spike',
        evidence_boundary='DUT valid/result/flags and full architectural diff still required')
    life.save(PRE/'preflight.json', record)
    print(json.dumps(dict(output=str(PRE),seal=life.digest(PRE/'preflight.json'),counts=counts)))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',action='store_true',required=True)
    p.parse_args();build()
