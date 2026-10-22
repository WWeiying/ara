"""Byte-role discovery is diagnostic; formal reader keeps the original guards."""
import hashlib
from types import FunctionType
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import eight_policy_epoch_735_report_v4 as r


class Phase(unittest.TestCase):
    def fixture(self, root, limit=128):
        a, b, c = [root / n for n in ('history.json', 'needed.json', 'source.txt')]
        a.write_bytes(b'"' + b'x' * 200 + b'"')
        b.write_bytes(b'{"schema":"exact","bits":[0,1]}')
        c.write_bytes(b'source')
        pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (a, b, c)}
        phase = r.DiagnosticPhase(pins, list(pins), [str(a), str(b)], {}, max_bytes=limit)
        return phase, a, b, c

    def test_large_unconsumed_history_streams_but_needed_json_parses(self):
        with tempfile.TemporaryDirectory() as directory:
            phase, a, b, c = self.fixture(Path(directory))
            phase.check_pins(phase.pins)
            self.assertEqual(phase.raw, {})
            self.assertEqual(phase.retained, 0)
            value = phase.loads(phase.text(b))
            self.assertEqual(value['bits'], [0, 1])
            with self.assertRaises(Exception): value['schema'] = 'changed'
            result = phase.finish()
            self.assertEqual(result['hashes'], 3)
            self.assertEqual(set(result['consumed']), {str(b)})
            self.assertLess(result['peak_simultaneous_json_bytes'], 128)
            self.assertEqual(phase.retained, 0)
            self.assertEqual(phase.buffers, {})

    def test_required_large_read_fails_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            phase, a, _, _ = self.fixture(Path(directory))
            with self.assertRaisesRegex(Exception, 'read budget exceeded'): phase.bytes(a)
            self.assertTrue(phase.failed)

    def test_bytes_and_text_leases_released_after_json(self):
        with tempfile.TemporaryDirectory() as directory:
            phase, _, b, _ = self.fixture(Path(directory))
            raw = phase.bytes(b)
            self.assertEqual(phase.retained, len(raw))
            phase.loads(raw)
            self.assertEqual(phase.retained, 0)
            text = phase.text(b)
            self.assertEqual(phase.retained, len(text.encode('utf-8')))
            phase.loads(text)
            self.assertEqual(phase.retained, 0)
            self.assertEqual(phase.endpoint_leases, {})

    def test_decode_and_json_errors_fail_closed_and_release(self):
        for raw in (b'{bad}', b'{"x":NaN}', b'\xff'):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'invalid.json'; path.write_bytes(raw)
                pins = {str(path): hashlib.sha256(raw).hexdigest()}
                phase = r.DiagnosticPhase(pins, list(pins), list(pins), {})
                with self.assertRaises(Exception): phase.loads(phase.text(path))
                self.assertTrue(phase.failed)
                self.assertEqual(phase.retained, 0)
                self.assertEqual(phase.buffers, {})
                with self.assertRaises(Exception): phase.finish()

    def test_literal_dotdot_alias_one_hash_and_same_consumption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'sub').mkdir()
            path = root / 'item.json'; path.write_bytes(b'{"x":1}')
            alias = str(root / 'sub' / '..' / 'item.json')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            pins = {str(path): digest, alias: digest}
            phase = r.DiagnosticPhase(pins, list(pins), list(pins), {})
            phase.check_pins(pins)
            self.assertEqual(phase.hashes, 1)
            self.assertEqual(phase.loads(phase.bytes(alias)), {'x': 1})
            self.assertEqual(phase.loads(phase.text(path)), {'x': 1})
            self.assertEqual(phase.finish()['verified_literal_paths'], 2)
            phase2 = r.DiagnosticPhase(pins, list(pins), list(pins), {})
            self.assertEqual(phase2.hashes, 0)
            conflict = {str(path): digest, alias: '0'*64}
            with self.assertRaisesRegex(Exception, 'authority conflict'):
                r.DiagnosticPhase(conflict, list(conflict), list(conflict), {})

    def test_superseded_same_endpoint_token_rejected_not_accumulated(self):
        with tempfile.TemporaryDirectory() as directory:
            phase, _, b, _ = self.fixture(Path(directory))
            first = phase.bytes(b)
            second = phase.bytes(b)
            self.assertEqual(phase.retained, len(second))
            self.assertNotIn(id(first), phase.buffers)
            with self.assertRaisesRegex(Exception, 'captured bytes'): phase.loads(first)

    def test_unused_hash_drift_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            phase, a, _, _ = self.fixture(Path(directory))
            a.write_bytes(b'changed')
            with self.assertRaisesRegex(Exception, 'Expected SHA differs'): phase.check_pins(phase.pins)

    def test_mutation_between_hash_and_consumer_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            phase, _, b, _ = self.fixture(Path(directory))
            phase.sha(b)
            b.write_bytes(b'{"schema":"bad","bits":[0,1]}')
            with self.assertRaisesRegex(Exception, 'metadata changed'): phase.text(b)

    def test_change_during_second_read_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            phase, _, b, _ = self.fixture(Path(directory))
            phase.sha(b)
            real = r.os.fdopen
            def altered(fd, mode):
                stream = real(fd, mode)
                b.write_bytes(b'{"schema":"evil","bits":[0,1]}')
                return stream
            with patch.object(r.os, 'fdopen', altered):
                with self.assertRaisesRegex(Exception, 'before diagnostic read'): phase.text(b)

    def test_foreign_json_and_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            phase, _, b, _ = self.fixture(Path(directory))
            with self.assertRaisesRegex(Exception, 'captured bytes'): phase.loads(b'{}')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'dup.json'
            path.write_bytes(b'{"x":1,"x":2}')
            pins = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()}
            phase = r.DiagnosticPhase(pins, list(pins), list(pins), {})
            with self.assertRaisesRegex(Exception, 'Duplicate JSON'): phase.loads(phase.bytes(path))

    def test_no_hash_only_read_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            phase, _, _, c = self.fixture(Path(directory))
            phase.read_endpoints.remove(str(c))
            with self.assertRaisesRegex(Exception, 'Undeclared'): phase.bytes(c)

    def test_finish_requires_all_pins_and_fresh_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            phase, _, b, _ = self.fixture(Path(directory))
            phase.sha(b)
            with self.assertRaisesRegex(Exception, 'Incomplete'): phase.finish()
        with tempfile.TemporaryDirectory() as directory:
            phase, _, b, _ = self.fixture(Path(directory))
            phase.check_pins(phase.pins)
            b.write_bytes(b'{}')
            with self.assertRaisesRegex(Exception, 'metadata changed'): phase.finish()


class Roles(unittest.TestCase):
    def fixture(self):
        source = dict(pins={'old': 'a', 'needed': 'b'}, byte_paths=['old', 'needed'], json_paths=['old', 'needed'])
        value = dict(source, pins=dict(source['pins'], new='c'))
        audit = dict(source_pins=source['pins'], byte_paths=['needed'], json_paths=['needed'], measured_endpoint_bytes=9)
        return value, source, audit

    def test_only_roles_removed_all_hashes_remain(self):
        value, source, audit = self.fixture()
        value['generated_paths'] = ['applied.el', 'states_selected.tsv', 'final-empty.el']
        value['targets'] = 5892; value['protected'] = 17774
        result = r.restrict_roles(value, source, audit, 'f'*64)
        self.assertEqual(result['pins'], value['pins'])
        self.assertEqual(result['byte_paths'], ['needed'])
        self.assertEqual(result['json_paths'], ['needed'])
        self.assertEqual(value['byte_paths'], ['old', 'needed'])
        self.assertEqual(result['generated_paths'], value['generated_paths'])
        self.assertEqual((result['targets'], result['protected']), (5892, 17774))

    def test_missing_or_changed_pin_cannot_be_excused_as_hash_only(self):
        for corrupt in ('missing', 'changed'):
            value, source, audit = self.fixture()
            if corrupt == 'missing': del value['pins']['old']
            else: value['pins']['old'] = 'wrong'
            with self.assertRaisesRegex(Exception, 'source pin'): r.restrict_roles(value, source, audit, 'f'*64)

    def test_foreign_consumption_role_rejected(self):
        value, source, audit = self.fixture(); audit['byte_paths'].append('foreign')
        with self.assertRaisesRegex(Exception, 'Unreviewed'): r.restrict_roles(value, source, audit, 'f'*64)

    def test_formal_capture_implementation_and_validator_unchanged(self):
        self.assertIs(r.report.check.__code__, r.prior.report.check.__code__)
        self.assertIs(r.report.check.__globals__['wiring'], r.prior.wiring)
        self.assertIs(r.prior.wiring.Wiring, r.prior.Wiring)
        self.assertIs(r.base.Wiring.enter.__globals__['CapturePhase'], r.base.CapturePhase)
        owner = r.prior.Wiring({}, [], [])
        self.assertIs(type(owner.phase), r.base.CapturePhase)
        self.assertEqual(owner.max_bytes, 805306368)

    def test_actual_audit_dependency_gate_preserves_foreign_function_globals(self):
        reader = r.prior.prior.clone(r.prior.report, wiring=r.prior.wiring,
            dependencies=r.prior.dependencies, save=r.prior.save, family=r.prior.report.family)
        self.assertIs(reader.check.__globals__['dependencies'], r.prior.dependencies)
        self.assertIs(reader.check.__globals__['dependencies'].__globals__['prior'], r.prior.prior)
        self.assertIn(r.prior.SCRIPT, reader.check.__globals__['dependencies']())
        self.assertIs(r.report.check.__globals__['family'], r.prior.report.family)

    def test_generated_catalog_and_actual_capture_remain_complete(self):
        self.assertEqual(r.report.generated_catalog(r.ROOT), r.prior.report.generated_catalog(r.ROOT))
        paths = {p.name for p in r.report.generated_catalog(r.ROOT)}
        for name in ('applied.el', 'reloaded.el', 'after-root.el', 'session-final-empty.el',
                     'live-identity.json', 'execution.json', 'summary_applied.csv'):
            self.assertIn(name, paths)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); a = root / 'observed.json'; b = root / 'observed.el'
            a.write_bytes(b'{"actual":true}'); b.write_bytes(b'EL')
            original = r.report.capture_generated
            capture = FunctionType(original.__code__, dict(original.__globals__,
                generated_catalog=lambda output: (a,b)), 'capture_generated')
            pins = capture(root, {})
            self.assertEqual(set(pins), {str(a), str(b)})
            self.assertEqual(pins[str(a)], hashlib.sha256(a.read_bytes()).hexdigest())
            with self.assertRaisesRegex(Exception, 'overlap'): capture(root, pins)


if __name__ == '__main__':
    unittest.main()
