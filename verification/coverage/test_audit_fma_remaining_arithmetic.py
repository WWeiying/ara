import copy
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import audit_fma_remaining_arithmetic as m


class StaticFMA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = m.frozen.xml(m.DB / 'design/verilog.design.xml')
        cls.shape = m.frozen.xml(m.DB / 'shape/tgl.verilog.shape.xml')
        cls.raw = m.load(m.frozen.CACHE, m.frozen.CACHE_SHA)['instances']
        cls.roots, cls.children, _ = m.hierarchy(cls.design)
        cls.scope = next(p['scope'] for p in cls.roots if '.i_ariane.' in p['scope'] and
                         cls.raw[p['scope']]['checksum'] == '3893821548')
        cls.definition = next(p for p in cls.shape.findall('tgldef') if p.get('chksum') == '3893821548')
        cls.fields = m.shape_fields(cls.definition, cls.raw[cls.scope])

    def test_actual32_roots96_children_no_arithmetic_child(self):
        self.assertEqual(len(self.roots), 32); self.assertEqual(len(self.children), 96)
        self.assertEqual({p['module'] for p in self.children}, {'lzc', 'fpnew_rounding', 'fpnew_classifier'})

    def test_added_vendor_multiplier_child_invalidates_absence_proof(self):
        design = copy.deepcopy(self.design)
        module = ET.SubElement(design, 'srcdef', id='new-definition', name='ct_vfmau_mult', chksum='1')
        ET.SubElement(module, 'srcinst', id='new-instance', pid=self.roots[0]['compiled_instance']['id'], name='x_mult')
        with self.assertRaises(ValueError): m.hierarchy(design)

    def test_missing_rounding_child_cannot_certify_full_complement(self):
        design = copy.deepcopy(self.design)
        module = next(p for p in design.iter('srcdef') if p.get('name') == 'fpnew_rounding')
        target = next(p for p in module.findall('srcinst') if p.get('id') ==
                      next(p['compiled_instance']['id'] for p in self.children if p['module'] == 'fpnew_rounding'))
        module.remove(target)
        with self.assertRaises(ValueError): m.hierarchy(design)

    def test_exact_scalar5_internal_objects_allother_objects_retained(self):
        targets, complement = m.scalar_partition(self.scope, '3893821548', self.fields, {'product'})
        self.assertEqual(len(targets), 5); self.assertEqual(len(complement), len(self.fields) - 5)
        self.assertEqual(sum(p['missing_raw741']['total'] for p in targets), 14)
        self.assertTrue(any(p['attributes']['name'] == 'inject_carry_in' for p in complement))
        self.assertTrue(any(p['attributes']['name'] == 'sum_carry' for p in complement))
        self.assertTrue(all(p['attributes']['portnode'] == '0' for p in targets))

    def test_modified_import_bytes_or_frozen_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.v'; path.write_bytes(b'unchanged\n')
            sha = m.digest(path); m.baseline_bytes(path, sha, b'unchanged\n')
            with self.assertRaises(ValueError): m.baseline_bytes(path, sha, b'modified\n')
            path.write_bytes(b'modified\n')
            with self.assertRaises(ValueError): m.baseline_bytes(path, sha, b'modified\n')

    def test_wrong_scope_range_type_port_line_and_duplicate_rejected(self):
        for key, value in (('left', '10'), ('right', '1'), ('portnode', '3'), ('type', '3'),
                           ('line_num', '282'), ('excluded', '1'), ('file', '375')):
            changed = copy.deepcopy(self.fields)
            target = next(p for p in changed if p['attributes']['name'] == 'exponent_a')
            target['attributes'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.scalar_partition(self.scope, '3893821548', changed, set())
        with self.assertRaises(ValueError): m.scalar_partition(self.scope.replace('.i_ariane.', '.i_ara.'), '3893821548', self.fields, set())
        with self.assertRaises(ValueError): m.scalar_partition(self.scope, '2313019818', self.fields, set())
        with self.assertRaises(ValueError): m.scalar_partition(self.scope, '3893821548', self.fields + [self.fields[0]], set())

    def test_prequalified_overlap_and_missing_candidate_rejected(self):
        with self.assertRaises(ValueError): m.scalar_partition(self.scope, '3893821548', self.fields, {'sum_raw'})
        changed = [p for p in self.fields if p['attributes']['name'] != 'sum_raw']
        with self.assertRaises(ValueError): m.scalar_partition(self.scope, '3893821548', changed, set())

    def test_wrong_compiled_bitmap_checksum_width_rejected(self):
        for key, value in (('checksum', '1'), ('width', 3158)):
            raw = dict(self.raw[self.scope]); raw[key] = value
            with self.assertRaises(ValueError): m.shape_fields(self.definition, raw)


if __name__ == '__main__': unittest.main()
