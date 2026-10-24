#!/usr/bin/env python3
"""Reject unsupported/rounded parameter assumptions before native execution."""
import unittest

from build_attention import scale_source_checks


class ScaleSourceTest(unittest.TestCase):
    def test_exact_source_contract(self):
        model = ('GGML_ASSERT(n_embd_head == hparams.n_embd_head_k());\n'
                 '1.0f/sqrtf(float(n_embd_head)), il);')
        graph = ('build_attn_mha(q, k, v, kq_b, kq_mask, sinks, v_mla, kq_scale, il)\n'
                 'ggml_flash_attn_ext(ctx0, q, k, v, kq_mask, kq_scale, hparams.f_max_alibi_bias,')
        params = dict(op='FLASH_ATTN_EXT', scale=0.0883883, max_bias=0, logit_softcap=0)
        scale_source_checks(model, graph, params)
        for field, value in [('op', 'MUL_MAT'), ('scale', 0.088), ('max_bias', 1), ('logit_softcap', 1)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                scale_source_checks(model, graph, dict(params, **{field: value}))
        for bad_model, bad_graph in [(model.replace('1.0f', '2.0f'), graph),
                                      (model, graph.replace('kq_scale', 'other_scale'))]:
            with self.assertRaises(ValueError):
                scale_source_checks(bad_model, bad_graph, params)


if __name__ == '__main__':
    unittest.main()
