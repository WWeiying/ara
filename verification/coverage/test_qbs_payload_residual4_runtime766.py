import copy
import struct
import unittest
import qualify_qbs_payload_residual4_766 as q
import run_qbs_payload_residual4_766 as run


class TestRuntime(unittest.TestCase):
    def test_actual_preflight(self):
        pre=run.life.read_bound(run.PRE/'preflight-manifest.json',run.SEAL)
        run.validate(pre)
        self.assertEqual(pre['binary_sha256'],run.life.digest(run.PRE/(run.NAME+'.elf')))

    def test_profile_and_budget_and_scope_rejected(self):
        pre=run.life.read_bound(run.PRE/'preflight-manifest.json',run.SEAL)
        for key,value in [('profile',[2]*4),('baseline',764),('budget_s',900),('full_vrf_bytes',4096),('vcs_launched',True)]:
            altered=copy.deepcopy(pre);altered[key]=value
            with self.assertRaises(ValueError):run.validate(altered)

    def test_real_elf_native_unpack_and_memory_sites(self):
        view=q.adapted_function(q.frozen.elf_view,[('item=unpack(w[','item=unpack(phase,w['),
            ('recipe.WP[phase]+1680','recipe.WP[phase]+8*recipe.SIZE[phase]')],dict(runner=run,recipe=q.recipe,unpack=q.unpack))
        symbols,data,sites,native=view()
        self.assertEqual(len(native),4)
        self.assertEqual([len(s) for s in sites],[8]*4)
        for phase in range(4):
            self.assertEqual(native[phase]['result_bits'],q.recipe.fixture(phase)[2])
            self.assertEqual(native[phase]['fflags'],0)

    def test_bsum_and_scale_negative(self):
        for phase in range(4):
            w,a,_=q.recipe.fixture(phase);w=w[64+q.recipe.WP[phase]:64+q.recipe.WP[phase]+8*q.recipe.SIZE[phase]]
            a=bytearray(a[64+q.recipe.AP[phase]:64+q.recipe.AP[phase]+2336]);a[2080]^=1
            with self.assertRaises(ValueError):q.unpack(phase,w,bytes(a))
        w,a,_=q.recipe.fixture(3);w=bytearray(w[74:74+672]);w[80]^=1
        with self.assertRaises(ValueError):q.unpack(3,bytes(w),a[72:72+2336])

    def test_data_corruption_not_reused_expected(self):
        for phase in range(4):
            w,a,gold=q.recipe.fixture(phase);start=64+q.recipe.WP[phase]
            w=bytearray(w[start:start+8*q.recipe.SIZE[phase]]);w[0]^=1
            native=q.unpack(phase,bytes(w),a[72:72+2336])
            self.assertNotEqual(native['result_bits'],gold)

    def test_descriptor_exact_profile(self):
        regions=q.adapted_function(q.frozen.regions,[('(2<<4)','(recipe.PROFILE[phase]<<4)')],dict(recipe=q.recipe))
        for phase in range(4):
            symbols={'weight%d'%phase:(0x80010000,2048)}
            blobs=regions(phase,symbols,None,None)
            header=struct.unpack_from('<Q',blobs['desc%d'%phase],64)[0]
            self.assertEqual((header>>4)&15,q.recipe.PROFILE[phase])
            self.assertEqual(len(blobs['frame%d'%phase]),4224)
            self.assertEqual(len(blobs['csr%d'%phase]),160)

    def test_unknown_phase_and_extent(self):
        for phase in (True,4,-1):
            with self.assertRaises(ValueError):q.unpack(phase,b'',b'')


if __name__=='__main__':unittest.main()
