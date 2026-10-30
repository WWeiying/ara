"""Synthetic evidence mutations only; no simulator or real output mutation."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('legacy_stdout_audit_tests', HERE/'audit_stdout_extension.py')
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


class StdoutAuditTests(unittest.TestCase):
    def test_exact_extension(self):
        for prefix in (b'', b'pinned earlier stdout\n'):
            sha = hashlib.sha256(prefix).hexdigest()
            self.assertEqual(audit.stdout_extension(prefix+b'PASS\n', sha)['original_prefix_bytes'], len(prefix))

    def test_prefix_suffix_mutations(self):
        sha = hashlib.sha256(b'').hexdigest()
        for data in (b'', b'PASS', b'PASS\r\n', b'PASS\n\n', b'PASS\nBOGUS\n',
                     b'FAIL\n', b'PASS_BOGUS\n', b'BOGUS\nPASS\n', b'PASS\nPASS\n'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                audit.stdout_extension(data, sha)
        with self.assertRaises(ValueError):
            audit.stdout_extension(b'changed\nPASS\n', hashlib.sha256(b'original\n').hexdigest())

    def fixture(self, source):
        names = ['worker.log']
        names += [mode+suffix for mode in ('baseline','candidate') for suffix in
                  ('-suite.log','-compile.log','-checked.json','-compile-admission.json',
                   '-suite.exit.json','-compile.exit.json','-suite.command.json',
                   '-compile.command.json','.f','/simv')]
        evidence = {}
        for name in names:
            p = source/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'' if name=='worker.log' else b'sealed fixture\n')
            evidence[str(p)] = audit.digest(p)
        (source/'worker.log').write_bytes(b'PASS\n')
        return evidence

    def test_original_failure_retained_other_evidence_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            evidence = self.fixture(p)
            result = audit.check_evidence(evidence, p)
            self.assertEqual(result['original_verifier_error'], 'Input identity changed: '+str(p/'worker.log'))
            for name in ('baseline-suite.log','candidate-compile.log','baseline/simv'):
                file = p/name
                original = file.read_bytes()
                file.write_bytes(original+b'PASS\n')
                with self.subTest(name=name), self.assertRaises(ValueError):
                    audit.check_evidence(evidence, p)
                file.write_bytes(original)

    def test_missing_and_no_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            evidence = self.fixture(p)
            for name in ('worker.log','candidate-suite.exit.json','baseline/simv'):
                changed = dict(evidence)
                changed.pop(str(p/name))
                with self.assertRaises(ValueError):
                    audit.check_evidence(changed, p)
            evidence[str(p/'worker.log')] = audit.digest(p/'worker.log')
            with self.assertRaises(ValueError):
                audit.check_evidence(evidence, p)


if __name__ == '__main__':
    unittest.main()
