import copy
import json
import unittest
import run_qbs_payload_matrix4 as m


class MatrixRun(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((m.PRE/'preflight-manifest.json').read_text())

    def test_actual_preflight(self):
        m.validate(self.pre)
        self.assertEqual(m.life.digest(m.PRE/'preflight-manifest.json'), m.SEAL)

    def test_no_scope_reduction(self):
        for key in ('commands','full_vrf_bytes','source_readback_bytes','csr_values','dut_checks'):
            bad = copy.deepcopy(self.pre)
            bad[key] -= 1
            with self.assertRaises(ValueError):
                m.validate(bad)

    def test_site_and_elf(self):
        for change in ('word','duplicate','elf'):
            bad = copy.deepcopy(self.pre)
            if change == 'word': bad['sites'][0]['word'] ^= 1
            elif change == 'duplicate': bad['sites'][1]['pc'] = bad['sites'][0]['pc']
            else: bad['binary_sha256'] = '0'*64
            with self.assertRaises(ValueError): m.validate(bad)

    def test_command(self):
        m.reused.NAME = m.NAME
        m.reused.ELF = m.PRE/(m.NAME+'.elf')
        m.reused.ELF_SEAL = m.ELF_SHA
        cmd = m.reused.command(m.life.OUT/'matrix-command-test')
        self.assertIn('+NO_FSDB', cmd)
        self.assertIn('+PRELOAD='+str(m.reused.ELF), cmd)
        self.assertEqual(cmd[0], str(m.life.IMAGE))


if __name__ == '__main__': unittest.main()
