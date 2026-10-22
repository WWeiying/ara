import copy
import unittest
from unittest.mock import patch

import report_population794_soc61 as c


class Report794(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = c.life.read_bound(c.LOCAL/'config.json',c.LOCAL_SHA)
        cls.report = c.life.read_bound(c.REPORT/'config.json',c.REPORT_CONFIG_SHA)
        cls.base = (c.REPORT/'combined.el').read_text()
        cls.extra = (c.LOCAL/'second.el').read_text()
        cls.proof = c.life.read_bound(c.native.old.SOURCE,c.native.old.SOURCE_SHA)

    def test_actual_EL_union_preserves_QBS_and_all_old_masks(self):
        text = c.union_gate(self.base,self.extra,self.config)
        old, new = c.physical(c.stable.semantic(self.base)),c.physical(c.stable.semantic(text))
        self.assertEqual(sum(bin(v & ~old.get(k,0)).count('1') for k,v in new.items()),7686)
        self.assertEqual(c.stable.semantic(self.base)[0],c.stable.semantic(text)[0])
        self.assertEqual(len(self.report['hierarchy_roots']),72)
        self.assertEqual(self.report['EL_additions']['new_direction_count'],3232)

    def test_already_owned_and_partial_overlap_rejected(self):
        with self.assertRaises(ValueError): c.union_gate(self.base+'\n'+self.extra,self.extra,self.config)

    def test_foreign_metric_checksum_range_missing_duplicate(self):
        lines = self.extra.splitlines()
        missing = '\n'.join(line for index,line in enumerate(lines)
                            if index != next(i for i,line in enumerate(lines) if line.startswith('Toggle ')))
        for bad in (self.extra.replace('Toggle','Branch',1),self.extra.replace('CHECKSUM: "','CHECKSUM: "0',1),
                    self.extra.replace('[63:0]','[62:0]',1),
                    missing,self.extra+'\n'+self.extra):
            with self.subTest(text=bad[:80]):
                with self.assertRaises(ValueError): c.union_gate(self.base,bad,self.config)

    def test_wrong_native_role_rejected(self):
        bad = copy.deepcopy(self.config)
        node = next(n for i in bad['instances'] for n in i['typed_objects']
                    if n['type'] == '3' and n['portnode'] == '2' and
                    any(s['name'] == n['name'] for s in i['signals']))
        node['portnode'] = '0'
        with self.assertRaises(ValueError): c.native.el_gate(self.extra,bad)

    def test_losing_one_inherited_mask_rejected(self):
        old = c.stable.semantic(self.base); extra = c.stable.semantic(self.extra)
        masks = dict(old[1]); masks.update(extra[1]); masks.pop(next(iter(old[1])))
        with patch.object(c.stable,'semantic',side_effect=[old,extra,(old[0],masks)]):
            with self.assertRaises(ValueError): c.union_gate(self.base,self.extra,self.config)

    def test_tampered_native_protected_row_rejected(self):
        i = self.config['instances'][0]
        before = c.native.previous.bind(i,(c.LOCAL/'native_before_0.tsv').read_text())
        actual = copy.deepcopy(before)
        protected = next(label for label in actual if label not in c.native.old.labels(i))
        actual[protected]['coverage'] = 'fabricated'
        with self.assertRaises(ValueError): c.native.old.stage_gate(i,before,actual,'applied')

    def test_source_constant_hit_and_wrong_offset_rejected(self):
        r = copy.deepcopy(self.proof['candidates'][0]); scope = r['scope']
        node = r['compiled_attributes']; width = node['serialized_offset']+2*r['width']
        import xml.etree.ElementTree as ET
        root = ET.Element('tgldef'); shape = ET.SubElement(root,'tglshape')
        if node['serialized_offset']:
            ET.SubElement(shape,'vectornode',name='prefix',left=str(node['serialized_offset']//2-1),right='0')
        attrs = {k:v for k,v in node.items() if k not in ('serialized_offset','logical_width','missing_coordinates','missing_slots')}
        ET.SubElement(shape,'vectornode',attrs)
        definitions = {scope:dict(shape=ET.tostring(root).decode())}
        rows = {scope:dict(width=width,checksum=r['toggle_checksum'],bits='0')}
        proof = dict(candidates=[r])
        c.constant_rows(rows,definitions,proof)
        rows[scope]['bits'] = hex(1)
        with self.assertRaises(ValueError): c.constant_rows(rows,definitions,proof)
        rows[scope]['bits'] = '0'; r['compiled_attributes']['serialized_offset'] += 2
        with self.assertRaises(ValueError): c.constant_rows(rows,definitions,proof)

    def test_real_first_second_semantics(self):
        first = (c.LOCAL/'first.el').read_text()
        self.assertEqual(c.native.el_gate(first,self.config),c.native.el_gate(self.extra,self.config))
        self.assertEqual(c.physical(c.stable.semantic(first)),c.physical(c.stable.semantic(self.extra)))

    def test_private_all_gates_new_metadata_and_run_bindings(self):
        prepare,check,verify,run = c.context()
        self.assertIs(prepare.__globals__['approved'],c.approved)
        self.assertIs(check.__globals__['dependencies'],c.dependencies)
        self.assertEqual(prepare.__globals__['SCHEMA'],c.SCHEMA)
        self.assertIs(run.__globals__['check'],check)
        self.assertIs(run.__globals__['verify'],verify)
        self.assertIs(run.__code__,c.engine.run.__code__)
        self.assertIn('EL_additions',prepare.__code__.co_consts)
        self.assertIn('new_exclusions_added',verify.__code__.co_consts)
        self.assertIsNot(prepare.__globals__,vars(c.engine))

    def test_genealogy_reject_same_count_fork(self):
        rows = [dict(population=i,manifest='old',seal='old') for i in range(784,795)]
        rows[-4].update(manifest=str(c.prior.inherited.BASE),seal=c.prior.inherited.BASE_SHA)
        rows[-3].update(manifest=str(c.prior.suffix.BASE/'admission-manifest.json'),seal=c.prior.suffix.BASE_SHA)
        rows[-2].update(manifest=str(c.prior.suffix.NEXT/'admission-manifest.json'),seal=c.FORMAL793_SHA)
        rows[-1].update(manifest=str(c.BASE),seal=c.BASE_SHA)
        self.assertEqual(len(c.suffix_chain(rows)),11)
        for index,key in ((-1,'seal'),(-2,'seal'),(-3,'manifest')):
            bad = copy.deepcopy(rows); bad[index][key] = 'foreign'
            with self.assertRaises(ValueError): c.suffix_chain(bad)

    def test_actual_local_full_verifier_and_protected_inventory(self):
        _,_,extra = c.local_authority(c.prior.inherited.Reader())
        self.assertEqual(extra,self.extra)
        self.assertEqual(len(self.config['instances']),18)
        self.assertEqual(sum(len(i['typed_objects']) for i in self.config['instances']),9012)

    def test_actual_794_approved_source_suffix_zero(self):
        reader = c.prior.inherited.Reader()
        source,pins,text,bits,chain,activity = c.approved(reader,c.BASE,c.BASE_SHA)
        self.assertEqual(len(source['input_ledger']),795)
        self.assertEqual(bits['tests'],source['input_ledger'][1:])
        self.assertEqual(chain[-1]['seal'],c.BASE_SHA)
        self.assertTrue(activity['EL_additions']['new_exclusions_added'])
        self.assertEqual(activity['EL_additions']['new_direction_count'],7686)
        self.assertTrue(activity['EL_additions']['inherited_QBS3232_retained_not_readded'])
        audits = activity['source_constant_suffix_audit']['new_suffixes']
        self.assertTrue(activity['source_constant_suffix_audit']['SOC61_complete_population792_zero']['complete_OR_zero'])
        self.assertEqual([a['population'] for a in audits],[793,794])
        self.assertTrue(all(a['SOC61_hits'] == a['QBS3232_hits'] == [] for a in audits))
        self.assertEqual(c.stable.semantic(text),c.stable.semantic(c.union_gate(self.base,self.extra,self.config)))
        self.assertIn(str(c.LOCAL/'capture-result.json'),pins)


if __name__ == '__main__': unittest.main()
