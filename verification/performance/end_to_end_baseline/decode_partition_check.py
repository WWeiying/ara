"""Strict per-partition target results and native service; UVM is separate."""
import re

from audit import require
from check_projection_native import checksum
from check_decode_rvv import fields
from check_decode_matched import oracle
from check_decode_matched_activity import ACCESS
from check_decode_native import CONTEXT_COUNTERS
from check_supply_decode import COUNTERS, WAIT, PHASES, read_contract
from decode_partition_driver import contract, scope, K, PROFILE, ORDER

CORE = 'Core Test *** SUCCESS *** (tohost = 0)'


def terminal(group):
    c = contract(group)
    return (f'DECODE_PARTITION_RESULT group={group} trials=4 native_commands={c["native_commands"]} '
            f'outputs_checked={c["outputs_checked"]} errors=0')


def check_command(row, width, part, access, seq):
    blocks = K[part]//256
    reused = int(access in (2, 3))
    activation = blocks*292
    weight = 32*blocks*(144 if PROFILE[part] == 1 else 210)
    wanted = dict(seq=seq, m=1, n=32, vlen=1024, lanes=4, success=1, fault=0,
                  validation_fault=0, read_fault=0, useful_pairs=8192*blocks,
                  dot_active_cycles=256*blocks, activation_access=access,
                  activation_bytes=activation, weight_bytes=weight,
                  payload_bytes=16+weight+(0 if reused else activation),
                  context_fill_count=int(access == 1), context_reuse_count=reused,
                  context_reuse_block_count=blocks if reused else 0,
                  context_read_bytes=activation if reused else 0,
                  activation_axi_bytes_saved=activation if reused else 0,
                  context_validation_fault_count=0)
    require(all(row.get(k) == v for k, v in wanted.items()), 'Native command identity/context/work differs')
    require(all(k in row for k in (*COUNTERS, *WAIT, *CONTEXT_COUNTERS)) and
            all('phase_'+p+'_cycles' in row for p in PHASES) and
            sum(row['phase_'+p+'_cycles'] for p in PHASES) == row['busy_cycles'] and
            sum(row[k] for k in WAIT) == row['weight_prefetch_wait_cycles'] and
            row['dot_active_cycles'] <= row['busy_cycles'], 'Native phase/wait conservation differs')
    read_contract(row, width, blocks, PROFILE[part], 1)


def check(text, group, width, native, rvv, packed, flags):
    c = contract(group)
    require(width in (128, 256) and len(native) == len(rvv) == len(flags) == 7 and
            all(len(x) == 256 for x in (*native, *rvv)) and
            list(map(len, packed)) == [2336, 2336, 7008, 2336] and
            all(type(x) is int and x in (0, 1) for x in flags), 'Partition oracle geometry/flags')
    lines = text.replace('\r', '').splitlines()
    require(not re.search(r'Fatal[-:]|Error[-:]|Assertion[^\n]*failed|\b(?:FAIL|FAILED|TIMEOUT)\b|mcause_val',
                          text, re.I), 'Failure diagnostic')
    require([l for l in lines if 'Core Test' in l] == [CORE], 'Contradictory/missing core completion')
    require(lines.count(scope(group)) == lines.count(terminal(group)) == 1 and
            lines.index(scope(group)) < lines.index(terminal(group)) < lines.index(CORE),
            'Partition scope/terminal order')
    severity = set()
    events = []
    for line in lines:
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            m = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(m is not None and m[1] not in severity, 'UVM failure/duplicate severity')
            severity.add(m[1])
        if line.startswith('Command:'): continue
        if 'AKV_PERF' in line: raise ValueError('Unexpected AKV work')
        if 'QBS_PERF' in line:
            require(line.startswith('[QBS_PERF] '), 'Malformed/unexpected native hardware record')
            events.append(('command', fields(line, '[QBS_PERF]')))
        elif 'DECODE_PARTITION_' in line:
            if line in (scope(group), terminal(group)):
                events.append(('scope' if line == scope(group) else 'end', None))
            else:
                tag = line.split(' ', 1)[0]
                require(tag in ('DECODE_PARTITION_BEGIN', 'DECODE_PARTITION_PREP',
                                'DECODE_PARTITION_PART', 'DECODE_PARTITION_TRIAL'), 'Unknown partition marker')
                events.append((tag.removeprefix('DECODE_PARTITION_').lower(), fields(line, tag)))
        elif line.startswith('MATCHED_DECODE_'): raise ValueError('Legacy evidence is not a partition')
    require(severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Missing zero UVM summaries')
    cursor = 0

    def take(kind):
        nonlocal cursor
        require(cursor < len(events) and events[cursor][0] == kind, 'Missing/misordered '+kind)
        row = events[cursor][1]; cursor += 1
        return row

    take('scope')
    trials, prep_rows, part_rows, commands, activity = [], [], [], [], []
    for trial, backend in enumerate(ORDER):
        require(take('begin') == dict(group=group, trial=trial, backend=backend), 'ABBA begin identity')
        call_commands = []
        if backend:
            for part in c['parts']:
                selected = []
                for access in ACCESS[part]:
                    row = take('command')
                    check_command(row, width, part, access, len(commands)+1)
                    commands.append(row); selected.append(row)
                call_commands.append((part, selected))
        selected_prep = []
        for stage in c['stages']:
            row = take('prep')
            wanted = dict(trial=trial, backend=backend, stage=stage, fcsr=9, vcsr=3,
                          vstart=0, checksum=checksum(packed[stage]), errors=0)
            require(set(row) == set(wanted)|{'cycles'} and row['cycles'] > 0 and
                    all(row[k] == v for k, v in wanted.items()), 'Payload/preparation/CSR mismatch')
            prep_rows.append(row); selected_prep.append(row)
        selected_parts = []
        fc = 9
        for part in c['parts']:
            if backend: fc |= flags[part]
            row = take('part')
            wanted = dict(trial=trial, backend=backend, part=part, profile=PROFILE[part], k=K[part],
                          fcsr=fc, vcsr=3, vstart=0, checksum=checksum((native if backend else rvv)[part]), errors=0)
            require(set(row) == set(wanted)|{'admission', 'execution'} and
                    row['admission'] > 0 and row['execution'] > 0 and
                    all(row[k] == v for k, v in wanted.items()), 'Output/part/CSR mismatch')
            if backend:
                selected = dict(call_commands)[part]
                busy = sum(x['busy_cycles'] for x in selected)
                require(busy <= row['execution'], 'Native busy outside timed execution')
                activity.append(dict(trial=trial, part=part, commands=selected,
                                     sdk_outside_busy_cycles=row['execution']-busy))
            part_rows.append(row); selected_parts.append(row)
        row = take('trial')
        wanted = dict(trial=trial, backend=backend, preparation=sum(x['cycles'] for x in selected_prep),
                      admission=sum(x['admission'] for x in selected_parts),
                      execution=sum(x['execution'] for x in selected_parts), commands=2*len(c['parts']) if backend else 0,
                      q4_calls=0 if backend else c['q4_calls'], q6_calls=0 if backend else c['q6_calls'],
                      outputs=64*len(c['parts']), untouched_errors=0, errors=0)
        require(set(row) == set(wanted)|{'region'} and all(row[k] == v for k, v in wanted.items()) and
                row['region'] >= sum(row[k] for k in ('preparation', 'admission', 'execution')),
                'Trial conservation/work/untouched-buffer mismatch')
        trials.append(row)
    take('end'); require(cursor == len(events) and len(commands) == c['native_commands'], 'Trailing/incomplete work')
    a = [r for r in trials if r['backend'] == 0]
    b = [r for r in trials if r['backend'] == 1]
    metadata = {k: v for k, v in c.items() if k not in ('parts', 'stages')}
    return dict(state='DECODE_PARTITION_RAW_CHECKED', **metadata, width=width, trials=trials,
                part_indices=c['parts'], stage_indices=c['stages'],
                preparation=prep_rows, parts=part_rows, native_activity=activity,
                speedups={k: sum(r[k] for r in a)/sum(r[k] for r in b)
                          for k in ('region', 'preparation', 'admission', 'execution')},
                matched_csr_completion=True, guest_all_words_bitexact_checked=True,
                external_individual_words_dumped=False, independent_protocol_checked=False,
                independent_reference='Original N128 Spike RVV bits exact N64 prefix; separate SDK C-reference bits',
                exact_mixed_elf_spike_executed=False, whole_model=False, continuous_seven_part_run=False)
