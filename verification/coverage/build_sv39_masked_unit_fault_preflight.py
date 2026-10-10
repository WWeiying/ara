"""Independent masked load fault/retry software proof; never launches VCS."""
import argparse
import json
from pathlib import Path
import re
import subprocess

import build_gap98_preflight as shared
from closure_point_inventory import definition, points, read_xml
from inventory_operand_debug import Design
from scoped_rv64c_memory import decode as compressed_memory

ROOT, OUT, require = shared.ROOT, shared.OUT, shared.require
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/vsv39_masked_unit_fault_retry.c'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
GUARD = 0xe370697c
WORDS = dict(smuf_masked_load=0x00038407, smuf_recovery_load=0x02038487,
             smuf_repair_store=0x006e3023, smuf_repair_sfence=0x120e0073,
             smuf_retry_mret=0x30200073, smuf_younger_store=0x0062b023)
SYMBOLS = ('tohost', 'g75_result', 'num_failed', 'trap_fail', 'smuf_pages',
           'smuf_guard_lo', 'smuf_guard_hi', 'seed', 'fault', 'result', 'records',
           'post', 'trap_count', 'marker', 'repair_pte', 'completed', 'smuf_masked_load',
           'smuf_recovery_load', 'smuf_repair_store', 'smuf_repair_sfence', 'smuf_retry_mret',
           'smuf_younger_store', 'smuf_ecall', 'smuf_m_resume')


def word(r, w, result=False):
    require(0 <= r < 6 and 0 <= w < 32, 'Bad oracle coordinate')
    seed = 0x55555555 if r == 4 else 0x6c700000 ^ (r << 16) ^ w
    data = bytearray(seed.to_bytes(4, 'little'))
    if result and r in (1, 2):
        for b in range(4):
            i = w * 4 + b
            if i < 17 and (r == 2 or i % 2 == 0):
                offset = (0x300 if r == 1 else 0x340) + i
                data[b] = ((0x91700000 ^ (offset // 4)) >> (8 * (offset % 4))) & 255
    return int.from_bytes(data, 'little')


def check_host(text):
    expected = []
    for r in range(6):
        for w in range(32):
            expected.append('R %d %d %08x %08x' % (r, w, word(r, w), word(r, w, True)))
    expected += ['D %d %08x' % (w, 0x91700000 ^ w) for w in range(1024)]
    expected += ['P %d %016x' % (w, ((0x91700000 ^ (2*w+1)) << 32) |
                               (0x91700000 ^ (2*w))) for w in range(512)]
    require(text.splitlines() == expected, 'Host/C oracle differs from independent Python gold')
    return dict(rows=len(expected), vector_words=192, data_bytes=4096)


def expected_memory(s):
    memory = {}
    def add(address, value, width):
        for i, b in enumerate(value.to_bytes(width, 'little')):
            require(address+i not in memory, 'Overlapping oracle memory')
            memory[address+i] = b
    pages = s['smuf_pages']
    require(pages % 4096 == 0 and s['smuf_guard_lo']+64 == pages and
            s['smuf_guard_hi'] == pages+16384, 'Page/guard layout differs')
    satp = (8 << 60) | ((pages+4096) >> 12)
    repaired = (pages >> 12 << 10) | 0xc7
    for w in range(1024):
        add(pages+4*w, 0x91700000 ^ w, 4)
    ptes = {512+1: ((pages+8192) >> 12 << 10) | 1, 512+2: 0x200000cf,
            1024: ((pages+12288) >> 12 << 10) | 1, 1536: repaired}
    for i in range(512, 2048):
        add(pages+i*8, ptes.get(i, 0), 8)
    for name in ('smuf_guard_lo', 'smuf_guard_hi'):
        for w in range(16):
            add(s[name]+4*w, GUARD, 4)
    for name in ('seed', 'fault', 'result'):
        require(s[name] % 64 == 0, 'Snapshot alignment differs')
        for offset in (0, 832):
            for w in range(16):
                add(s[name]+offset+4*w, GUARD, 4)
        for r in range(6):
            for w in range(32):
                add(s[name]+64+r*128+w*4, word(r, w, name == 'result'), 4)
    for phase in range(2):
        values = [13 if phase == 0 else 9,
                  s['smuf_masked_load'] if phase == 0 else s['smuf_ecall'],
                  0x40000300 if phase == 0 else 0, None, satp, 17, 0, 0,
                  117, 5, phase, 0 if phase == 0 else repaired]
        for i, value in enumerate(values):
            if value is not None:
                add(s['records']+phase*96+i*8, value, 8)
    for i, value in enumerate((17, 0, 0, 117, 5)):
        add(s['post']+8*i, value, 8)
    for name, value, width in (('trap_count', 2, 8), ('marker', 1, 8),
                                ('repair_pte', repaired, 8), ('completed', 0x67617037300001, 8),
                                ('g75_result', 85, 4), ('num_failed', 0, 4)):
        add(s[name], value, width)
    add(s['g75_result']+4, 0, 4)
    return memory


def validate_trace(text, s):
    expected = expected_memory(s)
    actual, regs, seen = {}, {0: 0}, {}
    traps = re.findall(r'exception\s+(\w+), epc 0x([0-9a-f]+)', text)
    require(traps == [('trap_load_page_fault', '%016x' % s['smuf_masked_load']),
                      ('trap_supervisor_ecall', '%016x' % s['smuf_ecall'])], 'Wrong exact trap ledger')
    tohost, vector_checks, partials, retired = [], [], 0, 0
    actions, awaiting_retry = [], False
    sites = {s[n]: n for n in ('smuf_masked_load', 'smuf_recovery_load',
             'smuf_repair_store', 'smuf_repair_sfence', 'smuf_retry_mret', 'smuf_younger_store')}
    for line in text.splitlines():
        require(not re.match(r'^core\s+[1-9][0-9]*:', line), 'Unexpected hart')
        m = re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$', line)
        if not m:
            continue
        mode, pc, instruction, tail = int(m[1]), int(m[2], 16), int(m[3], 16), m[4]
        require(pc != s['trap_fail'], 'Default trap handler executed')
        if pc in sites:
            require(instruction == WORDS[sites[pc]], 'Wrong exact site opcode')
        access = [(int(a, 16), int(v, 16) if v else None) for a, v in
                  re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?', tail)]
        if pc == s['smuf_masked_load'] and not access and not re.search(r'\bv8\s', tail):
            require(mode == 1 and re.fullmatch(r'\s+e8 m1 l17 c8_vstart 0x0+\s*', tail),
                    'Wrong faulting partial vector event')
            partials += 1
            actions.append('fault_partial')
            awaiting_retry = True
            continue
        retired += 1
        if awaiting_retry and instruction & 127 == 0x73 and instruction >> 20 == 0x341:
            require((instruction >> 12) & 7 in (2, 3, 6, 7) and (instruction >> 15) & 31 == 0,
                    'Original fault EPC overwritten before retry')
        if pc in sites:
            name = sites[pc]
            actions.append(name)
            seen[name] = seen.get(name, 0)+1
            require(mode == (1 if name in ('smuf_masked_load', 'smuf_recovery_load',
                                          'smuf_younger_store') else 3), 'Wrong site privilege')
            if name in ('smuf_masked_load', 'smuf_recovery_load'):
                r, vr, base = (1, 8, 0x40000300) if name == 'smuf_masked_load' else (2, 9, 0x40000340)
                want = sum(word(r, w, True) << (32*w) for w in range(32))
                writes = re.findall(r'\bv%d\s+0x([0-9a-f]+)' % vr, tail)
                require(len(writes) == 1 and int(writes[0], 16) == want and 'e8 m1 l17' in tail,
                        'Wrong complete active/masked/tail destination')
                require(access == [(base+i, None) for i in range(17)
                                   if name == 'smuf_recovery_load' or i % 2 == 0], 'Wrong masked memory addresses')
                vector_checks.append(vr)
            elif name == 'smuf_repair_store':
                require(access == [(s['smuf_pages']+12288, (s['smuf_pages'] >> 12 << 10) | 0xc7)],
                        'Wrong repair PTE store')
            elif name == 'smuf_repair_sfence':
                require(regs.get(28) == 0x40000000 and instruction == 0x120e0073,
                        'Wrong addressed SFENCE')
            elif name == 'smuf_retry_mret':
                require(instruction == 0x30200073, 'Wrong retry instruction')
                awaiting_retry = False
        for a, value in access:
            if value is None:
                continue
            opcode, funct = instruction & 127, (instruction >> 12) & 7
            if instruction & 3 != 3:
                decoded = compressed_memory(instruction)
                require(decoded is not None and decoded['kind'] == 'write', 'Unknown compressed store')
                require(a == (regs.get(decoded['base'], -1)+decoded['offset']) & ((1 << 64)-1),
                        'Compressed store address differs from decoded source GPR')
                width = decoded['size']
                # ABI stack spills can precede any trace write to that GPR.
                # They are not DUT ISA qualification; all oracle bytes below
                # are checked independently, never initialized from these spills.
                if decoded['register'] in regs:
                    require(value & ((1 << (width*8))-1) ==
                            regs[decoded['register']] & ((1 << (width*8))-1),
                            'Compressed store data differs from decoded source GPR')
                else:
                    require(not any(a+i in expected for i in range(width)),
                            'Unproven source GPR writes oracle memory')
            else:
                require(opcode in (0x23, 0x27), 'Unknown memory store opcode')
                width = (1 << funct) if opcode == 0x23 else {0: 1, 5: 2, 6: 4, 7: 8}.get(funct)
            require(width in (1, 2, 4, 8), 'Unknown store width')
            for i, byte in enumerate((value & ((1 << (8*width))-1)).to_bytes(width, 'little')):
                actual[a+i] = byte
            if a == s['tohost']:
                tohost.append(value)
        regs.update({int(r): int(v, 16) for r, v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)', tail)})
    require(tohost == [1] and partials == 1 and vector_checks == [8, 9] and
            seen == {n: 1 for n in sites.values()}, 'Incomplete/duplicate software execution')
    require(actions == ['fault_partial', 'smuf_repair_store', 'smuf_repair_sfence',
                        'smuf_retry_mret', 'smuf_masked_load', 'smuf_recovery_load',
                        'smuf_younger_store'] and not awaiting_retry and retired < 50000,
            'Fault/retry/recovery ordering or finite execution differs')
    require(all(actual.get(a) == b for a, b in expected.items()), 'Complete independent memory/CSR/guard oracle mismatch')
    for phase in range(2):
        status = int.from_bytes(bytes(actual.get(s['records']+phase*96+24+i, 255) for i in range(8)), 'little')
        require(status & 0x8000031888 == 0x800, 'Wrong S trap mstatus contract')
    return dict(status='SPIKE_MASKED_FAULT_RETRY_ORACLE_PASS_NOT_DUT', checks=85,
                retired=retired, verified_final_memory_bytes=len(expected), traps=2,
                masked_active_bytes=9, recovery_active_bytes=17, full_destination_bytes=256,
                mask_tail_snapshots_verified=True, original_PC_retry_verified=True,
                scalar_DUT_differential_qualified=False, coverage_admitted=False)


def bind_baseline(directory, seal):
    directory = directory.absolute()
    path = directory / 'admission-manifest.json'
    require(directory.parent == OUT and directory.resolve() == directory and
            re.fullmatch('[0-9a-f]{64}', seal) and shared.sha(path) == seal, 'Explicit admission seal mismatch')
    admission = json.loads(path.read_bytes())
    require(admission['output'] == str(directory), 'Foreign admission output')
    pins = dict(admission['output_pins'])
    require(all(str(directory/n) in pins for n in ('combined-bits.json', 'combined-inputs.txt', 'status.json')),
            'Admission missing baseline outputs')
    shared.check(pins)
    bitmap = json.loads((directory/'combined-bits.json').read_bytes())
    status = json.loads((directory/'status.json').read_bytes())
    count = len(bitmap['tests'])
    require(count >= 734 and len(set(bitmap['tests'])) == count and
            status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            status['aggregate_passed'] == count and status['coverage_admitted'] is True and
            (directory/'combined-inputs.txt').read_text().splitlines() ==
            [str(BUILD/'sim/simv.vdb'), *bitmap['tests']], 'Population/membership/PASS mismatch')
    pins[str(path)] = seal
    design = Design(BUILD/'sim/simv.vdb')
    for relative, expected in bitmap['design'].items():
        pins[str(design.db/relative)] = expected
    shared.check(pins)
    row = bitmap['metrics']['cond'][SCOPE]
    require(row['checksum'] == '1370170966' and row['width'] == 1140, 'Dispatcher shape drift')
    node = definition(read_xml(design.db/'shape/cond.verilog.shape.xml'), design.hierarchy[SCOPE], row['checksum'])
    target = points('cond', node, row['width'])[493]
    require(target['raw_index'] == 493 and target['line'] == '4353' and target['vector'] == '10' and
            target['expression'] == '(((!ara_req.vm)) || ara_req.use_vs2)' and
            target['attributes']['chksum'] == '1423779029', 'Compiled target drift')
    require(not (int(row['bits'],16) >> (row['width']-1-493)) & 1, 'Target already hit; no gain claim')
    return dict(baseline=str(directory), admission_seal=seal, tests=count,
                targets=[dict(scope=SCOPE, metric='cond', raw_index=493, checksum=row['checksum'],
                              width=row['width'], hit_before=False, point=target)],
                native_ID_claimed=False, inherited_cases_replayed=False), pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--baseline-seal', required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh agent-owned output required')
    baseline, pins = bind_baseline(args.baseline, args.baseline_seal)
    template = OUT/'gap99-csr-satp-mprv-preflight-707-20261006-01/compile-command.json'
    cmd = json.loads(template.read_bytes())
    old = str(ROOT/'apps/riscv-tests/isa/rv64uv/vgap99_csr_satp_mprv.c')
    require(cmd.count(old) == 1 and cmd[-2] == '-o', 'Compile template drift')
    cmd = [str(APP) if x == old else x for x in cmd]
    cmd[-1] = str(out/'input.elf')
    sources = json.loads((BUILD/'build-source-pins.json').read_bytes())
    source_bindings = {}
    for rel in ('hardware/src/ara_dispatcher.sv', 'hardware/src/lane/lane_sequencer.sv',
                'hardware/src/lane/operand_requester.sv', 'hardware/src/ara_soc.sv',
                'hardware/src/ara_system.sv', 'hardware/include/ara_pkg.sv'):
        original = ROOT/rel
        actual = (OUT/'old-image-source-evidence-20261006-01'/original.name if original.name in
                  ('ara_dispatcher.sv', 'lane_sequencer.sv') else original)
        require(shared.sha(actual) == sources[str(original)], 'Frozen source mismatch')
        pins[str(actual)] = sources[str(original)]
        source_bindings[str(original)] = str(actual)
    soc = (ROOT/'hardware/src/ara_soc.sv').read_text()
    require(re.findall(r'cfg\.NrPMPEntries\s*=\s*(\d+)\s*;', soc) == ['0'],
            'Old SoC PMP0 override differs')
    for p in (APP, Path(__file__).resolve(), Path(__file__).with_name('test_build_sv39_masked_unit_fault_preflight.py'),
              template, BUILD/'build-source-pins.json', ROOT/'verification/tests/gap75_start.S',
              ROOT/'verification/tests/gap75.ld', shared.LLVM/'clang', shared.LLVM/'llvm-readelf',
              shared.LLVM/'llvm-objdump', shared.SPIKE, Path(shared.__file__), Path(shared.parse_spike_commits.__code__.co_filename),
              Path(__file__).with_name('closure_point_inventory.py'), Path(__file__).parent/'reviewed_20261004/audit_readonly.py',
              Path(__file__).with_name('scoped_rv64c_memory.py'),
              Path('/usr/bin/cc').resolve()):
        pins[str(p.absolute())] = shared.sha(p)
    for p in (ROOT/'apps/riscv-tests/isa/macros').rglob('*'):
        if p.is_file():
            pins[str(p)] = shared.sha(p)
    shared.check(pins)
    out.mkdir()
    shared.save(out/'target-before.json', baseline)
    shared.save(out/'compile-command.json', cmd)
    try:
        host = ['/usr/bin/cc', '-DSMUF_ORACLE_HOST', str(APP), '-o', str(out/'host-oracle')]
        shared.save(out/'host-command.json', host)
        subprocess.run(host, check=True, timeout=30)
        host_text = subprocess.check_output([str(out/'host-oracle')], text=True, timeout=10)
        (out/'host.stdout').write_text(host_text)
        host_result = check_host(host_text)
        with (out/'compile.log').open('x') as stream:
            subprocess.run(cmd, check=True, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        symbols = {name: shared._elf_symbol(out/'input.elf', shared.LLVM/'llvm-readelf', name) for name in SYMBOLS}
        with (out/'input.disasm').open('x') as stream:
            subprocess.run([str(shared.LLVM/'llvm-objdump'), '-d', str(out/'input.elf')], check=True, stdout=stream, timeout=30)
        spike = [str(shared.SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
                 '-l', '--log-commits', str(out/'input.elf')]
        shared.save(out/'spike-command.json', spike)
        with (out/'spike.stdout').open('x') as stdout, (out/'spike.trace').open('x') as trace:
            subprocess.run(spike, check=True, stdout=stdout, stderr=trace, timeout=60)
        result = validate_trace((out/'spike.trace').read_text(), symbols)
        shared.save(out/'spike-validation.json', result)
        shared.check(pins)
        files = {str(p): shared.sha(p) for p in out.iterdir() if p.is_file()}
        manifest = dict(status='MASKED_UNIT_FAULT_SPIKE_PREFLIGHT_PASS_NOT_DUT', pins=pins,
            output_pins=files, baseline_binding=baseline, symbols=symbols, source_bindings=source_bindings,
            host_validation=host_result, spike_validation=result, input_elf=str(out/'input.elf'),
            VCS_budget_seconds=180, VCS_launched=False, native_DUT_qualified=False,
            rtl_changed=False, coverage_admitted=False, future_delta_requires_explicit_latest_admission_seal=True)
        shared.save(out/'preflight-manifest.json', manifest)
        print(json.dumps(dict(output=str(out), seal=shared.sha(out/'preflight-manifest.json'), validation=result)))
    except Exception as error:
        shared.save(out/'failure.json', dict(status='MASKED_FAULT_PREFLIGHT_FAILED', reason=str(error)))
        raise


if __name__ == '__main__':
    main()
