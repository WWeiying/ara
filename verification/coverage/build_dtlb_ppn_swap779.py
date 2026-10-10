"""Formal779-bound software-only DTLB physical-page swap preflight; no EDA."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

import build_tlb_asid_matrix as shared
from ara_verify.spike_trace import parse_spike_commits
from rank_cva6_scalar_data767 import typed_nodes

life, build, require = shared.life, shared.build, shared.require
ROOT, OUT = shared.ROOT, shared.OUT
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vdtlb_ppn_swap_matrix.c'
BASE = OUT/'btb-ring-admitted779-parent-20261008-01'
BASE_SHA = '299cc1cf1bd65f2f64f495c9f791c3a190ba5329e86344f035224678ccfbb9ca'
CACHE_SHA = '2e254ca9a304e0c20432c8b775f3c5917999d8fe1e2fabea88b80b34a24c3bfb'
SYMBOLS = ('tohost', 'num_failed', 'g75_result', 'g75_trap', 'trap_fail',
           'ppm_observed', 'ppm_csr', 'ppm_root', 'ppm_mid', 'ppm_leaf',
           'ppm_first_load', 'ppm_second_load', '_end')
MASK = (1 << 64) - 1


def page(phase, entry):
    require(type(phase) is int and phase in range(3) and
            type(entry) is int and entry in range(16), 'Invalid phase/entry')
    return 255 - 17 * entry if phase == 1 else 17 * entry


def pa(index):
    require(type(index) is int and index in range(256), 'Invalid physical page')
    return 0x80080000 + index * 4096


def gold(index):
    return shared.GOLD ^ ((index * 0x0101010101010101) & MASK)


def word(index, offset):
    require(type(offset) is int and offset in range(512), 'Invalid word offset')
    return shared.GUARD if offset in (0, 511) else gold(index) ^ (((offset-1)*0x1000100010001) & MASK)


def address(entry):
    return shared.address(0, entry)


def pte(a, flags):
    return ((a >> 12) << 10) | flags


def mapping_proof():
    orders = shared.plru_order()
    for i in range(16):
        require(((pa(page(0, i)) >> 12) ^ (pa(page(1, i)) >> 12)) & 255 == 255,
                'Physical low8 PPN not complementary')
    require(len({address(i) for i in range(16)}) == 16 and
            len({shared.vpn(0, i) & 511 for i in range(16)}) == 16,
            'Sparse VA/leaf collision')
    return dict(physical_pages=[pa(17*i) for i in range(16)],
        mappings=[[pa(page(p, i)) for i in range(16)] for p in range(3)],
        virtual_addresses=[address(i) for i in range(16)], asid=0,
        plru_entry_order=orders, logical_low_ppn_bits=list(range(8)),
        runtime_entry_coverage_proven=False,
        obligation='DUT must confirm 16 distinct replacements per phase and repeated-hit ownership; '
                   'Spike has no physical CVA6 TLB replacement model.',
        high_ppn_capacity_not_a_gain_promise=True)


def validate(commits, s):
    require(commits and not any(c.vector_writes or c.fpr_writes or
            c.pc == s['trap_fail'] for c in commits), 'Unexpected vector/FP/trap')
    writes, histories, reads = {}, {}, {}
    for c in commits:
        for a,v in c.memory_accesses:
            if v is None: reads.setdefault(a, []).append(c)
            else:
                writes[a] = v
                histories.setdefault(a, []).append(v)
    require([writes.get(s['g75_result']), writes.get(s['g75_result']+4),
             writes.get(s['num_failed']), writes.get(s['tohost'])] == [8297, 0, 0, 1],
            'Complete8297-check terminal')
    original = writes.get(s['ppm_csr'])
    require(original is not None and original & 0x20000 == 0, 'Initial MPRV not clear')
    setting = (original & ~0x21888) | 0x20800
    satp = (8 << 60) | (s['ppm_root'] >> 12)
    csr = [original, 0] + [satp]*3 + [original]*3 + [0]
    require([writes.get(s['ppm_csr']+8*i) for i in range(9)] == csr, 'CSR phase/restoration')
    loads = [c for c in commits if c.pc in (s['ppm_first_load'], s['ppm_second_load'])]
    require(len(loads) == 96, 'Missing/extra translated loads')
    expected = [gold(page(p, i)) for p in range(3) for i in range(16) for _ in range(2)]
    require([writes.get(s['ppm_observed']+8*i) for i in range(96)] == expected,
            'Independent96 observed values')
    for k, c in enumerate(loads):
        require(c.pc == s['ppm_first_load' if k % 2 == 0 else 'ppm_second_load'] and
                shared.is_ld_zero(c.instruction) and list(c.gpr_writes.values()) == [expected[k]] and
                tuple(c.memory_accesses) == ((address((k % 32)//2), None),), 'Exact load owner/VA/value')
    # No stack, loop or speculative architectural memory access inside MPRV windows.
    active, owners, status_history, satp_history = False, [], [], []
    for c in commits:
        if c.memory_accesses and active:
            require(c.pc in (s['ppm_first_load'], s['ppm_second_load']), 'Extra translated memory')
            owners.append(c.pc)
        if 0x300 in c.csr_writes:
            v = c.csr_writes[0x300]
            if c.pc >= 0x80002000:
                status_history.append(v)
                require(v in (original, setting), 'Unexpected mstatus phase')
            active = bool(v & 0x20000)
        if 0x180 in c.csr_writes:
            satp_history.append(c.csr_writes[0x180])
    require(not active and owners == [c.pc for c in loads] and
            status_history == [v for _ in range(48) for v in (setting, original)] and
            satp_history == [satp]*3 + [0], 'Exact MPRV/ASID/SATP lifecycle')
    tables = {s['ppm_root']+16:pte(0x80000000, 0xcf)}
    for i in range(16):
        v = shared.vpn(0, i)
        tables[s['ppm_root']+8*(v >> 18)] = pte(s['ppm_mid'], 1)
        tables[s['ppm_mid']+8*((v >> 9)&511)] = pte(s['ppm_leaf'], 1)
        tables[s['ppm_leaf']+8*(v&511)] = pte(pa(page(2, i)), 0xc7)
    for name in ('ppm_root', 'ppm_mid', 'ppm_leaf'):
        require(s[name] % 4096 == 0, 'Misaligned page table')
        require(all(writes.get(s[name]+8*i) == tables.get(s[name]+8*i, 0)
                    for i in range(512)), 'Full independent PTE image')
    for i in range(16):
        a = s['ppm_leaf']+8*(shared.vpn(0, i)&511)
        hist = histories.get(a)
        require(hist == [0]+[pte(pa(page(p, i)), 0xc7) for p in range(3)], 'Exact PTE swap history')
    for i in range(16):
        a = pa(17*i)
        for j in range(512):
            offset, value = 8*j, word(17*i, j)
            history = histories.get(a+offset)
            require(history == [value], 'Data/guard initialization or preservation')
            observations = reads.get(a+offset, [])
            require(len(observations) == 1 and list(observations[0].gpr_writes.values()) == [value],
                    'Full physical data/guard reread')
    allowed = {pa(17*i)+8*j for i in range(16) for j in range(512)}
    require(not any(0x80080000 <= a < 0x80180000 and a not in allowed for a in writes),
            'Unexpected physical data-region store')
    require(all(writes.get(s['g75_trap']+8*i) == 0 for i in range(3)), 'Trap guard')
    return dict(shared.architecture.reference_counts(commits, s), software_checks=8297,
                translated_loads=96, independent_page_images=3,
                physical_data_guard_checks=8192, physical_data_bytes=65536,
                traps=0, vector_data_requests_expected=0)


def bind779(pins):
    m = life.read_bound(BASE/'admission-manifest.json', BASE_SHA)
    require(m['coverage_admitted'] is True and m['output'] == str(BASE), 'Not formal779')
    pins[str(BASE/'admission-manifest.json')] = BASE_SHA
    for name in ('combined-inputs.txt', 'combined-bits.json'):
        p = BASE/name; pins[str(p)] = m['output_pins'][str(p)]
        require(life.digest(p) == pins[str(p)], 'Formal779 evidence drift')
    ledger = (BASE/'combined-inputs.txt').read_text().splitlines()
    bits = json.loads((BASE/'combined-bits.json').read_bytes())
    require(len(ledger) == len(set(ledger)) == 780 and bits['tests'] == ledger[1:], 'Exact779 population')
    db = Path(ledger[0])/'snps/coverage/db'
    paths = [db/'design/verilog.design.xml', db/'shape/tgl.verilog.info.xml', db/'shape/tgl.verilog.shape.xml']
    for p in paths:
        pins[str(p)] = m['input_pins'][str(p)]
        require(life.digest(p) == pins[str(p)], 'Compiled identity drift')
    checks, defs = shared.native.definitions(*(shared.native.xml(p) for p in paths), [shared.SCOPE])
    require(checks[shared.SCOPE] == '817233724', 'Compiled DTLB checksum')
    # This artifact includes exact773 OR plus qualified ITLB/VMACC suffixes (formal775).
    cache = OUT/'scalar-mmu-axi-post773-static-ranking-agent-20261007-01.json'
    pins[str(cache)] = CACHE_SHA
    d = life.read_bound(cache, pins[str(cache)])
    prior = next(Path(p) for p in d['pins'] if p.endswith('/sv39-fault-alternating-offline-admitted-773-agent-20261007-01/combined-inputs.txt'))
    pins[str(prior)] = d['pins'][str(prior)]
    require(life.digest(prior) == pins[str(prior)] and prior.read_text().splitlines() == ledger[:774],
            'Cached773 prefix')
    require([str(Path(x['toggle']).parents[5]) for x in d['overlay_qualifications']] == ledger[774:776],
            'Cached two-overlay lineage')
    merged = {shared.SCOPE:d['union'][shared.SCOPE]}
    for vdb in ledger[776:]:
        paths = list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(paths) == 1, 'Suffix Toggle ambiguity')
        rows,h = shared.native.rows(paths[0], [shared.SCOPE])
        require(h == m['input_pins'][str(paths[0])], 'Suffix Toggle drift')
        pins[str(paths[0])] = h; merged = shared.native.union(merged, rows)
    row = merged[shared.SCOPE]; require(row['width'] == 11852 and row['checksum'] == checks[shared.SCOPE], 'DTLB width')
    nodes, arrays = typed_nodes(defs[shared.SCOPE]['shape'], row)
    targets = [n for n in nodes if re.fullmatch(r'content_[qn]\[(?:[0-9]|1[0-5])\]\.pte\.ppn', n['name'])]
    require(len(targets) == 32 and all(n['logical_width'] == 44 for n in targets), 'Exact32 PPN fields')
    return dict(scope=shared.SCOPE, checksum=row['checksum'], binary_width=row['width'],
        objects=targets, arrays_not_flattened=len(arrays),
        missing_serialized_capacity=sum(n['missing_slots'] for n in targets),
        predicted_not_measured=True, official_percentage=False, native_direction_labels_not_bound=True)


def prepare(out):
    require(not out.exists(), 'Fresh output required')
    pins = {}; target = bind779(pins)
    book = life.read_bound(shared.SOURCE, shared.SOURCE_SHA); pins[str(shared.SOURCE)] = shared.SOURCE_SHA
    texts = {}
    for rel in ('core/cva6_mmu/cva6_tlb.sv', 'core/cva6_mmu/cva6_mmu.sv',
                'core/include/cv64a6_imafdcv_sv39_config_pkg.sv'):
        p = ROOT/'hardware/deps/cva6'/rel; pins[str(p)] = book[str(p)]
        require(life.digest(p) == pins[str(p)], 'Frozen source drift'); texts[p.name] = p.read_text()
    source = shared.source_contract(texts)
    cmdfile = OUT/'repaired-aligned-build-20260930-01/compile.command.json'
    pins[str(cmdfile)] = life.digest(cmdfile)
    require('sim_l2_mb=2' in json.loads(cmdfile.read_bytes())['command'], 'Actual2MiB build required')
    command = json.loads(shared.TEMPLATE.read_bytes())
    old = str(ROOT/'apps/riscv-tests/isa/rv64uv/vgap99_csr_satp_mprv.c')
    require(command.count(old) == 1, 'Known compile template')
    command = [str(APP) if x == old else str(out/'input.elf') if x.endswith('/input.elf') else x for x in command]
    for p in (APP, shared.TEMPLATE, Path(__file__), Path(__file__).with_name('test_build_dtlb_ppn_swap779.py'),
              Path(shared.__file__), Path(shared.architecture.__file__), Path(shared.native.__file__),
              ROOT/'verification/tests/gap75_start.S', ROOT/'verification/tests/gap75.ld',
              Path(command[0]), build.LLVM/'llvm-readelf', build.LLVM/'llvm-objdump', build.SPIKE,
              Path(__file__).with_name('dtlb_ppn_swap_probe.tcl')):
        pins[str(p)] = life.digest(p)
    for folder in ('apps/riscv-tests/isa/macros', 'apps/riscv-tests/env', 'apps/common', 'verification/ara_verify'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts: pins[str(p)] = life.digest(p)
    life.check(pins); out.mkdir()
    try:
        life.save(out/'compile-command.json', command)
        with (out/'build.log').open('x') as f: subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=120)
        s = {n:build._elf_symbol(out/'input.elf', build.LLVM/'llvm-readelf', n) for n in SYMBOLS}
        require(s['_end'] < 0x80080000 and s['tohost'] == 0x80001000, 'ELF/data-window overlap')
        from elftools.elf.elffile import ELFFile
        with (out/'input.elf').open('rb') as f:
            elf = ELFFile(f)
            require(elf['e_entry'] == 0x80000000 and all(0x80000000 <= p['p_paddr'] and
                p['p_paddr']+p['p_memsz'] <= 0x80080000 for p in elf.iter_segments() if p['p_type']=='PT_LOAD'),
                'Exact entry/physical ELF fit')
        with (out/'disassembly.txt').open('x') as f:
            subprocess.run([str(build.LLVM/'llvm-objdump'), '-d', str(out/'input.elf')], stdout=f, check=True, timeout=30)
        spike = [str(build.SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
                 '-m0x80000000:0x200000', '-l', '--log-commits', str(out/'input.elf')]
        life.save(out/'spike-command.json', spike)
        with (out/'spike.trace').open('x') as f: subprocess.run(spike, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=120)
        require('exception ' not in (out/'spike.trace').read_text(), 'Spike exception')
        counts = validate(parse_spike_commits(out/'spike.trace'), s)
        life.check(pins)
        outputs = {str(p):life.digest(p) for p in out.iterdir() if p.is_file()}
        life.save(out/'preflight.json', dict(schema='DTLB_PPN_SWAP_FORMAL779_SOFTWARE_PREFLIGHT_V1',
            status='FULL_SPIKE_PTE_DATA_CSR_GUARDS_PASS_NOT_DUT', baseline=779,
            baseline_seal=BASE_SHA, input_pins=pins, output_pins=outputs, symbols=s, counts=counts,
            mapping=mapping_proof(), source_contract=source, target_evidence=target,
            expected_vcs_budget_seconds=300, VCS_launched=False, coverage_admitted=False))
        print('PREFLIGHT_PASS', life.digest(out/'preflight.json'), counts, flush=True)
    except Exception as e:
        life.save(out/'failure.json', dict(reason=str(e), coverage_admitted=False)); raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    prepare(p.parse_args().output.absolute())
