import json
from pathlib import Path
import tempfile
import unittest

from build_matrix_soc import expected_graph,check_config,compiler_tool,FEATURE


class MatrixSocBuilderTests(unittest.TestCase):
    def test_host_compiler_not_path_wrapper(self):
        self.assertEqual(compiler_tool('g++'),'/usr/bin/g++')
        self.assertEqual(compiler_tool('python3'),'/usr/bin/python3')
        with self.assertRaises(ValueError):compiler_tool('clang++')

    def test_only_one_new_macro_per_context(self):
        text='+define+ARA_QBS_VRF_CONTINUATION=1\n/tmp/a.sv\n+define+ARA_QBS_VRF_CONTINUATION=1\n/tmp/b.sv\n'
        self.assertEqual(expected_graph(text,0),text.splitlines())
        wide=expected_graph(text,1)
        self.assertEqual(wide.count(FEATURE),2)
        self.assertEqual([s for s in wide if s!=FEATURE],text.splitlines())
        with self.assertRaises(ValueError):expected_graph(text+FEATURE+'\n',1)

    def test_config_rejects_missing_duplicate_or_wrong_width(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config';baseline=dict(qbs='1',vlen='1024')
            path.write_text('qbs=1\nvlen=1024\nqbs_matrix_dot=1\n')
            self.assertEqual(check_config(path,baseline,1)['qbs_matrix_dot'],'1')
            for text in ('qbs=1\nvlen=1024\n','qbs=1\nvlen=1024\nqbs_matrix_dot=0\n',
                         'qbs=1\nvlen=1024\nqbs_matrix_dot=1\nqbs_matrix_dot=1\n'):
                path.write_text(text)
                with self.assertRaises(ValueError):check_config(path,baseline,1)


if __name__=='__main__':unittest.main()
