"""Check hierarchy compatibility without generating or building an FPGA image."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

PATH = Path(__file__).resolve().parents[3] / 'hardware/fpga/vcu118/payload_hierarchy.py'
SPEC = importlib.util.spec_from_file_location('payload_hierarchy', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Root:
    def __init__(self, values):
        self.values = values

    def lookupName(self, path):
        return self.values.get(path)


def instance(name='qbs_payload_sram', inactive=False):
    return SimpleNamespace(definition=SimpleNamespace(name=name), isUninstantiated=inactive)


class PayloadHierarchyTests(unittest.TestCase):
    def test_original_package(self):
        self.assertEqual(MODULE.resolve_payload_ram(Root({'r.i_payload': instance()}), 'r'), 'r.i_payload')

    def test_selectable_storage_package(self):
        self.assertEqual(MODULE.resolve_payload_ram(Root({'r.gen_storage.i_payload': instance()}), 'r'),
                         'r.gen_storage.i_payload')

    def test_missing_and_inactive_rejected(self):
        for values in ({}, {'r.i_payload': instance(inactive=True)}):
            with self.assertRaises(RuntimeError):
                MODULE.resolve_payload_ram(Root(values), 'r')

    def test_both_active_paths_rejected(self):
        with self.assertRaises(RuntimeError):
            MODULE.resolve_payload_ram(Root({'r.i_payload': instance(), 'r.gen_storage.i_payload': instance()}), 'r')

    def test_unknown_hierarchy_and_wrong_type_rejected(self):
        for values in ({'r.arbitrary.i_payload': instance()}, {'r.i_payload': instance('fake_sram')}):
            with self.assertRaises(RuntimeError):
                MODULE.resolve_payload_ram(Root(values), 'r')


if __name__ == '__main__':
    unittest.main()
