"""Synthetic root fixtures only; never edits a formal admission or launches EDA."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import population_reader_732 as adapter
from verification_epoch import EpochError


class RootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.member = self.root / 'member'
        self.member.write_bytes(b'fixture-only')
        self.ledger = {str(self.member): hashlib.sha256(self.member.read_bytes()).hexdigest()}
        self.status = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', baseline=731,
            aggregate_passed=732, new_passed=1, coverage_admitted=True, exact731_prefix=True,
            complete_software_native_qualified=True, whole_VRF_CSR_source_guards_qualified=True,
            inherited731_pins_rechecked=True, historical_old_image_only=True,
            full_scalar_isa_verified=False, spike_custom_isa_pass=False, official_DVE_report=False,
            rtl_changed=False, simulations_started=False,
            raw_delta=dict(line=0, cond=2, branch=0, fsm=0),
            qualification_seal='1' * 64, candidate_seal='2' * 64)

    def fixture(self, mutate=None):
        for name in adapter.OUTPUTS:
            value = self.status if name == 'status.json' else self.ledger if name == 'evidence-pins.json' else {}
            (self.root / name).write_text(json.dumps(value))
        pins = {str(self.root / name): hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                for name in adapter.OUTPUTS}
        manifest = dict(schema=adapter.SCHEMA, output=str(self.root), output_pins=pins,
            baseline=str(self.root / 'pure-war-offline-admitted-731-parent-20261006-01'),
            baseline_seal='79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641',
            qualification_seal='1' * 64, candidate_seal='2' * 64, prepared_seal='3' * 64)
        if mutate:
            mutate(manifest)
        data = json.dumps(manifest).encode()
        (self.root / 'admission-manifest.json').write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def test_exact_root_and_fresh_full_ledger_epoch(self):
        root = adapter.bind_root(self.root, self.fixture())
        self.assertFalse(root.status['full_scalar_isa_verified'])
        first = root.new_pre_run_epoch()
        second = root.new_pre_run_epoch()
        self.assertIsNot(first, second)
        first.check_pins(first.pins)
        self.assertEqual(first.finish()['verified_paths'], len(first.pins))

    def test_unknown_schema_rejected(self):
        seal = self.fixture(lambda m: m.update(schema='ARBITRARY_PASS_V1'))
        with self.assertRaises(EpochError):
            adapter.bind_root(self.root, seal)

    def test_wrong_root_seal_rejected(self):
        self.fixture()
        with self.assertRaises(EpochError):
            adapter.bind_root(self.root, '0' * 64)

    def test_output_scope_injection_rejected(self):
        def inject(manifest):
            manifest['output_pins'][str(self.root / '../outside')] = '0' * 64
        with self.assertRaises(EpochError):
            adapter.bind_root(self.root, self.fixture(inject))

    def test_missing_output_rejected(self):
        with self.assertRaises(EpochError):
            adapter.bind_root(self.root, self.fixture(lambda m: m['output_pins'].pop(str(self.root / 'single-bits.json'))))

    def test_fail_population_bool_and_scope_flags_rejected(self):
        for key, value in (('status', 'FAIL'), ('aggregate_passed', True),
                           ('coverage_admitted', 1), ('rtl_changed', True),
                           ('full_scalar_isa_verified', True)):
            original = dict(self.status)
            self.status[key] = value
            with self.subTest(key=key), self.assertRaises(EpochError):
                adapter.bind_root(self.root, self.fixture())
            self.status = original

    def test_nonactual_delta_rejected(self):
        self.status['raw_delta']['cond'] = 3
        with self.assertRaises(EpochError):
            adapter.bind_root(self.root, self.fixture())

    def test_changed_output_bytes_rejected(self):
        seal = self.fixture()
        (self.root / 'target-hits.json').write_bytes(b'changed')
        with self.assertRaises(EpochError):
            adapter.bind_root(self.root, seal)

    def test_ledger_member_mutation_requires_fresh_epoch_rejection(self):
        root = adapter.bind_root(self.root, self.fixture())
        self.member.write_bytes(b'changed-later')
        reader = root.new_pre_run_epoch()
        with self.assertRaises(EpochError):
            reader.check_pins(reader.pins)

    def test_conflicting_additional_authority_rejected(self):
        root = adapter.bind_root(self.root, self.fixture())
        with self.assertRaises(EpochError):
            root.new_pre_run_epoch(additional_pins={str(self.member): '0' * 64})

    def test_conflicting_ledger_output_authority_rejected(self):
        self.ledger[str(self.root / 'status.json')] = '0' * 64
        with self.assertRaises(EpochError):
            adapter.bind_root(self.root, self.fixture())

    def test_literal_dotdot_retained_but_full_epoch_blocked(self):
        literal = str(self.root) + '/tool/bin/../include/header.h'
        self.ledger[literal] = '4' * 64
        root = adapter.bind_root(self.root, self.fixture())
        self.assertEqual(root.pending_literal_paths, (literal,))
        self.assertEqual(root.ledger[literal], '4' * 64)
        with self.assertRaises(EpochError):
            root.new_pre_run_epoch()


if __name__ == '__main__':
    unittest.main()
