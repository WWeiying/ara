import json
from pathlib import Path
import tempfile
import unittest
from export_fp_compare import original_binary
from trace_masks import sha


class OriginalIdentityTests(unittest.TestCase):
    def test_requires_unique_archive_and_exact_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root/'original'
            binary = folder/'overlay/opt/ara-tests/old'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'archived original')
            path = folder/'manifest.json'
            path.write_text(json.dumps(dict(cases=[dict(name='old', sha256=sha(binary))])))
            case = dict(original_name='old', original_manifest_sha256=sha(path),
                        original_elf_sha256=sha(binary))
            self.assertEqual(original_binary(root, case), (path, binary))
            binary.write_bytes(b'different')
            with self.assertRaises(ValueError):original_binary(root, case)
            binary.write_bytes(b'archived original')
            duplicate = root/'duplicate'; duplicate.mkdir()
            (duplicate/'manifest.json').write_bytes(path.read_bytes())
            with self.assertRaises(ValueError):original_binary(root, case)
            (duplicate/'manifest.json').unlink()
            case['original_manifest_sha256'] = 'missing'
            with self.assertRaises(ValueError):original_binary(root, case)


if __name__ == '__main__':
    unittest.main()
