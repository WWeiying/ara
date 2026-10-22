import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import report_population797_inherited796 as r


class Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = r.stable.Reader()
        cls.previous = cls.reader.read(r.REPORT / 'config.json', r.CONFIG_SHA, True)
        cls.q = cls.reader.read(r.REPORT / 'qualification.json', r.QUAL_SHA, True)
        cls.base = cls.reader.read(r.BASE, r.BASE_SHA, True)
        cls.pins = r.stable.merge(cls.previous['pins'], cls.q['output_pins'], cls.base['input_pins'], cls.base['output_pins'])
        def doc(folder, name):
            path = folder / name
            return cls.reader.read(path, cls.pins[str(path)], True)
        cls.before = doc(r.inherited.BASE.parent, 'combined-bits.json')
        cls.bits = doc(r.BASE.parent, 'combined-bits.json')
        cls.single = doc(r.BASE.parent, 'single-bits.json')
        cls.bt = doc(r.inherited.BASE.parent, 'combined-toggle-bits.json')
        cls.toggle = doc(r.BASE.parent, 'combined-toggle-bits.json')
        cls.path = r.admission.RUN / 'code.vdb/snps/coverage/db/testdata' / r.admission.r.NAME / 'tgl.verilog.data.xml'
        cls.sample, _ = r.admission.r.toggle.rows(cls.path, list(cls.bt))
        cls.ledger = (r.BASE.parent / 'combined-inputs.txt').read_text().splitlines()
        cls.source = dict(input_ledger=cls.ledger, hierarchy_roots=cls.previous['hierarchy_roots'],
                          tool_identity=cls.previous['tool_identity'])
        cls.chain = cls.previous['genealogy'] + [dict(population=797, manifest=str(r.BASE), seal=r.BASE_SHA, new_vdb=cls.ledger[-1])]
        cls.ac, cls.pc, cls.packet, _, more = r.inherited.qualification(cls.reader)
        cls.pins = r.stable.merge(cls.pins, more)
        cls.design = r.inherited.alua.source.Design(Path(cls.ledger[0]))

    def test_actual_approved797_full_audit_and_all_pins_no_EDA(self):
        reader = r.stable.Reader()
        with patch.object(r.engine, 'run', side_effect=AssertionError('No EDA')):
            source, pins, text, bits, chain, activity = r.approved(reader, r.BASE, r.BASE_SHA)
            reader.finish(r.stable.merge(pins, r.dependencies()))
        self.assertEqual(source['input_ledger'], self.ledger)
        self.assertEqual(text.encode('ascii'), (r.REPORT / 'combined.el').read_bytes())
        self.assertEqual(bits, self.bits)
        self.assertEqual(chain, self.chain)
        self.assertFalse(activity['new_exclusions_added'])
        self.assertFalse(activity['blanket_all_EL_inactive_claim'])
        self.assertEqual(activity['complete_Toggle_OR_instances'], 2989)
        self.assertEqual(activity['VSMUL797_constant_suffix_and_full_audit']['population'], 797)
        self.assertTrue(all(pins.get(p) == h for p,h in self.previous['pins'].items()))

    def test_actual_qualified796_report_and_full_EL(self):
        r.report_gate(self.previous, self.q)
        text = r.inherited_el(self.reader, self.previous, self.q, self.pins)
        self.assertEqual(text, (r.REPORT / 'combined.el').read_text())

    def test_missing_inherited_gate_or_wrong_population(self):
        for key, value in (('all_other_bits_protected', False), ('raw_reset_final_equal', False),
                           ('actual_selected_tests', 795), ('config_seal', '0'*64), ('new_exclusions_added', False)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                r.report_gate(self.previous, dict(self.q, **{key:value}))

    def test_inherited_pin_or_EL_authority_loss(self):
        for key in ('source_design_native_pins', 'EL_additions'):
            q = copy.deepcopy(self.q)
            q[key].pop(next(iter(q[key])))
            with self.assertRaises(ValueError):
                r.report_gate(self.previous, q)

    def test_actual_exact796prefix_and797_OR(self):
        r.corpus_gate(self.source, self.bits, self.chain, self.previous)
        r.engine.population_gate(self.before, self.bits, self.single, self.previous['input_ledger'], self.ledger)
        r.admission.c.exact_raw_union(self.before, self.single, self.bits, population=796)
        r.admission.toggle_or(self.bt, self.sample, self.toggle)

    def test_prefix_duplicate_roots_tool_or_lineage_drift(self):
        for mode in ('prefix', 'duplicate', 'roots', 'tools', 'seal', 'chain', 'missing'):
            source, bits, chain = copy.deepcopy((self.source, self.bits, self.chain))
            if mode == 'prefix':
                source['input_ledger'][1:3] = reversed(source['input_ledger'][1:3])
            elif mode == 'duplicate':
                source['input_ledger'][-1] = source['input_ledger'][-2]
            elif mode == 'roots':
                source['hierarchy_roots'].pop()
            elif mode == 'tools':
                source['tool_identity'] = {}
            elif mode == 'seal':
                chain[-1]['seal'] = '0'*64
            elif mode == 'chain':
                chain.pop(0)
            else:
                bits['metrics']['fsm'].pop(next(iter(bits['metrics']['fsm'])))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                r.corpus_gate(source, bits, chain, self.previous)

    def test_full_metric_lost_hit_and_shape(self):
        for mode in ('lost', 'shape'):
            bits = copy.deepcopy(self.bits)
            row = next(v for v in bits['metrics']['line'].values() if int(v['bits'], 16))
            if mode == 'lost':
                row['bits'] = '0x0'
            else:
                row['checksum'] = 'wrong'
            with self.assertRaises(ValueError):
                r.admission.c.exact_raw_union(self.before, self.single, bits)

    def test_full_Toggle_lost_hit_or_extra_scope(self):
        for mode in ('lost', 'extra'):
            rows = copy.deepcopy(self.toggle)
            row = next(v for v in rows.values() if int(v['bits'], 16))
            if mode == 'lost':
                row['bits'] = '0x0'
            else:
                rows['foreign'] = row
            with self.assertRaises(ValueError):
                r.admission.toggle_or(self.bt, self.sample, rows)

    def test_actual_ALUA137_PTW156_single_and_full_zero(self):
        for bits, toggle in ((self.single, self.sample), (self.bits, self.toggle)):
            result = r.inherited.added_zero(bits, toggle, self.ac, self.pc, self.packet, self.design)
            self.assertTrue(result['ALUA137_zero'] and result['PTW156_zero'])

    def test_suffix_or_full_ALUA_collision(self):
        for original in (self.single, self.bits):
            bits = copy.deepcopy(original)
            scope, metrics = next(iter(self.ac['plan']['scopes'].items()))
            target = next(e for e in metrics['branch'] if e['target'])
            row = bits['metrics']['branch'][scope]
            row['bits'] = hex(int(row['bits'], 16) | 1 << (row['width'] - 1 - target['point']['raw_index']))
            with self.assertRaises(ValueError):
                r.inherited.added_zero(bits, self.toggle, self.ac, self.pc, self.packet, self.design)

    def test_suffix_or_full_PTW_collision(self):
        for original in (self.sample, self.toggle):
            rows = copy.deepcopy(original)
            instance = self.pc['instances'][0]
            row = rows[instance['scope']]
            index = instance['signals'][0]['missing_coordinates'][0]
            row['bits'] = hex(int(row['bits'], 16) | 1 << (row['width'] - 1 - index))
            with self.assertRaises(ValueError):
                r.inherited.added_zero(self.bits, rows, self.ac, self.pc, self.packet, self.design)

    def test_no_endpoint_fallback(self):
        with self.assertRaises(ValueError):
            r.approved(None, r.inherited.BASE, r.inherited.BASE_SHA)

    def test_five_stage_engine_unchanged_no_new_waiver(self):
        functions = r.context()
        for i, original in enumerate((r.engine.prepare, r.engine.check, r.engine.verify)):
            self.assertEqual(functions[i].__code__, original.__code__)
        self.assertIs(functions[3].__globals__['check'], functions[1])
        self.assertIs(functions[3].__globals__['verify'], functions[2])
        self.assertIs(functions[1].__globals__['approved'], r.approved)
        self.assertEqual(len(r.stable.STAGES), 5)
        for p,h in r.inherited.dependencies().items():
            self.assertEqual(r.dependencies()[p], h)


if __name__ == '__main__':
    unittest.main()
