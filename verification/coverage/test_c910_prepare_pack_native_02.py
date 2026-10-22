from pathlib import Path
import tempfile
import unittest
import c910_prepare_pack_native_02 as successor
from test_c910_prepare_pack_native import fixture
from c910_prepare_pack_native_mock import qualify


class Successor(unittest.TestCase):
    def test_actual02_disk_entry_five_stage_checks(self):
        c=fixture()
        with tempfile.TemporaryDirectory(dir=successor.base.life.OUT) as directory:
            out=Path(directory)
            (out/'selection.tcl').write_text(successor.base.selection(c),encoding='ascii')
            (out/'candidate.el').write_text(successor.base.el_text(c),encoding='ascii')
            proof=qualify(out,c)
            self.assertEqual([s['stage'] for s in proof['stages']],list(successor.base.STAGES))
            self.assertTrue(all(s['all_checked_non_targets']==3740 for s in proof['stages']))

    def test_no_unsupported_native_tcl_constructs(self):
        text=successor.ENTRY.read_text()
        self.assertNotIn('{*}',text);self.assertNotIn(' in {',text)
        self.assertIn('[lsearch -exact',text)
        self.assertIn('puts [eval [concat $command $args]]',text)

    def test_actual01_failure_preserved(self):
        config=successor.base.life.read_bound(successor.ORIGIN/'config.json',successor.ORIGIN_SHA)
        self.assertEqual(config['objects'],240)
        self.assertIn('looking for close parenthesis',(successor.ORIGIN/'error.txt').read_text())


if __name__=='__main__':unittest.main()
