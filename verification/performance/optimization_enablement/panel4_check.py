#!/usr/bin/env python3
"""Strict current AUTO ABBA plus bad-capability fallback, distinct from old ABBA."""
from pathlib import Path
import re
import sys

ROOT = Path('/home/wangwy/openproject/ara_dsa')
sys.path[:0] = [str(ROOT/'verification/akv'), str(ROOT/'verification/qbs')]
if (Path(__file__).resolve().parent/'run_qk_panel4_abba.py').is_file():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_qk_panel4_abba as old

MODES = (0, 1, 1, 0, 0)
REQUESTS = ('off', 'auto', 'auto', 'off', 'badcap')
BEGIN = re.compile(r'PANEL4_TRIAL_BEGIN trial=([0-4]) selected=([01]) request=(off|auto|badcap)')
END = re.compile(r'PANEL4_ATTENTION trial=([0-4]) selected=([01]) request=(off|auto|badcap) '
    r'native=1 kv=128 outputs=1536 cycles=([1-9][0-9]*) fcsr=3 vcsr=5 checksum=([0-9a-f]{16}) errors=0')
SUITE = 'PANEL4_AUTO_ABBA_PASS trials=5 outputs_per_trial=1536 bytewise_equal=1 csr_equal=1 guards=1 badcap_fallback=1'


def check_log(text):
    trials, records, group = [], [], []
    active = suite = terminal = False
    severity, summary = set(), None
    for line in text.splitlines():
        old.require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            m = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            old.require(m is not None and m[1] not in severity, 'UVM severity')
            severity.add(m[1])
        if 'Core Test' in line:
            old.require(line == old.TERMINAL and suite and not terminal, 'Core terminal')
            terminal = True
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            raise ValueError('Unexpected QBS work')
        if 'AKV_PERF' in line and not line.startswith('Command:'):
            if line.startswith('[AKV_PERF] '):
                old.require(active and not suite and len(trials) < 5, 'Command outside trial')
                mode = MODES[len(trials)]; schedule = old.commands(mode)
                old.require(len(group) < len(schedule), 'Extra command')
                row = old.numeric_fields(line[len('[AKV_PERF] '):], old.PERF_FIELDS)
                old.check_record(row, schedule[len(group)], mode, len(records)+1)
                records.append(row); group.append(row)
            elif line.startswith('[AKV_PERF_SUMMARY] '):
                old.require(suite and not active and summary is None, 'Summary placement')
                summary = old.numeric_fields(line[len('[AKV_PERF_SUMMARY] '):], old.SUMMARY_FIELDS)
            else:
                raise ValueError('Malformed AKV metric')
        if 'PANEL4_' in line:
            begin, end = BEGIN.fullmatch(line), END.fullmatch(line)
            if begin:
                i = len(trials)
                old.require(not active and not suite and i < 5 and
                    (int(begin[1]), int(begin[2]), begin[3]) == (i, MODES[i], REQUESTS[i]), 'Trial begin/order')
                active, group = True, []
            elif end:
                i = len(trials)
                old.require(active and i < 5 and
                    (int(end[1]), int(end[2]), end[3]) == (i, MODES[i], REQUESTS[i]) and
                    len(group) == len(old.commands(MODES[i])), 'Trial completion')
                t = old.totals(group)
                old.require(t['records'] == (390 if MODES[i] else 774) and
                    t['v2_logical_column'] == 512 and t['v2_row_load'] == 256 and
                    t['v2_column_panel'] == (128 if MODES[i] else 0) and
                    t['v2_k_view_bank_cycles'] == (1024 if MODES[i] else 4096), 'Trial totals')
                trials.append(dict(trial=i, selected=MODES[i], request=REQUESTS[i], cycles=int(end[4]),
                    checksum=end[5], fcsr=3, vcsr=5, derived_hardware_totals=t))
                active = False
            elif line == SUITE:
                old.require(not active and len(trials) == 5 and not suite, 'Suite terminal')
                suite = True
            else:
                raise ValueError('Malformed/unknown PANEL4 marker')
    old.require(not active and suite and terminal and len(records) == 3102 and
        severity == {'UVM_ERROR', 'UVM_FATAL'} and summary == old.totals(records), 'Incomplete final evidence')
    old.require(len({t['checksum'] for t in trials}) == 1, 'Numerical checksum changed')
    traffic = ('ar', 'r_beats', 'q_external_bytes', 'kv_external_bytes', 'replay_bytes',
               'read_ranges', 'read_payload_bytes')
    old.require(all(len({t['derived_hardware_totals'][k] for t in trials}) == 1 for k in traffic), 'Traffic changed')
    off = trials[0]['cycles']+trials[3]['cycles']; auto = trials[1]['cycles']+trials[2]['cycles']
    return dict(state='PASS', trials=trials, summed_cycles_off=off, summed_cycles_auto=auto,
        cycle_reduction_percent=100*(1-auto/off), raw_hardware_summary=summary,
        badcap_fallback=True, rounding='RNE', kv=128, same_elf=True,
        scope='Current single-C SDK AUTO vs explicit0; captured KV128 D128/GQA6 only; not full-model timing')
