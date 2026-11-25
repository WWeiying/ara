import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from analyze import analyze, records


class Checks(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(mode="resident", tokens=137, trial=i, warmup=i == 0,
                          ns=1000 + i, accepted=True, portal_calls=1,
                          portal_completed=1, fflags=3, errors=0) for i in range(4)]

    def log(self, rows=None, marker=True):
        return '\n'.join('PAIR ' + json.dumps(r) for r in (self.rows if rows is None else rows)) + (
            '\nRESIDENT_GGML_PAIR_PASS\n' if marker else '')

    def test_pass(self):
        self.assertEqual(len(records(self.log(), "resident", 137, 0)), 4)

    def test_reject(self):
        for key, value in (("mode", "native"), ("tokens", 128), ("trial", 0),
                           ("warmup", True), ("accepted", False), ("errors", 1),
                           ("ns", 0), ("ns", -1), ("portal_calls", 0), ("portal_completed", 0)):
            with self.subTest(key=key, value=value):
                rows = copy.deepcopy(self.rows)
                rows[1][key] = value
                with self.assertRaises(ValueError):
                    records(self.log(rows), "resident", 137, 0)

    def test_incomplete(self):
        for text, rc in ((self.log(self.rows[:2]), 0), (self.log(marker=False), 0),
                         (self.log(), 1), (self.log(self.rows + self.rows), 0)):
            with self.subTest(rc=rc, text=text):
                with self.assertRaises(ValueError):
                    records(text, "resident", 137, rc)

    def test_full_pair_and_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle, result = Path(tmp) / 'bundle', Path(tmp) / 'result'
            bundle.mkdir()
            result.mkdir()
            elf = b'fixture, not a hardware program'
            (bundle / 'resident-ggml-pair').write_bytes(elf)
            manifest = dict(elf_sha256=hashlib.sha256(elf).hexdigest(),
                            expected_flags={str(t): 3 for t in (65, 128, 137)}, scope='unit test')
            for root in (bundle, result):
                (root / 'manifest.json').write_text(json.dumps(manifest))
                (root / 'SHA256SUMS').write_text('unit test checksum list')
            for name, text in dict(status='COMPLETE', board_id='fixture', module_sha256='fixture',
                                   uname='fixture', probe='RESIDENT_INFO abi=1 lanes=4 vlen=1024 max_tokens=256').items():
                suffix = '.log' if name == 'probe' else '' if name == 'status' else '.txt'
                (result / (name + suffix)).write_text(text)
            for tokens in (65, 128, 137):
                for index, mode in enumerate(('native', 'resident', 'resident', 'native')):
                    rows = copy.deepcopy(self.rows)
                    for row in rows:
                        row.update(mode=mode, tokens=tokens, ns=1000 if mode == 'resident' else 2000,
                                   portal_calls=int(mode == 'resident'), portal_completed=int(mode == 'resident'))
                    stem = result / f't{tokens}_{index}_{mode}'
                    stem.with_suffix('.log').write_text(self.log(rows))
                    stem.with_suffix('.rc').write_text('0')
            report = analyze(result, bundle)
            self.assertTrue(all(r['speedup'] == 2 and r['latency_reduction_percent'] == 50
                                for r in report['results']))
            for name in ('status', 'manifest.json', 'probe.log', 't65_0_native.rc', 'board_id.txt'):
                path = result / name
                before = path.read_bytes()
                path.write_text('')
                with self.subTest(name=name), self.assertRaises(ValueError):
                    analyze(result, bundle)
                path.write_bytes(before)
            (bundle / 'resident-ggml-pair').write_bytes(b'wrong program')
            with self.assertRaisesRegex(ValueError, 'ELF hash'):
                analyze(result, bundle)


if __name__ == "__main__":
    unittest.main()
