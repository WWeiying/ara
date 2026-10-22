import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import report_native_full771 as r


class Full771Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=r.life.read_bound(r.BASE/'config.json',r.predecessor.SEAL)
        cls.extra={key:r.qualified_family(key) for key in r.ADDED}
        cls.c=copy.deepcopy(cls.original)
        cls.c['new_families'].update(cls.extra)
        cls.c['output']=str(r.life.OUT/'HOST_ONLY_FULL771_NOT_CREATED')
        cls.text=(r.BASE/'combined.el').read_text()+''.join(i['el'] for i in cls.extra.values())
        cls.c['expected_union']=r.model()['records'](cls.text,cls.c)

    def test_actual_complete_canonical_retained_union(self):
        actual=r.canonical_gate(self.c,self.text)
        retained=copy.deepcopy(actual)
        for key,count in [('padding51',6528),('pack323',35632)]:
            self.assertEqual(len(retained.pop(key)),count)
        self.assertEqual(retained,self.original['expected_union'])

    def test_foreign_annotation_checksum_and_direction_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            c=dict(self.c,output=directory)
            Path(directory,'combined.el').write_text(self.text)
            annotation=next(l for l in self.text.splitlines() if l.startswith('ANNOTATION:'))
            for changed in [self.text.replace(annotation,'ANNOTATION: "FOREIGN"',1),
                            self.text.replace('0to1','1to0',1)]:
                with self.assertRaises(ValueError):r.canonical_gate(c,changed)
            headers=[l for l in self.text.splitlines() if l.startswith('CHECKSUM:')]
            self.assertTrue(headers)
            changed=self.text.replace(headers[0],'CHECKSUM: 0',1)
            with self.assertRaises(ValueError):r.canonical_gate(c,changed)

    def test_actual_retained_queue_owners_and_partial_protection(self):
        groups=r.model()['merged_observers'](self.c)
        queues=[g for k,g in groups.items() if k.startswith('queue312')]
        self.assertEqual(len(queues),20)
        for g in queues:
            self.assertIn('cmd_pop_o',g['targets'])
            self.assertIn('flush_i',g['targets'])
        additions=[g for k,g in groups.items() if k.startswith('padding51')]
        self.assertEqual(len(additions),4)
        self.assertTrue(all(not g['targets'] for g in additions))

    def test_actual_generated_source_full_five_stage_hook(self):
        selection=(r.BASE/'selection.tcl').read_text()+r.base.prior.selection_tail(
            dict(self.c,observer_captures=r.model()['merged_observers'](self.c)))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'selection.tcl';path.write_text(selection)
            result=r.host_hook(path,self.c)
        self.assertEqual(result['stages'],list(r.base.prior.STAGES))
        self.assertFalse(result['EDA_launched'])

    def test_actual_formal771_prefix_full6162_or(self):
        ledger,selected,pins=r.population(self.original)
        self.assertEqual(ledger[:-1],self.original['input_ledger'])
        self.assertEqual(len(selected),771)
        self.assertEqual(len(set(selected)),771)
        self.assertEqual(pins[str(r.MANIFEST)],r.MANIFEST_SHA)
        bad=dict(self.original,input_ledger=self.original['input_ledger'][:-1])
        with self.assertRaises(ValueError):r.population(bad)

    def test_closed_registry_hold_and_retained_contract(self):
        with self.assertRaises(ValueError):r.qualified_family('mfpu_constants272')
        held=r.held_candidates()
        self.assertFalse(held['mfpu_constants272']['included'])
        self.assertFalse(held['mfpu_constants272']['local_qualified'])
        self.assertFalse(held['monitor02']['included'])
        for key,value in [('hierarchy_roots',[]),('runtime_timeout_seconds',1)]:
            bad=copy.deepcopy(self.c);bad[key]=value
            with self.assertRaises(ValueError):r.retained_gate(bad,self.original)

    def test_transitive_tcl_dependency_drift_rejected(self):
        pins=r.dependency_pins()
        for name in ['report_native_increment770.tcl','report_native_increment769.tcl',
                     'report_native_batch768_v3.tcl','apply_points740_v4.tcl']:
            p=r.HERE/name
            self.assertEqual(pins[str(p)],r.life.digest(p))
        digest=r.life.digest;p=r.HERE/'report_native_increment769.tcl'
        with patch.object(r.life,'digest',lambda f:'0'*64 if Path(f)==p else digest(f)):
            changed=r.dependency_pins()
            self.assertNotEqual(pins[str(p)],changed[str(p)])

    def test_namespace_budget_and_real_snapshot_binding(self):
        ns=r.namespace()
        self.assertEqual(ns['TCL'],r.TCL)
        self.assertIn('audit_six',ns['verify'].__code__.co_names)
        self.assertIn('audit_observers',ns['verify'].__code__.co_names)
        self.assertEqual(self.original['runtime_timeout_seconds'],5400)
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            with patch.object(r.life,'read_bound',return_value=dict(self.c,schema=r.SCHEMA,population=771)):
                with self.assertRaises(ValueError):ns['snapshot_stdout'](dict(config_seal='0'*64),out)


if __name__=='__main__':unittest.main()
