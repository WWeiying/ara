import unittest
from pathlib import Path
from trace_fault import instrument, INSERTS, unit_shape, segment_shape, strided_shape, restore_unit_handler


class TraceTests(unittest.TestCase):
    def test_strided_controls_domain(self):
        for fields in (1,2,8):
            for negative,zero in ((False,False),(True,False),(False,True)):
                prefix='rvv_fault_replay'+(f'_segment_nf{fields}' if fields>1 else '')
                name=prefix+'_strided'+('_negative_stride' if negative else '')+('_zero_stride' if zero else '')+'_e16_m1'
                case=dict(name=name,sew=16,lmul='m1',fields=fields)
                manifest=dict(fields=fields,strided=True,negative_stride=negative,zero_stride=zero)
                self.assertEqual(strided_shape(manifest,case),((16,'m1',1,1,0),fields))
                for bad in (dict(manifest,indexed=True),dict(manifest,negative_skip=True),
                            dict(manifest,strided=False),dict(manifest,trace=True),
                            dict(manifest,negative_stride=True,zero_stride=True)):
                    with self.assertRaises(ValueError):strided_shape(bad,case)

    def test_stride_logging_does_not_change_recovery(self):
        source=(Path(__file__).parents[1]/'fault_replay_oracle.c').read_text()
        plain=instrument(source)
        traced=instrument(source,True)
        extra='''num(split);
#if !ZERO_STRIDE
        text(" gap=");num(gap);
#endif
        text("\\n");'''
        self.assertIn(extra,traced)
        self.assertEqual(traced.replace(extra,'num(split);text("\\n");'),plain)

    def test_segment_controls_preserve_field_count_and_limits(self):
        case=dict(name='rvv_fault_replay_segment_nf2_e16_m1',sew=16,lmul='m1')
        self.assertEqual(segment_shape({'fields':2},case),((16,'m1',1,1,0),2))
        for manifest in ({'fields':1},{'fields':3},{'fields':2,'strided':True},
                         {'fields':2,'indexed':True},{'fields':2,'negative_restart':True}):
            with self.assertRaises(ValueError):segment_shape(manifest,case)
        with self.assertRaises(ValueError):
            segment_shape({'fields':2},dict(case,fields=3))
        with self.assertRaises(ValueError):
            segment_shape({'fields':2},dict(case,lmul='m8',name='rvv_fault_replay_segment_nf2_e16_m8'))
        for fields in range(2,9):
            c=dict(case,name=f'rvv_fault_replay_segment_nf{fields}_e16_m1')
            self.assertEqual(segment_shape({'fields':fields},c)[1],fields)

    def test_recovery_logic_preserved(self):
        source=(Path(__file__).parents[1]/'fault_replay_oracle.c').read_text()
        changed=instrument(source)
        for insert in INSERTS.values():changed=changed.replace(insert,'')
        self.assertEqual(changed,source)

    def test_drift_rejected(self):
        with self.assertRaises(ValueError):instrument('missing')

    def test_restored_candidate_preserves_surrounding_code(self):
        source=(Path(__file__).parents[1]/'fault_replay_oracle.c').read_text()
        candidate=restore_unit_handler(source)
        before=source.split('    unsigned address_matches=0;')[0]
        after=source.split('    if(sig!=SIGSEGV || !address_matches ||')[1]
        self.assertEqual(candidate,before+'    if(sig!=SIGSEGV || (uintptr_t)info->si_addr!=expected_address ||'+after)
        self.assertIn('RVV_FAULT_CONTEXT',instrument(candidate))
        with self.assertRaises(ValueError):restore_unit_handler(candidate)

    def test_unit_shapes_and_unsupported_domains(self):
        case=dict(name='rvv_fault_replay_e64_m8',sew=64,lmul='m8')
        self.assertEqual(unit_shape({},case),(64,'m8',8,1,3))
        small=dict(name='rvv_fault_replay_e8_mf8',sew=8,lmul='mf8')
        self.assertEqual(unit_shape({},small),(8,'mf8',1,8,5))
        for manifest in ({'strided':True},{'indexed':True},{'fields':2},
                         {'negative_restart':True},{'trace':True}):
            with self.assertRaises(ValueError):unit_shape(manifest,case)
        with self.assertRaises(ValueError):
            unit_shape({},dict(name='rvv_fault_replay_e64_mf8',sew=64,lmul='mf8'))


if __name__=='__main__':unittest.main()
