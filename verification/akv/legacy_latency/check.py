"""Strict monitor transcript and exact per-command paired comparison."""
import re

SUITE = ('AKV engine PASS: v1 D64/D128 plus v2 D64/D96/D128 and segmented D256 '
         'row/column views, tails, counters, validation, and faults')
COUNTERS = ('command_cycles full_count refill_count load_count release_count v2_full_count '
    'v2_refill_count v2_row_load_count v2_column_load_count v2_column_panel_count '
    'v2_logical_column_count v2_k_view_bank_cycles v2_bank_conflict_cycles v2_rejected_count '
    'q_external_bytes kv_external_bytes replay_bytes replay_backpressure_cycles read_range_count '
    'read_translation_count read_ar_count read_beat_count read_payload_bytes read_store_wait_cycles '
    'read_backpressure_cycles read_outstanding_occupancy_sum read_outstanding_max '
    'read_outstanding_full_cycles aggregate_write_count early_ack_count busy').split()
META = ('seq command id vd dim descriptor tile selector columns translation accept first fire '
        'first_latency fire_latency wait_cycles success fault context_ready validation validation_error '
        'read_fault_kind fault_vaddr mmu_valid mmu_cause mmu_tval').split()
HEX = {'descriptor', 'tile', 'selector', 'fault_vaddr', 'mmu_cause', 'mmu_tval'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(line, prefix, names):
    require(line.startswith(prefix+' '), 'Malformed monitor prefix')
    tokens = line[len(prefix)+1:].split(' ')
    require(len(tokens) == len(names), 'Missing/extra monitor fields')
    result = {}
    for token, name in zip(tokens, names):
        parts = token.split('=')
        require(len(parts) == 2 and parts[0] == name, 'Monitor field schema/order')
        value = parts[1]
        require(re.fullmatch('[0-9a-f]{16}' if name in HEX else '[0-9]+', value) is not None,
                'Invalid/unknown monitor value')
        result[name] = int(value, 16 if name in HEX else 10)
    return result


def check_log(text, exit_code):
    require(type(exit_code) is int and exit_code == 0, 'Nonzero simulator exit')
    rows, started, suite, summary = [], False, False, None
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error(?:-|:)|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if line == SUITE:
            require(started and not suite and summary is None, 'Duplicate/misordered original suite PASS')
            suite = True
        if 'AKV_LATENCY_' not in line:
            continue
        if line == 'AKV_LATENCY_BEGIN version=1':
            require(not started and not rows and not suite, 'Duplicate monitor BEGIN')
            started = True
        elif line.startswith('AKV_LATENCY_COMMAND '):
            require(started and not suite and summary is None, 'Command outside suite')
            row = fields(line, 'AKV_LATENCY_COMMAND', META+COUNTERS)
            require(row['seq'] == len(rows)+1 and 0 <= row['command'] <= 6 and row['id'] < 16 and
                    row['vd'] < 32 and row['columns'] < 8 and row['dim'] < 65536, 'Command identity/shape')
            require(0 < row['accept'] < row['first'] <= row['fire'] < 2**64 and
                    row['first_latency'] == row['first']-row['accept'] and
                    row['fire_latency'] == row['fire']-row['accept'] and
                    row['wait_cycles'] == row['fire']-row['first'], 'Latency arithmetic')
            require(not rows or row['accept'] > rows[-1]['fire'], 'Overlapping command records')
            require(all(row[k] in (0,1) for k in ('success','fault','context_ready','validation',
                                                   'translation','mmu_valid','busy')) and
                    row['success']+row['fault'] == 1 and row['busy'] == 1, 'Terminal handshake')
            require(all(row[k] < 2**32 for k in COUNTERS) and row['command_cycles'] > 0 and
                    row['read_outstanding_max'] <= 2, 'Counter bounds')
            if row['success']:
                require(all(row[k] == 0 for k in ('validation','validation_error','read_fault_kind',
                                                 'fault_vaddr','mmu_valid','mmu_cause','mmu_tval')),
                        'Success contains unqualified fault metadata')
            elif row['validation']:
                require(row['validation_error'] > 0 and row['read_fault_kind'] == 0, 'Validation fault metadata')
            else:
                require(row['validation_error'] == 0 and row['read_fault_kind'] > 0, 'Read fault metadata')
            if row['read_fault_kind'] != 2:  # QBS_READ_FAULT_MMU in the pinned ABI.
                require(row['mmu_valid'] == row['mmu_cause'] == row['mmu_tval'] == 0, 'Inactive MMU metadata')
            rows.append(row)
        elif line.startswith('AKV_LATENCY_SUMMARY '):
            require(suite and summary is None, 'Early/duplicate summary')
            summary = fields(line, 'AKV_LATENCY_SUMMARY', ['version','accepted','completed','pending','errors'])
        else:
            raise ValueError('Unknown/malformed monitor record')
    require(started and suite and rows and summary == dict(version=1, accepted=len(rows),
            completed=len(rows), pending=0, errors=0), 'Incomplete observation ledger')
    for dim in (64,128):
        for command in (0,2):
            require(any(r['success'] and r['command'] == command and r['dim'] == dim for r in rows),
                    'Missing legacy FULL/LOAD shape')
    require(any(r['success'] and r['command'] == 1 for r in rows) and
            any(r['success'] and r['command'] == 3 for r in rows) and
            any(r['validation'] for r in rows) and
            {2,3,5} <= {r['read_fault_kind'] for r in rows if r['fault']}, 'Missing legacy lifecycle/fault coverage')
    return dict(state='FUNCTIONAL_OBSERVATION_PASS', commands=len(rows), rows=rows, summary=summary)


def compare(old, new):
    require(old['commands'] == new['commands'] and bool(old['rows']), 'Different command counts')
    deltas = []
    ignored = {'accept', 'first', 'fire'}
    for before, after in zip(old['rows'], new['rows']):
        require(set(before) == set(after) == set(META+COUNTERS), 'Paired schema drift')
        differences = {k:dict(baseline=before[k], candidate=after[k])
                       for k in before if k not in ignored and before[k] != after[k]}
        if differences:
            deltas.append(dict(seq=before['seq'], fields=differences))
    return dict(state='PASS' if not deltas else 'REGRESSION', exact_per_command=not deltas,
                commands=old['commands'], differences=deltas, baseline=old, candidate=new,
                scope='Original full AKV unit suite, private reader/storage versus composed shared reader/unified storage',
                soc_verified=False, model_performance=False, ppa_measured=False, production_promoted=False)
