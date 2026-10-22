"""Qualify program-prefix architecture separately from failed timeout harness."""
import argparse
from collections import Counter
import csv
import hashlib
import inspect
import io
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification'))
from ara_verify import spike_trace as st, vector_commit as vc
import check_operand_mask_data_preflight as independent
import scoped_rv64c_memory as compressed

OUT = ROOT / 'verification/out'
RUN = OUT / 'operand-mask-data-old-image-parent-20261007-01'
PRE = OUT / 'operand-mask-data-preflight-parent-20261007-01'
COMMIT_FIELDS = tuple('cycle event order port trans_id pc insn rd rd_wdata mem_addr mem_rmask mem_wmask mem_wdata trap'.split())
VECTOR_FIELDS = tuple('cycle event arch_seq vid lane source insn use_vd vd eew vl vstart addr be wdata nr_lanes vlen_bits'.split())
HEXES = {'pc', 'insn', 'rd_wdata', 'mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'}
MASK = (1 << 64) - 1


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, result):
    with Path(path).open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')


def table(raw, fields):
    reader = csv.DictReader(io.StringIO(raw.decode()))
    need(tuple(reader.fieldnames or ()) == fields, 'Exact native CSV schema required')
    rows = list(reader)
    need(rows and all(set(r) == set(fields) and all(v is not None and v != '' for v in r.values())
                      for r in rows), 'Empty/truncated/foreign CSV row')
    return rows


def prefix(raw, tohost=0x80001000):
    lines = raw.splitlines(keepends=True)
    need(lines and lines[0].decode().strip() == ','.join(COMMIT_FIELDS), 'Commit header differs')
    result, retired, previous = [], 0, -1
    for line_number, line in enumerate(lines[1:], 1):
        need(line.endswith(b'\n'), 'Truncated row before successful terminal')
        rows = table(lines[0] + line, COMMIT_FIELDS)
        row = rows[0]
        cycle = int(row['cycle'])
        need(cycle >= previous and int(row['trap']) == 0, 'Reordered cycle or trap before terminal')
        previous = cycle
        need(row['event'] in ('retire', 'arch_start', 'cvx_req', 'cvx_resp', 'uop_alloc', 'uop_done'), 'Unknown event')
        result.append(row)
        if row['event'] == 'retire':
            need(int(row['order']) == retired, 'Missing/duplicate/reordered scalar retirement')
            retired += 1
        if int(row['mem_addr'], 16) == tohost and int(row['mem_wmask'], 16):
            need(row['event'] == 'retire' and int(row['mem_wmask'], 16) == 255 and
                 int(row['mem_rmask'], 16) == 0 and int(row['mem_wdata'], 16) == 1,
                 'Failed/partial/nonretired terminal store')
            need(int(row['insn'], 16) == 0x00a2b023 and int(row['pc'], 16) == 0x8000007a,
                 'Wrong terminal PC/original opcode')
            return b''.join(lines[:line_number + 1]), result, dict(cycle=cycle,
                order=int(row['order']), pc=row['pc'], instruction=row['insn'],
                address='0x80001000', value=1, source_line=line_number + 1,
                retained_bytes=sum(map(len, lines[:line_number + 1])),
                ignored_postterminal_bytes=sum(map(len, lines[line_number + 1:])))
    raise ValueError('Missing successful tohost terminal')


def memory_decode(insn):
    if insn & 3 != 3:
        return compressed.decode(insn)
    op, fn = insn & 127, insn >> 12 & 7
    if op not in (3, 0x23):
        return None
    need(fn in ((0, 1, 2, 3, 4, 5, 6) if op == 3 else (0, 1, 2, 3)), 'Unknown memory width')
    immediate = insn >> 20 if op == 3 else ((insn >> 25) << 5) | ((insn >> 7) & 31)
    if immediate & 2048:
        immediate -= 4096
    return dict(kind='read' if op == 3 else 'write', size=1 << (fn & 3), base=insn >> 15 & 31,
                register=insn >> (7 if op == 3 else 20) & 31, offset=immediate, signed=fn < 4)


def full_scalar(rows, reference, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    need(len(retired) == len(reference) == 191288, 'Not complete exact scalar reference')
    regs, memory, reads, counts = {i: 0 for i in range(32)}, {}, set(), Counter()
    terminals = []
    for index, (raw, c) in enumerate(zip(retired, reference)):
        r = {k: v if k == 'event' else int(v, 16 if k in HEXES else 10) for k, v in raw.items()}
        need(r['order'] == index and r['trap'] == 0 and (r['pc'], r['insn']) == (c.pc, c.instruction),
             'Full scalar order/PC/opcode/trap mismatch')
        need(not c.fpr_writes and 0 <= r['rd'] < 32, 'Unexpected FPR/invalid GPR')
        expected = {k: v for k, v in c.gpr_writes.items() if k}
        actual = {r['rd']: r['rd_wdata']} if r['rd'] else {}
        need(actual == expected, 'Full scalar GPR/CSR-return mismatch at order%d' % index)
        d = memory_decode(c.instruction)
        if d:
            addr = (regs[d['base']] + d['offset']) & MASK
            size, register = d['size'], d['register']
            mask = ((1 << size) - 1) << (addr & 7)
            need(addr % size == 0 and r['mem_addr'] == addr and mask <= 255,
                 'Scalar/RVC effective address/alignment mismatch')
            if d['kind'] == 'write':
                value = regs[register] & ((1 << (8 * size)) - 1)
                need(c.memory_accesses == ((addr, value),) and not actual and
                     r['mem_wmask'] == mask and r['mem_rmask'] == 0 and
                     r['mem_wdata'] & ((1 << (8 * size)) - 1) == value, 'Full scalar/RVC store mismatch')
                if addr == symbols['tohost']:
                    terminals.append((index, size, value))
            else:
                need(c.memory_accesses == ((addr, None),) and set(actual) == {register} and
                     r['mem_rmask'] == mask and r['mem_wmask'] == 0, 'Full scalar/RVC load mismatch')
                value = actual[register] & ((1 << (8 * size)) - 1)
                signed = d.get('signed', True)
                extension = value - (1 << (8 * size)) if signed and value >> (8 * size - 1) else value
                need(actual[register] == extension & MASK, 'Load sign/zero extension differs')
                reads.update(range(addr, addr + size))
            memory.update({addr + i: byte for i, byte in enumerate(value.to_bytes(size, 'little'))})
            counts[d['kind']] += 1
            if c.instruction & 3 != 3:
                counts['compressed_' + d['kind']] += 1
        else:
            need(r['mem_rmask'] == r['mem_wmask'] == 0, 'Unknown scalar memory effect')
            if c.memory_accesses:
                need(c.instruction & 127 in (0x07, 0x27), 'Unverified nonvector memory effect')
        counts['gpr_writes'] += len(actual)
        regs.update(actual)
        regs[0] = 0
    need(terminals == [(191287, 8, 1)], 'Wrong/extra/early terminal')
    return dict(status='ALL_SCALAR_RVC_PC_GPR_MEMORY_EXACT', retirements=len(retired),
                traps=0, counts=dict(counts), skipped_memory_events=0), memory, reads


def independent_actual(memory, reads, symbols):
    def read(addr, size, require_load=True):
        need(all(addr + i in memory for i in range(size)), 'Missing independent output/signature byte')
        if require_load:
            need(set(range(addr, addr + size)) <= reads, 'Independent output not scalar-read back')
        return bytes(memory[addr + i] for i in range(size))
    target_bytes, guard_bytes = 0, 0
    for phase in range(4):
        add, mask, gather = independent.expected(phase)
        for name, stride, data, guard in (
            ('output', 1040, add, bytes([0x69]) * 16),
            ('compared', 32, mask.to_bytes(16, 'little'), bytes([0x69]) * 16),
            ('gathered', 1040, gather, bytes([0x69]) * 16)):
            addr = symbols[name] + phase * stride
            need(read(addr, len(data)) == data, 'Independent phase%d %s data mismatch' % (phase, name))
            need(read(addr + len(data), len(guard)) == guard, 'Independent guard mismatch')
            target_bytes += len(data)
            guard_bytes += len(guard)
    signature = [int.from_bytes(read(symbols['g75_result'] + i * 4, 4, False), 'little') for i in (0, 1)]
    failed = int.from_bytes(read(symbols['num_failed'], 4, False), 'little')
    need(signature == [5256, 0] and failed == 0 and target_bytes == 8256 and guard_bytes == 192,
         'Independent5256 checks/signature/8256 bytes mismatch')
    return dict(status='ACTUAL_READBACK_INDEPENDENT_INTEGER_ORACLE_PASS', phases=4,
                target_instructions=12, independently_compared_bytes=target_bytes,
                guard_bytes=guard_bytes, software_checks=5256, failed_checks=failed,
                actual_signature=signature, source='Actual DUT scalar readback, not copied Spike vector data')


def lifecycle(rows, vectors=None):
    starts, pending, live = {}, {}, {}
    req, resp, alloc, done = [], [], Counter(), Counter()
    for r in rows:
        event, seq, tid, cycle = r['event'], int(r['order']), int(r['trans_id']), int(r['cycle'])
        if event == 'arch_start':
            need(seq not in starts and tid not in pending, 'Duplicate architectural/live request')
            starts[seq], pending[tid] = r, [seq, False]
        elif event == 'cvx_req':
            need(tid in pending and not pending[tid][1] and
                 r['insn'] == starts[pending[tid][0]]['insn'], 'Unowned/duplicate CVX request')
            pending[tid][1] = True
            req.append((cycle, tid, int(r['insn'], 16), pending[tid][0]))
        elif event == 'cvx_resp':
            need(tid in pending and pending[tid][1] and seq == -1 and
                 int(r['pc'], 16) == int(r['insn'], 16) == 0 and int(r['trap']) == 0, 'Unowned/exception CVX response')
            resp.append((cycle, tid, pending.pop(tid)[0]))
        elif event in ('uop_alloc', 'uop_done'):
            vid = int(r['port'])
            need(seq in starts and r['insn'] == starts[seq]['insn'] and
                 tid == int(starts[seq]['trans_id']) and 0 <= vid < 8, 'Unowned backend activity')
            if event == 'uop_alloc':
                need(vid not in live, 'Live backend SID reused')
                live[vid] = (seq, cycle)
                alloc[seq, vid, cycle] += 1
            else:
                need(vid in live and live[vid][0] == seq and live[vid][1] <= cycle, 'Unknown/premature backend completion')
                live.pop(vid)
                done[seq, vid, cycle] += 1
    need(not pending and not live and len(req) == len(resp) == len(starts) == 62 and
         Counter(x[3] for x in req) == Counter(x[2] for x in resp) == Counter(starts.keys()), 'Architectural lastdrain not complete')
    if vectors is None:
        need(sum(alloc.values()) == sum(done.values()) == 48 and
             Counter((seq, vid) for seq, vid, cycle in alloc.elements()) ==
             Counter((seq, vid) for seq, vid, cycle in done.elements()), 'Commit backend lastdrain incomplete')
        return dict(requests=62, responses=62, exceptions=0, backend_uops=48,
                    pending_at_terminal=0, native_lifecycle_complete=False,
                    last_response_commit_cycle=resp[-1][0]), req, resp
    va, vd, metadata, previous = Counter(), Counter(), {}, -1
    for r in vectors:
        cycle, seq, vid = int(r['cycle']), int(r['arch_seq']), int(r['vid'])
        need(cycle >= previous and (int(r['nr_lanes']), int(r['vlen_bits'])) == (4, 1024), 'Vector time/geometry differs')
        previous = cycle
        if r['event'] == 'config':
            continue
        need(seq in starts and r['insn'] == starts[seq]['insn'] and 0 <= vid < 8, 'Vector activity identity differs')
        if r['event'] == 'alloc':
            key = seq, vid, cycle
            need(key not in metadata, 'Duplicate native allocation')
            metadata[key] = r
            va[key] += 1
        elif r['event'] == 'done':
            vd[seq, vid, cycle] += 1
        else:
            need(r['event'] == 'write' and int(r['use_vd']) == 1 and 0 <= int(r['lane']) < 4,
                 'Unknown/invalid VRF activity')
    need(va == alloc and vd == done and sum(alloc.values()) == sum(done.values()) == 48,
         'Native/commit complete backend lifecycle differs')
    return dict(requests=62, responses=62, exceptions=0, backend_uops=48,
                pending_at_terminal=0, native_lifecycle_complete=True,
                last_response_commit_cycle=resp[-1][0]), req, resp


CONTRACT = re.compile(r'\[ARA_CONTRACT_TRACE\] sample=pre_edge cycle=(\d+) req=([01])/([01]) fire=([01]) id=([0-9a-f]+) insn=([0-9a-f]+) resp=([01])/([01]) fire=([01]) id=([0-9a-f]+) exc=([01]) pending=([0-9a-f]+) stalled=([01])([01]) errors=([01]{7})')


def protocol(text, requests, responses, terminal_cycle):
    pending, records, req, resp = 0, [], [], []
    for line in text.splitlines():
        need('[ARA_CONTRACT_ERROR]' not in line and not re.search(r'\b(?:Error:|Fatal:|Error-\[|Fatal-\[)', line),
             'Simulator/contract diagnostic')
        if re.search(r'\b(?:UVM_ERROR|UVM_FATAL)\b', line):
            need(re.fullmatch(r'\s*(?:UVM_ERROR|UVM_FATAL)\s*:\s*0+\s*', line) is not None, 'UVM diagnostic')
        need('Core Test *** FAILED' not in line, 'Core test failure diagnostic')
        if '[ARA_CONTRACT_TRACE]' not in line:
            continue
        match = CONTRACT.fullmatch(line.strip())
        need(match is not None, 'Malformed/unknown contract sample')
        v = match.groups()
        cycle, rv, rr, rf, rid, insn, sv, sr, sf, sid, exc, before, rs, ss, errors = (
            int(x, 16 if i in (4, 5, 9, 11) else 2 if i == 14 else 10) for i, x in enumerate(v))
        need(not records or cycle > records[-1]['cycle'], 'Reordered/duplicate contract sample')
        need(0 <= rid < 8 and 0 <= sid < 8 and before == pending and
             rf == rv * rr and sf == sv * sr and (rf or sf) and exc == errors == 0, 'Protocol ownership/error mismatch')
        need(not rf or not (pending >> rid & 1) or (sf and rid == sid), 'Duplicate protocol ID')
        need(not sf or (pending >> sid & 1) or (rf and rid == sid), 'Orphan protocol response')
        if rf:
            req.append((cycle, rid, insn))
        if sf:
            resp.append((cycle, sid))
        if rf and not sf:
            pending |= 1 << rid
        elif sf and not rf:
            pending &= ~(1 << sid)
        elif rf and sf and rid != sid:
            pending = (pending | (1 << rid)) & ~(1 << sid)
        records.append(dict(cycle=cycle, pending_before=before, pending_after=pending,
                            req_valid=rv, req_ready=rr, resp_valid=sv, resp_ready=sr,
                            req_stalled_before=rs, resp_stalled_before=ss))
    need(len(req) == len(requests) == len(resp) == len(responses) == 62 and len(records) < 100000,
         'Missing/capped protocol handshake trace')
    offsets = set()
    for a, b in zip(req, requests):
        need(a[1:] == b[1:3], 'Protocol/commit exact request identity differs')
        offsets.add(a[0] - b[0])
    for a, b in zip(resp, responses):
        need(a[1] == b[1], 'Protocol/commit response identity differs')
        offsets.add(a[0] - b[0])
    need(offsets == {5}, 'Reset-origin protocol/commit cycle offset not exact5')
    last = records[-1]
    need(pending == 0 and last['pending_before'] == 4 and last['pending_after'] == 0 and
         last['req_valid'] == 0 and last['resp_valid'] == last['resp_ready'] == 1 and
         last['req_stalled_before'] == last['resp_stalled_before'] == 0 and
         last['cycle'] - 5 < terminal_cycle, 'Lastdrain incomplete/nonzero/after terminal')
    return dict(status='EXACT_HANDSHAKE_LASTDRAIN_PASS_NOT_SIMULATOR_FINAL_SUMMARY', requests=62,
        responses=62, observed_fire_errors=0, lastdrain=last, cycle_origin_offset=5,
        cycle_origin_reason='Contract cycle_q advances during reset; commit cycle_q resets to0. All124 matched handshakes independently establish +5.',
        final_summary_present='[ARA_CONTRACT]' in text, final_summary_required_for_normal_run=True,
        timeout_final_summary_claimed=False, stalled_after_last_edge=0)


def inspect_vdb(path):
    members = sorted(p for p in path.rglob('*') if p.is_file())
    need(not any(p.is_symlink() for p in path.rglob('*')), 'Aliased original VDB')
    return dict(status='INCOMPLETE_NO_TESTDATA_NOT_ADMISSIBLE',
                members=[dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p)) for p in members],
                testdata_directory_present=(path / 'snps/coverage/db/testdata').is_dir(),
                testdata_present=any((path / 'snps/coverage/db/testdata').glob('*/*')),
                coverage_admissible=False)


def duplicate_log_prefix(raw, complete):
    actual = [line for line in raw.splitlines() if '[ARA_CONTRACT_TRACE]' in line]
    expected = [line for line in complete.splitlines() if '[ARA_CONTRACT_TRACE]' in line]
    partial = actual[-1] if actual and not raw.endswith('\n') else None
    finished = actual[:-1] if partial is not None else actual
    need(finished == expected[:len(finished)], 'Duplicate VCS log differs from authoritative console prefix')
    if partial is not None:
        need(len(finished) < len(expected) and expected[len(finished)].startswith(partial),
             'Partial duplicate log is not a prefix of the actual console event')
    return dict(complete=False, full_records=len(finished), partial_last_line=partial,
                source='Truncated duplicate run.vcs.log, not used to invent missing events',
                authoritative_protocol_source='console.log')


def collect(output):
    need(output.parent == OUT and not output.exists(), 'Fresh independent output required')
    vdb = inspect_vdb(RUN / 'code.vdb')
    need(not vdb['testdata_present'] and len(vdb['members']) == 1 and
         Path(vdb['members'][0]['path']).name == '.mode64' and vdb['members'][0]['bytes'] == 0,
         'Original VDB state differs; separately re-audit, never assume complete')
    record = json.loads((RUN / 'manifest.json').read_bytes())
    pre = json.loads((PRE / 'preflight.json').read_bytes())
    state = json.loads((RUN / 'simulation-status.json').read_bytes())
    started = json.loads((RUN / 'started.json').read_bytes())
    need(state['status'] == 'SIMULATION_NOT_ADMITTED' and state['reason'].startswith('TimeoutExpired:') and
         not state['coverage_admitted'] and not state['admission_performed'], 'Original timeout receipt differs')
    need(record['preflight'] == pre and pre['software_checks'] == 5256 and
         pre['independently_compared_vector_bytes'] == 8256 and pre['target_instructions'] == 12,
         'Independent preflight differs')
    need(started['command'] == record['command'] and not any(x.startswith('+COMMIT_TOHOST=') for x in record['command'])
         and record['timeout_s'] == started['budget_s'] == 1800 and
         started['image_sha256'] == '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3',
         'Actual timeout harness/command differs')
    pins = dict(record['pins'])
    for p, digest in pins.items():
        need(sha(p) == digest, 'Inherited run/preflight pin drift: ' + p)
    extra = [RUN / name for name in ('manifest.json', 'simulation-status.json', 'started.json',
             'commit_trace.csv', 'vector_trace.csv', 'run.vcs.log', 'console.log')]
    extra += [Path(__file__).resolve(), Path(__file__).with_name('test_qualify_operand_mask_data_timeout_offline.py'),
              Path(st.__file__), Path(vc.__file__), Path(compressed.__file__), Path(independent.__file__),
              ROOT / 'hardware/tb/ara_commit_monitor.sv', ROOT / 'verification/uvm/ara_acc_contract_monitor.sv']
    # Runner/test pins are external qualification evidence; never edit them.
    external = [ROOT / 'verification/coverage/run_operand_mask_data.py',
                ROOT / 'verification/coverage/test_operand_mask_data_preflight.py']
    extra += external
    pins.update({str(p): sha(p) for p in extra})
    pins.update({m['path']: m['sha256'] for m in vdb['members']})
    buildpins = json.loads((OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
    for p in extra[-4:-2]:
        need(str(p) in buildpins and sha(p) == buildpins[str(p)], 'Monitor frozen source drift')
    raw, rows, terminal = prefix((RUN / 'commit_trace.csv').read_bytes())
    need((terminal['cycle'], terminal['order']) == (247776, 191287), 'Actual exact reviewed terminal differs')
    reference = []
    for c in st.parse_spike_commits(PRE / 'spike.trace'):
        if not reference and c.pc != 0x80000000:
            continue
        reference.append(c)
        if (0x80001000, 1) in c.memory_accesses:
            break
    need(len(reference) == 191288 and reference[-1].memory_accesses == ((0x80001000, 1),), 'Incomplete Spike terminal')
    need(independent.validate(reference) == 8256, 'Independent sealed Spike oracle differs')
    output.mkdir()
    (output / 'commit-prefix.csv').write_bytes(raw)
    scalar = st.compare_commit_prefix(PRE / 'spike.trace', output / 'commit-prefix.csv', 0x80000000,
                                     terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
    save(output / 'scalar-comparison.json', scalar)
    fixed = dict(record['counts'], status='TERMINAL_TOHOST_MATCH', ara_trap_events=0,
                 ara_retired_instructions=191288, ara_committed_instructions=191288,
                 skipped_unobservable_register_values=0, stopped_at_unobservable=None,
                 aligned_vector_faults=[], mismatch=None, terminal_ecall=None)
    need(all(k in scalar and type(scalar[k]) is type(v) and scalar[k] == v for k, v in fixed.items()), 'Full scalar baseline checker differs')
    architecture, memory, reads = full_scalar(rows, reference, pre['symbols'])
    oracle = independent_actual(memory, reads, pre['symbols'])
    control, requests, responses = lifecycle(rows)
    contract = protocol((RUN / 'console.log').read_text(), requests, responses, terminal['cycle'])
    duplicate_log = duplicate_log_prefix((RUN / 'run.vcs.log').read_text(), (RUN / 'console.log').read_text())
    vector_complete = False
    try:
        vectors = table((RUN / 'vector_trace.csv').read_bytes(), VECTOR_FIELDS)
        need(all(int(r['cycle']) <= terminal['cycle'] for r in vectors), 'Postterminal vector activity')
        (output / 'vector-prefix.csv').write_bytes((RUN / 'vector_trace.csv').read_bytes())
        control, _, _ = lifecycle(rows, vectors)
        vector = vc.compare_vector_commits(PRE / 'spike.trace', output / 'commit-prefix.csv', output / 'vector-prefix.csv', 0x80000000)
        need(vector['status'] == 'PASS' and all(vector[k] == 0 for k in
             ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions')) and
             not any(vector[k] for k in ('incomplete_requests', 'unretired_requests', 'trapped_requests')) and
             vector['first_mismatch'] is None and len(vector['instructions']) == len([c for c in reference if c.vector_writes]),
             'Strict full architectural vector comparison failed')
        vector_complete = True
    except (ValueError, vc.VectorCommitComparisonError) as error:
        last = (RUN / 'vector_trace.csv').read_bytes().splitlines()[-1].decode()
        vector = dict(status='HOLD_INCOMPLETE_NATIVE_VECTOR_CAPTURE', reason=str(error),
                      raw_last_line=last, partial_line_discarded=False,
                      missing_bytes_fabricated=False, full_architectural_vector_qualified=False)
    save(output / 'vector-comparison.json', vector)
    for p, digest in pins.items():
        need(sha(p) == digest, 'Source changed during offline qualification: ' + p)
    for p in output.iterdir():
        pins[str(p)] = sha(p)
    result = dict(schema='OPERAND_MASK_DATA_TIMEOUT_PROGRAM_QUALIFICATION_V1',
        status=('PROGRAM_COMPLETE_FULL_ARCHITECTURE_QUALIFIED_HARNESS_TIMEOUT_FAILED_VDB_REJECTED' if vector_complete else
                'PROGRAM_COMPLETION_SCALAR_ORACLE_LASTDRAIN_PASS_FULL_VECTOR_CAPTURE_HOLD'),
        harness_status='TIMEOUT_EXIT_FAILURE_NOT_PASS', original_simulation_status=state,
        harness_root_cause='Executed command omits COMMIT_TOHOST; frozen monitor activates terminal finish only with that plusarg. Program continued in finish self-loop after successful terminal.',
        original_VDB=vdb, terminal=terminal, full_scalar=architecture, independent_oracle=oracle,
        protocol_lastdrain=contract, duplicate_VCS_log=duplicate_log, lifecycle=control,
        full_vector=vector, full_architecture_qualified=vector_complete,
        external_qualification_evidence={str(p): sha(p) for p in external},
        pins=pins, original_trace_modified=False, timeout_marked_PASS=False,
        simulation_launched=False, coverage_admitted=False, population_modified=False,
        scope='Whole program through exact successful tohost retirement. Scalar/RVC, independent output readback and protocol are separate gates; full native vector comparison must independently PASS. Not successful simulator exit or coverage qualification.')
    save(output / 'qualification.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.output.absolute())
    print(json.dumps(dict(status=result['status'], seal=sha(args.output / 'qualification.json'),
                          terminal=result['terminal'], vector_status=result['full_vector']['status'], coverage_admitted=False)))
