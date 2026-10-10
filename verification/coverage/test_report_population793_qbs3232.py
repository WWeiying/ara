import inspect
import unittest

import report_population793_qbs3232 as c


class ExactUnion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = c.life.read_bound(c.REPORT/'config.json',c.REPORT_CONFIG_SHA)
        cls.q = c.life.read_bound(c.REPORT/'qualification.json',c.REPORT_QUAL_SHA)
        cls.base = (c.REPORT/'combined.el').read_text()
        cls.config = c.life.read_bound(c.suffix.LOCAL/'config.json',c.suffix.CONFIG_SHA)
        cls.extra = (c.suffix.LOCAL/'first.el').read_text()
        c.need(c.life.digest(c.REPORT/'combined.el') == cls.old['pins'][str(c.REPORT/'combined.el')], 'Native inherited EL pin')

    def test_actual_qualified791_exact_addition_disjoint(self):
        merged = c.union_gate(self.base,self.extra,self.config)
        old, new = c.physical(c.stable.semantic(self.base)), c.physical(c.stable.semantic(merged))
        self.assertEqual(sum(bin(v & ~old.get(k,0)).count('1') for k,v in new.items()),3232)
        self.assertEqual(c.stable.semantic(merged)[0], c.stable.semantic(self.base)[0])
        self.assertEqual(len(self.old['hierarchy_roots']),72)

    def test_already_owned_not_claimed_new(self):
        with self.assertRaises(ValueError): c.union_gate(self.base+'\n'+self.extra,self.extra,self.config)

    def test_foreign_scope_checksum_whole_direction_and_missing_rejected(self):
        for text in (self.extra.replace('3028946256','0',1),self.extra.replace('Toggle','Branch',1),
                     self.extra+'\nToggle foreign', '\n'.join(self.extra.splitlines()[:-1])):
            with self.assertRaises(ValueError): c.union_gate(self.base,text,self.config)

    def test_private_metadata_true_at_all_three_gates(self):
        prepare,check,verify,run = c.context()
        self.assertIn('EL_additions',prepare.__code__.co_consts)
        self.assertIn('EL_additions',check.__code__.co_consts)
        self.assertIn('new_exclusions_added',verify.__code__.co_consts)
        self.assertIsNot(check.__globals__,vars(c.engine))
        self.assertIs(check.__globals__['approved'],c.approved)
        self.assertIs(run.__globals__['check'],check)
        self.assertIs(run.__globals__['verify'],verify)
        self.assertIs(run.__code__,c.engine.run.__code__)
        self.assertIn('new_exclusions_added=False',inspect.getsource(c.engine.prepare))
        self.assertIn("config['new_exclusions_added'] is False",inspect.getsource(c.engine.check))

    def test_exact_consecutive_genealogy_not_samecount_other_branch(self):
        rows = [dict(population=i,manifest='earlier',seal='earlier') for i in range(784,794)]
        rows[-3].update(manifest=str(c.inherited.BASE),seal=c.inherited.BASE_SHA)
        rows[-2].update(manifest=str(c.suffix.BASE/'admission-manifest.json'),seal=c.suffix.BASE_SHA)
        rows[-1].update(manifest=str(c.suffix.NEXT/'admission-manifest.json'))
        self.assertEqual(len(c.suffix_chain(rows)),10)
        rows[-2]['seal'] = 'foreign'
        with self.assertRaises(ValueError): c.suffix_chain(rows)


if __name__ == '__main__': unittest.main()
