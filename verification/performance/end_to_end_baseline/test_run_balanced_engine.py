import json
import unittest

from audit import digest
from run_balanced_engine import BASE, BASE_SHA, COMPONENT, COMPONENT_SHA, CLONES, ORIGINAL, VECTOR_SHA
from matrix_dot_pair import candidate_vectors
from check_balanced_compute import vector
from run_wide_compute import parse_vectors
from balanced_engine_source import engine


class ControllerRun(unittest.TestCase):
    def test_accepted_source_composition(self):
        self.assertEqual(digest(BASE/'result.json'),BASE_SHA)
        self.assertEqual(digest(COMPONENT/'result.json'),COMPONENT_SHA)
        report=json.loads((COMPONENT/'result.json').read_text())
        pins=json.loads((COMPONENT/'source-pins.json').read_text())
        for name in CLONES:
            p=COMPONENT/'source'/name
            self.assertEqual(digest(p),pins[str(p)])
        self.assertTrue(report['post_pins_match'])
        source=(BASE/'tree/hardware/src/vlsu/qbs/qbs_engine.sv').read_text()
        result,trace=engine(source)
        self.assertTrue(trace['source_reversible'])
        self.assertIn('qbs_compute_engine_balanced #(',result)

    def test_original_payloads_and_accepted_prefix_preserved(self):
        accepted=(COMPONENT/'vectors-balanced.txt').read_text().split('\n',1)[1]
        for name,sha in VECTOR_SHA.items():
            path=ORIGINAL/(name+'-base.txt');self.assertEqual(digest(path),sha)
            base=candidate_vectors(path.read_text());modified=vector(base)
            self.assertEqual(len(parse_vectors(base)),36 if name=='matrix' else 12)
            for a,b in zip(base.splitlines(),modified.splitlines()):
                if not a.startswith('C '):self.assertEqual(a,b)
            if name=='matrix':self.assertTrue(accepted.startswith(modified.split('\n',1)[1]))


if __name__=='__main__':unittest.main()
