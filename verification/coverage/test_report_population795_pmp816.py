"""Real admitted DIV795 host audits and negative typed source-zero tests."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import report_population795_pmp816 as r


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = r.prior.prior.inherited.Reader()
        cls.manifest = cls.reader.read(r.BASE,r.BASE_SHA,True)
        cls.old = cls.reader.read(r.handoff.GLOBAL/'config.json',r.handoff.GLOBAL_CONFIG_SHA,True)
        cls.handoff = cls.reader.read(r.HANDOFF,r.HANDOFF_SHA,True)
        cls.pins = r.stable.merge(cls.manifest['input_pins'],cls.manifest['output_pins'],cls.handoff['input_pins'])
        cls.ledger = cls.reader.read(r.BASE.parent/'combined-inputs.txt',cls.pins[str(r.BASE.parent/'combined-inputs.txt')]).decode().splitlines()
        cls.bits = cls.reader.read(r.BASE.parent/'combined-bits.json',cls.pins[str(r.BASE.parent/'combined-bits.json')],True)
        cls.record = dict(population=795,manifest=str(r.BASE),seal=r.BASE_SHA,new_vdb=cls.ledger[-1])
        cls.old_source = {k:cls.old[k] for k in ('input_ledger','hierarchy_roots','tool_identity')}
        cls.source = dict(cls.old_source,input_ledger=cls.ledger)
        cls.chain = cls.old['genealogy']+[cls.record]
        native = r.prior.prior.suffix.native
        path = next((Path(cls.ledger[-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        cls.current = cls.reader.read(r.BASE.parent/'combined-toggle-bits.json',cls.pins[str(r.BASE.parent/'combined-toggle-bits.json')],True)
        cls.single,_ = native.rows(path,set(cls.current))
        before_path = r.prior.BASE.parent/'combined-toggle-bits.json'
        cls.before = cls.reader.read(before_path,cls.pins[str(before_path)],True)
        cls.soc = cls.reader.read(r.prior.native.old.SOURCE,r.prior.native.old.SOURCE_SHA,True)
        cls.pmp = cls.reader.read(r.handoff.local.SOURCE,r.handoff.local.SOURCE_SHA,True)
        cls.qbs_c = cls.reader.read(r.prior.prior.suffix.LOCAL/'config.json',r.prior.prior.suffix.CONFIG_SHA,True)
        p = r.life.OUT/'qbs-bank1-group-hit789-all-cycle-source-review-agent-20261008-01.json'
        qbs = cls.reader.read(p,cls.qbs_c['plan']['source_review_sha256'],True)
        cls.targets = {t['name']:t for t in qbs['source_targets']}
        cls.scopes = {t['scope'] for t in cls.soc['candidates']} | {t['scope'] for t in cls.pmp['fresh_candidates']} | {qbs['scope']}
        db = Path(cls.ledger[0])/'snps/coverage/db'
        _, cls.defs = native.definitions(*(native.xml(db/n) for n in
            ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')),cls.scopes)
        cls.nodes = list(ET.fromstring(cls.defs[qbs['scope']]['shape']).find('tglshape'))
        cls.rows = {s:cls.single[s] for s in cls.scopes}

    def audit(self, rows=None, definitions=None, soc=None, pmp=None):
        return r.typed_added_zero(self.rows if rows is None else rows,
            self.defs if definitions is None else definitions,
            self.soc if soc is None else soc,self.pmp if pmp is None else pmp,self.nodes,self.targets)

    def hit(self,scope,coordinate):
        rows = copy.deepcopy(self.rows)
        rows[scope]['bits'] = hex(int(rows[scope]['bits'],16) | (1 << (rows[scope]['width']-1-coordinate)))
        return rows

    def test_actual795_all_typed_families_suffix_and_full_OR(self):
        reader = r.prior.prior.inherited.Reader()
        result = r.suffix_zero(reader,dict(self.pins),self.record,self.source)
        self.assertEqual(result['complete_Toggle_OR_instances'],2989)
        self.assertEqual(len(result['suffix_and_full_population']),2)
        self.assertTrue(all(v['all_source_zero'] for v in result['suffix_and_full_population']))
        self.assertEqual(len(result['RR190_classpadding_FPNEW90']),1)

    def test_actual795_exact794_prefix_metric_roots_and_chain(self):
        r.corpus_gate(self.source,self.bits,self.chain,self.old_source,self.old['genealogy'])
        r.toggle_or_gate(self.before,self.current,self.single)

    def test_prefix_duplicate_endpoint_and_roots_rejected(self):
        for kind in ('prefix','duplicate','roots','tool','chain'):
            source = copy.deepcopy(self.source);chain = copy.deepcopy(self.chain)
            if kind == 'prefix':source['input_ledger'][1:3] = reversed(source['input_ledger'][1:3])
            elif kind == 'duplicate':source['input_ledger'][-1] = source['input_ledger'][-2]
            elif kind == 'roots':source['hierarchy_roots'] = source['hierarchy_roots'][:-1]
            elif kind == 'tool':source['tool_identity'] = {}
            else:chain[-1]['seal'] = '0'*64
            with self.subTest(kind=kind),self.assertRaises(Exception):
                r.corpus_gate(source,self.bits,chain,self.old_source,self.old['genealogy'])

    def test_metric_missing_extra_and_width_or_drift_rejected(self):
        for kind in ('missing','extra'):
            bits = copy.deepcopy(self.bits)
            if kind == 'missing':bits['metrics']['line'].pop(next(iter(bits['metrics']['line'])))
            else:bits['metrics']['line']['foreign'] = dict(width=1,checksum='0',bits='0x0')
            with self.subTest(kind=kind),self.assertRaises(Exception):
                r.corpus_gate(self.source,bits,self.chain,self.old_source,self.old['genealogy'])
        for kind in ('scope','width','checksum','bits'):
            current = copy.deepcopy(self.current);key = next(iter(current))
            if kind == 'scope':current['foreign'] = current.pop(key)
            elif kind == 'width':current[key]['width'] += 1
            elif kind == 'checksum':current[key]['checksum'] = '0'
            else:current[key]['bits'] = hex(int(current[key]['bits'],16)^1)
            with self.subTest(kind=kind),self.assertRaises(Exception):r.toggle_or_gate(self.before,current,self.single)

    def test_SOC61_source_hit_rejected(self):
        target = self.soc['candidates'][0]
        with self.assertRaises(Exception):self.audit(rows=self.hit(target['scope'],target['compiled_attributes']['serialized_offset']))

    def test_PMP816_source_hit_and_module_drift_rejected(self):
        target = self.pmp['fresh_candidates'][0]
        with self.assertRaises(Exception):self.audit(rows=self.hit(target['scope'],target['compiled']['serialized_offset']))
        definitions = copy.deepcopy(self.defs);definitions[target['scope']]['module']['chksum'] = '0'
        with self.assertRaises(Exception):self.audit(definitions=definitions)

    def test_QBS_partial_source_hit_and_coordinate_drift_rejected(self):
        target = next(iter(self.targets.values()))
        with self.assertRaises(Exception):self.audit(rows=self.hit(r.prior.prior.suffix.SCOPE,target['actual_missing789_coordinates'][0]))
        targets = copy.deepcopy(self.targets);targets[target['name']]['actual_missing789_coordinates'][0] += 1
        with self.assertRaises(Exception):
            r.typed_added_zero(self.rows,self.defs,self.soc,self.pmp,self.nodes,targets)

    def test_dynamic_QBS_complement_not_claimed_zero(self):
        target = next(iter(self.targets.values()))
        bit = next(b for b in range(32) if b not in target['source_zero_bit_indices'])
        offset = target['actual_missing789_coordinates'][0]-2*target['source_zero_bit_indices'][0]
        self.assertTrue(self.audit(rows=self.hit(r.prior.prior.suffix.SCOPE,offset+2*bit))['all_source_zero'])

    def test_missing_family_scope_and_checksum_rejected(self):
        rows = copy.deepcopy(self.rows);rows.pop(next(iter(rows)))
        with self.assertRaises(Exception):self.audit(rows=rows)
        rows = copy.deepcopy(self.rows);rows[r.prior.prior.suffix.SCOPE]['checksum'] = '0'
        with self.assertRaises(Exception):self.audit(rows=rows)

    def test_exact_parent_handoff_and_no_generic_fallback(self):
        with self.assertRaises(Exception):r.context(r.HANDOFF,'0'*64)
        with self.assertRaises(Exception):r.approved(None,r.BASE,'0'*64)
        reader = r.prior.prior.inherited.Reader()
        with patch.object(r.engine,'approved',return_value=(self.source,{},'GENERIC FALLBACK',self.bits,self.chain,{})), \
             patch.object(r.inherited,'approved_for',side_effect=ValueError('missing strict authority')):
            with self.assertRaises(Exception):r.approved(reader,r.BASE,r.BASE_SHA)

    def test_private_five_stage_and_runtime_gates_preserved(self):
        old = r.inherited.context(r.HANDOFF,r.HANDOFF_SHA);new = r.context()
        for i in range(3):self.assertEqual(old[i].__code__,new[i].__code__)
        self.assertIs(new[3].__globals__['check'],new[1])
        self.assertIs(new[3].__globals__['verify'],new[2])
        self.assertEqual(new[1].__globals__['SCHEMA'],r.SCHEMA)
        for path,sha in r.inherited.dependencies().items():self.assertEqual(r.dependencies()[path],sha)


if __name__ == '__main__':unittest.main()
