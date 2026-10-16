import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from audit_segment_setup import inspect
from audit_segment_single import audit
from test_audit_segment_setup import OUTPUT, DIS
from trace_masks import sha


class SegmentSingleTests(unittest.TestCase):
    def test_exact_trap_and_identity_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);name='small';parent='original';directory=root/name;directory.mkdir()
            (root/'binaries').mkdir();(root/'binaries'/name).write_bytes(b'candidate')
            (directory/'original.elf').write_bytes(b'original');(directory/'scenario.c').write_text('source')
            old=dict(name=parent,status='failed',output=OUTPUT)
            oldcase=dict(name=parent,sew=16,lmul='m1',sha256=sha(directory/'original.elf'))
            original=root/'original_report.json'
            original.write_text(json.dumps(dict(inputs=dict(cases=[oldcase]),results=[old])))
            c=dict(oldcase,name=name,sha256=sha(root/'binaries'/name),original_name=parent,
                   original_elf_sha256=oldcase['sha256'],scenario_role='single_preparation_call',
                   measured_original=inspect(oldcase,old,DIS),
                   scenario_sources={'scenario.c':sha(directory/'scenario.c')})
            (root/'manifest.json').write_text(json.dumps(dict(original_report_sha256=sha(original),cases=[c])))
            report=dict(inputs=dict(cases=[dict(name=name,sha256=c['sha256'])]),results=[])
            path=root/'report.json'
            def check():
                path.write_text(json.dumps(report))
                with patch('audit_segment_single.subprocess.check_output',return_value=DIS):
                    return audit(root,path,'cross-')
            self.assertEqual(check()['pending'],1)
            report['results']=[dict(old,name=name)]
            self.assertEqual(check()['confirmed'],1)
            self.assertFalse(check()['architectural_bug_proven'])
            report['results'][0]['output']=OUTPUT.replace('signal 7','signal 11')
            self.assertEqual(check()['confirmed'],0)
            report['inputs']['cases'][0]['sha256']='different'
            with self.assertRaises(ValueError):check()


if __name__=='__main__':unittest.main()
