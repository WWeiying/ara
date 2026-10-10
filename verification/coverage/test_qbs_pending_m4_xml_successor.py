"""Actual completed sample XML, ownership and strict negative mutations."""
import copy
import gzip
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

import collect_qbs_pending_m4_xml_successor as case

RUN = case.life.OUT / 'qbs-pending-two-phase-m4-vcs783-agent-20261008-01'
SEAL = '8db9ab6f8f66508675302457dd1ddd3b12ac93e860fd4f3dd4efb8831b8b41e4'


class ActualXML(unittest.TestCase):
    def setUp(self):
        self.record = case.life.read_bound(RUN.with_name(RUN.name + '.prepared.json'), SEAL)
        folder = RUN / 'code.vdb/snps/coverage/db/testdata' / case.original.runner.NAME
        self.sim = case.toggle.xml(folder / 'siminfo.xml')
        self.args = case.toggle.xml(folder / 'vcmArguments.xml')
        self.design = str(case.life.IMAGE) + '.vdb'

    def check(self):
        return case.native_identity(RUN, self.sim, self.args, self.record, self.design)

    def test_actual_native_identity(self):
        value = self.check()
        self.assertEqual(value['workdir'], str(RUN))
        self.assertEqual(value['command'], self.record['command'])
        self.assertTrue(value['XML_teststatus_is_not_PASS_authority'])

    def test_wrong_owner(self):
        self.sim.find('srctest').set('workdir', str(RUN) + '-wrong')
        with self.assertRaises(ValueError): self.check()

    def test_wrong_command(self):
        self.sim.find('srctest').set('cmdline', 'simv +wrong')
        with self.assertRaises(ValueError): self.check()

    def test_incomplete_time(self):
        row = self.sim.find('srctest')
        row.set('finishtime', row.get('starttime'))
        with self.assertRaises(ValueError): self.check()

    def test_duplicate_sample(self):
        self.sim.append(copy.deepcopy(self.sim.find('srctest')))
        with self.assertRaises(ValueError): self.check()

    def test_wrong_compile(self):
        self.args.set('compvdbpath', self.design + '-wrong')
        with self.assertRaises(ValueError): self.check()

    def test_missing_metric(self):
        self.args.remove(next(n for n in self.args.findall('vcm_arg_data') if n.get('vcm_opt')))
        with self.assertRaises(ValueError): self.check()

    def test_plain_and_gzip_xml(self):
        raw = ET.tostring(self.sim)
        with tempfile.TemporaryDirectory() as tmp:
            for name, data in [('plain', raw), ('gzip', gzip.compress(raw))]:
                path = Path(tmp) / name
                path.write_bytes(data)
                self.assertEqual(ET.tostring(case.toggle.xml(path)), raw)

    def test_toggle_operations_unchanged(self):
        for name in ('rows', 'union', 'gains'):
            self.assertIs(getattr(case.toggle, name), getattr(case.original.toggle, name))


if __name__ == '__main__':
    unittest.main()
