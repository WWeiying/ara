"""Host-only full794 PMP report contracts; no simulator or GUI launch."""
import copy
import unittest
from unittest.mock import patch

import report_population794_pmp816 as r


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = r.life.OUT/'host-only-pmp816-fixture/handoff.json'
        cls.seal = 'a'*64
        cls.c = r.life.read_bound(r.handoff.GLOBAL/'config.json', r.handoff.GLOBAL_CONFIG_SHA)
        cls.g = r.life.read_bound(r.handoff.GLOBAL/'qualification.json', r.handoff.GLOBAL_SHA)
        cls.local_q = r.life.read_bound(r.handoff.LOCAL/'capture-result.json', r.handoff.LOCAL_SHA)
        cls.local_c = r.life.read_bound(r.handoff.LOCAL/'config.json', cls.local_q['config_seal'])
        cls.base = (r.handoff.GLOBAL/'combined.el').read_text()
        cls.extra = (r.handoff.LOCAL/'second.el').read_text()
        cls.text = r.handoff.union_gate(cls.base, cls.extra, cls.local_c)
        cls.q = dict(status='PMP816_EXACT794_UNION_HANDOFF_PREPARED_NOT_POPULATION_APPLIED',
            population=794, global_qualification_sha256=r.handoff.GLOBAL_SHA,
            local_qualification_sha256=r.handoff.LOCAL_SHA, fields=816, directions=2176,
            source_MDA_HOLD=13, exact_physical_disjoint=True, inherited_EL_bytes_preserved=True,
            EDA_started=False, population_application=False, initial_X_qualified=False,
            global_combined_EL_sha256=r.stable.merge(cls.c['pins'],cls.g['output_pins'])[str(r.handoff.GLOBAL/'combined.el')],
            union_semantic_sha256=r.stable.semantic_seal(r.stable.semantic(cls.text)),
            input_pins=r.stable.merge(cls.c['pins'], cls.g['output_pins'], cls.local_c['pins'], cls.local_q['pins'],
                {str(r.handoff.GLOBAL/'config.json'):r.handoff.GLOBAL_CONFIG_SHA,
                 str(r.handoff.GLOBAL/'qualification.json'):r.handoff.GLOBAL_SHA,
                 str(r.handoff.LOCAL/'config.json'):cls.local_q['config_seal'],
                 str(r.handoff.LOCAL/'capture-result.json'):r.handoff.LOCAL_SHA}),
            output_pins={str(cls.path.parent/'candidate-union.el'): 'b'*64})
        cls.source = {k:cls.c[k] for k in ('input_ledger','hierarchy_roots','tool_identity')}

    def fixture(self, q=None, source=None):
        data = self.q if q is None else q
        class Reader:
            pins = {}
            def read(self, path, seal, parse=False):
                if path == ReportTests.path: return copy.deepcopy(data)
                if path == ReportTests.path.parent/'candidate-union.el': return ReportTests.text.encode('ascii')
                self.pins[str(path)] = seal
                if parse: return r.life.read_bound(path, seal)
                r.need(r.life.digest(path) == seal, 'Actual fixture file pin')
                return path.read_bytes()
        value = (copy.deepcopy(self.source if source is None else source), {}, '',
                 {'tests':self.c['input_ledger'][1:]}, [], {})
        return Reader(), patch.object(r.engine, 'approved', return_value=value)

    def test_actual_complete_EL_union_full794_roots(self):
        reader, mocked = self.fixture()
        with mocked:
            source, pins, text, bits, chain, activity = r.approved_for(self.path,self.seal)(
                reader,r.prior.BASE,r.prior.BASE_SHA)
        self.assertEqual(text,self.text)
        self.assertTrue(text.startswith(self.base.rstrip('\n')+'\n'))
        self.assertEqual(len(source['hierarchy_roots']),72)
        self.assertEqual(len(bits['tests']),794)
        self.assertEqual(activity['EL_additions']['new_direction_count'],2176)
        self.assertEqual(activity['EL_additions']['source_MDA_HOLD'],13)

    def test_handoff_mutations_rejected(self):
        for key, value in [('population',795),('fields',815),('directions',2175),
                           ('source_MDA_HOLD',0),('EDA_started',True),
                           ('population_application',True),('initial_X_qualified',True),
                           ('exact_physical_disjoint',False),('local_qualification_sha256','0'*64)]:
            q = dict(self.q, **{key:value})
            with self.subTest(key=key), self.assertRaises(Exception): r.handoff_gate(q)

    def test_population_root_and_tool_drift_rejected(self):
        for key in ('input_ledger','hierarchy_roots','tool_identity'):
            source = copy.deepcopy(self.source)
            source[key] = source[key][:-1] if isinstance(source[key],list) else {}
            reader, mocked = self.fixture(source=source)
            with self.subTest(key=key), mocked, self.assertRaises(Exception):
                r.approved_for(self.path,self.seal)(reader,r.prior.BASE,r.prior.BASE_SHA)

    def test_missing_receipt_rejected_no_output(self):
        functions = r.context(self.path,self.seal)
        with self.assertRaises(Exception):
            functions[1](r.life.OUT/'absent-pmp-report', '0'*64)

    def test_manifest_rebase_rejected(self):
        with self.assertRaises(Exception):
            r.approved_for(self.path,self.seal)(None,r.prior.BASE,'0'*64)

    def test_private_lifecycle_and_five_stage_verifier_preserved(self):
        old = r.prior.context(); new = r.context(self.path,self.seal)
        for i in range(3): self.assertEqual(new[i].__code__,old[i].__code__)
        self.assertEqual(new[3].__code__,r.engine.run.__code__)
        self.assertIs(new[3].__globals__['check'],new[1])
        self.assertIs(new[3].__globals__['verify'],new[2])
        self.assertEqual(new[1].__globals__['SCHEMA'],r.SCHEMA)

    def test_runtime_foreign_identity_and_unsealed_handoff_rejected(self):
        with self.assertRaises(Exception): r.context(self.path,'bad')
        with patch.object(r.life,'read_bound',return_value=dict(schema='foreign')):
            with self.assertRaises(Exception): r.runtime_context(self.path.parent,'0'*64)

    def test_dependency_closure_includes_frozen_Tcl(self):
        pins = r.dependencies()
        for path, seal in r.prior.dependencies().items(): self.assertEqual(pins[path],seal)
        self.assertIn(str(r.HERE/'test_report_population794_pmp816.py'),pins)
        self.assertIn(str(r.handoff.local.__file__),pins)

    def test_omitted_native_protection_pin_rejected(self):
        q = copy.deepcopy(self.q)
        del q['input_pins'][str(r.handoff.LOCAL/'config.json')]
        reader, mocked = self.fixture(q=q)
        with mocked, self.assertRaises(Exception):
            r.approved_for(self.path,self.seal)(reader,r.prior.BASE,r.prior.BASE_SHA)

    def test_runtime_entry_and_receipt_pin_drift_rejected(self):
        entry = str(r.HERE/'report_population794_pmp816.py')
        c = dict(schema=r.SCHEMA,successor_entry=entry,output=str(self.path.parent),
                 EL_additions=dict(handoff_path=str(self.path),handoff_seal=self.seal),
                 pins={entry:r.life.digest(entry),str(self.path):self.seal})
        for key in (entry,str(self.path)):
            bad = copy.deepcopy(c);bad['pins'][key]='0'*64
            with self.subTest(key=key), patch.object(r.life,'read_bound',return_value=bad):
                with self.assertRaises(Exception):r.runtime_context(self.path.parent,'0'*64)


if __name__ == '__main__': unittest.main()
