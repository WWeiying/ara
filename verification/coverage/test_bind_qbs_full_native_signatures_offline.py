"""Actual fullcapture fixture and typed-signature/complement mutation gates; no EDA."""
import copy
import json
from pathlib import Path
import unittest

import bind_qbs_full_native_signatures_offline as b


class Offline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads((b.f.PARENT/'proof-native-plan.json').read_bytes())
        cls.raw = (b.CAPTURE/'native-rows.tcllist').read_bytes()

    def native_model(self):
        # Typed grammar fixture only; intentionally non-compiled IDs, never saved as evidence.
        lines = []
        identities = {}
        for c in self.artifact['candidates']:
            p = c['point']; key = c['scope'], p['expression']
            if key not in identities: identities[key] = 900000+len(identities)
            attrs = p['attributes']
            lines += ['CHECKSUM: "%s %s"' % (c['module_checksum'], c['checksum']), 'INSTANCE: '+c['scope'],
                'ANNOTATION: "'+b.f.proof.ANNOTATION+'"',
                'Condition %s "%s" "%s %s -1" (%s "%s")' %
                (identities[key], attrs['chksum'], p['expression'], attrs['width'], 700000+p['raw_index'], p['vector'])]
        return ('\n'.join(lines)+'\n').encode('ascii')

    def test_actual_all1344_display_fields_have_no_numeric_IDs(self):
        rows = b.displays(self.raw, self.artifact)
        self.assertEqual(len(rows), 1344)
        self.assertTrue(all(r['condition_display_kind'] == 'META_ONLY_NO_NUMERIC_ID' and
                            r['vector_display_kind'] == 'TRUTH_NAMES_ONLY_NO_VECTOR_IDS' for r in rows))
        self.assertTrue(all(r['observed_native_condition_id'] is None and r['observed_native_vector_ids'] is None for r in rows))

    def test_handle_is_not_a_numeric_signature(self):
        with self.assertRaises(ValueError): b.bind_explicit_native(self.raw, self.artifact)

    def test_compiled_signature_model_requires_explicit_native_records(self):
        records = b.bind_explicit_native(self.native_model(), self.artifact)
        self.assertEqual(len(records), 1792)
        self.assertGreater(int(records[0]['native_id']), 899999)

    def test_native_checksum_width_bit_expression_scope_vector_missing_extra_alias_mutations(self):
        raw = self.native_model(); lines = raw.splitlines(keepends=True)
        native = next(l for l in lines if l.startswith(b'Condition '))
        c = self.artifact['candidates'][0]; p = c['point']; attrs = p['attributes']
        mutations = [b''.join(lines[:-4]), raw+native,
            raw.replace(('"'+attrs['chksum']+'"').encode(), b'"123"', 1),
            raw.replace((p['expression']+' '+attrs['width']+' -1').encode(), (p['expression']+' 999 -1').encode(), 1),
            raw.replace(b' -1"', b' 0"', 1), raw.replace(b'i_payload_buffer', b'i_wrong_scope', 1),
            raw.replace(('"'+p['vector']+'")').encode(), b'"unexpected")', 1),
            raw.replace(p['expression'].encode(), b'wrong expression', 1),
            raw.replace(b'Condition 900001 ', b'Condition 900000 ', 1),
            raw+b'Branch 1 "x"\n', raw+b'INSTANCE: other\n']
        for changed in mutations:
            self.assertNotEqual(changed, raw)
            with self.assertRaises(ValueError): b.bind_explicit_native(changed, self.artifact)

    def test_nonascii_native_records_rejected_not_ignored(self):
        with self.assertRaises(UnicodeDecodeError): b.bind_explicit_native(self.native_model()+b'\xc8\n', self.artifact)

    def test_actual41214_complement_and1792_neighbors(self):
        scopes = b.protection(self.artifact)
        self.assertEqual(sum(s['protected_count'] for s in scopes.values()), 41214)
        self.assertEqual(sum(s['target_count'] for s in scopes.values()), 1792)
        self.assertEqual(sum(len(g['retained_vectors']) for s in scopes.values() for g in s['retained_target_group_vectors']), 1792)

    def test_protection_overlap_gap_wholecondition_rejected(self):
        scope = next(iter(self.artifact['scope_protection']))
        for mode in ('overlap', 'gap', 'targetdrift', 'wholecondition'):
            a = copy.deepcopy(self.artifact); s = a['scope_protection'][scope]
            if mode == 'overlap': s['protected_raw_bitmap'] = hex(int(s['protected_raw_bitmap'],16)|int(s['target_raw_bitmap'],16))
            if mode == 'gap': s['protected_raw_bitmap'] = '0x0'
            if mode == 'targetdrift': s['target_raw_bitmap'] = '0x0'
            if mode == 'wholecondition': a['native_groups'][0]['retained'] = []
            with self.subTest(mode=mode), self.assertRaises(ValueError): b.protection(a)

    def test_actual_success_is_not_fullqualification(self):
        record = b.evidence()
        self.assertEqual(record['observed_native_numeric_records'], 0)
        self.assertFalse(record['native_qualified'])
        self.assertFalse(record['protection_qualified'])
        self.assertFalse(record['EDA_started'])


if __name__ == '__main__':
    unittest.main()
