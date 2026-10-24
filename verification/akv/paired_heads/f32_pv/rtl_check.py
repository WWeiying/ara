"""Strict actual-log PV numerical and command checks; not a simulator launcher."""
import importlib.util
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent))
from attention_run import (require, read_json, digest, hashes, merge_pins, verify_pins,
    totals, numeric_fields, PERF_FIELDS, SUMMARY_FIELDS, TERMINAL)

spec = importlib.util.spec_from_file_location('f32_parent_rtl_check', HERE.parent/'rtl_check.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
SHAPES = [dict(id=0, head=0, d=64, tokens=1), dict(id=1, head=1, d=96, tokens=63),
          dict(id=2, head=1, d=128, tokens=64)]
EXPECTED = dict(pairs=3, runs=6, outputs=1152, commands=396, v2_full=6,
    v2_row_load=384, release=6, q_external_bytes=2304, kv_external_bytes=147456,
    read_ranges=786, read_payload_bytes=150144, replay_bytes=85824)
CAP = 'F32_PV_CAP native=1 vlenb=128 pairs=3 resident=64'
SUITE = 'F32_PV_SUITE_PASS pairs=3 runs=6 outputs=1152 commands=396'


def work(case, mode):
    return [4] + [2]*(case['tokens']*(1 if mode else 2)) + [3]


def begin(case, mode):
    return f"F32_PV_BEGIN case={case['id']} mode={mode} d={case['d']} tokens={case['tokens']} stride={4*case['d']}"


def end(case, mode, golden):
    d, i = case['d'], case['id']
    return (f"F32_PV_RESULT case={i} mode={mode} outputs={2*d} tailbytes={1024-8*d} compared=1024 "
        f"hash={prior.fnv(golden[i*1024:(i+1)*1024]):08x} fcsr={case['fcsr']} vcsr=5 guardbytes=1024 inputbytes=35072 errors=0")


def check_log(text, cases, golden):
    require(len(golden) == 3072 and len(cases) == 3 and
        [{k: c[k] for k in SHAPES[0]} for c in cases] == SHAPES and
        all(type(c['fcsr']) is int and 0 <= c['fcsr'] <= 31 and c['fcsr'] & 8 for c in cases), 'Oracle geometry/status')
    for c in cases:
        require(golden[c['id']*1024+8*c['d']:(c['id']+1)*1024] == b'\xa5'*(1024-8*c['d']), 'Oracle tail poison')
    records, group, runs = [], [], []
    cap = active = suite = terminal = False
    summary, severity = None, set()
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Simulator failure')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            m = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(m is not None and m[1] not in severity, 'UVM error/duplicate')
            severity.add(m[1])
        if 'Core Test' in line:
            require(line == TERMINAL and suite and not terminal, 'Core terminal missing/duplicate/malformed')
            terminal = True
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            raise ValueError('Unexpected QBS work')
        if 'AKV_PERF' in line and not line.startswith('Command:'):
            if line.startswith('[AKV_PERF] '):
                require(active, 'Command outside run')
                case, mode = cases[len(runs)//2], len(runs) % 2
                sequence = work(case, mode)
                require(len(group) < len(sequence), 'Extra command')
                row = numeric_fields(line[len('[AKV_PERF] '):], PERF_FIELDS)
                want = prior.expected_record(case, mode, sequence[len(group)], len(records)+1)
                require(all(row[k] == v for k, v in want.items()) and row['translations'] == 0, 'Command work/fault/order')
                require(row['id'] < 8 and row['busy_cycles'] > 0 and row['read_outstanding_max'] <= 2, 'ID/cycles/outstanding')
                if row['command'] == 4:
                    require(row['ar'] >= 131 and row['r_beats'] >= row['ar'] and row['read_outstanding_max'] > 0, 'FULL traffic missing')
                else:
                    require(all(row[k] == 0 for k in ('ar', 'r_beats', 'read_outstanding_max',
                        'read_outstanding_occ_sum', 'read_outstanding_full_cycles')), 'Unexpected local read traffic')
                group.append(row)
                records.append(row)
            elif line.startswith('[AKV_PERF_SUMMARY] '):
                require(suite and not active and summary is None, 'Premature/duplicate summary')
                summary = numeric_fields(line[len('[AKV_PERF_SUMMARY] '):], SUMMARY_FIELDS)
            else:
                raise ValueError('Unknown/malformed AKV metric prefix')
        if 'F32_PV_' in line:
            if line == CAP:
                require(not cap and not active and not runs, 'Duplicate/misplaced cap')
                cap = True
            elif line.startswith('F32_PV_BEGIN '):
                require(cap and not active and not suite and len(runs) < 6, 'BEGIN order')
                require(line == begin(cases[len(runs)//2], len(runs) % 2), 'BEGIN shape/mode')
                active, group = True, []
            elif line.startswith('F32_PV_RESULT '):
                require(active, 'RESULT outside run')
                case, mode = cases[len(runs)//2], len(runs) % 2
                require(line == end(case, mode, golden) and len(group) == len(work(case, mode)), 'Numeric/oracle/command mismatch')
                runs.append(dict(case=case['id'], mode=mode, fcsr=case['fcsr'],
                    output_hash=f"{prior.fnv(golden[case['id']*1024:(case['id']+1)*1024]):08x}", hardware_totals=totals(group)))
                active = False
            elif line == SUITE:
                require(cap and not active and len(runs) == 6 and not suite, 'Premature/duplicate suite')
                suite = True
            else:
                raise ValueError('Unknown/malformed numeric prefix')
    require(cap and suite and terminal and not active and len(records) == 396 and
        severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete actual evidence')
    total = totals(records)
    require(summary == total, 'Raw summary differs from sum/max')
    require(all(total[k] == v for k, v in EXPECTED.items() if k in total), 'Aggregate work mismatch')
    return dict(state='PASS', runs=runs, hardware_totals=total,
        scope='Derived real-data F32 PV leaf only; independent host oracle plus generic/paired exact on-chip comparisons; no Attention/performance/odd-caller acceptance')


def check_pins(build):
    report = read_json(build/'build.json')
    require(report.get('state') == 'BUILT_NOT_EXECUTED' and report.get('execution') == 'NOT_RUN' and
            report.get('expected') == EXPECTED and report.get('post_pins_match') is True, 'Invalid build receipt')
    require(digest(build/'source-pins.json') == report['source_pins_sha256'], 'Source receipt drift')
    pins = read_json(build/'source-pins.json')
    merge_pins(pins, report['artifact_sha256'])
    require(pins.get(report['elf']) == report['elf_sha256'] == digest(report['elf']), 'ELF identity')
    verify_pins(pins)
    return report
