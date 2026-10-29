import unittest
from summarize_prefill_pair import require_build


class BuildScope(unittest.TestCase):
    def test_scope(self):
        build=dict(state='BUILT_NOT_EXECUTED',register_prefill=True,whole_call=True,
                   value_binding='shared_rvv_q8_0',kind='q4_0',commands_per_trial=4,
                   outputs_per_trial=1024,rebuilt_objects=17,reused_objects=0)
        require_build(build)
        for key,value in [('register_prefill',False),('whole_call',False),
                          ('value_binding','scalar'),('kind','q4_K'),
                          ('commands_per_trial',1),('outputs_per_trial',256),
                          ('rebuilt_objects',16),('reused_objects',1)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                require_build(dict(build,**{key:value}))


if __name__=='__main__':unittest.main()
