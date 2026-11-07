import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from execute_rms_ggml_model import admit, verify_paths, BASE_ELF


class PreparedGuest(unittest.TestCase):
    def test_same_bytes_symlink_retarget_still_rejected(self):
        with TemporaryDirectory() as root:
            root = Path(root); first = root/'first'; second = root/'second'; alias = root/'alias'
            first.write_bytes(b'identical'); second.write_bytes(first.read_bytes()); alias.symlink_to(first)
            identities = {str(alias): str(first.resolve())}; verify_paths(identities)
            alias.unlink(); alias.symlink_to(second)
            with self.assertRaises(ValueError): verify_paths(identities)

    def test_only_complete_nonexecuted_preflight(self):
        record = dict(state='RMS_GGML_MODEL_PAIR_PREPARED_NOT_EXECUTED', performance_measured=False,
                      rtl_changed=False, production_library_promoted=False, compiled_translation_units=1,
                      common_model_object_reused=True, default_enabled=False,
                      baseline_link_reproduced_exactly=True, guest_cpio_parsed_and_bound=True,
                      baseline_elf_sha256=BASE_ELF, child_pid=None)
        admit(record)
        for key, value in record.items():
            with self.subTest(missing=key), self.assertRaises(ValueError):
                admit({k: v for k, v in record.items() if k != key})
            wrong = not value if isinstance(value, bool) else 'wrong'
            with self.subTest(wrong=key), self.assertRaises(ValueError):
                admit({**record, key: wrong})


if __name__ == '__main__':
    unittest.main()
