"""Focused actual fixtures and rejecting mutations; no admission or EDA."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import admit_akv_entropy777 as a


class Gates(unittest.TestCase):
    def setUp(self):
        self.q = a.life.read_bound(a.QUAL / 'qualification.json', a.Q_SHA)
        self.c = a.life.read_bound(a.QUAL / 'manifest-order-closure.json', a.C_SHA)

    def test_actual_qualification_closure(self):
        a.qualification(self.q, self.c)

    def test_wrong_qualification(self):
        self.q['scalar_model_skips'] = False
        with self.assertRaises(ValueError): a.qualification(self.q, self.c)

    def test_missing_closure_output(self):
        self.c['original_output_pins'] = {}
        with self.assertRaises(ValueError): a.qualification(self.q, self.c)

    def test_wrong_manifest_seal(self):
        self.c['actual_manifest_sha256'] = '0'*64
        with self.assertRaises(ValueError): a.qualification(self.q, self.c)

    def identity(self):
        folder = a.RUN / 'code.vdb/snps/coverage/db/testdata/akv_descriptor_entropy'
        manifest = a.life.read_bound(a.RUN / 'manifest.json', a.ACTUAL_SHA)
        return (a.toggle.xml(folder / 'siminfo.xml'), a.toggle.xml(folder / 'vcmArguments.xml'),
                manifest['command'], str(a.life.IMAGE)+'.vdb')

    def test_actual_native_identity_unknown_not_pass(self):
        result = a.native_identity(*self.identity())
        self.assertEqual(result['XML_teststatus'], 'unknown')
        self.assertEqual(result['seed'], 1)

    def test_foreign_workdir_seed_command(self):
        for key, value in [('workdir', '/tmp'), ('seed', '0'), ('cmdline', 'simv'), ('teststatus', 'pass')]:
            sim, args, cmd, design = self.identity()
            sim.find('srctest').set(key, value)
            with self.subTest(key=key), self.assertRaises(ValueError):
                a.native_identity(sim, args, cmd, design)

    def test_missing_metric_foreign_design(self):
        for field in ('metric', 'design'):
            sim, args, cmd, design = self.identity()
            if field == 'metric': args.remove(args.findall('vcm_arg_data')[-1])
            else: args.set('compvdbpath', '/foreign.vdb')
            with self.subTest(field=field), self.assertRaises(ValueError):
                a.native_identity(sim, args, cmd, design)

    def test_actual_rebase_subtracts_formal776(self):
        base = a.life.read_bound(a.BASE / 'admission-manifest.json', a.BASE_SHA)
        ledger = (a.BASE / 'combined-inputs.txt').read_text().splitlines()
        old = json.loads((a.QUAL / 'toggle-gain775.json').read_bytes())
        path = next((Path(ledger[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        added, h = a.toggle.rows(path, [a.case.fixture.SCOPE])
        self.assertEqual(h, base['input_pins'][str(path)])
        result = a.rebased_gain(old['before'], added, {old['scope']: old['single']})
        bits = int(old['single']['bits'], 16) & ~(int(old['before']['bits'], 16) |
                int(added[old['scope']]['bits'], 16))
        self.assertEqual(result['new_positions'], bin(bits).count('1'))
        self.assertLessEqual(result['new_positions'], old['new_positions'])

    def test_zero_gain_and_shape_drift(self):
        old = json.loads((a.QUAL / 'toggle-gain775.json').read_bytes())
        scope = old['scope']; single = {scope: old['single']}
        with self.assertRaises(ValueError): a.rebased_gain(old['before'], single, single)
        single = copy.deepcopy(single); single[scope]['checksum'] = 'foreign'
        with self.assertRaises(ValueError): a.rebased_gain(old['before'], {scope: old['before']}, single)

    def test_actual_complete6162_union(self):
        base = a.life.read_bound(a.BASE / 'admission-manifest.json', a.BASE_SHA)
        p = a.BASE / 'combined-bits.json'
        before = a.life.read_bound(p, base['output_pins'][str(p)])
        single = json.loads((a.QUAL / 'single-bits.json').read_bytes())
        after = a.full_union(before, single)
        self.assertEqual(len(after['tests']), 777)
        self.assertEqual(after['tests'][:776], before['tests'])
        self.assertEqual(sum(map(len, after['metrics'].values())), 6162)

    def test_duplicate_membership_and_foreign_metric(self):
        base = a.life.read_bound(a.BASE / 'admission-manifest.json', a.BASE_SHA)
        p = a.BASE / 'combined-bits.json'
        before = a.life.read_bound(p, base['output_pins'][str(p)])
        single = json.loads((a.QUAL / 'single-bits.json').read_bytes())
        single['tests'] = [before['tests'][0]]
        with self.assertRaises(ValueError): a.full_union(before, single)
        single['tests'] = [str(a.RUN / 'code.vdb')]; single['metrics']['foreign'] = {}
        with self.assertRaises(ValueError): a.full_union(before, single)

    def test_dedup_uses_only_history(self):
        ledger = ['design'] + ['vdb%d' % i for i in range(776)]
        authority = {'historical': 'sha'}
        result = dict(ledger_members=776, duplicate=False,
                      members=[dict(vdb=p) for p in ledger[1:]], pins=authority)
        with patch.object(a, 'dedup', return_value=result) as f:
            a.historical(ledger, authority)
            self.assertIs(f.call_args[0][2], authority)
        result['pins'] = {'candidate': 'sha'}
        with patch.object(a, 'dedup', return_value=result), self.assertRaises(ValueError):
            a.historical(ledger, authority)

    def test_actual_fresh_singleton_no_model(self):
        path = a.QUAL / 'single-inputs.txt'
        q = self.q
        self.assertEqual(a.life.digest(path), q['output_pins'][str(path)])
        single = a.bitmap.collect(path)
        self.assertEqual(single, a.life.read_bound(a.QUAL / 'single-bits.json',
                         q['output_pins'][str(a.QUAL / 'single-bits.json')]))
        self.assertTrue(all(q['input_pins'].get(p) == h for p, h in single['input_hashes'].items()))


if __name__ == '__main__': unittest.main()
