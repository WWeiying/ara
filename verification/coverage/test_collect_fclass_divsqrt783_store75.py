import copy
import unittest
import tempfile
from pathlib import Path
import collect_fclass_divsqrt783_store75 as s
from test_collect_fclass_divsqrt783 import native_fixture


def fixture():
    refs, activities, mapping, symbols = native_fixture()
    rows = []
    for seq, activity in activities.items():
        c = refs[mapping[seq]]
        if not c.vector_writes:
            eew, vl = activity.eew, activity.vl
            c.instruction = 0x27 | ((eew + 4) << 12) | (24 << 7)
            activity.instruction = c.instruction
            activity.vd = 24
            activity.eew = activity.vl = activity.vstart = None
            for event, cycle in (('alloc', seq * 2), ('done', seq * 2 + 1)):
                rows.append(dict(arch_seq=str(seq), event=event, insn=hex(c.instruction),
                    eew=str(eew), vl=str(vl), vstart='0', use_vd='0', vd='0',
                    vid=str(seq % 8), cycle=str(cycle), nr_lanes='4', vlen_bits='1024'))
    return activities, rows, refs, mapping, symbols


class Store75(unittest.TestCase):
    def test_only_metadata_changes_all75(self):
        args = fixture(); before = copy.deepcopy(args[0]); restored, proof = s.restore_stores(*args)
        self.assertEqual(args[0], before)
        self.assertEqual(proof['store_count'], 75)
        self.assertEqual(len(proof['records']), 75)
        for seq, a in restored.items():
            if a.instruction & 127 == 0x27:
                self.assertEqual(a.eew, (seq - 6) // 100 + 1)
                self.assertEqual(a.vl, 32 // (1 << a.eew))
            else: self.assertEqual(a, before[seq])
        self.assertEqual(s.original.native_state(args[2], restored, args[3], args[4])['operations']['store'], 75)

    def test_missing_extra_wrong_owner_or_opcode(self):
        for kind in ('missing_activity', 'extra_activity', 'mapping', 'pc', 'opcode', 'unknown_event', 'extra_done'):
            with self.subTest(kind=kind):
                activities, rows, refs, mapping, symbols = fixture(); seq = int(rows[0]['arch_seq'])
                if kind == 'missing_activity': activities.pop(seq)
                if kind == 'extra_activity': activities[999] = copy.deepcopy(activities[seq])
                if kind == 'mapping': mapping[seq] = 0
                if kind == 'pc': refs[mapping[seq]].pc = symbols['matrix_store32']
                if kind == 'opcode': rows[0]['insn'] = '0'
                if kind == 'unknown_event': rows[0]['event'] = 'write'
                if kind == 'extra_done': rows.append(copy.deepcopy(rows[1]))
                with self.assertRaises(ValueError): s.restore_stores(activities, rows, refs, mapping, symbols)

    def test_context_order_geometry_negative(self):
        for key, value in (('eew', '2'), ('vl', '8'), ('vstart', '1'), ('use_vd', '1'), ('vd', '24'),
            ('vid', '8'), ('cycle', '-1'), ('nr_lanes', '8'), ('vlen_bits', '2048')):
            with self.subTest(key=key):
                args = fixture(); args[1][1][key] = value
                with self.assertRaises(ValueError): s.restore_stores(*args)

    def test_parser_contract_negative(self):
        for key, value in (('allocations', 2), ('completions', 0), ('use_vd', True), ('vd', 0),
            ('eew', 1), ('vl', 16), ('vstart', 0), ('writes', [object()])):
            with self.subTest(key=key):
                args = fixture(); seq = int(args[1][0]['arch_seq']); setattr(args[0][seq], key, value)
                with self.assertRaises(ValueError): s.restore_stores(*args)

    def test_exclusive_closure_never_overwrites_existing_core(self):
        _, proof = s.restore_stores(*fixture())
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); core = out / 'qualification.json'
            value = dict(status='FCLASS_DIVSQRT783_FULL_ARCHITECTURE_NATIVE_RAW_QUALIFIED_NOT_ADMITTED',
                native=dict(operations=dict(store=75)), input_pins={})
            s.life.save(core, value); content = core.read_bytes(); sha = s.life.digest(core)
            # The real exclusive publisher must reject an existing core overwrite.
            with self.assertRaises(FileExistsError): s.life.save(core, value)
            closure = s.publish_closure(out, sha, proof, {})
            saved = s.life.read_bound(closure, s.life.digest(closure))
            self.assertEqual(saved['core_qualification_sha'], sha)
            self.assertEqual(saved['input_pins'][str(core)], sha)
            self.assertEqual(core.read_bytes(), content)
            closure_bytes = closure.read_bytes()
            with self.assertRaises(ValueError): s.publish_closure(out, sha, proof, {})
            self.assertEqual(core.read_bytes(), content)
            self.assertEqual(closure.read_bytes(), closure_bytes)

    def test_publication_wrong_core_or_missing_proof_rejected(self):
        _, proof = s.restore_stores(*fixture())
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); core = out / 'qualification.json'
            s.life.save(core, dict(status='HOLD', native=dict(operations=dict(store=75)), input_pins={}))
            sha = s.life.digest(core)
            with self.assertRaises(ValueError): s.publish_closure(out, sha, proof, {})
            self.assertFalse((out / 'store75-closure.json').exists())
            self.assertEqual(s.life.digest(core), sha)

    def test_actual_trace_mapping_and_diff(self):
        run = s.life.OUT / 'fclass-divsqrt783-old-image-agent-20261008-01'
        pins = {str(run / n): s.life.digest(run / n) for n in ('vector_trace.csv', 'commit_trace.csv')}
        restored, proof = s.actual_store_proof(run)
        self.assertEqual(proof['store_count'], 75)
        self.assertEqual({e: sum(r['after']['eew'] == e for r in proof['records']) for e in (1, 2, 3)}, {1: 25, 2: 25, 3: 25})
        self.assertEqual(sum(a.instruction & 127 == 0x27 for a in restored.values()), 75)
        print('ACTUAL_STORE75_FIRST_LAST', proof['records'][0], proof['records'][-1])
        s.life.check(pins)


if __name__ == '__main__': unittest.main()
