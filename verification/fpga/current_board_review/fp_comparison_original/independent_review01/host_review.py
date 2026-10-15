"""Read-only inputs; host evidence only. Never calls prepare/work or launches DUT."""
import collections
import csv
import hashlib
import importlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(ROOT))
import replay_restart_successor as r

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    plan = r.read(ROOT / 'candidate04_restart_plan05/plan.json')
    inherited = r.prior.self_test()
    log = io.StringIO()
    tests = unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module('test_restart_successor'))
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(tests)
    (OUT / 'successor_rerun.log').write_text(log.getvalue())
    assert len(inherited) == 27 and result.wasSuccessful() and result.testsRun == 15
    r.contract(plan)
    imported = []
    for name in ('recover', 'prepare_m4_plan', 'replay_restart_successor', 'replay19', 'prepare19', 'run', 'prepare'):
        path = Path(sys.modules[name].__file__).resolve()
        imported.append(dict(module=name, path=str(path), sha256=sha(path), pinned=str(path) in plan['pins']))

    entry = plan['cases'][0]
    good = '\n'.join(entry['pass_markers']) + '\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'
    extra = []
    for marker in ('BOARD_CASE_FAIL', 'BOARD_REPLAY_MISMATCH', 'BOARD_REPLAY_SERVICE_FAIL',
                   'BOARD_REPLAY_VLEN_FAIL', 'Fatal: assertion', 'UVM_FATAL', 'Assertion xyz failed'):
        assert not r.prior.strict_console(entry, marker + '\n' + good)
        extra.append('earlier_failure_veto:' + marker)
    for marker in entry['pass_markers']:
        assert not r.prior.strict_console(entry, good + marker + '\n')
        extra.append('duplicate_marker:' + marker)

    with tempfile.TemporaryDirectory(prefix='fp-independent-') as tmp:
        tmp = Path(tmp)
        trace = tmp / 'commit_trace.csv'
        target = entry['target_retirements'][0]
        header = 'cycle,event,order,pc,insn,trap\n'
        rows = ''.join(f'{i//2},retire,{i},{target["pc"]},{target["opcode"]},0\n' for i in range(130))
        trace.write_text(header + rows)
        assert r.prior.check_trace(entry, trace)['retired'] == 130
        extra.append('130_targets_same_cycle_allowed')
        mutations = {
            'missing_target': header + rows.rsplit('\n', 2)[0] + '\n',
            'duplicate_target': header + rows + f'65,retire,130,{target["pc"]},{target["opcode"]},0\n',
            'zero_count_other_op': header + rows + f'65,retire,130,{entry["target_retirements"][1]["pc"]},{entry["target_retirements"][1]["opcode"]},0\n',
            'backward_cycle': header + rows + '0,retire,130,80000000,00000013,0\n',
            'wrong_pc': header + rows.replace(target['pc'], '80000000', 1),
            'malformed': header + rows + 'garbage\n',
        }
        for name, content in mutations.items():
            trace.write_text(content)
            try:
                r.prior.check_trace(entry, trace)
            except (AssertionError, ValueError, TypeError, KeyError):
                extra.append('trace_reject:' + name)
            else:
                raise AssertionError(name)

        class Parent:
            def _run_test(self, test, image):
                return SimpleNamespace(status='PASS', returncode=0, reason='', artifact_dir=tmp)
        checked = r.prior.runner_class(Parent, {entry['id']: entry})()
        checked.cancel_event = threading.Event()
        test = SimpleNamespace(name=entry['id'])
        for name in ('missing_console', 'unreadable_console', 'missing_trace', 'invalid_trace'):
            console = tmp / 'console.log'
            if console.is_file(): console.unlink()
            elif console.is_dir(): console.rmdir()
            if name == 'unreadable_console': console.mkdir()
            elif name in ('missing_trace', 'invalid_trace'): console.write_text(good)
            if name == 'missing_trace': trace.unlink()
            if name == 'invalid_trace': trace.write_text(header)
            checked.cancel_event.clear()
            try:
                checked._run_test(test, None)
            except (OSError, AssertionError):
                assert checked.cancel_event.is_set()
                extra.append('exception_cancels:' + name)
            else:
                raise AssertionError(name)

    traces = []
    for item in r.read(ROOT / 'budget01/finding.json')['calibrations']:
        path = Path(item['trace'])
        # Only closed historical traces already referenced by the sealed budget.
        assert str(path) in plan['pins'] and sha(path) == plan['pins'][str(path)]
        previous = -1
        count = 0
        traps = collections.Counter()
        events = collections.Counter()
        with path.open() as stream:
            for row in csv.DictReader(stream):
                cycle = int(row['cycle'])
                assert cycle >= previous
                previous = cycle
                events[row['event']] += 1
                if row['event'] == 'retire':
                    assert int(row['order']) == count
                    count += 1
                    traps[row['trap']] += 1
        assert count == item['retired'] and previous == item['last_cycle'] and set(traps) == {'0'}
        traces.append(dict(path=str(path), sha256=sha(path), retirements=count, last_cycle=previous,
                           retire_traps=dict(traps), events=dict(events)))

    sources = []
    provenance = r.read(ROOT / 'prepared02/prepared/provenance.json')
    for item in provenance['records']:
        name = item['id']
        base = ROOT / 'prepared02/prepared' / name
        parent = item['parent']
        assert sha(base / 'original_rebuilt.elf') == parent['sha256'] == sha(parent['original_elf'])
        assert (base / 'original/scenario.S').read_bytes() == Path(parent['assembly']).read_bytes()
        before = (base / 'original/parent.c').read_text()
        prefix = (base / 'original/prefix.c').read_text()
        count = 682 if '682' in name else 130
        assert prefix.replace(f'        if(cases=={count})goto prefix_done;\n', '').replace('prefix_done:\n', '') == before
        seq = r.read(base / 'call_sequence.json')
        assert len(seq) == count
        sources.append(dict(name=name, original_elf_sha256=parent['sha256'], assembly_sha256=sha(parent['assembly']),
                            calls=len(seq), sample_tuple=seq[-1], first_tuple=seq[0]))
    evidence = dict(status='PASS_HOST_CHECKS_NOT_DUT', inherited_count=len(inherited), successor_count=result.testsRun,
                    additional_checks=extra, imported_modules=imported, historical_traces=traces, original_sources=sources)
    (OUT / 'host_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(dict(status=evidence['status'], inherited_count=27, successor_count=15,
                         additional_checks=len(extra), historical_traces=len(traces), originals=len(sources))))

if __name__ == '__main__':
    main()
