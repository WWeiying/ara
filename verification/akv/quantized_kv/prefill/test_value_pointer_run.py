import json
from pathlib import Path
import tempfile
import unittest
from value_pointer_run import validate_variant


class Variant(unittest.TestCase):
    def test_only_completed_pointer_variant(self):
        good=dict(state='BUILT_NOT_EXECUTED',value_pointer=True,pointer_transport_source_verified=True)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'build.json').write_text(json.dumps(good));validate_variant(root)
            for key,value in [('state','VARIANT_AUDIT_FAILED'),('value_pointer',False),
                              ('pointer_transport_source_verified',False)]:
                bad={**good,key:value}
                (root/'build.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):validate_variant(root)


if __name__=='__main__':unittest.main()
