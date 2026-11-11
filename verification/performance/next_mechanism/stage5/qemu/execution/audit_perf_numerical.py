#!/usr/bin/env python3
"""Preserve BUILD07 real perf numerical evidence separately from its failed gate."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RUN_SHA = '2ba39edd9dcf9b62b9a136aa87929b654d4721df814bd1e4b20f0a4e43af5118'
if hashlib.sha256((HERE / 'run_v3.py').read_bytes()).hexdigest() != RUN_SHA:
    raise ValueError('Frozen execution reader drift')
spec = importlib.util.spec_from_file_location('perf_audit_frozen_execution', HERE / 'run_v3.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
c, require, sha = v.c, v.require, v.sha
ORIGIN = v.OUT / 'stage5_qemu_execution_20261110_02'
ORIGIN_SHA = 'e0330acc921dd503a2586b80e89accdf9e21c56dd5e88833391ba3828be26135'
SOURCE_PINS = '324c2e3e6aee456fa49a765230398d22f5d061236f6adac5e5a62c274706b04c'


def audit(output):
    output = Path(output).absolute()
    require(output == output.resolve() and output.parent == v.OUT and
            output.name.startswith('stage5_qemu_perf_numerical_audit_') and not output.exists(), 'Fresh owned audit required')
    output.mkdir()
    g = v.shared()
    report = dict(state='FAIL', guest_reexecuted=False, original_failure_relabelled=False,
                  architecture_gate_pass=False, performance_acceptance=False, rtl_timing=False)
    try:
        require(sha(ORIGIN / 'result.json') == ORIGIN_SHA and sha(ORIGIN / 'source-pins.json') == SOURCE_PINS,
                'Original first-failure evidence changed')
        original, selection = v.read(ORIGIN / 'result.json'), v.read(ORIGIN / 'selection.json')
        require(original['state'] == 'FAIL' and [x['kind'] for x in original['gates']] == ['qbs'] and
                {x.name for x in (ORIGIN / 'work').iterdir()} == {'qbs', 'perf'}, 'Unexpected original execution scope')
        require(g.files(ORIGIN, exclude=('result.json', 'status.json', 'service.stdout.log', 'service.stderr.log')) ==
                original['artifacts'], 'Original artifact membership/hash differs')
        work = ORIGIN / 'work/perf'
        guest, failed = v.read(work / 'guest.command.json'), v.read(work / 'checked.command.json')
        for row, key, log, seconds, rc in ((guest, 'guest', 'guest.log', 300, 0),
                                          (failed, 'checker', 'checked.json', 120, 1)):
            require(row['argv'] == selection['commands'][1][key] and row['cwd'] == str(work) and
                    row['timeout_seconds'] == seconds and row['state'] == 'EXITED' and row['returncode'] == rc and
                    row['pid'] > 1 and row['ended_ns'] > row['started_ns'] and row['log_sha256'] == sha(work / log),
                    'Actual command receipt differs')
        require(guest['ended_ns'] <= failed['started_ns'] and
                guest['argv'][0] == str(v.BUILD / 'qemu-system-riscv64') and
                selection['qemu']['build_sha256'] == v.BUILD_SHA and
                sha(guest['argv'][0]) == selection['qemu']['executable_sha256'] == v.BINARY_SHA,
                'Different image or command order')
        owner = v.read(ORIGIN / 'owner.json')
        require(original['service_owner'] == owner and owner['main_pid'] == owner['owner_pid'] and
                v.read(ORIGIN / 'attempt.json') == dict(review_sha256=SOURCE_PINS, **owner), 'Owner/attempt differs')
        path, build, frozen, fixture = c.stage4('perf')
        text = (work / 'guest.log').read_text()
        numerical = frozen.numerical(text, fixture, (path / 'data.bin').read_bytes())
        numerical.pop('timing')
        calls, groups, outputs = [], {}, [[] for _ in fixture['trials']]
        for line in text.splitlines():
            if not line.startswith('FEATURE_'):
                continue
            tag, payload = line[len('FEATURE_'):].split(' ', 1)
            row = frozen.parse(payload, frozen.SCHEMAS[tag].split(),
                               ('q', 'k', 'v', 'out', 'bits', 'query_hash', 'guard_hash', 'hash'))
            if tag == 'CALL':
                calls.append({k: row[k] for k in ('trial', 'case', 'requested', 'frm', 'initial', 'fcsr', 'vcsr', 'vstart', 'groups', 'errors')})
            elif tag == 'OUT':
                outputs[row['trial']].append(row['bits'])
            elif tag == 'GROUP':
                groups[row['trial'], row['group']] = row
        pairs = []
        for a, b in ((0, 2), (3, 1)):
            require(outputs[a] == outputs[b] and calls[a]['initial'] == calls[b]['initial'] and
                    calls[a]['fcsr'] == calls[b]['fcsr'], 'OFF/ON same-initial flags/outputs differ')
            pairs.append(dict(off=a, on=b, initial=calls[a]['initial'], fcsr=calls[a]['fcsr'], bitexact=True))
        bound = c.binding('perf', build)
        events, cancelled = c.trace_events((work / 'trace.log').read_text(), set(bound['points']))
        names = {row['pc']: name for name, row in bound['entries'].items()}
        ledger, trial = [], -1
        for tag, row in events:
            if tag == 'exec' and row['pc'] in names:
                name = names[row['pc']]
                if name == 'feature_full_call':
                    trial += 1
                    entries, info, ops = Counter(), Counter(), Counter()
                    completed, memory_reads = 0, 0
                elif name == 'feature_terminal_marker':
                    expected_entries = frozen.expected_entries(fixture, fixture['trials'][trial])
                    expected_ops = c.schedule(fixture, trial, groups, frozen)
                    expected_codes = Counter(hex(op['insn']) for op in expected_ops)
                    actual_entries = {name: entries[name] for name in expected_entries}
                    require(actual_entries == expected_entries and ops == expected_codes and completed == len(expected_ops),
                            'Diagnostic found real missing entry or work')
                    require(info == Counter({i: 2 for i in range(4)}), 'Perf trace differs from two source queries')
                    ledger.append(dict(trial=trial, entries_actual=actual_entries, entries_expected=expected_entries,
                        entries_delta={}, info_actual=dict(info), info_original_expected={i: 1 for i in range(4)},
                        info_source_expected={i: 2 for i in range(4)}, info_delta_from_old={i: 1 for i in range(4)},
                        ops_pos=completed, ops_expected=len(expected_ops), opcodes_actual=dict(ops),
                        opcodes_expected=dict(expected_codes), memory_reads=memory_reads))
                else:
                    entries[name] += 1
            elif tag == 'info':
                info[row['index']] += 1
            elif tag == 'begin':
                ops[hex(row['insn'])] += 1
            elif tag == 'end':
                completed += 1
            elif tag == 'read':
                memory_reads += 1
        require(len(ledger) == 4 and [r['ops_pos'] for r in ledger] == [237, 10, 10, 237], 'Incomplete four-call diagnostic')
        g.save(output / 'calls.json', [dict(row, output_bits=outputs[i],
                    oracle_bits=fixture['oracle']['cases'][fixture['trials'][i]['case']]['expected']['bits'])
                    for i, row in enumerate(calls)])
        g.save(output / 'architecture-delta.json', ledger)
        sources = [path / 'inputs/main.c', path / 'inputs/sdk/software/akv/src/akv_v2_native_riscv.c',
                   path / 'inputs/sdk/software/akv/src/akv_runtime.c',
                   path / 'inputs/sdk/software/akv/experimental/paired_heads/native_selection.h']
        pins = {str(p): sha(p) for p in [HERE / 'audit_perf_numerical.py', *[HERE / n for n in v.OWN],
                 ORIGIN / 'result.json', ORIGIN / 'source-pins.json', ORIGIN / 'selection.json',
                 ORIGIN / 'owner.json', ORIGIN / 'attempt.json', work / 'guest.log', work / 'trace.log',
                 work / 'guest.command.json', work / 'checked.command.json', work / 'checked.json',
                 path / 'build.json', path / 'source-pins.json', path / 'fixture.json', path / 'data.bin',
                 path / 'attention_features.elf', path / 'inputs/check.py', path / 'inputs/target/oracle.json',
                 *sources]}
        g.save(output / 'source-pins.json', pins)
        report.update(state='PERF_NUMERICAL_CHECKED_ARCHITECTURE_GATE_FAILED', numerical=numerical,
            original_execution=str(ORIGIN), original_result_sha256=ORIGIN_SHA, original_guest_command=guest,
            original_failed_checker_command=failed, service_owner=owner, qemu=selection['qemu'],
            oracle_sha256=sha(path / 'inputs/target/oracle.json'), original_numerical_checker_sha256=c.CHECK_SHA,
            original_fixture_sha256=c.FIXTURE_SHA, target_libm_sha256=c.LIBM_SHA,
            same_initial_flag_pairs=pairs, per_call_values=256, cancelled_tb_events=cancelled,
            source_explanation='main.c:97 device query, then native.c:764-766 automatic=0 selection; '
                'native_selection.h:25-26 queries again even for resident ON; main.c:28-29 only PAIR_HEADS enabled',
            sources={str(p): sha(p) for p in sources}, source_pins_sha256=sha(output / 'source-pins.json'),
            artifacts={str(output / n): sha(output / n) for n in ('calls.json', 'architecture-delta.json')})
        require(sha(ORIGIN / 'result.json') == ORIGIN_SHA, 'Original failure changed')
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        g.save(output / 'result.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    def expired(sig, frame):
        raise TimeoutError('180-second offline numerical audit bound')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    print(json.dumps(audit(parser.parse_args().output), indent=2))
