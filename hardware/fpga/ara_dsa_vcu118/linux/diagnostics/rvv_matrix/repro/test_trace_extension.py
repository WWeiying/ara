import unittest
from pathlib import Path
from trace_extension import instrument, isolate


class TraceTests(unittest.TestCase):
    def test_single_trial_preserves_fixture_and_target(self):
        source=(Path(__file__).parents[1]/'extension_oracle.c').read_text()
        selector='            if(seed!=0 || op!=2 || l!=5 || mode!=0)continue;\n'
        self.assertEqual(isolate(source).replace(selector,''),source)
        with self.assertRaises(ValueError):
            isolate('no selector')

    def test_original_preserved_when_markers_removed(self):
        source=(Path(__file__).parents[1]/'extension_oracle.c').read_text()
        changed=instrument(source)
        before=changed.index('            text("RVV_EXTENSION_BEGIN')
        target=changed.index('            if(functions[op]')
        after=changed.index('            text("RVV_EXTENSION_RETURN')
        end=changed.index('            for(unsigned i=0;i<bytes;',after)
        self.assertEqual(changed[:before]+changed[target:after]+changed[end:],source)
        with self.assertRaises(ValueError):
            instrument('no target')


if __name__=='__main__':
    unittest.main()
