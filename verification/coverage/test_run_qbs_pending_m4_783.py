"""Preparation contract tests; no worker/EDA mode."""
import copy
import unittest

import run_qbs_pending_m4_783 as r


class PrepareTests(unittest.TestCase):
    def test_actual_preflight_validate(self):
        r.validate(r.life.read_bound(r.PRE/'preflight-manifest.json',r.SEAL))

    def test_invalid_m8_rejected(self):
        p=r.life.read_bound(r.PRE/'preflight-manifest.json',r.SEAL);p['phases'][1]['m']=8
        with self.assertRaises(ValueError):r.validate(p)

    def test_wrong_source_offsets(self):
        p=r.life.read_bound(r.PRE/'preflight-manifest.json',r.SEAL);p['phases'][1]['ap']=0
        with self.assertRaises(ValueError):r.validate(p)

    def test_missing_checkpoint(self):
        p=r.life.read_bound(r.PRE/'preflight-manifest.json',r.SEAL);p['full_vrf_checkpoint_bytes']=[4096]
        with self.assertRaises(ValueError):r.validate(p)

    def test_custom_word(self):
        p=r.life.read_bound(r.PRE/'preflight-manifest.json',r.SEAL);p['sites'][1]['word']=0x0eb5045b
        with self.assertRaises(ValueError):r.validate(p)

    def test_command_exact_image_elf_probe(self):
        command=r.command(r.life.OUT/'uncreated-m4-test')
        self.assertEqual(command[0],str(r.life.IMAGE))
        self.assertIn('+PRELOAD='+str(r.ELF),command)
        self.assertEqual(command[-3:],['-ucli','-do',str(r.PROBE)])
        self.assertNotIn('+FSDB',command)

    def test_duplicate_elf_and_empty_evidence(self):
        with self.assertRaises(ValueError):r.reject_duplicate([dict(ELF_candidates={'elf':r.ELF_SHA})],r.ELF_SHA)
        with self.assertRaises(ValueError):r.reject_duplicate([dict(ELF_candidates={})],r.ELF_SHA)
        r.reject_duplicate([dict(ELF_candidates={'elf':'a'*64})],r.ELF_SHA)


if __name__=='__main__':unittest.main()
