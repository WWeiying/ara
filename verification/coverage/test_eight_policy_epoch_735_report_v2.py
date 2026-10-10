"""Strict historical catalog authority and private735 reader regressions."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import eight_policy_epoch_735_report_v2 as r


class Catalog(unittest.TestCase):
    def fixture(self, ledger=None, node=None):
        node = node or dict(population=734, admission=str(r.ORIGIN),
                            manifest_sha256=r.ORIGIN_SEAL, ledger_sha256=r.ORIGIN_BOOK_SEAL)
        context = SimpleNamespace(cc_proof=lambda: dict(chain=[node]))
        manifest = dict(schema='GAP110_HISTORICAL734_SOFTWARE_NATIVE_ADMISSION_V1',
                        output_pins={str(r.ORIGIN / 'evidence-pins.json'): r.ORIGIN_BOOK_SEAL})
        def read(path, seal, pins):
            self.assertEqual((path, seal), (r.ORIGIN, r.ORIGIN_SEAL))
            pins[str(path / 'admission-manifest.json')] = seal
            pins[str(path / 'evidence-pins.json')] = r.ORIGIN_BOOK_SEAL
            return manifest, dict(r.CATALOG) if ledger is None else ledger
        return context, SimpleNamespace(sealed_ledger=read)

    def test_only_two_exact_sealed_keys_not_foreign(self):
        c, reader = self.fixture(dict(r.CATALOG, foreign='f'*64))
        ledger, pins = r.catalog_authority(c, reader)
        self.assertEqual(ledger, r.CATALOG)
        self.assertEqual(len(pins), 2)

    def test_missing_or_changed_historical_expected_rejected(self):
        for ledger in ({}, {p: '0'*64 for p in r.CATALOG}):
            c, reader = self.fixture(ledger)
            with self.assertRaisesRegex(Exception, 'tool catalog differs'):
                r.catalog_authority(c, reader)

    def test_wrong_ancestor_path_manifest_or_book_rejected(self):
        for field in ('admission', 'manifest_sha256', 'ledger_sha256'):
            c, reader = self.fixture()
            node = c.cc_proof()['chain'][0]
            node[field] = 'wrong'
            with self.assertRaisesRegex(Exception, 'ancestry absent'):
                r.catalog_authority(c, reader)

    def test_actual735_context_and_full_ancestry_catalog(self):
        context, _ = r.report.preparation_context()
        ledger = context.ledger()
        self.assertEqual((context.admission, context.seal, context.population),
                         (r.prior.ADMISSION, r.prior.SEAL, 735))
        self.assertEqual([n['population'] for n in context.cc_proof()['chain']], list(range(735, 722, -1)))
        for path, expected in r.CATALOG.items():
            self.assertEqual(ledger[path], expected)
        self.assertEqual(context.catalog_authority_pins[str(r.ORIGIN / 'evidence-pins.json')], r.ORIGIN_BOOK_SEAL)

    def test_no_frozen_globals_mutated_and_check_uses_successor(self):
        self.assertIs(r.prior.report.check.__globals__['wiring'], r.prior.wiring)
        self.assertIs(r.report.check.__globals__['wiring'], r.wiring)
        self.assertIsNot(r.wiring.Wiring, r.prior.wiring.Wiring)
        self.assertIs(r.report.prepare.__globals__['family'], r.family)
        self.assertIn(r.SCRIPT, r.dependencies())
        self.assertIn(r.TEST, r.dependencies())

    def test_actual_source_binding_invokes_inherited_strict_checks(self):
        context, _ = r.report.preparation_context()
        base = type(context).__mro__[1]
        pins = {}
        context.ledger()
        with patch.object(base, 'source_binding', return_value={'strict_base': True}) as original:
            result = context.source_binding(pins)
        original.assert_called_once_with(pins)
        self.assertTrue(result['strict_base'])
        self.assertFalse(result['inherited734_tool_catalog']['claimed_as735_top_level'])
        self.assertEqual(result['inherited734_tool_catalog']['expected_pins'], r.CATALOG)
        self.assertEqual(pins[str(r.ORIGIN / 'evidence-pins.json')], r.ORIGIN_BOOK_SEAL)


if __name__ == '__main__':
    unittest.main()
