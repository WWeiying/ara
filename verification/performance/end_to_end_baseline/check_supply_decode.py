"""Decode successor: same numerical/context contract, explicit reader width.

The sealed legacy checker remains unchanged. The width-dependent accounting
is physical read service; activation/descriptor transfers remain 16 bytes.
"""
import re

from audit import require
from check_decode_native import SCOPE, K, PROFILE, STAGE_PART, ACCESS, CONTEXT_COUNTERS
from check_projection_native import checksum, fields
from collect_projection_native import PHASES, COUNTERS
from diagnose_projection_pair import WAIT
from supply_footprint import plan_range


def read_contract(command, bus_bits, blocks, profile, m):
    require(bus_bits in (128, 256) and blocks > 0 and profile in (1, 2) and m in (1, 4),
            'Unsupported declared read geometry')
    weight_beat = bus_bits // 8
    reused = command['activation_access'] in (2, 3)
    activation = 0 if reused else m * blocks * 292
    weight = 32 * blocks * (144 if profile == 1 else 210)
    expected_ranges = 1 + 8 * blocks + (0 if reused else blocks)
    # The fixed SDK ELFs use 64-byte aligned R4 weights and activation storage.
    # Q4 R4 starts stay 32-byte aligned; Q6 R4 starts cycle through multiples
    # of eight. M1 activation starts cycle through multiples of four; M4 stays
    # 16-byte aligned. Page and AXI burst boundaries are transfer aligned.
    def beats(length, step, phases):
        counts = {sum(b.beats for b in plan_range(0x1fc0 + phase, length,
                  physical_bits=bus_bits, transfer_bytes=step)) for phase in phases}
        require(len(counts) == 1, 'SDK alignment phases do not have a unique beat count')
        return counts.pop()
    weight_beats = beats(4 * (144 if profile == 1 else 210), weight_beat,
                         (0,) if profile == 1 else (0, 8, 16, 24))
    activation_beats = beats(m * 292, 16, (0, 4, 8, 12) if m == 1 else (0,))
    exact_beats = 1 + 8 * blocks * weight_beats + (0 if reused else blocks * activation_beats)
    minimum_beats = 1 + (weight + weight_beat - 1)//weight_beat + (activation + 15)//16
    require(command['weight_bytes'] == weight and command['payload_bytes'] == 16 + weight + activation and
            command['read_ranges'] == expected_ranges and command['ar'] >= expected_ranges and
            minimum_beats <= command['r_beats'] == exact_beats <= command['busy_cycles'],
            'Physical transfer/range/work accounting mismatch')
    return dict(weight_beat_bytes=weight_beat, activation_beat_bytes=16,
                descriptor_beat_bytes=16, minimum_beats=minimum_beats, exact_beats=exact_beats,
                evidence='Exact beat accounting consistent with the pinned role-specific transfer implementation; '
                         'not an independent per-role ARSIZE observation')


def check(text, golden, packed, profiles, flags, bus_bits):
    require(bus_bits in (128, 256), 'Explicit physical bus width required')
    require(tuple(profiles) == PROFILE and len(golden) == len(flags) == 7 and len(packed) == 4 and
            all(len(x) == 512 for x in golden) and list(map(len,packed)) == [2336,2336,7008,2336] and
            all(0 <= f < 32 for f in flags), 'Decode oracle geometry')
    require(text.splitlines().count(SCOPE) == 1 and 'DECODE_NATIVE_FAIL' not in text and
            not re.search(r'Fatal:|Error:|^UVM_(?:ERROR|FATAL)\s+@', text, re.M), 'Simulation/scope failure')
    def rows(tag): return [fields(s, tag) for s in text.splitlines() if s.startswith(tag+' ')]
    prep, parts, total, commands = (rows(t) for t in (
        'DECODE_NATIVE_PREP', 'DECODE_NATIVE_PART', 'DECODE_NATIVE_RESULT', '[QBS_PERF]'))
    require(tuple(map(len, (prep,parts,total,commands))) == (4,7,1,28), 'Incomplete Decode work')
    for stage, row in enumerate(prep):
        before = 8 if stage == 0 else 9
        for flag in flags[:STAGE_PART[stage]]: before |= flag
        expected = dict(stage=stage, k=6144 if stage == 2 else 2048, before_fcsr=before,
                        fcsr=before|1, vcsr=3, vstart=0, checksum=checksum(packed[stage]))
        require(all(row.get(k) == v for k,v in expected.items()) and row['cycles'] > 0,
                'Preparation payload/state')
    fc, activity = 9, []
    for part, row in enumerate(parts):
        fc |= flags[part]
        expected = dict(part=part, profile=profiles[part], k=K[part], context=int(part != 5),
            scope=(1,2,3,1,3,0,0)[part], admitted=0, status=0, fcsr=fc, vcsr=3, vstart=0,
            checksum=checksum(golden[part]), errors=0)
        require(all(row.get(k) == v for k,v in expected.items()) and
                row['execution'] > 0 and row['admission'] > 0, 'Output, context or architectural state mismatch')
        selected = commands[part*4:part*4+4]
        for tile, c in enumerate(selected):
            blocks, access = K[part]//256, ACCESS[part][tile]
            activation = blocks*292
            weight = 32*blocks*(144 if profiles[part] == 1 else 210)
            reused = int(access in (2,3))
            expected = dict(seq=part*4+tile+1, m=1, n=32, vlen=1024, lanes=4, success=1, fault=0,
                validation_fault=0, read_fault=0, useful_pairs=8192*blocks, dot_active_cycles=256*blocks,
                activation_access=access, activation_bytes=activation, weight_bytes=weight,
                payload_bytes=16+weight+(0 if reused else activation), context_fill_count=int(access == 1),
                context_reuse_count=reused, context_reuse_block_count=blocks if reused else 0,
                context_read_bytes=activation if reused else 0, activation_axi_bytes_saved=activation if reused else 0,
                context_validation_fault_count=0)
            require(all(c.get(k) == v for k,v in expected.items()), 'Wrong command service/context work')
            require(all(k in c for k in (*COUNTERS,*WAIT,*CONTEXT_COUNTERS)) and
                    all('phase_'+p+'_cycles' in c for p in PHASES) and
                    sum(c['phase_'+p+'_cycles'] for p in PHASES) == c['busy_cycles'] and
                    sum(c[k] for k in WAIT) == c['weight_prefetch_wait_cycles'] and
                    c['dot_active_cycles'] <= c['busy_cycles'] and c['ar'] > 0,
                    'Counter domain/partition mismatch')
            read_contract(c, bus_bits, blocks, profiles[part], 1)
        count = {k:sum(c[k] for c in selected) for k in (*COUNTERS,*WAIT,*CONTEXT_COUNTERS)}
        require(count['busy_cycles'] <= row['execution'], 'QBS busy outside SDK execution')
        axi_activation = count['payload_bytes']-count['weight_bytes']-16*len(selected)
        require(axi_activation == count['activation_bytes']-count['activation_axi_bytes_saved'], 'Reader payload identity')
        activity.append(dict(part=part, counters=count, activation_axi_payload_bytes=axi_activation,
            phases={p:sum(c['phase_'+p+'_cycles'] for c in selected) for p in PHASES},
            sdk_outside_qbs_busy_cycles=row['execution']-count['busy_cycles'],
            weight_bytes_per_busy_cycle=count['weight_bytes']/count['busy_cycles'],
            r_beats_per_busy_cycle=count['r_beats']/count['busy_cycles']))
    result = total[0]
    require(result['commands'] == 28 and result['outputs'] == 896 and result['errors'] == 0 and
            result['preparation'] == sum(r['cycles'] for r in prep) and
            result['admission'] == sum(r['admission'] for r in parts) and
            result['execution'] == sum(r['execution'] for r in parts) and
            result['region'] >= sum(result[k] for k in ('preparation','admission','execution')), 'SDK region accounting')
    return dict(preparation=prep, parts=parts, total=result, activity=activity, commands=28, outputs=896,
                useful_pairs=sum(c['useful_pairs'] for c in commands),
                qbs_busy_cycles=sum(c['busy_cycles'] for c in commands),
                dot_issue_count=sum(c['dot_active_cycles'] for c in commands),
                preparation_included=True, existing_context_reuse=True, cold_weight_repack_included=False,
                full_k=True, full_n=False, full_ggml=False, whole_model=False, single_reset_trial=True)
