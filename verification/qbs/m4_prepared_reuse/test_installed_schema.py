import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('m4_installed_checker',Path(__file__).with_name('run_installed.py'))
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


class SchemaTest(unittest.TestCase):
    def log(self):
        return '\n'.join([
            'M4_RUNTIME_GRAPH_MODE mode=0',
            'GGML_RISCV_QBS_LIFETIME quantize_time_valid=0 quantize_time_us=0',
            'GGML_RISCV_QBS_LIFETIME_SUMMARY quantizations=1',
            'M4_RUNTIME_GRAPH_MODE mode=1',
            'GGML_RISCV_QBS_LIFETIME preparation_time_valid=0 preparation_time_us=0',
            'GGML_RISCV_QBS_LIFETIME_SUMMARY_V2 prepared_buffer_invocations=1'])
    def test_versions(self):
        r=checker.check_schema(self.log(),'graph');self.assertEqual(r['logical_records'],{0:1,1:1})
    def test_reject_ambiguous(self):
        for a,b in [('prepared_buffer_invocations=1','quantizations=1'),
                    ('preparation_time_valid=0','quantize_time_valid=0'),
                    ('prepared_buffer_invocations=1','prepared_buffer_invocations=2')]:
            with self.subTest(change=a),self.assertRaises(ValueError):checker.check_schema(self.log().replace(a,b),'graph')
    def test_missing(self):
        with self.assertRaises(ValueError):checker.check_schema(self.log().rsplit('\n',1)[0],'graph')


if __name__=='__main__':unittest.main()
