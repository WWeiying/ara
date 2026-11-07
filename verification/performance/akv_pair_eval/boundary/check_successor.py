#!/usr/bin/env python3
"""Read-only, maintenance-aware audit of sealed boundary evidence; not a worker reclassification.

The frozen dispatcher initializes maintenance_req from ara_req (including
verify_arch_seq/insn), then injects VSLIDEDOWN at EW16, LMUL1, VL=VLENB/2.
The monitor records those inherited tags, not the backend op. A D96 partial
LMUL2 destination can therefore have two tagged VL64 preservation reshuffles
before the actual VL96 load. Only that complete, ordered triple is admitted.
"""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SEALED = {
    'build.py': 'e9811405b436ddd7626762790e9b4f7f7342c60bec560da93ebbeaa925f2a0ff',
    'main.c': 'fbce019455cb00036acadba57d08a75174623435e5fca19df6c1cddd88571e06',
    'check.py': '321c6bbe98faa90f1853e32b90442761f34f4d8790491994b85038067e166849',
    'test_boundary.py': '25ff570dd3cf570cc47a56a3fc8ba9f1937e58327ef04e7594f01c4aeba6fa7a',
}
for _name, _digest in SEALED.items():
    if hashlib.sha256((HERE / _name).read_bytes()).hexdigest() != _digest:
        raise ValueError('Sealed boundary source changed: ' + _name)
_spec = importlib.util.spec_from_file_location('boundary_sealed_original_check', HERE / 'check.py')
original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(original)
require = original.require
check_run = original.check_run
INFO = 0x0005455b
VECTOR_FIELDS = ('cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,'
                 'addr,be,wdata,nr_lanes,vlen_bits').split(',')
COMMIT_FIELDS = ('cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,'
                 'mem_rmask,mem_wmask,mem_wdata,trap').split(',')
META = ('arch_seq', 'insn', 'use_vd', 'vd', 'eew', 'vl', 'vstart')
SHAPE = ('use_vd', 'vd', 'eew', 'vl', 'vstart')
FROZEN_HW = original.contract.OUT / 'chain_soc_20261107_01/source/hardware'
SEMANTICS_PINS = {
    str(FROZEN_HW / 'src/ara_dispatcher.sv'):
        '7bd7b46c87e2821e349d7c8938870ac79b2a77bf31eb3525fa07b904fc4eadf8',
    str(FROZEN_HW / 'tb/ara_commit_monitor.sv'):
        '38b7642703c49e31fd0493b81e948388f2dbc72f97da418f3ed76e73bd42c782',
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def decimal(text, limit=(1 << 64) - 1):
    require(text.isascii() and text.isdecimal(), 'Invalid unsigned trace integer: ' + text)
    value = int(text)
    require(value <= limit, 'Trace integer out of range')
    return value


def hexadecimal(text, width):
    require(len(text) == width and re.fullmatch('[0-9a-fA-F]+', text), 'Invalid trace hex field')
    return int(text, 16)


def rows(path, fields):
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == fields, 'Unexpected/duplicate trace schema: ' + str(path))
        for line, row in enumerate(reader, 2):
            require(None not in row and all(v is not None for v in row.values()),
                    'Malformed trace row at ' + str(line))
            yield line, row


def expected_work():
    calls = original.expected_vector_calls()
    native = [w for call in calls for w in call]
    # A D96 tile's first PV row follows its QK column phase. Positions are
    # derived from the workload, never from observed seq/cycle coordinates.
    triples = {i for i, w in enumerate(native) if w == original.ROW96 and
               native[i - 1] in (original.COLUMN, original.PANEL)}
    extended = [INFO] * 4
    for index, call in enumerate(calls):
        case = original.contract.CASES[index // 3]
        if index % 3 == 1 and not (case['d'] == 128 and case['heads'] == 6):
            extended += [INFO] * 4
        extended += call
    require(len(triples) == 6 and len(native) == 3680 and len(extended) == 3696,
            'Sealed work/INFO/maintenance formulas changed')
    return native, extended, triples


def operation_shape(word):
    if word in (original.FULL, original.REFILL, original.RELEASE):
        return (0, 0, 1, 1, 0)
    vl = {original.COLUMN: 64, original.COLUMN9: 64, original.PANEL: 256,
          original.ROW64: 64, original.ROW96: 96,
          original.ROW128: 128, original.ROW128_GQA6: 128}[word]
    return (1, (word >> 7) & 31, 1, vl, 0)


def read_vector(path):
    groups, pending, uop_events = [], {}, []
    configs, last_cycle, last_seq, last_alloc_cycle, last_word = 0, -1, -1, -1, None
    for line, row in rows(path, VECTOR_FIELDS):
        cycle = decimal(row['cycle'])
        require(cycle >= last_cycle and (row['nr_lanes'], row['vlen_bits']) == ('4', '1024'),
                'Vector cycle/image drift')
        last_cycle = cycle
        event = row['event']
        if event == 'config':
            require(configs == 0 and line == 2 and cycle == 0 and
                    [row[k] for k in VECTOR_FIELDS[2:-2]] ==
                    ['0', '0', '0', '0', '00000000', '0', '0', '0', '0', '0', '0', '00',
                     '0000000000000000'], 'Duplicate/late/malformed vector config')
            configs += 1
            continue
        require(configs == 1 and event in ('alloc', 'done', 'write'), 'Vector reset/unknown event')
        seq, vid = decimal(row['arch_seq']), decimal(row['vid'], 7)
        word = hexadecimal(row['insn'], 8)
        if event == 'write':
            decimal(row['lane'], 3)
            decimal(row['source'], 4)
            # The monitor may retain write metadata after done. Full VRF/write
            # protocol checking belongs to the owner's independent UVM audit.
            continue
        require(row['lane'] == row['source'] == row['addr'] == '0' and row['be'] == '00' and
                row['wdata'] == '0000000000000000', 'Malformed vector alloc/done record')
        for key, limit in (('use_vd', 1), ('vd', 31), ('eew', 3), ('vl', 1024), ('vstart', 1024)):
            decimal(row[key], limit)
        meta = tuple(row[k] for k in META)
        if event == 'done':
            active = pending.pop(vid, None)
            require(active is not None and active['metadata'] == meta and cycle >= active['cycle'],
                    'Unknown/duplicate/changed VID completion')
            active['done_cycle'] = cycle
        else:
            require(seq >= last_seq and cycle > last_alloc_cycle and vid not in pending,
                    'Vector sequence regression/multiple allocation/busy VID reuse')
            require(seq != last_seq or word == last_word, 'Architecture tag changed within backend group')
            last_seq, last_alloc_cycle, last_word = seq, cycle, word
            active = dict(line=line, cycle=cycle, arch_seq=seq, vid=vid, insn=f'{word:08x}',
                          metadata=meta, shape=tuple(int(row[k]) for k in SHAPE))
            pending[vid] = active
            if word & 0x7f == 0x5b:
                require(word in original.SIGNATURE_NAMES, 'Unknown custom allocation signature')
                if not groups or groups[-1]['arch_seq'] != seq:
                    require(not groups or seq > groups[-1]['arch_seq'], 'Noncontiguous custom group')
                    groups.append(dict(arch_seq=seq, word=word, allocations=[]))
                require(groups[-1]['word'] == word, 'Custom group changed original instruction tag')
                groups[-1]['allocations'].append(active)
        if word & 0x7f == 0x5b:
            require(word in original.SIGNATURE_NAMES, 'Unknown custom completion signature')
            uop_events.append((event, seq, vid, word, cycle))
    require(configs == 1 and not pending, 'Missing vector configuration or incomplete VID lifetime')
    return groups, uop_events


def validate_groups(groups):
    native, _, triples = expected_work()
    require(len(groups) == len(native), 'Missing/extra architectural native group')
    raw, maintenance = Counter(), []
    for index, (group, wanted) in enumerate(zip(groups, native)):
        require(group['word'] == wanted, 'Native group originalword/order mismatch')
        allocs = group['allocations']
        require(all(int(a['insn'], 16) == wanted and a['arch_seq'] == group['arch_seq'] for a in allocs),
                'Group instruction/architecture identity changed')
        if index in triples:
            require(wanted == original.ROW96 and len(allocs) == 3 and
                    [a['shape'] for a in allocs] == [(1, 8, 1, 64, 0), (1, 9, 1, 64, 0), (1, 8, 1, 96, 0)],
                    'Incomplete/unknown D96 maintenance triple or missing original operation')
            require(max(a['done_cycle'] for a in allocs[:2]) < allocs[2]['cycle'],
                    'Original D96 load issued before maintenance drained')
            maintenance.append(dict(native_index=index, arch_seq=group['arch_seq'], originalword=f'{wanted:08x}',
                allocations=[{k: a[k] for k in ('line', 'cycle', 'done_cycle', 'vid', 'insn', 'shape')}
                             for a in allocs]))
        else:
            require(len(allocs) == 1 and allocs[0]['shape'] == operation_shape(wanted),
                    'Unexpected duplicate/maintenance or wrong original operation shape')
        raw[original.SIGNATURE_NAMES[wanted]] += len(allocs)
    counts = Counter(original.SIGNATURE_NAMES[g['word']] for g in groups)
    require(dict(counts) == original.EXPECTED_COUNTS and len(maintenance) == 6 and sum(raw.values()) == 3692,
            'Native versus maintenance work totals mismatch')
    return dict(counts=dict(counts), raw_custom_alloc_counts=dict(raw), maintenance_groups=maintenance,
                raw_custom_allocations=3692, architectural_native_commands=3680, maintenance_allocations=12)


def elf_custom_instructions(elf):
    result = {}
    for symbol in original.elf_contents(elf).values():
        if symbol['type'] == 2:
            for pc, word, size in original.instructions(symbol['data'], symbol['address']):
                if size == 4 and word & 0x7f == 0x5b:
                    result[pc] = word
    require(result, 'No actual ELF custom instructions')
    return result


def check_commit(path, groups, vector_events, elf_words):
    native, extended, _ = expected_work()
    retired, starts, commit_events = [], [], []
    last_cycle, retire_order, start_seq = -1, -1, -1
    native_starts, native_retires = [], []
    for line, row in rows(path, COMMIT_FIELDS):
        cycle = decimal(row['cycle'])
        require(cycle >= last_cycle and row['trap'] == '0', 'Commit cycle drift or trap/exception')
        last_cycle = cycle
        event = row['event']
        require(event in ('retire', 'arch_start', 'uop_alloc', 'uop_done', 'cvx_req', 'cvx_resp'),
                'Unknown/reset commit event')
        word = hexadecimal(row['insn'], 8)
        if event == 'retire':
            order = decimal(row['order'])
            require(order == retire_order + 1 and row['port'] in ('0', '1') and row['trans_id'] == '-1',
                    'Missing/duplicate/out-of-order architectural retirement')
            retire_order = order
            if word & 0x7f == 0x5b:
                require(len(retired) < len(extended) and word == extended[len(retired)],
                        'Commit custom/native/INFO signature/order mismatch')
                pc = hexadecimal(row['pc'], 16)
                require(elf_words.get(pc) == word, 'Retired custom PC/instruction not in actual sealed ELF')
                retired.append(word)
                if word != INFO:
                    native_retires.append(dict(line=line, order=order, cycle=cycle, word=word))
        elif event == 'arch_start':
            seq = decimal(row['order'])
            require(seq == start_seq + 1 and row['port'] == '-1', 'Missing/duplicate architectural start sequence')
            start_seq = seq
            decimal(row['trans_id'], 15)
            if word & 0x7f == 0x5b:
                require(len(starts) < len(extended) and word == extended[len(starts)],
                        'Architectural start custom/INFO signature mismatch')
                starts.append(word)
                if word != INFO:
                    native_starts.append((seq, word, cycle))
        elif event in ('uop_alloc', 'uop_done') and word & 0x7f == 0x5b:
            commit_events.append(('alloc' if event == 'uop_alloc' else 'done',
                decimal(row['order']), decimal(row['port'], 7), word, cycle))
    require(retired == starts == extended and len(native_retires) == len(native) and
            len(native_starts) == len(groups), 'Incomplete independent architectural retirement/start evidence')
    require(commit_events == vector_events, 'Raw vector and commit backend-uop evidence differs')
    for group, (seq, word, cycle), retired_row in zip(groups, native_starts, native_retires):
        require((group['arch_seq'], group['word']) == (seq, word) and
                cycle <= group['allocations'][0]['cycle'] and retired_row['cycle'] >= cycle and
                retired_row['word'] == word, 'Vector group/architecture entry/retirement identity mismatch')
    return dict(retired_custom_instructions=len(retired), retired_native_commands=len(native_retires),
                retired_info_commands=retired.count(INFO), trap_records=0,
                ordered_retirement_checked=True, retired_elf_pc_checked=True,
                raw_backend_events_checked=len(commit_events), architectural_starts_checked=True)


def audit_work(vector_path, elf_words):
    vector_path = Path(vector_path).resolve(strict=True)
    commit_path = vector_path.with_name('commit.csv').resolve(strict=True)
    require(commit_path.parent == vector_path.parent and commit_path != vector_path, 'Unpaired commit trace')
    before = {str(p): digest(p) for p in (vector_path, commit_path)}
    groups, events = read_vector(vector_path)
    result = validate_groups(groups)
    result['commit_checks'] = check_commit(commit_path, groups, events, elf_words)
    require(all(digest(p) == h for p, h in before.items()), 'Raw evidence changed during read-only audit')
    result.update(trace_sha256=before[str(vector_path)], commit_sha256=before[str(commit_path)],
        commit_path=str(commit_path), raw_preserved=True, independent_protocol_checked=False,
        panel_commands=result['counts']['panel4'],
        column_commands=result['counts']['column_v8'] + result['counts']['column_v9'],
        d64_commands=result['counts']['row_d64'], d96_commands=result['counts']['row_d96'],
        d128_commands=result['counts']['row_d128'] + result['counts']['row_d128_gqa6'],
        lifecycle_commands=27, native_commands=3680, replay_commands=3653,
        per_call_commands=[len(c) for c in original.expected_vector_calls()],
        ordered_signatures_checked=True, life_signatures_checked=True,
        classification='Separate functional audit; original worker FAIL remains unchanged; independent UVM required')
    return result


def check_vector_workcounts(vector_path, build_dir):
    build = original.verify_build(build_dir)
    original.contract.verify(SEMANTICS_PINS)
    result = audit_work(vector_path, elf_custom_instructions(build['elf']))
    after = original.verify_build(build_dir)
    require(after['elf_sha256'] == build['elf_sha256'] and
            after['source_pins_sha256'] == build['source_pins_sha256'], 'Original build receipt changed')
    return dict(result, elf_sha256=build['elf_sha256'], source_pins_sha256=build['source_pins_sha256'],
                post_build_pins_match=True, semantics_pins=SEMANTICS_PINS, performance_measured=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    directory = args.build.parent if args.build.name == 'build.json' else args.build
    result = check_run(args.log, directory)
    result['successor_vector_audit'] = check_vector_workcounts(args.trace, directory)
    result['classification'] = 'Separate read-only audit, not a clean original-worker PASS'
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
