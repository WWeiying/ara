"""Read original evidence only; never launches a simulator or admits coverage.

These data readback checks supplement, not replace, the original full oracle.
The immutable ELF hashes bind the compiled PCs and the reference formulas.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import struct

import akv_historical_budget_oracle_717 as original
import audit_akv_budget_qualification_gaps as descriptor
from audit_historical_timeout_contracts_717 import code_at


HASHES = {
    'cache': '37c66165e5499258bb505c6f38431f74e7b19d5bb5e6232973441543b044c8c8',
    'descriptor': 'f08781d48f8a29a5413850b54af4de7d4c31117bc588934acfd6d46b585df7c2',
    'skew': 'bb333b09bee3df3280dff94abb0aedb257c8c7ae434396c7c5b604d470ab0051',
}
WORDS = [0x00b5205b, 0x0005345b, 0x0005345b, 0x0005345b,
         0x02a0605b, 0x02a0205b, 0x0005345b, 0x00b5605b,
         0x0005345b, 0x0005345b, 0x0005345b, 0x0000505b]
SELECTORS = [0, 0, 1, 2, 0, 0, 0, 0, 0, 1, 2, 0]
require = original.require


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def rows(path):
    with Path(path).open() as stream:
        yield from csv.DictReader(stream)


def number(row, key):
    return int(row[key], 16)


def cache_prefix(trace):
    stores, loads, checks = [0]*3, [0]*3, [0]*3
    store_pcs = [0x8000013c, 0x800001c0, 0x80000248]
    load_pcs = [0x80000170, 0x800001f4, 0x8000027c]
    check_pcs = [0x8000017a, 0x800001fe, 0x80000286]
    fail_pcs = [0x80000188, 0x8000020c, 0x80000294]
    total, last, fences = 0, None, Counter()
    progress = []
    for row in trace:
        if row['event'] != 'retire':
            continue
        require(int(row['order']) == total, 'Noncontiguous retirement sequence')
        require(not int(row['trap']), 'Unexpected cache trap')
        pc = number(row, 'pc')
        require(pc not in fail_pcs, 'Cache software failure counter executed')
        if pc in store_pcs:
            r = store_pcs.index(pc)
            i = stores[r]
            require(i < 4096 and (not r or checks[r-1] == 586), 'Store phase/order')
            require(number(row, 'mem_addr') == 0x80001680 + 8*i and
                    number(row, 'mem_wmask') == 255 and
                    number(row, 'mem_wdata') == ((r << 32) ^ i ^ 0xfeed1234),
                    'Cache store address/data differs from independent formula')
            stores[r] += 1
            if i in (0, 2048, 4095):
                progress.append(dict(round=r, index=i, cycle=int(row['cycle'])))
        elif pc in load_pcs:
            r = load_pcs.index(pc)
            i = loads[r]*7
            require(stores[r] == 4096 and i < 4096, 'Read before complete store round')
            require(number(row, 'mem_addr') == 0x80001680 + 8*i and
                    number(row, 'mem_rmask') == 255 and int(row['rd']) == 12 and
                    number(row, 'rd_wdata') == ((r << 32) ^ i ^ 0xfeed1234),
                    'Cache readback differs from independent formula')
            loads[r] += 1
        elif pc in check_pcs:
            r = check_pcs.index(pc)
            require(loads[r] == checks[r]+1 and number(row, 'mem_addr') == 0x80009680
                    and number(row, 'mem_wmask') == 15 and
                    number(row, 'mem_wdata') == r*586+checks[r]+1, 'Check counter/order')
            checks[r] += 1
        if number(row, 'insn') in (0x0120000f, 0x0330000f, 0x0000100f):
            fences[hex(number(row, 'insn'))] += 1
        total += 1
        last = {k: row[k] for k in ('cycle', 'order', 'pc', 'insn')}
    require(total > 0 and sum(stores) > 0, 'No cache workload progress')
    complete = stores == [4096]*3 and loads == checks == [586]*3
    return dict(status='COMPLETE_DATA_CHECKS_PENDING_FULL_ACCEPTANCE' if complete else
                'INCOMPLETE_PREFIX_NO_OBSERVED_DATA_FAILURE', stores=stores, loads=loads,
                check_counter_updates=checks, total_expected_checks=1758,
                total_expected_stores=12288, retirements=total, last_retirement=last,
                progress=progress, fences=dict(fences), full_acceptance=False,
                interpretation='Retirement prefix only; no claim that remaining execution passes or that a cache wait is impossible.')


def offset(epoch, stream):
    return 64 if epoch else 64 + (2, 6, 14)[stream]


def source_byte(epoch, stream, byte, poisoned=False):
    start = offset(epoch, stream)
    if start <= byte < start+128:
        d = byte-start
        half = 0x1100 + epoch*0x1000 + stream*0x2000 + (d//2)*7
        return ((half ^ (0x5a5a if poisoned else 0)) >> (8*(d % 2))) & 255
    return (0xa7 + epoch*19 + stream*29 + byte*11) & 255


def frame_bytes(phase, is_got):
    before = [0xc100+i for i in range(32)]
    after = [0xd200+i for i in range(32)]
    data = [0x9000 + phase*0x100 + i*13 for i in range(256)]
    if is_got and phase in (1, 2, 3, 8, 9, 10):
        data[:64] = [0x1100 + int(phase >= 8)*0x1000 + SELECTORS[phase]*0x2000 + i*7
                     for i in range(64)]
    return struct.pack('<320H', *(before+data+after))


def descriptor_bytes(source_base):
    result = b''
    for e in range(2):
        stride = 128 if e else 130
        bases = [source_base+e*768+s*256+offset(e, s) for s in range(3)]
        result += struct.pack('<4B2H4I5Q', 1, 1, 1, 0, 64, 1,
                              stride, stride, stride, 0, *bases, 0, 0)
    return result


def skew_readback(trace, symbols):
    phase, commands = -1, []
    seen = {(p, n): set() for p in range(12)
            for n in ('got', 'initial', 'source', 'descriptor', 'descriptor_copy')}
    expected_pcs = {'got': {0x800007e6, 0x800008c0, 0x800008d0},
                    'initial': {0x8000084c, 0x800008b8, 0x800008c8},
                    'source': {0x8000099e}, 'descriptor': {0x80000a3c},
                    'descriptor_copy': {0x80000a40}}
    poisoned = set()
    poison_reads, poison_writes = set(), set()
    desc = descriptor_bytes(symbols['source']['value'])
    read_count = 0
    for row in trace:
        if row['event'] == 'cvx_req' and number(row, 'insn') & 127 == 91:
            phase += 1
            commands.append(number(row, 'insn'))
            require(phase < 12 and commands[-1] == WORDS[phase], 'Original AKV sequence changed')
        if row['event'] != 'retire' or phase < 0:
            continue
        addr, pc = number(row, 'mem_addr'), number(row, 'pc')
        for name in expected_pcs:
            base, size = symbols[name]['value'], symbols[name]['size']
            if not base <= addr < base+size:
                continue
            off = addr-base
            read, write = number(row, 'mem_rmask'), number(row, 'mem_wmask')
            if not read and not write:
                continue
            if name == 'source':
                e, s, b = off//768, off%768//256, off%256
                if write:
                    require(pc in (0x80000b06, 0x80000b34, 0x80000b70) and
                            phase in (0, 7) and e == int(phase == 7) and
                            offset(e, s) <= b < offset(e, s)+128, 'Unexpected source mutation')
                    key = (phase, off)
                    require(key in poison_reads and key not in poison_writes and
                            number(row, 'mem_wdata') & 255 == source_byte(e, s, b, True) and
                            write == 1 << (addr % 8), 'Poison write/reference mismatch')
                    poison_writes.add(key)
                    poisoned.add(off)
                    continue
                if pc in (0x80000afe, 0x80000b2c, 0x80000b68):
                    require(phase in (0, 7) and e == int(phase == 7) and off not in poisoned
                            and offset(e, s) <= b < offset(e, s)+128,
                            'Poison read outside original window')
                    require(number(row, 'rd_wdata') == source_byte(e, s, b), 'Poison input mismatch')
                    require(read == 1 << (addr % 8) and int(row['rd']) != 0, 'Poison load visibility')
                    poison_reads.add((phase, off))
                    continue
            if not read:
                continue  # Frame seeding and vector stores are verified by full later readback.
            require(pc in expected_pcs[name], 'Unexpected compare PC in original object')
            width = 2 if name in ('got', 'initial') else 1
            require(off % width == 0 and off+width <= size and read == ((1 << width)-1) << (addr % 8)
                    and int(row['rd']) != 0, 'Readback size/mask/destination')
            word = number(row, 'insn')
            if name == 'source':
                expected = source_byte(e, s, b, off in poisoned)
            elif name in ('got', 'initial'):
                expected = int.from_bytes(frame_bytes(phase, name == 'got')[off:off+width], 'little')
            else:
                expected = desc[off]
            # C.LHU is not present in this immutable ELF; all compare loads are full-width LHU/LBU.
            require(word & 127 == 3 and (word >> 12 & 7) == (5 if width == 2 else 4),
                    'Compare instruction changed')
            require(number(row, 'rd_wdata') == expected,
                    'Independent skew data mismatch phase=%d object=%s offset=%d' % (phase, name, off))
            require(off not in seen[(phase, name)], 'Duplicated read replacing missing evidence')
            seen[(phase, name)].update(range(off, off+width))
            read_count += 1
    require(commands == WORDS, 'Missing custom commands')
    for (p, name), covered in seen.items():
        require(covered == set(range(symbols[name]['size'])),
                'Incomplete independent frame: phase=%d object=%s' % (p, name))
    require(len(poison_reads) == len(poison_writes) == 768 and poison_reads == poison_writes,
            'Incomplete two-epoch poison sequence')
    return dict(status='INDEPENDENT_ORIGINAL12_PHASE_READBACK_PASS_NOT_ADMITTED',
                phases=12, scalar_compare_loads=read_count, independently_checked_bytes=36864,
                bytes_per_phase=dict(got=640, initial=640, source=1536, descriptor=128, descriptor_copy=128),
                poison_reads=768, poison_writes=768, full_ISA_qualified=False,
                full_native_vector_qualified=False, coverage_admitted=False)


def audit(case, run):
    elf = run/'input.elf'
    require(sha(elf) == HASHES[case], 'Not the original ELF: no same-name substitution')
    trace = run/'commit_trace.csv'
    before = {str(p.resolve()): sha(p) for p in (elf, trace)}
    if case == 'cache':
        blob = elf.read_bytes()
        def exact_rows():
            for item in rows(trace):
                if item['event'] == 'retire':
                    word = number(item, 'insn')
                    size = 4 if word & 3 == 3 else 2
                    require(int.from_bytes(code_at(blob, number(item, 'pc'), size), 'little') == word,
                            'Retirement differs from original stripped ELF')
                yield item
        result = cache_prefix(exact_rows())
        result['all_retired_encodings_bound_to_original_ELF'] = True
    else:
        for name in ('console.log', 'run.vcs.log', 'trace_hart_0.log'):
            before[str((run/name).resolve())] = sha(run/name)
        kind = original.DESCRIPTOR if case == 'descriptor' else original.SKEW
        core = original.verify(kind, run, elf.read_bytes(), 2097152)
        result = (descriptor.descriptor_readback(list(rows(trace)), core['elf_layout']['symbols'])
                  if case == 'descriptor' else skew_readback(rows(trace), core['elf_layout']['symbols']))
        result['original_checks'] = core['checks']
    require(all(sha(p) == h for p, h in before.items()), 'Input changed during audit')
    result.update(case=case, input_pins=before, helper_sha256=sha(__file__),
                  simulation_started=False, RTL_changed=False, coverage_admitted=False,
                  current_RTL_acceptance=False)
    return result


def scalar_owner(run):
    # Directly parse the existing VCD: do not call collect(), which may run EDA converters.
    import check_scalar_c910_pattern795_two_layer as owner
    from ara_verify.spike_trace import compare_commit_prefix
    pins = owner.authority()
    pre = owner.life.read_bound(owner.c.runner.PRE/'preflight.json', owner.c.runner.PRE_SHA)
    wave = owner.life.OUT/'scalar-c910-pattern795-qualified-v2-parent-20261008-01/probe.vcd'
    require(sha(wave) == '49a271e84ac41af940ce16e0f6c5d56a9df2edd1a2f98e6ce5ee5dd38c737977',
            'Not the previously reviewed original wave')
    trace = run/'commit_trace.csv'
    golden = owner.c.runner.PRE/'spike.trace'
    for p in (wave, trace, golden, owner.c.runner.PRE/'input.elf'):
        pins[str(p)] = sha(p)
    owner.life.check(pre['pins'])
    scalar = compare_commit_prefix(golden, trace, 0x80000000,
                                  terminal_tohost_address=pre['symbols']['tohost'],
                                  rvfi_store_data_layout='unshifted')
    arch = owner.c.architecture([r for r in rows(trace) if r['event'] == 'retire'], pre, scalar)
    result = owner.wave_audit(wave, owner.c.runner.source_contract(), pre)
    owner.life.check(pins)
    return dict(status='ARCHITECTURE_AND_PHYSICAL_MATH_PASS_OWNER_MAPPING_HOLD',
                architecture=arch, scalar_comparison=scalar,
                physical={k: v for k, v in result.items() if k not in
                          ('outputs', 'cancellations', 'stages', 'flush_edges')},
                input_pins=pins, helper_sha256=sha(__file__),
                physical_output_to_retirement_mapping_claimed=False,
                coverage_admitted=False, current_RTL_acceptance=False,
                RTL_changed=False, simulation_started=False,
                remaining='Complete physical issue/flush epoch to architectural retire association is unproven; not a demonstrated arithmetic RTL failure.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=(*HASHES, 'scalar-owner'), required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    require(not args.output.exists(), 'Never replace an earlier audit')
    report = (scalar_owner(args.run.resolve()) if args.case == 'scalar-owner'
              else audit(args.case, args.run.resolve()))
    with args.output.open('x') as out:
        json.dump(report, out, indent=2, sort_keys=True)
        out.write('\n')
    print(json.dumps(dict(output=str(args.output), status=report['status'], coverage_admitted=False)))


if __name__ == '__main__':
    main()
