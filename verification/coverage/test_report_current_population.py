import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import report_current_population as m
import test_report_global777_compact as fixtures

FORMAL = m.OUT / 'btb-ring-admitted779-parent-20261008-01'
SEAL = '299cc1cf1bd65f2f64f495c9f791c3a190ba5329e86344f035224678ccfbb9ca'


class PopulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = json.loads((FORMAL/'combined-bits.json').read_bytes())
        cls.single = json.loads((FORMAL/'single-bits.json').read_bytes())
        cls.manifest = json.loads((FORMAL/'admission-manifest.json').read_bytes())
        cls.parent = Path(cls.manifest['baseline'])
        cls.previous = json.loads((cls.parent/'combined-bits.json').read_bytes())
        cls.ledger = (cls.parent/'combined-inputs.txt').read_text().splitlines()
        cls.new = (FORMAL/'combined-inputs.txt').read_text().splitlines()

    def test_actual779_full6162_OR_prefix(self):
        m.population_gate(self.previous,self.current,self.single,self.ledger,self.new)
        self.assertEqual(sum(map(len,self.current['metrics'].values())),6162)

    def test_missing_extra_scope_rejected(self):
        scope = next(iter(self.current['metrics']['line']))
        for extra in (False,True):
            bad = copy.deepcopy(self.current)
            row = bad['metrics']['line'].pop(scope)
            if extra: bad['metrics']['line']['foreign.scope'] = row
            with self.assertRaises(ValueError):
                m.population_gate(self.previous,bad,self.single,self.ledger,self.new)

    def test_changed_shape_OR_and_bounds_rejected(self):
        scope = next(iter(self.current['metrics']['line']))
        for field,value in [('checksum','foreign'),('width',-1),('bits','0x'+ 'f'*100000)]:
            bad = copy.deepcopy(self.current); bad['metrics']['line'][scope][field]=value
            with self.assertRaises(ValueError):
                m.population_gate(self.previous,bad,self.single,self.ledger,self.new)

    def test_duplicate_or_changed_prefix_rejected(self):
        for new in (self.new[:-1]+[self.new[-2]],self.new[1:]+self.new[:1]):
            with self.assertRaises(ValueError):
                m.population_gate(self.previous,self.current,self.single,self.ledger,new)

    def test_actual777_to779_genealogy_and_selected(self):
        anchor = json.loads((m.ANCHOR_MANIFEST.parent/'combined-bits.json').read_bytes())
        ledger = (m.ANCHOR_MANIFEST.parent/'combined-inputs.txt').read_text().splitlines()
        current,new,pins,chain = m.genealogy(m.stable.Reader(),FORMAL/'admission-manifest.json',SEAL,anchor,ledger)
        self.assertEqual(current,self.current)
        self.assertEqual([x['population'] for x in chain],[778,779])
        self.assertEqual(len(m.selected_tests(new)),779)
        self.assertIn(str(FORMAL/'admission-manifest.json'),pins)

    def test_wrong_seal_and_unadmitted_rejected(self):
        with self.assertRaises(ValueError):
            m.genealogy(m.stable.Reader(),FORMAL/'admission-manifest.json','0'*64,{},[])
        bad = dict(self.manifest,coverage_admitted=False)
        with patch.object(m.stable.Reader,'read',return_value=bad):
            with self.assertRaises(ValueError):
                m.genealogy(m.stable.Reader(),FORMAL/'admission-manifest.json',SEAL,{},[])

    def test_zero_contract_rejects_activity_shape_direction(self):
        row = dict(width=4,checksum='12',bits='0')
        m.zero_row(row,4,'12',[0,1])
        for bad,positions in [(dict(row,bits='8'),[0]),(dict(row,bits='4'),[1]),
                              (dict(row,checksum='13'),[0]),(row,[0,0]),(row,[4])]:
            with self.assertRaises(ValueError):m.zero_row(bad,4,'12',positions)

    def test_testdata_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td)/'case.vdb'; folder=db/'snps/coverage/db/testdata'
            folder.mkdir(parents=True); (folder/'alias').symlink_to(Path(td),target_is_directory=True)
            with self.assertRaises(ValueError):m.selected_tests([str(Path(td)/'design.vdb'),str(db)])

    def test_private_lifecycle_only_rebinds_check_verify(self):
        captured={}
        def construct(code,namespace):
            captured.update(namespace)
            self.assertIs(code,m.stable.run.__code__)
            return lambda *args: args
        with patch.object(m,'FunctionType',side_effect=construct):
            self.assertEqual(m.run(Path('/out'),'seal','reviewed'),(Path('/out'),'seal','reviewed'))
        self.assertIs(captured['check'],m.check)
        self.assertIs(captured['verify'],m.verify)
        self.assertEqual(captured['TCL'],m.stable.TCL)


class GeneratedTclTests(fixtures.TclIntegration):
    # Execute the exact reused exporter/hook, not just Tcl syntax completeness.
    pass


if __name__ == '__main__':
    unittest.main()
