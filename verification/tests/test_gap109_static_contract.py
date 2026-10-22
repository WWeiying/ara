import unittest
import gap109_static_contract as s

class Static(unittest.TestCase):
    def test_formal731_exact_native_zero_and_parameter_binding(self):
        record=s.contract()
        self.assertEqual(record['baseline_seal'],'79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641')
        self.assertEqual(len(record['targets']),1)
        t=record['targets'][0]
        self.assertEqual((t['width'],t['instance_checksum'],t['compiled_definition_checksum']),
                         (117,None,'1503069325'))
        self.assertIn('full_parameter',t['binding'])
        p=t['point']
        self.assertEqual((p['raw_index'],p['native_id'],p['line'],p['vector']),(77,'26','567','01'))
        self.assertEqual(p['attributes']['chksum'],'3351797643')
        self.assertFalse(t['before_hit'])
        self.assertIsNone(t['measured_hit'])
        self.assertFalse(record['coverage_admitted'])

    def test_old_fma_and_all_producer_pins_present(self):
        record=s.contract()
        self.assertEqual(record['pins'][str(s.ROOT/'hardware/deps/fpnew/src/fpnew_fma.sv')],
                         'f46700037a6f9efe9b74855d3d21ebaeaf42f5dd522b9e812bbc56ad7193ec71')
        for suffix in ('qbs_engine','qbs_descriptor_decoder','qbs_profile_engine_int',
                       'qbs_compute_engine','qbs_fp_accumulator','qbs_commit','qbs_block_adapter'):
            self.assertIn(str(s.ROOT/('hardware/src/vlsu/qbs/'+suffix+'.sv')),record['pins'])
        self.assertEqual(record['shape']['k_blocks'],2)
        self.assertEqual(record['expected_fflags'],[0,1])
        self.assertEqual(record['expected_csr_fflags'],[8,9])

if __name__=='__main__':unittest.main()

