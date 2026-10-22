import json
import unittest
import audit_full766_pmp_annotations as audit


class AnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=json.loads((audit.report.PMP/'config.json').read_bytes())
        cls.text=(audit.report.PMP/'first.el').read_text()

    def test_actual_exact_annotation_and770(self):
        self.assertEqual(len(audit.strict_records(self.text,self.c)),770)

    def test_changed_annotation_rejected(self):
        with self.assertRaises(Exception):
            audit.strict_records(self.text.replace(audit.ANNOTATION,'ANNOTATION: "changed"'),self.c)

    def test_missing_annotation_rejected(self):
        with self.assertRaises(Exception):
            audit.strict_records('\n'.join(s for s in self.text.splitlines() if not s.startswith('ANNOTATION:')),self.c)


if __name__=='__main__':unittest.main()
