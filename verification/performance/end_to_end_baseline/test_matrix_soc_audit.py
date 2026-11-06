import unittest

from collect_matrix_soc import check_graph
from build_matrix_soc import FEATURE


class MatrixSocAuditTests(unittest.TestCase):
    def test_exact_single_blank_difference(self):
        text = '+define+ARA_QBS_VRF_CONTINUATION=1\n/tmp/module.sv\n'
        self.assertTrue(check_graph(text.encode(), (text+'\n').encode(), text, 0)['meaningful_graph_equal'])
        wide = text.replace('\n/tmp', '\n'+FEATURE+'\n/tmp')
        check_graph(wide.encode(), (wide+'\n').encode(), text, 1)

    def test_reject_meaningful_or_other_whitespace_drift(self):
        text = '+define+ARA_QBS_VRF_CONTINUATION=1\n/tmp/module.sv\n'
        for actual in (text, text+'\n\n', text.replace('module', 'other')+'\n',
                       text+'+define+OTHER=1\n\n', text.replace('/tmp', ' /tmp')+'\n'):
            with self.assertRaises(ValueError): check_graph(text.encode(), actual.encode(), text, 0)
        with self.assertRaises(ValueError): check_graph(text.encode(), (text+'\n').encode(), text, 1)


if __name__ == '__main__': unittest.main()
