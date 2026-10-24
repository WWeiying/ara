"""Check the 71-command fixture using one physical reader's actual wave state."""
import csv
from pathlib import Path
import re
from shared_wave import profile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command_order():
    result = [('akv', 4)] + [('akv', 2)] * 8
    for stage in range(6):
        result += [('qbs', stage), ('akv', 2)]
        if stage == 3:
            result += [('akv', 4)]
        result += [('akv', 2)] * 8
    return result + [('akv', 3)]


def check_cycles(path):
    required = {s['alias'] for s in profile()['signals']}
    counts = dict(qbs=0, akv=0)
    resident = dict(qbs=0, akv=0)
    contexts, fires, terminals, faults = {}, [], [], []
    pending = None
    after_terminal = started = False
    previous = -1
    rows = zero_read_commands = range_fires = ar_fires = 0
    order = command_order()
    with Path(path).open(newline='') as handle:
        reader = csv.DictReader(handle)
        require(required <= set(reader.fieldnames or ()), 'Incomplete shared-reader profile')
        for row in reader:
            rows += 1

            def value(alias):
                text = row[alias].strip()
                require(re.fullmatch('[0-9a-fA-F]+', text) is not None, 'Unknown control: ' + alias)
                return int(text, 16)

            def r(field):
                return value('reader_' + field)

            def identity(client):
                prefix = 'akv_context_' if client == 'akv' else 'activation_context_'
                flag = value(prefix + ('ready_q' if client == 'akv' else 'valid_q'))
                require(flag in (0, 1), 'Invalid context validity')
                fields = (('q_rows_q', 'head_dim_q', 'kv_length_q', 'q_base_q', 'k_base_q',
                           'v_base_q', 'tile_count_q', 'v2_q') if client == 'akv' else
                          ('id_q', 'generation_q', 'profile_q', 'layout_q', 'm_q', 'k_blocks_q'))
                return (0,) if not flag else (1, *(value(prefix + f) for f in fields))

            timestamp = int(row['time_100fs'])
            require(timestamp > previous, 'Nonmonotonic samples')
            if started:
                require(timestamp - previous == 10000, 'Missing settled half-cycle sample')
            previous = timestamp
            if value('reset_n') == 0:
                require(not started, 'Reset interrupts handoff proof')
                continue
            require(value('reset_n') == 1, 'Invalid reset')
            owners = [o for o in counts if value(o + '_active_q')]
            accepted = [o for o in counts if value(o + '_command_fire')]
            require(len(owners) <= 1 and len(accepted) <= 1, 'Nonexclusive ownership/acceptance')
            if after_terminal:
                require(not owners, 'Owner not released after terminal')
                after_terminal = False
            elif pending is not None:
                require(owners == [pending], 'Owner disappeared or switched early')
            else:
                require(not owners, 'Owner lacks acceptance')
            require(r('counters_clear_i') == int(bool(accepted)), 'Counter reset missed acceptance')
            require(r('range_fifo_count_q') <= 2 and r('burst_fifo_count_q') <= 2,
                    'Outstanding capacity changed')
            if owners or accepted or r('busy_o'):
                require(value('reader_clk_en') == 1, 'Shared reader clock disabled while needed')
            if not owners:
                for field in ('range_fifo_count_q', 'burst_fifo_count_q', 'plan_state_q',
                        'ar_stalled_q', 'response_drain_q', 'completion_valid_q', 'fault_pending_q',
                        'fault_valid_o', 'busy_o', 'mmu_req_o', 'axi_ar_valid_o', 'axi_r_valid_i',
                        'physical_check_valid_o', 'range_valid_i', 'data_valid_o',
                        'data_ready_i', 'completion_ready_i', 'fault_ready_i'):
                    require(r(field) == 0, 'Reader activity without owner: ' + field)
            for client, checkpoint in contexts.items():
                if owners != [client]:
                    require(identity(client) == checkpoint, 'Foreign owner changed resident identity')
                    if owners and checkpoint[0]:
                        resident[client] += 1
            for owner in counts:
                active = owners == [owner]
                endpoint = lambda f: value(owner + '_read_' + f)
                # Observe actual engine wires; do not fabricate two readers.
                for local, physical in (('range_ready', 'range_ready_o'),
                        ('data_valid', 'data_valid_o'), ('completion_valid', 'completion_valid_q'),
                        ('fault_valid', 'fault_valid_o')):
                    require(endpoint(local) == (r(physical) if active else 0), 'Response routing: ' + local)
                require(value(owner + '_read_busy') == (r('busy_o') if active else 0), 'Busy routing')
                if not active:
                    for f in ('data', 'data_strb', 'data_offset', 'data_tag', 'completion_tag',
                              'fault_kind', 'fault_vaddr', 'fault_tag'):
                        require(endpoint(f) == 0, 'Inactive endpoint received payload: ' + f)
                else:
                    require(endpoint('range_valid') == r('range_valid_i'), 'Request-valid routing')
                    if r('range_valid_i'):
                        for f in ('tag', 'vaddr', 'bytes'):
                            require(endpoint('range_' + f) == r('range_' + f + '_i'), 'Range routing: ' + f)
                    for valid, pairs in (
                        ('data_valid_o', ('data', 'data_strb', 'data_offset', 'data_tag')),
                        ('completion_valid_q', ('completion_tag',)),
                        ('fault_valid_o', ('fault_kind', 'fault_vaddr', 'fault_tag'))):
                        if r(valid):
                            for f in pairs:
                                require(endpoint(f) == r(f + '_o'), 'Return payload routing: ' + f)
                    for local, physical in (('data_ready', 'data_ready_i'),
                            ('completion_ready', 'completion_ready_i'), ('fault_ready', 'fault_ready_i')):
                        require(endpoint(local) == r(physical), 'Backpressure routing: ' + local)
            if accepted:
                owner = accepted[0]
                require(not owners and pending is None and value('normal_vlsu_idle') == 1 and
                        value('prepare_inflight') == 0 and value('ar_hold_empty') == 1,
                        'Unsafe acquisition')
                for field in ('range_fifo_count_q', 'burst_fifo_count_q', 'plan_state_q',
                        'ar_stalled_q', 'response_drain_q', 'completion_valid_q', 'fault_pending_q',
                        'busy_o', 'mmu_req_o', 'axi_ar_valid_o'):
                    require(r(field) == 0, 'Undrained reader at acquisition: ' + field)
                require(value('akv_context_write_busy') == 0, 'Pending context write at acquisition')
                for channel in ('ar', 'r', 'aw', 'w', 'b'):
                    for slot in ('a_full_q', 'b_full_q'):
                        require(value('cut_' + channel + '_' + slot) == 0, 'Undrained AXI cut')
                require(len(fires) < len(order) and order[len(fires)][0] == owner, 'Wrong command order')
                fires.append(dict(owner=owner, time_100fs=timestamp))
                counts[owner] += 1
                pending, started = owner, True
                range_fires = ar_fires = 0
            range_fires += int(bool(r('range_valid_i') and r('range_ready_o')))
            ar_fires += int(bool(r('axi_ar_valid_o') and r('axi_ar_ready_i')))
            if r('fault_valid_o'):
                require(owners == ['qbs'] and counts['qbs'] == 2 and r('fault_kind_o') == 5 and
                        r('fault_vaddr_o') == 0 and r('burst_fifo_count_q') == 0 and
                        r('ar_stalled_q') == 0, 'Unexpected or premature read fault')
                if r('fault_ready_i'):
                    faults.append(timestamp)
                    require(len(faults) == 1, 'Repeated read fault handshake')
            ending = [o for o in counts if value(o + '_terminal')]
            if ending:
                require(len(ending) == 1 and owners == ending == [pending], 'Unmatched terminal')
                owner = ending[0]
                require(not r('busy_o') and not r('ar_stalled_q') and not r('response_drain_q'),
                        'Premature reader release')
                expected_fault = owner == 'qbs' and counts['qbs'] == 2
                require(value(owner + '_fault_valid') == int(expected_fault), 'Wrong fault ordinal')
                if expected_fault:
                    require(len(faults) == 1, 'Fault terminal without read fault')
                if order[len(terminals)][0] == 'akv' and order[len(terminals)][1] in (2, 3):
                    require(range_fires == ar_fires == 0, 'Resident command inherited external reads')
                    zero_read_commands += 1
                contexts[owner] = identity(owner)
                terminals.append(dict(owner=owner, time_100fs=timestamp))
                pending, after_terminal = None, True
    require(counts == dict(qbs=6, akv=65) and len(terminals) == 71 and pending is None and
            not after_terminal and len(faults) == 1 and zero_read_commands == 63 and
            all(v > 0 for v in resident.values()), 'Incomplete shared-reader handoff window')
    return dict(state='SHARED_READER_HANDOFF_WAVE_CHECKED', samples=rows, fires=fires,
                terminals=terminals, reader_fault_handshakes=faults, resident_samples=resident,
                zero_read_commands=zero_read_commands, physical_readers_observed=1,
                sampling='Settled negedge snapshots, not pre-NBA equivalence',
                stalled_ar_fault_in_soc=False, ppa_measured=False)
