#!/usr/bin/env python3
import unittest
from build_live_ggml_runtime import ROOT,check_policy


class LivePolicyTest(unittest.TestCase):
    def test_per_source_contract_not_global_override(self):
        names = ('akv_runtime.c','akv_native_riscv.c','akv_v2_native_riscv.c',
                 'akv_prefill_reference.c','akv_features.c')
        rows = [dict(file=str(ROOT/'software/akv/src'/name),
                     command='cc -march=rv64gcv_zfh_zvfh -O3 -fno-fast-math -ffp-contract=off -c source.c')
                for name in names]
        rows += [dict(file='/other/ggml-quants.c',command='cc -march=rv64gcv_zfh_zvfh -O3 -c source.c')]
        check_policy(rows)
        bad = [dict(r) for r in rows]
        bad[0]['command'] = bad[0]['command'].replace(' -ffp-contract=off','')
        with self.assertRaises(ValueError):
            check_policy(bad)
        with self.assertRaises(ValueError):
            check_policy(rows[1:])


if __name__ == '__main__':
    unittest.main()
