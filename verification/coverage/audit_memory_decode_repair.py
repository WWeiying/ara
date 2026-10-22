"""Full original memory-decode repair cases, with no old RTL/VDB binding.

source(name) returns the sealed original ELF/reference directory. Copy its
input.elf into the new run directory. audit(directory, name) requires complete
commit/vector traces, CVA6 tracer and run.vcs.log. The runner separately pins
the new image/configuration and verifies normal process exit without timeout.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import build_gap101_preflight as g101
import collect_memory_emul_r2_strict as r2

common = r2.common
vc = r2.vc
ROOT = Path(__file__).resolve().parents[2]
CASES = {
    'vgap101_illegal_segment_store': (
        'gap101-illegal-segment-store-preflight-20261006-02',
        'fb201ab205a72b1790da0873237868bb7b389c9c0b9d08a589953851df652298',
        '0ee7feec51d7e25f8b17abc445a3b14eef99dace42a686e5d481335b825f3d59'),
    'vmemory_emul_r2_boundary_reject': (
        'memory-emul-r2-preflight-721-20261006-01',
        '1f3ae5b8faf7195a6eca0f29688ed8d8b4e03c90ee09fc6f7fc806fd76514245',
        'e252560b829c20be94bce7651d64596a3bc7daabe5d3936ef3d6bf2a889ca186'),
}
HELPERS = {
    'verification/coverage/build_gap101_preflight.py':
        '4d4796d95be6c4ebfef4444cfdd8e966033a77a8f60e25ac071fef90e96e8d72',
    'verification/coverage/collect_memory_emul_r2_strict.py':
        '3b36e6b64873cf6336802bebbfe0d6c3f2a7ef804f054cf95f524922a9d4cfcb',
    'verification/coverage/build_memory_emul_r2_preflight.py':
        'a003fe002bc173685cdb531018025c0101c3697da73d7cda3030194438edffb3',
    'verification/coverage/collect_opivx_vsbc_strict.py':
        '5bafc9df7ef8b0773b89689612372e844382b0a0f9ccb1ab2284a2167902c43e',
    'verification/ara_verify/vector_commit.py':
        'ed9e2cae2be4ab6d79eed5bf2499ad0f217bd116d3cba11b4454d42623c5a133',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def source(name):
    require(name in CASES, 'Unknown complete repair case')
    return ROOT / 'verification/out' / CASES[name][0]


def check_pins(pins):
    for path, value in pins.items():
        require(digest(path) == value, 'Changed evidence/checker: ' + str(path))


def fixture(directory, name):
    pre_dir = source(name)
    prefile = pre_dir / 'preflight-manifest.json'
    require(digest(prefile) == CASES[name][1], 'Original preflight changed')
    pre = json.loads(prefile.read_text())
    require(pre['case'] == name, 'Different reference case')
    pins = {str(ROOT / p): v for p, v in HELPERS.items()}
    pins.update({str(prefile): CASES[name][1],
                 str(directory / 'input.elf'): CASES[name][2],
                 str(pre_dir / 'input.elf'): CASES[name][2],
                 str(pre_dir / 'spike.trace'): pre['pins'][str(pre_dir / 'spike.trace')]})
    # Bind the independent reference and parser, not preflight's old-image pins.
    for module in (common.spike_trace, vc):
        path = str(Path(module.__file__).resolve())
        require(path in pre['pins'], 'Unpinned reference parser: ' + path)
        pins[path] = pre['pins'][path]
    check_pins(pins)
    pins[str(Path(__file__).resolve())] = digest(__file__)
    return pre, pins


def gap101_lifecycle(rows, vectors):
    starts, pending, live, ended = {}, {}, {}, {}
    allocated, completed, va, vd = Counter(), Counter(), Counter(), Counter()
    requests, responses, rejected = [], [], []
    for row in rows:
        event, seq, tid = row['event'], int(row['order']), int(row['trans_id'])
        word, cycle = int(row['insn'], 16), int(row['cycle'])
        if event == 'arch_start':
            require(seq not in starts and tid not in pending, 'Duplicate start/live transaction')
            starts[seq], pending[tid] = row, [seq, False]
        elif event == 'cvx_req':
            require(tid in pending and not pending[tid][1], 'Unknown/duplicate request')
            owner = pending[tid][0]
            require(word == int(starts[owner]['insn'], 16), 'Request opcode differs')
            pending[tid][1] = True
            requests.append(owner)
        elif event == 'cvx_resp':
            require(tid in pending and pending[tid][1], 'Unknown/duplicate response')
            owner = pending.pop(tid)[0]
            responses.append(owner)
            require(int(row['trap']) in (0, 1), 'Invalid response trap')
            if int(row['trap']):
                rejected.append(owner)
        elif event in ('uop_alloc', 'uop_done'):
            key = seq, int(row['port'])
            require(seq in starts and word == int(starts[seq]['insn'], 16)
                    and cycle >= int(starts[seq]['cycle']), 'Unowned/mismatched backend event')
            if event == 'uop_alloc':
                require(key not in live, 'Live backend VID reused')
                live[key] = cycle
                allocated[key] += 1
            else:
                require(key in live and cycle >= live.pop(key), 'Backend done without allocation')
                completed[key] += 1
        else:
            require(event == 'retire' and not int(row['trap']), 'Unexpected trace event/trap')
    require(not pending and Counter(requests) == Counter(responses) == Counter(starts.keys()),
            'Request/response conservation differs')
    require(not live and allocated == completed, 'Incomplete backend activity')
    require([int(starts[s]['insn'], 16) for s in rejected] == list(g101.WORDS),
            'Both original illegal phases must reject in order')
    require(not any(s in rejected for s, _ in allocated), 'Illegal backend/VLSU allocation')
    for row in vectors:
        event, seq = row['event'], int(row['arch_seq'])
        require((int(row['nr_lanes']), int(row['vlen_bits'])) == (4, 1024), 'VRF geometry differs')
        require(seq not in rejected, 'Illegal vector activity')
        if event == 'config':
            continue
        key = seq, int(row['vid'])
        require(seq in starts and int(row['insn'], 16) == int(starts[seq]['insn'], 16),
                'Unowned vector event')
        if event == 'alloc':
            require(key not in live, 'Live vector VID reused')
            live[key] = row
            va[key] += 1
        else:
            alloc = live.get(key)
            if alloc is None and event == 'write':
                alloc = ended.get(key)
                require(alloc is not None and row['cycle'] == alloc['cycle'], 'Write after completion')
            require(alloc is not None and int(row['cycle']) >= int(alloc['cycle'])
                    and all(row[k] == alloc[k] for k in ('insn', 'use_vd', 'vd', 'eew', 'vl', 'vstart')),
                    'Vector lifetime/metadata differs')
            require(event in ('done', 'write'), 'Unknown vector event')
            if event == 'done':
                live.pop(key)
                ended[key] = row
                vd[key] += 1
    require(not live and va == vd == allocated, 'Commit/vector lifecycle differs')
    return dict(requests=len(requests), responses=len(responses), exceptions=2,
                rejected_arch_seqs=rejected, rejected_backend_uops=0,
                rejected_vrf_activities=0, backend_uops=sum(allocated.values()))


def gap101_observed(rows, symbols):
    retires = [r for r in rows if r['event'] == 'retire']
    require(retires and [int(r['order']) for r in retires] == list(range(len(retires))),
            'Incomplete retirement stream')
    badpcs = {symbols[n] for n in ('g101_bad_a', 'g101_bad_b', 'trap_fail')}
    memory, terminals = {}, []
    for row in retires:
        require(not int(row['trap']) and int(row['pc'], 16) not in badpcs, 'Illegal/fatal retirement')
        if not int(row['mem_wmask'], 16):
            continue
        address = int(row['mem_addr'], 16)
        access = common.scalar_memory(int(row['insn'], 16))
        require(access is not None and access[0] == 'write', 'Unknown scalar store')
        width = access[1]
        require(address % width == 0 and int(row['mem_wmask'], 16) ==
                ((1 << width) - 1) << (address & 7), 'Scalar store mask/alignment')
        value = int(row['mem_wdata'], 16) & ((1 << (8 * width)) - 1)
        memory.update({address + i: b for i, b in enumerate(value.to_bytes(width, 'little'))})
        if address == symbols['tohost']:
            terminals.append(row)
    require(terminals == [retires[-1]], 'Missing/extra/post-terminal retirement')

    def read(name, offset=0, width=8):
        address = symbols[name] + offset
        require(all(address + i in memory for i in range(width)), 'Missing full signature: ' + name)
        return int.from_bytes(bytes(memory[address + i] for i in range(width)), 'little')

    require(read('g75_result', width=4) == 1075 and read('g75_result', 4, 4) == 0
            and read('num_failed', width=4) == 0 and read('tohost') == 1,
            '1075-check self-check failure')
    for (name, offset), expected in g101.expected_words().items():
        require(read(name, offset) == expected, 'Full VRF/target/recovery signature differs')
    for phase, site in enumerate(('g101_bad_a', 'g101_bad_b')):
        expected = [2, symbols[site], g101.WORDS[phase], 1, 1-phase, 0, 0, phase+1]
        require([read('g101_ledger', phase * 80 + i * 8) for i in range(8)] == expected,
                'Precise two-phase trap/CSR ledger differs')
    restore = [read('g101_restore', i * 8) for i in range(4)]
    require(restore[0] == restore[1] and restore[2] == restore[3], 'Trap CSR restoration differs')
    return dict(checks=1075, failed_checks=0, phases=2, illegal_traps=2,
                observed_vrf_bytes=8192, target_guard_bytes=128, recovery_guard_bytes=128)


def gap101_vector(result, control, reference):
    fixed = dict(status='PASS', compared_instructions=64, compared_bytes=8192,
                 skipped_unknown_bytes=0, non_bit_exact_instructions=0,
                 nr_lanes=4, vlen_bits=1024, selected_index=None,
                 stopped_at_spike_index=None, first_mismatch=None,
                 trapped_requests=control['rejected_arch_seqs'], unobservable_instructions=0,
                 incomplete_requests=[], unretired_requests=[])
    for k, expected in fixed.items():
        require(k in result and type(result[k]) is type(expected) and result[k] == expected,
                'Full original vector gate differs: ' + k)
    records = result['instructions']
    expected = [(c.pc, c.instruction) for c in reference if c.vector_writes]
    require(len(records) == len(expected) == 64 and
            [(int(r['pc'], 16), int(r['instruction'], 16)) for r in records] == expected,
            'Both full original VRF initializations required')
    require(all(r['status'] == 'PASS' and r['compared_bytes'] == 128
                and r['skipped_unknown_bytes'] == r['unknown_write_bytes'] == r['mismatch_count'] == 0
                and r['first_mismatch'] is None for r in records), 'Unknown/missing/incorrect vector bytes')


def audit(directory, name):
    directory = Path(directory).resolve()
    pre, pins = fixture(directory, name)
    files = ['input.elf', 'commit_trace.csv', 'vector_trace.csv', 'run.vcs.log', 'trace_hart_0.log']
    pins.update({str(directory / n): digest(directory / n) for n in files})
    log = (directory / 'run.vcs.log').read_text()
    require(log.count('Core Test *** SUCCESS ***') == 1 and
            not common.check_contract_log(directory / 'run.vcs.log') and
            not re.search(r'(?m)^\s*(?:Error|Fatal)(?:-|:)', log), 'Runtime/contract failure')
    rows = common.read_csv((directory / 'commit_trace.csv').read_bytes(), common.COMMIT_FIELDS)
    vectors = common.read_csv((directory / 'vector_trace.csv').read_bytes(), common.VECTOR_FIELDS)
    symbols = pre['symbols']
    ref = source(name) / 'spike.trace'
    reference = g101.shared.parse_spike_commits(ref)
    scalar = common.spike_trace.compare_commit_prefix(
        ref, directory / 'commit_trace.csv', 0x80000000,
        terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
    counts = pre.get('reference_counts') or common.reference_counts(reference, symbols)
    common.scalar_exact(scalar, counts)
    vector = common.compare_vector_commits(ref, directory / 'commit_trace.csv',
                                           directory / 'vector_trace.csv', 0x80000000)
    tracer = (directory / 'trace_hart_0.log').read_text()
    if name == 'vmemory_emul_r2_boundary_reject':
        control = r2.lifecycle(rows, vectors, symbols)
        observed = r2.observed(rows, symbols)
        traps = r2.tracer_exact(tracer, rows, symbols)
        r2.vector_exact(vector, control, reference, symbols)
    else:
        control = gap101_lifecycle(rows, vectors)
        observed = gap101_observed(rows, symbols)
        gap101_vector(vector, control, reference)
        events = re.findall(r'Exception @\s*([0-9a-fA-F]+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)', tracer)
        pcs = [symbols[n] for n in ('g101_bad_a', 'g101_bad_b')]
        require(len(events) == tracer.count('Exception @') == 2 and
                [(int(e[1], 16), e[2]) for e in events] == [(pc, 'Illegal Instruction') for pc in pcs]
                and [int(v, 16) for v in re.findall(r'tval: ([0-9a-fA-F]+)', tracer)] == list(g101.WORDS),
                'Both original trap PC/cause/tval required')
        traps = dict(illegal_exceptions=2, pcs=pcs, tvals=list(g101.WORDS))
    contract = re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)', log)
    require(len(contract) == 1 and tuple(map(int, contract[0])) ==
            (control['requests'], control['responses'], control['exceptions'], 0, 0),
            'Missing exact request/response/exception conservation')
    check_pins(pins)
    return dict(status='PASS', case=name, observed=observed, lifecycle=control,
                traps=traps, scalar=scalar, vector=vector, input_pins=pins,
                coverage_admitted=False, old_vdb_reuse=False,
                image_provenance_verified=False, simulator_process_exit_verified=False,
                scope='Complete original case, not a reduced subset; caller owns new-image and exit checks')
