import unittest
from run_f16_native import accept_program


class F16RunAdmission(unittest.TestCase):
    def test_exact_program_scope_and_missing_fields(self):
        p=dict(state='REAL_QWEN3_F16_PHASE_ELF_BUILT_NOT_EXECUTED',post_pins_match=True,
            target_executed=False,performance_measured=False,rtl_changed=False,whole_model=False,
            order=[0,1,1,0],trials=8,outputs_checked=66560,q_heads=2,kv_heads=1,head_dim=128,
            prefill_queries=64,decode_visible=137,pair_heads_enabled=True,pair_pv_enabled=True,
            timing_includes_csr_completion=True,decode_preparation_included=True,
            probe_perturbation_limit=.05,default_runtime_promoted=False)
        accept_program(p)
        for key in p:
            bad=dict(p);del bad[key]
            with self.subTest(key=key),self.assertRaises(ValueError):accept_program(bad)

    def test_wrong_shape_completion_or_claim_rejected(self):
        with self.assertRaises(ValueError):accept_program({})
        # Deliberately valid-looking legacy smaller slices cannot be admitted.
        for change in (dict(prefill_queries=4),dict(decode_visible=64),dict(whole_model=True),
                       dict(performance_measured=True),dict(default_runtime_promoted=True)):
            with self.subTest(change=change),self.assertRaises(ValueError):accept_program(change)


if __name__=='__main__':unittest.main()
