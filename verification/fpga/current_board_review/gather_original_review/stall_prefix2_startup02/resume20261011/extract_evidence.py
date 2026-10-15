#!/usr/bin/env python3
"""Read completed launch02 artifacts; no simulator, helper import, or test execution."""
import csv
import hashlib
import json
from collections import Counter, deque
from pathlib import Path

OUT = Path(__file__).resolve().parent
HERE = OUT.parent.parent
RUN = HERE / 'stall_prefix2_launch02/vcs_candidate04_01'
DATA = HERE / 'stall_prefix2_03'
FROZEN = Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/frozen/sources')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def extract(spec):
    folder = RUN / 'replay/tests' / spec['name']
    model = read(DATA / (spec['name'] + '.host_expected.json'))
    lookup = {entry['pc']: i for i, entry in enumerate(spec['soc_routine'])}
    regs, memory = {}, {}
    calls, first, previous = [], None, deque(maxlen=24)
    tail, near = deque(maxlen=20), []
    events = Counter()
    retired, rows, order_errors, traps = 0, 0, 0, []
    call = None
    with (folder / 'commit_trace.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            rows += 1
            events[row['event']] += 1
            tail.append(row)
            if first is not None and len(near) < 60:
                near.append(row)
            if row['event'] != 'retire':
                continue
            order = int(row['order'])
            order_errors += order != retired
            retired += 1
            pc, insn = int(row['pc'], 16), int(row['insn'], 16)
            value, address = int(row['rd_wdata'], 16), int(row['mem_addr'], 16)
            if int(row['trap']):
                traps.append(row)
            # RVFI scalar store write data is unshifted; retain only SB/SH/SW/SD.
            if int(row['mem_wmask'], 16) and insn & 127 == 0x23:
                width = 1 << ((insn >> 12) & 7)
                if width <= 8:
                    raw = int(row['mem_wdata'], 16)
                    for offset in range(width):
                        memory[address + offset] = (raw >> (8 * offset)) & 255
            if pc in lookup:
                step = lookup[pc]
                if step == 0:
                    ordinal = len(calls) + 1
                    expected = model['rows'][ordinal - 1]
                    checks = {}
                    for key, base, values, width in (
                        ('input', spec['input_address'], model['input'], 1),
                        ('indices16' if spec['operation'] == 20 else 'indices',
                         spec['index_address'], model['indices16'] if spec['operation'] == 20 else model['indices'],
                         2 if spec['operation'] == 20 else 1),
                        ('predicate', spec['predicate_address'], expected['predicate'], 1),
                        ('output_initial', spec['output_address'], [91] * 514, 1),
                    ):
                        differences = []
                        for index, want in enumerate(values):
                            actual = [memory.get(base + index * width + byte) for byte in range(width)]
                            got = None if None in actual else sum(v << (8 * b) for b, v in enumerate(actual))
                            if got != want:
                                differences.append(dict(index=index, expected=want, actual=got))
                        checks[key] = dict(elements=len(values), mismatches=len(differences), first=differences[:3])
                    call = dict(ordinal=ordinal, tuple=expected['tuple'], vl=expected['vl'],
                                vstart=expected['vstart'], scalar=expected['scalar'],
                                setup_registers={str(reg): hex(regs.get(reg, 0)) for reg in range(10, 18)},
                                setup_memory=checks, routine=[], output_reads=0, output_mismatches=[],
                                distinct_output_indices=[])
                    calls.append(call)
                call['routine'].append(row)
                if step == 8:
                    call['target'] = row
                if step == 9:
                    call['returned_vstart'] = value
            if call and int(row['mem_rmask'], 16) and spec['output_address'] <= address < spec['output_address'] + 514:
                index = address - spec['output_address']
                expected = model['rows'][call['ordinal'] - 1]
                want = 91 if index in (0, 513) else expected['output'][index - 1]
                actual = value & 255
                call['output_reads'] += 1
                call['distinct_output_indices'].append(index)
                if actual != want:
                    mismatch = dict(ordinal=call['ordinal'], element=index - 1, expected=want, actual=actual, row=row)
                    call['output_mismatches'].append(mismatch)
                    if first is None:
                        first = mismatch
                        near = list(previous) + [row]
            if int(row['rd']):
                regs[int(row['rd'])] = value
            previous.append(row)
    for call in calls:
        indices = call.pop('distinct_output_indices')
        call['unique_output_reads'] = len(set(indices))
        call['both_guards_read'] = 0 in indices and 513 in indices
    paths = [folder / 'commit_trace.csv', folder / 'console.log', folder / 'work/run.vcs.log',
             folder / 'input.elf', folder / 'inputs.json', folder / 'command.json',
             DATA / 'prepared' / spec['name'] / 'case.c',
             DATA / 'prepared' / spec['name'] / 'original/operations.S',
             DATA / (spec['name'] + '.host_expected.json')]
    return dict(name=spec['name'], rows=rows, event_counts=dict(events), retired=retired,
                retire_order_errors=order_errors, traps=traps, call_count=len(calls), calls=calls,
                first_mismatch=first, first_mismatch_window=near, final_rows=list(tail),
                last_cycle=int(tail[-1]['cycle']),
                input_hashes={str(path): sha(path) for path in paths})


def main():
    plan = read(RUN / 'plan.json')
    result = dict(scope='Completed launch02 read-only analysis; not acceptance or simulation',
                  run=str(RUN), plan_sha256=sha(RUN / 'plan.json'),
                  complete=read(RUN / 'complete.json'), summary=read(RUN / 'replay/summary.json'),
                  cases=[extract(spec) for spec in plan['cases']])
    paths = [FROZEN / relative for relative in (
        'hardware/src/lane/lane_sequencer.sv', 'hardware/src/lane/operand_requester.sv',
        'hardware/src/lane/valu.sv', 'hardware/src/lane/simd_alu.sv', 'hardware/src/masku/masku.sv')]
    result['frozen_source_hashes'] = {str(path): sha(path) for path in paths}
    destination = OUT / 'evidence.json'
    with destination.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    for case in result['cases']:
        print(case['name'], 'calls', case['call_count'], 'retired', case['retired'], 'last_cycle', case['last_cycle'])
        print('first_mismatch', case['first_mismatch'])
        for call in case['calls'][-2:]:
            print('call', call['ordinal'], call['tuple'], 'reads', call['output_reads'],
                  'setup', call['setup_memory'], 'target', call.get('target'))
    print(destination)


if __name__ == '__main__':
    main()
