from pathlib import Path
import tempfile
import unittest

import audit_completed_v2 as a


class ExportDerivationTest(unittest.TestCase):
    def test_accepts_only_exact_reproduced_cycles(self):
        with tempfile.TemporaryDirectory() as temp:
            original=Path(temp)/'checked.csv'
            reproduced=Path(temp)/'reproduced.csv'
            original.write_text('cycle,owner\n0,1\n')
            reproduced.write_bytes(original.read_bytes())
            a.compare_export(original,reproduced)
            for bad in ('cycle,owner\n0,0\n','cycle,owner\n',''):
                reproduced.write_text(bad)
                with self.assertRaises(ValueError):
                    a.compare_export(original,reproduced)
            reproduced.unlink()
            with self.assertRaises(ValueError):
                a.compare_export(original,reproduced)

    def test_reexports_under_pins_instead_of_trusting_metadata_paths(self):
        text=Path(a.__file__).read_text()
        self.assertLess(text.index('s.verify_pins(pins)'),text.index('s.run_command(command'))
        self.assertLess(text.index('s.run_command(command'),text.index('compare_export(replay/'))
        self.assertIn("s.run_command(command,out/'export.log',180,env,started)",text)
        self.assertIn("'--fsdb',str(fsdb),'--profile',str(profile)",text)
        self.assertIn('exporter_files(args.fsdbreport)',text)
        self.assertIn('original_worker_state',text)


if __name__=='__main__':
    unittest.main()
