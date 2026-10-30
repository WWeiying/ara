"""PMA failure after Q writes, foreign context preservation and owner recovery."""
import csv
from pathlib import Path
import re
from run_handoff import log_checker
from shared_wave import profile as original_profile, VLSU

ORDER = [('qbs', 1), ('akv', 4), ('qbs', 2), ('akv', 4)] + [('akv', 2)] * 8 + [('qbs', 3), ('akv', 3)]
BEGIN = 'READER_FAULT_BEGIN qbs=3 akv=11 fault_owner=akv qbs_context=1 fault_q_rows=8'
PASS = 'READER_FAULT_PASS qbs=3 akv=11 traps=1 cause=5 tval=0 rows=8 qbs_words=96'


def profile(shared):
    result = original_profile()
    # The baseline has two real readers. Use the AKV reader as this fixture's
    # fault-path observation, without claiming physical sharing for that image.
    if not shared:
        for signal in result['signals']:
            signal['path'] = signal['path'].replace('/i_shared_reader/i_read_engine/',
                                                    '/i_akv_engine/i_read_engine/')
        result['signals'] = [s for s in result['signals'] if s['alias'] != 'reader_clk_en']
    result['signals'].append(dict(alias='akv_q_write_valid',
        path='/' + (VLSU + '.i_akv_engine.v1_context_write_valid').replace('.', '/'),
        format='h', required=True))
    result['topology'] = 'Shared or baseline AKV fault observation; reader routing is not checked here'
    return result


def script(shared):
    paths = ['ara_tb.clk'] + [s['path'][1:].replace('/', '.') for s in profile(shared)['signals']]
    return '\n'.join(['dump -file reader.fsdb -type FSDB',
        *('dump -add {' + p + '}' for p in paths), 'run 500000ns', 'dump -close', 'run']) + '\n'


def check_log(text, rtl):
    require = log_checker.require
    records, markers, counts, severity = [], [], dict(qbs=0, akv=0), set()
    terminal = False
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT|SKIP)\b', line, re.I), 'Failure in fault fixture')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(match and match[1] not in severity, 'Protocol error or duplicate summary')
            severity.add(match[1])
        if 'READER_FAULT_' in line:
            require(not terminal, 'Late fixture marker')
            markers.append(line)
        if line.startswith(('[QBS_PERF] ', '[AKV_PERF] ')):
            require(markers == [BEGIN] and len(records) < 14 and not terminal, 'Unexpected command')
            owner = 'qbs' if line.startswith('[QBS_PERF] ') else 'akv'
            require(owner == ORDER[len(records)][0], 'Wrong owner order')
            row = log_checker.numeric_fields(line.split('] ', 1)[1],
                log_checker.schema(rtl) if owner == 'qbs' else log_checker.PERF_FIELDS)
            counts[owner] += 1
            fault = owner == 'akv' and counts['akv'] == 1
            require(row['seq'] == counts[owner] and row['success'] == 1-int(fault) and
                    row['fault'] == int(fault) and row['validation_fault'] == 0 and
                    row['read_fault'] == (5 if fault else 0) and row['read_outstanding_max'] <= 2,
                    'Command fault/result mismatch')
            if owner == 'qbs':
                access = ORDER[len(records)][1]
                require((row['m'], row['n'], row['vlen'], row['lanes']) == (1,3,1024,4) and
                        row['activation_access'] == access and row['commit_groups'] == 4 and
                        row['useful_pairs'] == 768 and row['weight_bytes'] == 432,
                        'QBS output work mismatch')
                reuse = int(access in (2, 3))
                require(row['context_fill_count'] == int(access == 1) and
                        row['context_reuse_count'] == reuse and row['context_read_bytes'] == 292*reuse and
                        row['activation_axi_bytes_saved'] == 292*reuse, 'QBS context not reused')
            else:
                command = ORDER[len(records)][1]
                require(row['command'] == command, 'Wrong AKV operation')
                if command in (2, 3):
                    require(row['ar'] == row['r_beats'] == row['read_ranges'] == 0, 'Local command read RAM')
                elif not fault:
                    require(row['q_external_bytes'] == 256 and row['kv_external_bytes'] == 768 and
                            row['read_payload_bytes'] == 1088, 'AKV retry traffic mismatch')
            records.append(row)
        if 'Core Test' in line:
            require(line == log_checker.TERMINAL and markers == [BEGIN, PASS] and
                    len(records) == 14 and not terminal, 'Incomplete core result')
            terminal = True
    require(terminal and markers == [BEGIN, PASS] and counts == dict(qbs=3,akv=11) and
            severity == {'UVM_ERROR','UVM_FATAL'}, 'Incomplete fault fixture')
    return dict(state='READER_FAULT_LOG_CHECKED', commands=14, hardware_records=records,
                qbs=3, akv=11, traps=1, qbs_words=96, resident_rows_self_checked=8)


def check_cycles(path, shared):
    required = {s['alias'] for s in profile(shared)['signals']}
    fires, terminals, pending, checkpoint = 0, 0, None, None
    q_writes = faults = resident_samples = 0
    previous = -1
    started = after_terminal = False
    counts = dict(qbs=0, akv=0)
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        log_checker.require(required <= set(reader.fieldnames or ()), 'Incomplete fault wave')
        for row in reader:
            def v(name):
                value = row[name].strip()
                log_checker.require(re.fullmatch('[0-9a-fA-F]+', value), 'Unknown fault control ' + name)
                return int(value,16)
            def require(cond, text):
                log_checker.require(cond, text)
            time = int(row['time_100fs'])
            require(time > previous and (not started or time-previous == 10000), 'Missing fault sample')
            previous = time
            if not v('reset_n'):
                require(not started, 'Reset hides fault recovery')
                continue
            owners = [o for o in counts if v(o+'_active_q')]
            accept = [o for o in counts if v(o+'_command_fire')]
            require(len(owners) <= 1 and len(accept) <= 1, 'Overlapping owners')
            if after_terminal:
                require(not owners, 'Owner failed to leave')
                after_terminal = False
            elif pending:
                require(owners == [pending], 'Owner changed before completion')
            else:
                require(not owners, 'Owner without acceptance')
            valid = v('activation_context_valid_q')
            identity = (valid,) if not valid else (valid, *(v('activation_context_'+f) for f in
                ('id_q','generation_q','profile_q','layout_q','m_q','k_blocks_q')))
            if checkpoint is not None and owners != ['qbs']:
                require(identity == checkpoint, 'AKV fault changed resident QBS identity')
                resident_samples += int(bool(owners) and bool(checkpoint[0]))
            if accept:
                owner = accept[0]
                require(not owners and pending is None and fires < 14 and ORDER[fires][0] == owner and
                        v('normal_vlsu_idle') and not v('akv_context_write_busy'), 'Unsafe fault recovery admission')
                for channel in ('ar','r','aw','w','b'):
                    for slot in ('a_full_q','b_full_q'):
                        require(not v('cut_'+channel+'_'+slot), 'AXI cut survived recovery')
                fires += 1
                counts[owner] += 1
                pending, started = owner, True
            if owners == ['akv'] and counts['akv'] == 1:
                q_writes += v('akv_q_write_valid')
                if v('reader_fault_valid_o'):
                    require(v('reader_fault_kind_o') == 5 and v('reader_fault_vaddr_o') == 0 and
                            not v('reader_burst_fifo_count_q') and not v('reader_ar_stalled_q'),
                            'Wrong or undrained AKV read fault')
                    faults += int(bool(v('reader_fault_ready_i')))
            ending = [o for o in counts if v(o+'_terminal')]
            if ending:
                require(ending == owners == [pending], 'Unmatched fault terminal')
                owner = ending[0]
                fault = owner == 'akv' and counts['akv'] == 1
                require(v(owner+'_fault_valid') == int(fault), 'Wrong fault terminal')
                if shared or owner == 'akv':
                    require(not v('reader_busy_o') and not v('reader_ar_stalled_q') and
                            not v('reader_response_drain_q'), 'Reader released before drain')
                if owner == 'qbs':
                    checkpoint = identity
                terminals += 1
                pending, after_terminal = None, True
    log_checker.require(fires == terminals == 14 and pending is None and not after_terminal and
                        counts == dict(qbs=3,akv=11) and faults == 1 and q_writes > 0 and resident_samples > 0,
                        'Missing commands, partial Q write or fault/context recovery evidence')
    return dict(state='READER_FAULT_WAVE_CHECKED', commands=14, faults=1,
                q_write_samples_before_fault=q_writes, foreign_context_samples=resident_samples,
                shared_image=shared, sampling='Settled negedge', stalled_ar_fault=False)
