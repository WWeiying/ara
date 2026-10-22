import json
import unittest
from unittest.mock import patch

import admit_gather_war798_v2 as v


class HistoricalInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = v.life.read_bound(v.prior.BASE / 'admission-manifest.json', v.prior.BASE_SHA)
        cls.ledger = (v.prior.BASE / 'combined-inputs.txt').read_text().splitlines()
        q = v.life.read_bound(v.prior.QUAL, v.prior.Q_SHA)
        cls.authority = v.life.merge_pins(v.life.merge_pins(cls.base['input_pins'],
            cls.base['output_pins']), q['input_pins'])
        cls.manifest = v.life.read_bound(v.prior.RUN.with_name(v.prior.RUN.name + '.prepared.json'),
                                       v.prior.PREPARED_SHA)

    def test_actual_full798_unique_inventory(self):
        result = v.historical(self.base, self.ledger, self.authority, self.manifest)
        self.assertEqual(result['ledger_members'], 798)
        self.assertEqual(len(result['members']), 798)
        self.assertEqual([m['vdb'] for m in result['members']],
                         self.ledger[1:] + [str(v.prior.RUN / 'code.vdb')])

    def test_old796_prefix_cannot_change(self):
        ledger = list(self.ledger)
        ledger[1], ledger[2] = ledger[2], ledger[1]
        with self.assertRaisesRegex(ValueError, 'Exact sealed796'):
            v.historical(self.base, ledger, self.authority, self.manifest)

    def test_historical797_elf_pin_cannot_change(self):
        p = v.prior.Path(self.ledger[-1]).parent / 'manifest.json'
        record = v.life.read_bound(p, self.authority[str(p)])
        elf = next(s.split('=', 1)[1] for s in record['command'] if s.startswith('+PRELOAD='))
        with self.assertRaisesRegex(ValueError, 'Historical797 ELF'):
            v.historical(self.base, self.ledger, dict(self.authority, **{elf: '0'*64}), self.manifest)

    def test_new_elf_cannot_reuse_historical797(self):
        p = v.prior.BASE / 'elf-ledger-dedup.json'
        old = v.life.read_bound(p, self.base['output_pins'][str(p)])
        bad = dict(self.manifest, elf_sha256=old['new_ELF_sha256'])
        with self.assertRaisesRegex(ValueError, 'Actual Gather ELF'):
            v.historical(self.base, self.ledger, self.authority, bad)


if __name__ == '__main__':
    unittest.main()
