import json
from pathlib import Path
import tempfile
import unittest
from audit_slide import audit
from trace_masks import sha
from test_match_slide import LINE


class AuditTests(unittest.TestCase):
    def test_identity_and_symptom_gates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'binaries').mkdir()
            (root/'small').mkdir()
            binary=root/'binaries/small'
            binary.write_bytes(b'candidate')
            parent=root/'parent.original.elf'
            parent.write_bytes(b'original')
            source=root/'small/scenario.c'
            source.write_text('fixture')
            original=root/'original.json'
            original.write_text(json.dumps(dict(inputs=dict(cases=[dict(name='parent',sha256=sha(parent))]),
                results=[dict(name='parent',status='failed',exit_code=1,output=LINE)])))
            manifest=dict(original_report_sha256=sha(original),cases=[dict(name='small',original_name='parent',
                sha256=sha(binary),original_elf_sha256=sha(parent),scenario_role='single_original_trial',
                scenario_sources={'scenario.c':sha(source)},original_failure_detail=LINE)])
            (root/'manifest.json').write_text(json.dumps(manifest))
            report=root/'report.json'
            data=dict(inputs=dict(cases=[dict(name='small',sha256=sha(binary))]),
                results=[dict(name='small',status='failed',exit_code=1,output=LINE)])
            report.write_text(json.dumps(data))
            self.assertEqual(audit(root,original,report)['confirmed'],1)
            data['results'][0]['output']=LINE.replace('actual=91','actual=0')
            report.write_text(json.dumps(data))
            self.assertEqual(audit(root,original,report)['confirmed'],0)
            data['inputs']['cases'][0]['sha256']='wrong'
            report.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Deployed ELF'):
                audit(root,original,report)
            data['inputs']['cases']=[]
            report.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'no deployed identity'):
                audit(root,original,report)
            data['results']=[]
            report.write_text(json.dumps(data))
            self.assertEqual(audit(root,original,report)['pending'],1)
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError,'source changed'):
                audit(root,original,report)


if __name__=='__main__':
    unittest.main()
