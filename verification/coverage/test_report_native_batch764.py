import copy
import json
from pathlib import Path
import unittest
import report_native_batch764 as r


class Batch764(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads((r.BASE/'config.json').read_bytes())
        cls.additions = {}
        for key,(name,sha) in r.CAPTURES.items():
            out = r.life.OUT/name
            q = r.life.read_bound(out/'capture-result.json',sha)
            r.prep.native_gate(key,q)
            c = r.life.read_bound(out/'config.json',q['config_seal'])
            if key == 'c910240': actual = r.prep.c910.parse_el((out/'first.el').read_text(),c)
            else: actual = r.prep.vmfpu.native.native_records((out/'first.el').read_text())
            cls.additions[key] = dict(output=str(out),config=c,qualification=q,seal=sha,
                                     canonical_records=r.old.normalized(actual))

    def config(self):
        c = copy.deepcopy(self.original); c['future_captures'] = self.additions
        for key in ('vmfpu10','sldu2'): c['plan'],_ = r.prep.merge_fsm(c['plan'],self.additions[key]['config']['plan'])
        r.add_c910_groups(c)
        return c

    def test_actual_approved_capture_counts(self):
        self.assertEqual(set(self.additions), {'vmfpu10','sldu2','c910240'})
        self.assertEqual(len(self.additions['c910240']['canonical_records']),240)

    def test_actual_retained_union_and_exact_additions(self):
        c = self.config()
        text = (r.BASE/'applied.el').read_text()+''.join((Path(i['output'])/'first.el').read_text() for i in self.additions.values())
        result = r.records(text,c)
        r.partition_check(result,self.original['expected_union'],self.additions)
        damaged = copy.deepcopy(result); damaged['c910240'].pop()
        with self.assertRaises(Exception): r.partition_check(damaged,self.original['expected_union'],self.additions)

    def test_no_protected_field_acceptance(self):
        c = self.config()
        text = (Path(self.additions['c910240']['output'])/'first.el').read_text()
        text = text.replace('ex4_frac_52','ex4_out_result',1)
        with self.assertRaises(Exception):r.records(text,c)

    def test_complete_c910_guard_scopes_preserved(self):
        c = self.config(); groups = c['toggle_groups'][len(self.original['toggle_groups']):]
        self.assertEqual(len(groups),82)
        self.assertEqual(sum(len(g['targets']) for g in groups),240)
        self.assertEqual(sum(len(g['protected']) for g in groups),3740)

    def test_fsm_full_complement_plus_twelve(self):
        c = self.config()
        self.assertEqual(c['plan']['targets'],self.original['plan']['targets']+12)
        self.assertEqual(c['plan']['protected'],self.original['plan']['protected']-10+34)
        self.assertEqual(len(c['plan']['groups']),34)

    def test_generated_bracketed_source_and_five_stages(self):
        import tempfile
        c = self.config()
        selection = (r.BASE/'selection.tcl').read_text()+r.selection_tail(c,self.original)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'selection.tcl'; path.write_text(selection)
            r.old.generated.evaluate(path,{str(path):r.life.digest(path)},('fx_groups','combo_groups'))
            evidence = r.host_hook(path,c)
            self.assertIn('FIVE_STAGE_PASS',evidence['status'])

    def test_namespace_substantive_verifier_and_own_tcl(self):
        ns = r.namespace()
        self.assertEqual(ns['TCL'],r.TCL)
        self.assertIs(ns['records'],r.records)
        self.assertIs(ns['check'],r.check)
        self.assertIn('batch_scale',ns['verify'].__code__.co_consts)


if __name__ == '__main__':unittest.main()
