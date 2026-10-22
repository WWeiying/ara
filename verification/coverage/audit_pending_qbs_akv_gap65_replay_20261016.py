#!/usr/bin/env python3
"""Independent offline e0650 successor acceptance; never start a simulation."""
import argparse
import csv
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_pending_qbs_akv_20261016 as base
import gap65_late_fault_checks as oracle
import qualify_gap105_native_v5 as decoder
from ara_verify.vector_commit import (_parse_vector_trace, _architectural_bytes,
    _parse_architecture_mapping, _map_architecture_retires)
from postprocess_gap115_events_v2 import backend

ROOT = base.ROOT
ORIGINAL = base.RUNS / 'e0650'


def phase_regions(proof, phase):
    sym = proof['buffer_symbols']
    fixtures = oracle.vectors()
    guard = b''.join(struct.pack('<Q', oracle.GUARD ^ i) for i in range(8))
    seed = b''.join(struct.pack('<I', 0x41800000 + 7919 * i) for i in range(128))
    result = seed if phase == 0 else b''.join(struct.pack('<I', fixtures['expected_bits'][(i // 32) * 4 + i % 32]
        if i % 32 < 4 else 0) for i in range(128))
    header = 2 | (1 << 4) | (1 << 8) | (1 << 12) | (1 << 16) | ((4 if phase == 0 else 3) << 20)
    packets = dict(gap65_seed=guard + seed + guard, gap65_observed=guard + result + guard,
        gap65_activation=bytes.fromhex(fixtures['activation_image']),
        gap65_descriptor=guard + struct.pack('<QQ', header, 0xbffffdc0) + guard,
        gap65_csrs=guard + struct.pack('<12Q', *([32, 16, 0, 0, 0, 0] * 2)) + guard,
        gap65_trap=guard + struct.pack('<4Q', 1, 5, 0xc0000000, proof['sites']['gap65_fault_site']) + guard,
        gap65_boot=struct.pack('<5Q', 0xc0000000, 0x80110000, 1, 0, 128))
    regions = {n: (sym[n]['Value'], data) for n, data in packets.items()}
    regions.update(tail=(0xbffffd80, bytes.fromhex(fixtures['weight_image'])),
        stack_low=(proof['fixed_symbols']['__gap65_stack_guard_low'], guard),
        stack_high=(proof['fixed_symbols']['__gap65_stack_guard_high'], guard))
    return regions


def readback(rows, begin, end, regions):
    observed = {n: set() for n in regions}
    for r in rows:
        if r['event'] != 'retire' or not begin <= int(r['cycle']) < end or not int(r['mem_rmask'], 16):
            continue
        address = int(r['mem_addr'], 16)
        word = int(r['insn'], 16)
        access = decoder.scalar_access(word)
        for name, (start, expected) in regions.items():
            if not start <= address < start + len(expected):
                continue
            base.require(access is not None and access[0] == 'read', 'Unknown native packet load: ' + name)
            size = access[1]
            fpr, rd = decoder.load_destination(word)
            base.require(address % size == 0 and address + size <= start + len(expected) and
                int(r['mem_rmask'], 16) == ((1 << size) - 1) << (address & 7) and
                int(r['rd']) == rd and (fpr or rd != 0) and not int(r['trap']), 'Packet load identity/mask: ' + name)
            offset = address - start
            actual = (int(r['rd_wdata'], 16) & ((1 << (size * 8)) - 1)).to_bytes(size, 'little')
            base.require(actual == expected[offset:offset + size], f'Native {name} byte mismatch at offset {offset}')
            observed[name].update(range(offset, offset + size))
    for name, (_, expected) in regions.items():
        base.require(observed[name] == set(range(len(expected))), 'Incomplete native packet readback: ' + name)
    return {name: len(data) for name, (_, data) in regions.items()}


def vectors(a, rows, proof):
    path = a.bind(a.work / 'vector_trace.csv')
    lanes, vlen, acts = _parse_vector_trace(path)
    base.require((lanes, vlen) == (4, 1024), 'Replay vector configuration differs')
    starts = {int(r['order']): r for r in rows if r['event'] == 'arch_start'}
    selected = sorted(acts, key=lambda s: int(starts[s]['cycle']))
    base.require(len(selected) == 6, 'Exactly two seed/custom/snapshot triplets required')
    with path.open() as stream:
        raw = list(csv.DictReader(stream))
    backend(rows, raw, set())
    arch, retires, trapped = _parse_architecture_mapping(a.runtime / 'commit_trace.csv')
    mapping = _map_architecture_retires(arch, retires, trapped)
    base.require(trapped == {selected[1]}, 'Only first custom architecture request may fault')
    results = []
    for ordinal, seq in enumerate(selected):
        phase, kind = divmod(ordinal, 3)
        act = acts[seq]
        records = [r for r in raw if r['event'] != 'config' and int(r['arch_seq']) == seq]
        alloc = [r for r in records if r['event'] == 'alloc']
        done = [r for r in records if r['event'] == 'done']
        base.require(act.allocations == act.completions == 1 and len(alloc) == len(done) == 1 and
            all(int(r['vstart']) == 0 and int(r['eew']) == 2 and int(r['vl']) == 128 for r in records) and
            int(starts[seq]['cycle']) <= int(alloc[0]['cycle']) <= int(done[0]['cycle']) and
            all(int(alloc[0]['cycle']) <= w.cycle <= int(done[0]['cycle']) for w in act.writes),
            'Exact M4 activity/lifecycle metadata and write timing')
        if kind == 1:
            base.require(act.instruction == 0x06b5045b and act.use_vd and act.vd == 8 and
                         ((seq in trapped and seq not in mapping) if phase == 0 else
                          (seq in mapping and mapping[seq].pc == proof['sites']['gap65_recovery_site'])),
                         'Custom fault/recovery site/metadata')
            if phase == 0:
                base.require(not act.writes, 'Faulting QBS command wrote native VRF')
                results.append(dict(phase=phase, kind='fault', native_write_bytes=0))
                continue
        elif kind == 0:
            base.require(act.instruction & 127 == 7 and act.use_vd and act.vd == 8,
                         'Exact M4 seed-load activity')
        else:
            base.require(act.instruction & 127 == 39 and not act.use_vd and not act.writes,
                         'Exact M4 snapshot-store activity')
            continue
        image = phase_regions(proof, phase if kind == 1 else 0)['gap65_observed'][1][64:576]
        expected = {(8 + i // 128, i % 128): value for i, value in enumerate(image)}
        values = _architectural_bytes(act.writes, lanes, vlen)
        base.require(len(act.writes) == len({(w.lane, w.addr) for w in act.writes}) == 64 and
            all(w.be == w.known_be == 255 for w in act.writes) and
            {k: v for k, (v, _) in values.items()} == expected, 'Bit-exact full native seed/recovery VRF differs')
        if kind == 1:
            base.require(all(w.source == 4 for w in act.writes), 'Recovery QBS write source differs')
        results.append(dict(phase=phase, kind='recovery' if kind == 1 else 'seed', native_write_bytes=512))
    return dict(activities=results, backend_lifecycle_mirrored=True, full_native_comparison=True,
                fault_write_bytes=0, recovery_write_bytes=512, numerical_results=16, zero_tail_words=112)


def architecture(a):
    original = a.native()
    proof = original['proof']
    with (a.runtime / 'commit_trace.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    pending, responses = {}, []
    for r in rows:
        key = int(r['trans_id'])
        if r['event'] == 'cvx_req':
            pending[key] = int(r['insn'], 16)
        elif r['event'] == 'cvx_resp':
            if pending.pop(key) == 0x06b5045b:
                responses.append(int(r['cycle']))
    base.require(len(responses) == 2, 'Two native response phase boundaries required')
    address = proof['buffer_symbols']['gap65_observed']['Value'] + 64
    inspected = [r for r in rows if r['event'] == 'retire' and int(r['mem_rmask'], 16) and
                 address <= int(r['mem_addr'], 16) < address + 512]
    base.require(len(inspected) == 256, 'Complete snapshot inspection phase boundaries required')
    bounds = [int(inspected[0]['cycle']), int(inspected[128]['cycle']), max(int(r['cycle']) for r in rows) + 1]
    base.require(responses[0] < bounds[0] < responses[1] < bounds[1], 'Snapshot inspections must follow corresponding responses')
    packets = [readback(rows, bounds[p], bounds[p + 1], phase_regions(proof, p)) for p in (0, 1)]
    return dict(original=original, native_packets=packets, native_vector=vectors(a, rows, proof),
                vector_trace_required=True, UART_only_acceptance=False)


def execution(a):
    receipt = a.read(a.run / 'simulation-exit.json')
    base.require(receipt['executed'] is True and type(receipt['returncode']) is int and receipt['returncode'] == 0 and
        receipt['timed_out'] is False and receipt['cancelled'] is False and type(receipt['pid']) is int and
        receipt['pid'] > 0 and receipt['finished'] > receipt['started'] and receipt['command'] == a.plan['command'] and
        receipt['cwd'] == str(a.work), 'Successor actual execution identity differs')
    original = a.read(ORIGINAL / 'plan.json')
    original_receipt = a.read(ORIGINAL / 'simulation-exit.json')
    base.require(a.plan['original_command'] == original_receipt['command'] == original['command'] and
        a.plan['elf_sha256'] == original['elf_sha256'] and a.plan['command'][0] == original['command'][0],
        'Only same-image/same-ELF successor allowed')
    for p, h in a.plan['pins'].items():
        a.bind(p, h)
    book = a.read(ROOT / 'verification/out/full-regression-build-20261015-01/build-image.json')
    freeze = a.read(ORIGINAL.parent.parent / 'freeze.json')
    base.require(a.plan['image'] == book == freeze['image'], 'Full current image membership/hash mismatch')
    for path, digest in book.items():
        a.bind(path, digest)
    from run_vcs_dve_batch import valid_vdb
    vdb = valid_vdb(a.work / 'code.vdb', 'qbs_gap65_late_fault', a.plan['command'][0])
    for path, digest in vdb.items():
        a.bind(path, digest)
    a.current_sources = a.read(ROOT / 'verification/out/full-regression-build-20261015-01/build-source-pins.json')
    a.bind(a.run / 'input.elf', original['elf_sha256'])
    a.original_elf = a.bind(ORIGINAL / 'input.elf', original['elf_sha256'])
    frozen = Path(original['command'][original['command'].index('-do') + 1])
    observer = a.bind(a.plan['observer'], a.plan['observer_sha256'])
    base.require(a.bind(frozen, original['pins'][str(frozen)]).read_bytes() == observer.read_bytes(), 'Observer logic changed')
    sources = {str(observer): observer.read_text()}
    from replay_historical_extensions_20261015 import RAW_FAIL
    from ara_verify.runner import FAIL_RE
    for name, path in [('console.log', a.run / 'console.log'), ('run.vcs.log', a.work / 'run.vcs.log')]:
        with a.bind(path).open() as stream:
            text = ''.join(base.iter_runtime_lines(stream, sources))
        base.require(text.count('Core Test *** SUCCESS ***') == 1 and not RAW_FAIL.search(text) and
                     not FAIL_RE.search(text), 'Successor runtime failure')
        (a.runtime / name).write_text(text)
    for name in ('commit_trace.csv', 'vector_trace.csv'):
        (a.runtime / name).write_bytes(a.bind(a.work / name).read_bytes())
    return dict(actual_wait=receipt, original_command_bound=True, same_ELF_and_image=True,
                frozen_observer_byte_identical=True, actual_execution_identity_validated=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--base-audit', type=Path)
    args = p.parse_args()
    output = args.output.resolve()
    base.require(not output.exists() and output.is_relative_to(ROOT / 'verification/out'), 'Fresh private output required')
    output.mkdir()
    base.install_guard(output)
    a = object.__new__(base.Audit)
    a.index = 650
    a.case = dict(index=650, coverage_test='qbs_gap65_late_fault')
    a.run = args.run.resolve(strict=True)
    a.work = a.run / 'work'
    a.out = output / 'e0650'
    a.out.mkdir()
    a.runtime = a.out / 'runtime'
    a.runtime.mkdir()
    a.inputs, a.components = {}, {}
    a.plan = a.read(a.run / 'plan.json')
    a.old = a.read(a.plan['command_source'])
    base.ACTIVE = a
    sys.addaudithook(base.record_reads)
    a.check('execution', lambda: execution(a), 'Typed actual successor wait and original/current same-image ELF binding', context=True)
    if a.components['execution']['status'] == 'PASS':
        a.check('architecture', lambda: architecture(a), 'Original oracle plus independent all-packet and native vector strict comparison')
        a.check('microstructure', a.wave, 'Original live fault observer on successor output')
    result = a.finish()
    # The successor requires vector evidence even though the original oracle did not.
    result.update(execution_plan=str(a.run / 'plan.json'), supersedes_plan=str(ORIGINAL / 'plan.json'),
                  vector_trace_required=True, vdb=str(a.work / 'code.vdb'))
    for module in list(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if file and Path(file).suffix == '.py' and Path(file).resolve().is_relative_to(ROOT / 'verification'):
            a.bind(file)
    result['input_pins'] = dict(a.inputs)
    base.ACTIVE = None
    for path, h in a.inputs.items():
        base.require(base.sha(path) == h, 'Final successor input drift: ' + path)
    base.save(a.out / 'result.json', result)
    cases = [result]
    if args.base_audit:
        previous = json.loads(args.base_audit.read_text())
        cases = [result if c['index'] == 650 else c for c in previous['cases']]
    base.save(output / 'audit.json', dict(cases=cases,
        counts={s: sum(c['status'] == s for c in cases) for s in ('PASS', 'FAIL', 'CHECKER_REQUIRED')},
        accepted_ids=[c['index'] for c in cases if c['status'] == 'PASS'],
        rejected_ids=[c['index'] for c in cases if c['status'] == 'FAIL'],
        pending_ids=[c['index'] for c in cases if c['status'] == 'CHECKER_REQUIRED']))
    print(json.dumps(dict(status=result['status'], report=result['report'], summary=str(output / 'audit.json'))))


if __name__ == '__main__':
    main()
