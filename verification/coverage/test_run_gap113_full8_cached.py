import copy
import json
import unittest
import run_gap113_full8_cached as r


class Cached(unittest.TestCase):
    def test_actual_cached_manifest_complete(self):
        pre=r.life.read_bound(r.PRE/'preflight-manifest.json',r.SEAL)
        r.run_adapter().validate(pre)
        r.life.check(r.life.merge_pins(pre['input_pins'],pre['output_pins']))
        self.assertEqual(pre['initialization'],'STATIC_CONST_SAME_PINNED_FULL8_NATIVE_BYTES')
        self.assertEqual(pre['input_templates_bytes'],7040)

    def test_native_gold_and_full_regions_unchanged(self):
        q=r.qualifier('test-only-no-run');native=q.independent_native()
        symbols,data,sites=q.adapter().elf_view()
        for phase in (0,1):
            self.assertEqual(len(native[phase]['result_bits']),64)
            regions=q.regions(phase,symbols,data,native)
            self.assertEqual(sum(map(len,regions.values())),12272)
            for name in ('weights','activation'):
                template='gap110_%s%d'%(name,phase)
                self.assertEqual(data(*symbols[template]),regions[name])
        self.assertEqual([len(s) for s in sites],[8,8])

    def test_wrong_elf_shape_or_reduced_checks_reject(self):
        pre=r.life.read_bound(r.PRE/'preflight-manifest.json',r.SEAL)
        for key,value in [('binary_sha256','0'*64),('m',5),('n',1),('full_vrf_words',1024),
                          ('source_guard_bytes',0),('csr_words',12),('commands',1),('budget_s',900)]:
            bad=copy.deepcopy(pre);bad[key]=value
            with self.assertRaises(ValueError):r.run_adapter().validate(bad)

    def test_original_modules_unchanged(self):
        self.assertNotEqual(r.frozen_run.PRE,r.PRE)
        self.assertNotEqual(r.frozen_qual.RUN,r.RUN)
        self.assertEqual(r.qualifier('test').prepare.__globals__['RUN'],r.RUN)


if __name__=='__main__':unittest.main()
