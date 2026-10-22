import unittest
import xml.etree.ElementTree as ET

import rvh_direct_native_candidates_725 as subject


class MappingTests(unittest.TestCase):
    def group(self, expr="1'b0", file='7', line='10'):
        return ET.fromstring('<branch_spec file_id="7"><branch_expr id="%s" index="2" file_id="%s" exprstr="%s"/></branch_spec>' % (line,file,expr))

    def test_source_only_direct_rvh_not_comments_compounds_other_zero(self):
        text = "// if (CVA6Cfg.RVH)\nif (1'b0) x=1;\nif (CVA6Cfg.RVH && x) y=1;\nif (CVA6Cfg.RVH) z=1;\n/* if (CVA6Cfg.RVH) */\n"
        self.assertEqual(set(subject.direct_sites(text)), {4})

    def test_exact_file_line_constant_binding(self):
        self.assertEqual(len(subject.matched_expressions(self.group(), {10:'if (CVA6Cfg.RVH)'}, '7')),1)
        self.assertEqual(subject.matched_expressions(self.group(line='11'), {10:'if (CVA6Cfg.RVH)'}, '7'),[])
        with self.assertRaises(ValueError):
            subject.matched_expressions(self.group(file='8'), {10:'if (CVA6Cfg.RVH)'}, '7')
        with self.assertRaises(ValueError):
            subject.matched_expressions(self.group(expr="1'b1"), {10:'if (CVA6Cfg.RVH)'}, '7')

    def test_constant_zero_without_rvh_source_is_not_selected(self):
        self.assertEqual(subject.matched_expressions(self.group(), {}, '7'), [])

    def test_right_index_and_dash_false_are_protected(self):
        expressions=[{'index':'2'}]
        self.assertTrue(subject.true_pattern('0010',expressions))
        self.assertFalse(subject.true_pattern('0100',expressions))
        self.assertFalse(subject.true_pattern('00-0',expressions))
        with self.assertRaises(ValueError): subject.true_pattern('0100',[])
        with self.assertRaises(ValueError): subject.true_pattern('00X0',expressions)

    def test_partition_preserves_false_and_inactive_points(self):
        mapped=[dict(raw_index=i,native_vector={'vector':p}) for i,p in enumerate(('01','10','-0'))]
        targets, protected=subject.partition(mapped,[{'index':'1'}],dict(width=3,bits='2'))
        self.assertEqual([r['point']['raw_index'] for r in targets],[0])
        self.assertEqual([r['point']['raw_index'] for r in protected],[1,2])
        self.assertTrue(protected[0]['hit725'])

    def test_hit_true_pattern_and_bitmap_overflow_rejected(self):
        mapped=[dict(raw_index=0,native_vector={'vector':'01'})]
        for bits in ('1','2'):
            with self.assertRaises(ValueError):
                subject.partition(mapped,[{'index':'1'}],dict(width=1,bits=bits))

    def test_config_path_rejects_rvh_override(self):
        config="localparam CVA6ConfigHExtEn = 0; RVH: bit'(CVA6ConfigHExtEn)"
        build='cfg.RVH = CVA6Cfg.RVH;'
        soc='function automatic config_pkg::cva6_user_cfg_t gen_usr_cva6_config(); cfg.NrPMPEntries = 0; return cfg; endfunction\n'+ '\n'.join((
            'gen_usr_cva6_config(cva6_config_pkg::cva6_cfg)',
            'build_config_pkg::build_config(CVA6AraConfig_user)',
            '.CVA6Cfg           (CVA6AraConfig        )'))
        self.assertEqual(subject.config_chain(config,build,soc)['RVH'],0)
        for c,b,s in ((config.replace('= 0','= 1'),build,soc),
                      (config,build+' cfg.RVH = 1;',soc),
                      (config,build,soc.replace('return cfg;','cfg.RVH = 1; return cfg;'))):
            with self.assertRaises(ValueError): subject.config_chain(c,b,s)


if __name__ == '__main__':
    unittest.main()
