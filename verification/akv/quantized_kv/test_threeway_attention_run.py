"""Fail-closed prerequisite/build tests; no simulator execution."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_threeway_attention as r


class ThreewayRunTest(unittest.TestCase):
    def test_rejects_untyped_or_two_way_build_before_artifact_access(self):
        for data in ({}, {'kind': 'q8_0', 'state': 'STRIDED_ENTRY_BUILT_NOT_EXECUTED'},
                     {'kind': 'q4_0', 'state': 'THREEWAY_ENTRY_BUILT_NOT_EXECUTED', 'trials': 4}):
            with patch.object(r.s, 'read_json', return_value=data), self.assertRaises(ValueError):
                r.checked_build(Path('/synthetic/build'))

    def test_rejects_nonterminal_or_unchecked_prerequisites(self):
        base = dict(state='PASS', child_pid=None, post_pins_match=True,
                    independent_protocol_checked=True, simulator_exit_code=0)
        for key, value in (('state', 'RUNNING'), ('child_pid', 42), ('post_pins_match', False),
                           ('independent_protocol_checked', False), ('simulator_exit_code', 1),
                           ('simulator_exit_code', False)):
            data = dict(base, **{key: value})
            with patch.object(r.s, 'read_json', return_value=data), \
                 self.assertRaises(ValueError):
                r.terminal_inputs(Path('/synthetic/run'), lambda _: self.fail('builder called'), Path('/unused'))

    def fixture(self, root):
        run = root/'run'
        (run/'work').mkdir(parents=True)
        script, required, elf = (root/name for name in ('worker.py', 'input.c', 'test.elf'))
        for path in (script, required, elf):
            path.write_bytes(b'fixed '+path.name.encode())
        report = dict(elf=str(elf), elf_sha256=r.s.digest(elf), simv='/synthetic/simv', accepted_image_pins={})
        status = dict(state='PASS', child_pid=None, build='/synthetic/build', elf=str(elf), simv=report['simv'])
        for name in ('run.vcs.log', 'vector_trace.csv'):
            (run/'work'/name).write_text('synthetic evidence')
        protocol = dict(log_sha256=r.s.digest(run/'work/run.vcs.log'),
                        vector_trace_sha256=r.s.digest(run/'work/vector_trace.csv'))
        (run/'work/uvm_result.json').write_text(json.dumps(protocol))
        pins = r.s.hashes([script, required])
        (run/'source-pins.json').write_text(json.dumps(pins))
        result = dict(state='PASS', post_pins_match=True, independent_protocol_checked=True,
                      simulator_exit_code=0, elf_sha256=report['elf_sha256'],
                      source_pins_sha256=r.s.digest(run/'source-pins.json'),
                      evidence_sha256=r.s.hashes(run/'work'/name for name in
                                                ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json')))
        result['evidence_sha256'].update(r.s.hashes([run/'source-pins.json']))
        for name, data in (('status.json', status), ('result.json', result)):
            (run/name).write_text(json.dumps(data))
        return run, script, required, report

    def test_prerequisite_identity_pins_and_protocol_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            run, script, required, report = self.fixture(Path(temp))
            def builder(_):
                return report, r.s.hashes([required])
            with patch.object(r.s, 'check_result') as protocol:
                checked = r.terminal_inputs(run, builder, script)
                self.assertEqual(checked[0], report)
                self.assertEqual(checked[3], 'synthetic evidence')
                protocol.assert_called_once()
            # Correct-looking PASS is not enough if the actual log changed.
            (run/'work/run.vcs.log').write_text('changed')
            with patch.object(r.s, 'check_result'), self.assertRaises(ValueError):
                r.terminal_inputs(run, builder, script)

    def test_prerequisite_cannot_omit_required_source_or_worker(self):
        for omit_worker in (False, True):
            with tempfile.TemporaryDirectory() as temp:
                run, script, required, report = self.fixture(Path(temp))
                pins = r.s.read_json(run/'source-pins.json')
                del pins[str(script if omit_worker else required)]
                (run/'source-pins.json').write_text(json.dumps(pins))
                result = r.s.read_json(run/'result.json')
                result['source_pins_sha256'] = r.s.digest(run/'source-pins.json')
                result['evidence_sha256'][str(run/'source-pins.json')] = result['source_pins_sha256']
                (run/'result.json').write_text(json.dumps(result))
                with self.assertRaises(ValueError):
                    r.terminal_inputs(run, lambda _: (report, r.s.hashes([required])), script)

    def test_prerequisite_must_pin_every_consumed_evidence_file(self):
        for name in ('source-pins.json', 'work/run.vcs.log', 'work/vector_trace.csv', 'work/uvm_result.json'):
            with tempfile.TemporaryDirectory() as temp:
                run, script, required, report = self.fixture(Path(temp))
                result = r.s.read_json(run/'result.json')
                del result['evidence_sha256'][str(run/name)]
                (run/'result.json').write_text(json.dumps(result))
                with patch.object(r.s, 'check_result'), self.assertRaises(ValueError):
                    r.terminal_inputs(run, lambda _: (report, r.s.hashes([required])), script)

    def test_worker_checks_raw_gates_before_simulation(self):
        text = Path(r.__file__).read_text()
        self.assertLess(text.index('receipts = prerequisites('), text.index("'+PRELOAD='"))
        self.assertIn('wait_owner(gate, pid, script, 10800)', text)
        for marker in ('--require-axi-write', 'manifest-after', 's.check_result(',
                       's.verify_pins(pins)', "simulator_exit_code=0"):
            self.assertIn(marker, text)


if __name__ == '__main__':
    unittest.main()
