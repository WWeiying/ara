#!/usr/bin/env python3
"""Read-only checks of the prepared twelve and the 83-source coverage ledger."""
import difflib
from fractions import Fraction
from pathlib import Path
import re
import sys
import unittest

sys.dont_write_bytecode = True
from prepare_batch import HERE, INTEGRATION, sha
from prepare_successor import replacements
from replay_candidate03 import read, pins_check, oracle

OUT = HERE / 'remainder12_01'


class Prepared(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provenance = read(OUT / 'prepared01/provenance.json')

    def test_readiness_and_preserved_baseline(self):
        ready = read(OUT / 'ready.json')
        self.assertEqual(ready['status'], 'PREPARED_12_HOST_SPIKE_PASS_NOT_DUT')
        self.assertFalse(ready['vcs_started'])
        pins_check(read(OUT / 'source_pins.json'))
        self.assertEqual(sha(OUT / 'source_pins.json'), ready['source_pins_sha256'])
        self.assertEqual(sha(OUT / 'coverage83.json'), ready['coverage_sha256'])
        self.assertEqual(sha(OUT / 'reference01/reference.json'), ready['reference_sha256'])
        for file, digest in self.provenance['files'].items():
            self.assertEqual(sha(OUT / 'prepared01' / file), digest)

    def test_only_six_loop_changes_and_untouched_full_oracle(self):
        sys.path.insert(0, str(INTEGRATION))
        from prepare import adapt
        self.assertEqual(len(self.provenance['cases']), 12)
        for case in self.provenance['cases']:
            folder = OUT / 'prepared01' / case['id']
            archive = Path(case['source_directory'])
            original = (archive / 'scenario.c').read_text()
            port = (folder / 'case.c').read_text()
            unbounded = adapt(original, case['id'])
            restored = port
            for before, after in replacements(case['original_case']['selected_trial']['op']):
                self.assertEqual(restored.count(after), 1)
                restored = restored.replace(after, before)
            self.assertEqual(restored, unbounded)
            anchor = '            for(unsigned i=0;i<128;'
            self.assertEqual(port[port.index(anchor):], unbounded[unbounded.index(anchor):])
            for file, digest in case['original_case']['scenario_sources'].items():
                self.assertEqual(sha(folder / 'original' / file), digest)
                self.assertEqual((folder / 'original' / file).read_bytes(), (archive / file).read_bytes())
            for label, before, after in (('adapter', original, unbounded), ('loops', unbounded, port)):
                expected = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                    fromfile=case['id']+'/'+label+'_before.c', tofile=case['id']+'/'+label+'_after.c'))
                self.assertEqual((OUT / 'source_diffs' / (case['id']+'.'+label+'.diff')).read_text(), expected)
        for file in ('runtime.c', 'startup.S', 'replay.ld'):
            self.assertEqual((OUT / 'prepared01' / file).read_bytes(), (INTEGRATION / file).read_bytes())

    def test_host_full_cap_values_and_guards(self):
        checks = {r['name']: r for r in read(OUT / 'host_semantics.json')['results']}
        for case in self.provenance['cases']:
            archived = case['original_case']
            op = archived['selected_trial']['op']
            check = checks[case['id']]
            cap = int(Fraction(archived['lmul'].replace('mf', '1/').replace('m', '')) * 1024 / archived['sew'])
            x, data = 0xe736815b449aec21, []
            for _ in range(cap):
                for shift in (13, -7, 17):
                    x = (x ^ (x << shift if shift > 0 else x >> -shift)) % (1 << 64)
                data.append(x % (1 << archived['sew']))
            index = 1 if op in (0, 20) else 31 if op == 3 else 0
            expected = [91, data[index] if index < cap else 0] + [91] * (cap - 2)
            self.assertEqual(check['capacity'], cap)
            self.assertEqual(check['full_cap_expected'], expected)
            self.assertEqual(check['tuple'], [0, op, 0, 2, 0, 0])
            self.assertEqual(check['guards'], [91, 91])
            self.assertEqual(check['expected_returned_vstart'], 0)
            self.assertEqual((check['old_enumerations'], check['new_enumerations']), (56448, 1))
            self.assertEqual((check['expected_cases'], check['expected_errors']), (1, 0))

    def test_spike_identity_exit_fullmarkers_and_fail_veto(self):
        reference = read(OUT / 'reference01/reference.json')
        self.assertEqual(reference['status'], 'SPIKE_12_FULLORACLE_PASS_NOT_DUT')
        self.assertEqual(len(reference['results']), 12)
        for backend in ('soc', 'spike'):
            programs = read(OUT / (backend+'01/programs.json'))
            self.assertEqual(programs['provenance_sha256'], sha(OUT / 'prepared01/provenance.json'))
            for name, entry in programs['programs'].items():
                self.assertEqual(sha(Path(entry['path'])), entry['sha256'])
                row, = [r for r in reference['results'] if r['name'] == name]
                self.assertEqual(row['soc_elf_sha256'] if backend == 'soc' else row['elf_sha256'], entry['sha256'])
                log = OUT / 'reference01' / (name+'.log')
                self.assertEqual(sha(log), row['log_sha256'])
                text = log.read_text()
                self.assertTrue(oracle(entry, text))
                self.assertFalse(oracle(entry, text+'\nRVV_PERMUTE_FAIL sew=8 cases=1 errors=1\n'))
                self.assertFalse(oracle(entry, text+'\nBOARD_REPLAY_PASS\n'))
                self.assertRegex(text, re.compile(r'^0x0{16}$', re.M))
                self.assertEqual(row['returncode'], 0)
                self.assertEqual(row['spike_target_hits'], 1)
                self.assertEqual(row['original_routine_instructions'], 13)
                self.assertTrue(row['archived_routine_encoding_identical'])
                self.assertEqual(sha(OUT / 'reference01' / (name+'.commits.log')), row['commit_log_sha256'])

    def test_no_duplicate_or_parent_closure(self):
        ledger = read(OUT / 'coverage83.json')
        self.assertEqual((ledger['accepted'], ledger['prepared_not_dut'], ledger['not_prepared']), (8, 12, 63))
        self.assertEqual(ledger['still_unaccepted'], 75)
        records = ledger['records']
        self.assertEqual(len(records), 83)
        self.assertEqual(len({tuple(r['shape_opcode']) for r in records}), 83)
        self.assertEqual(len({r['parent']['name'] for r in records}), 19)
        self.assertFalse(ledger['parent_closure'])
        for row in records:
            self.assertFalse(row['parent_closed'])
            self.assertFalse(row['duplicate_aliases_add_coverage'])
            for alias in row['verified_duplicate_aliases']:
                self.assertEqual(sha(Path(alias['path'])), alias['sha256'])
        accepted_shapes = {tuple(r['shape_opcode'][:2]) for r in records if r['status'] == 'ACCEPTED_SOURCE_SINGLE'}
        prepared_shapes = {tuple(r['shape_opcode'][:2]) for r in records if r['status'] == 'PREPARED_NOT_DUT'}
        self.assertEqual((len(accepted_shapes), len(prepared_shapes), len(accepted_shapes | prepared_shapes)), (7, 12, 19))
        self.assertFalse(accepted_shapes & prepared_shapes)


if __name__ == '__main__':
    unittest.main()
