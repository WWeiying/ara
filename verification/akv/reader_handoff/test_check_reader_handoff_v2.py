import re
import unittest

import check_reader_handoff_v2 as c
import test_check_reader_handoff as old_tests


class CorrectCommitWordContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        old_tests.HandoffCheckTest.setUpClass()
        cls.rtl=old_tests.HandoffCheckTest.rtl

    def transcript(self):
        text=old_tests.HandoffCheckTest().transcript()
        lines=[]
        for line in text.splitlines():
            if line.startswith('[QBS_PERF] '):
                values=dict(re.findall(r'(\w+)=(\d+)',line))
                reuse=int(values['activation_access'] in ('2','3'))
                line=line.replace('commit_groups=1 ','commit_groups=4 ')
                for name,value in (('vlen',1024),('lanes',4),
                                   ('context_fill_count',int(values['activation_access']=='1')),
                                   ('context_reuse_count',reuse),('context_reuse_block_count',reuse),
                                   ('context_read_bytes',292*reuse),('activation_axi_bytes_saved',292*reuse)):
                    line=re.sub(r'\b'+name+r'=\d+',name+'='+str(value),line)
            lines.append(line)
        return '\n'.join(lines)

    def test_full_legacy_register_not_one_command(self):
        parsed=c.check_log(self.transcript(),self.rtl)
        self.assertEqual(parsed['legacy_commit_words_per_success'],4)
        for before,after in (('commit_groups=4','commit_groups=1'),('commit_groups=4','commit_groups=0'),
                             ('vlen=1024','vlen=256'),('lanes=4','lanes=1'),
                             ('context_read_bytes=292','context_read_bytes=0'),
                             ('activation_axi_bytes_saved=292','activation_axi_bytes_saved=0')):
            with self.subTest(before=before),self.assertRaises(ValueError):
                c.check_log(self.transcript().replace(before,after,1),self.rtl)

    def test_old_checker_remains_original_and_rejects_four_words(self):
        import check_reader_handoff as old
        with self.assertRaisesRegex(ValueError,'context/atomic commit mismatch'):
            old.check_log(self.transcript(),self.rtl)


if __name__=='__main__':
    unittest.main()
