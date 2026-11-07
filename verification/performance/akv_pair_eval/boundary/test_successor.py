#!/usr/bin/env python3
"""Host-only maintenance/retirement fixtures. No simulator or original report writes."""
from collections import Counter
import copy
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('boundary_successor_hosttests', HERE / 'check_successor.py')
s = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s)
o = s.original
PC_WORDS = {0x80001000 + i * 4: w for i, w in enumerate([s.INFO, *o.SIGNATURE_NAMES])}
WORD_PC = {w: pc for pc, w in PC_WORDS.items()}


def vector_row(event, cycle, seq=0, vid=0, word=0, shape=(0, 0, 0, 0, 0)):
    row = dict.fromkeys(s.VECTOR_FIELDS, '0')
    row.update(event=event, cycle=str(cycle), arch_seq=str(seq), vid=str(vid),
               insn=f'{word:08x}', be='00', wdata='0000000000000000', nr_lanes='4', vlen_bits='1024')
    row.update({k: str(v) for k, v in zip(s.SHAPE, shape)})
    return row


def commit_row(event, cycle, order, word=0, port=-1, pc=0):
    row = dict.fromkeys(s.COMMIT_FIELDS, '0')
    row.update(event=event, cycle=str(cycle), order=str(order), port=str(port), trans_id='-1',
               pc=f'{pc:016x}', insn=f'{word:08x}', rd_wdata='0000000000000000',
               mem_addr='0000000000000000', mem_rmask='00', mem_wmask='00', mem_wdata='0000000000000000')
    return row


def fixture(prefix=3, cycle_offset=100, vid_offset=0, override=None):
    """Create independent raw alloc/done and architecture/retirement namespaces."""
    native, extended, triples = s.expected_work()
    metadata = {
        o.FULL: (0, 0, 1, 1, 0), o.REFILL: (0, 0, 1, 1, 0), o.RELEASE: (0, 0, 1, 1, 0),
        o.COLUMN: (1, 8, 1, 64, 0), o.COLUMN9: (1, 9, 1, 64, 0), o.PANEL: (1, 8, 1, 256, 0),
        o.ROW64: (1, 8, 1, 64, 0), o.ROW96: (1, 8, 1, 96, 0),
        o.ROW128: (1, 8, 1, 128, 0), o.ROW128_GQA6: (1, 14, 1, 128, 0),
        0x00000057: (1, 0, 1, 64, 0)}
    vector, commit, native_index, retirement = [vector_row('config', 0)], [], -1, 0
    for seq, word in enumerate([0x00000057] * prefix + extended):
        cycle = cycle_offset + seq * 32
        start = commit_row('arch_start', cycle, seq, word)
        start['trans_id'] = str(seq % 16)
        commit.append(start)
        if word != s.INFO:
            shapes = [metadata[word]]
            if word & 0x7f == 0x5b:
                native_index += 1
                if native_index in triples:
                    shapes = [(1, 8, 1, 64, 0), (1, 9, 1, 64, 0), (1, 8, 1, 96, 0)]
                shapes = (override or {}).get(native_index, shapes)
            for i, shape in enumerate(shapes):
                vid = (i + vid_offset) % 8
                for event, offset in (('alloc', 2 + i * 4), ('done', 4 + i * 4)):
                    row = vector_row(event, cycle + offset, seq, vid, word, shape)
                    vector.append(row)
                    commit.append(commit_row('uop_' + event, cycle + offset, seq, word, vid))
        retire = commit_row('retire', cycle + 20, retirement, word, 0, WORD_PC.get(word, 0x80002000))
        commit.append(retire)
        retirement += 1
        # Scalar retirements do not increment accelerator arch_seq.
        commit.append(commit_row('retire', cycle + 21, retirement, 0x00000013, 0, 0x80002004))
        retirement += 1
    return vector, commit


def write_csv(path, fields, data):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)


def reindex_retirements(data):
    index = 0
    for row in data:
        if row['event'] == 'retire':
            row['order'] = str(index)
            index += 1


class SuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = fixture()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='.host-successor-', dir=HERE)
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.vector, self.commit = self.directory / 'vector_trace.csv', self.directory / 'commit.csv'

    def audit(self, vector=None, commit=None):
        vector = self.fixture[0] if vector is None else vector
        commit = self.fixture[1] if commit is None else commit
        write_csv(self.vector, s.VECTOR_FIELDS, vector)
        write_csv(self.commit, s.COMMIT_FIELDS, commit)
        return s.audit_work(self.vector, PC_WORDS)

    def test_strict_positive_and_raw_preservation(self):
        result = self.audit()
        before = (self.vector.read_bytes(), self.commit.read_bytes())
        again = s.audit_work(self.vector, PC_WORDS)
        self.assertEqual(before, (self.vector.read_bytes(), self.commit.read_bytes()))
        self.assertEqual(result, again)
        self.assertEqual(result['raw_custom_allocations'], 3692)
        self.assertEqual(result['architectural_native_commands'], 3680)
        self.assertEqual(result['maintenance_allocations'], 12)
        self.assertEqual(len(result['maintenance_groups']), 6)
        self.assertEqual(result['counts'], o.EXPECTED_COUNTS)
        self.assertEqual(result['raw_custom_alloc_counts']['row_d96'], 532)
        self.assertEqual(result['counts']['row_d96'], 520)
        self.assertEqual(result['commit_checks']['retired_custom_instructions'], 3696)
        self.assertEqual(result['commit_checks']['retired_info_commands'], 16)
        self.assertEqual(result['commit_checks']['trap_records'], 0)
        self.assertFalse(result['independent_protocol_checked'])

    def test_seq_cycle_vid_coordinates_are_not_hardcoded(self):
        vector, commit = fixture(prefix=11, cycle_offset=1 << 35, vid_offset=4)
        result = self.audit(vector, commit)
        seqs = [x['arch_seq'] for x in result['maintenance_groups']]
        self.assertEqual(len(set(seqs)), 6)
        self.assertNotEqual(seqs, [2344, 3466, 4068, 4954, 5716, 6838])
        self.assertTrue(all(a['cycle'] >= 1 << 35 for g in result['maintenance_groups'] for a in g['allocations']))

    def test_original_log_api_is_exact_alias(self):
        self.assertIs(s.check_run, o.check_run)

    def test_original_checker_reproduces_semantic_rejection(self):
        self.audit()
        with self.assertRaisesRegex(ValueError, 'Duplicate/replayed boundary allocation'):
            o.vector_workcounts(self.vector)

    def test_frozen_sources_and_build_pins(self):
        for name, digest in s.SEALED.items():
            self.assertEqual(s.digest(HERE / name), digest)
        o.contract.verify(s.SEMANTICS_PINS)
        build = o.contract.OUT / 'akv_pair_boundary_build_20261107_01'
        report = o.verify_build(build)
        self.assertEqual(report['expected_commands'], 3680)
        self.assertTrue(report['elf_link_checks']['knowncall_signatures_checked'])
        words = s.elf_custom_instructions(report['elf'])
        self.assertTrue(set(o.SIGNATURE_NAMES) | {s.INFO} <= set(words.values()))

    def test_api_validates_all_original_pins_before_and_after(self):
        self.audit()
        info = dict(elf='fixture-only', elf_sha256='fixture-only', source_pins_sha256='fixture-only')
        with mock.patch.object(o, 'verify_build', return_value=info) as gate, \
             mock.patch.object(s, 'elf_custom_instructions', return_value=PC_WORDS):
            result = s.check_vector_workcounts(self.vector, self.directory)
            self.assertEqual(gate.call_count, 2)
            self.assertTrue(result['post_build_pins_match'])
            self.assertFalse(result['performance_measured'])
        with mock.patch.object(o, 'verify_build', side_effect=ValueError('missing original pin')), \
             mock.patch.object(s, 'audit_work') as work, self.assertRaisesRegex(ValueError, 'original pin'):
            s.check_vector_workcounts(self.vector, self.directory)
        work.assert_not_called()
        with mock.patch.object(o, 'verify_build', side_effect=[info, dict(info, elf_sha256='drift')]), \
             mock.patch.object(s, 'elf_custom_instructions', return_value=PC_WORDS), \
             self.assertRaisesRegex(ValueError, 'receipt changed'):
            s.check_vector_workcounts(self.vector, self.directory)

    def test_unknown_duplicate_and_wrong_location_rejected(self):
        native, _, triples = s.expected_work()
        column = native.index(o.COLUMN)
        late_row = next(i for i, w in enumerate(native) if w == o.ROW96 and i not in triples)
        for index, shapes in [(column, [(1, 8, 1, 64, 0)] * 2),
                              (late_row, [(1, 8, 1, 64, 0), (1, 9, 1, 64, 0), (1, 8, 1, 96, 0)])]:
            vector, commit = fixture(override={index: shapes})
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'Unexpected duplicate'):
                self.audit(vector, commit)

    def test_original_operation_and_maintenance_missing(self):
        index = min(s.expected_work()[2])
        for shapes in ([(1, 8, 1, 64, 0), (1, 9, 1, 64, 0)], [(1, 8, 1, 96, 0)],
                       [(1, 8, 1, 64, 0), (1, 8, 1, 96, 0)], []):
            vector, commit = fixture(override={index: shapes})
            with self.subTest(shapes=shapes), self.assertRaises(ValueError):
                self.audit(vector, commit)

    def test_triple_shape_and_order_mutations(self):
        index = min(s.expected_work()[2])
        shapes = [(1, 8, 1, 64, 0), (1, 9, 1, 64, 0), (1, 8, 1, 96, 0)]
        for item, field, value in [(0, 1, 9), (1, 1, 8), (0, 2, 2), (1, 3, 96),
                                    (2, 3, 64), (2, 4, 1), (0, 0, 0)]:
            bad = [list(x) for x in shapes]
            bad[item][field] = value
            vector, commit = fixture(override={index: bad})
            with self.subTest(item=item, field=field), self.assertRaisesRegex(ValueError, 'triple'):
                self.audit(vector, commit)
        vector, commit = fixture(override={index: [shapes[1], shapes[0], shapes[2]]})
        with self.assertRaisesRegex(ValueError, 'triple'):
            self.audit(vector, commit)

    def test_global_vid_lifetime_and_tag_mutations(self):
        word = f'{o.ROW96:08x}'
        vector, commit = copy.deepcopy(self.fixture)
        seq = next(r['arch_seq'] for r in vector if r['insn'] == word and r['vl'] == '64')
        for field, value in [('vid', '8'), ('arch_seq', '-1'), ('eew', '4')]:
            bad = copy.deepcopy(vector)
            next(r for r in bad if r['event'] == 'alloc' and r['arch_seq'] == seq)[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.audit(bad, commit)
        bad = copy.deepcopy(vector)
        alloc = next(r for r in bad if r['event'] == 'alloc' and r['arch_seq'] == seq)
        done = next(r for r in bad if r['event'] == 'done' and r['arch_seq'] == seq)
        done['vd'] = '7'
        with self.assertRaisesRegex(ValueError, 'completion'):
            self.audit(bad, commit)
        bad = copy.deepcopy(vector)
        first = next(i for i, r in enumerate(bad) if r['event'] == 'alloc' and r['arch_seq'] == seq)
        # Keep the first VID live, then attempt to allocate that same VID again.
        bad.pop(first + 1)
        bad[first + 1]['vid'] = bad[first]['vid']
        with self.assertRaisesRegex(ValueError, 'busy VID'):
            self.audit(bad, commit)
        with self.assertRaisesRegex(ValueError, 'incomplete VID'):
            self.audit(vector[:-1], commit)

    def test_native_word_and_shape_changes_rejected(self):
        for field, value in [('insn', f'{o.ROW128:08x}'), ('vl', '95'), ('use_vd', '0')]:
            vector, commit = copy.deepcopy(self.fixture)
            seq = next(r['arch_seq'] for r in vector if r['insn'] == f'{o.ROW96:08x}' and r['vl'] == '96')
            for row in vector:
                if row['arch_seq'] == seq:
                    row[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.audit(vector, commit)

    def test_commit_retirement_mismatch_missing_duplicate_and_info(self):
        vector, commit = self.fixture
        first_native = next(i for i, r in enumerate(commit) if r['event'] == 'retire' and
                            int(r['insn'], 16) == o.FULL)
        first_info = next(i for i, r in enumerate(commit) if r['event'] == 'retire' and
                          int(r['insn'], 16) == s.INFO)
        changed = copy.deepcopy(commit)
        changed[first_native]['insn'] = f'{o.REFILL:08x}'
        missing = copy.deepcopy(commit)
        missing.pop(first_native)
        duplicated = copy.deepcopy(commit)
        duplicated.insert(first_native, copy.deepcopy(duplicated[first_native]))
        info_missing = copy.deepcopy(commit)
        info_missing.pop(first_info)
        for bad in (changed, missing, duplicated, info_missing):
            reindex_retirements(bad)
            with self.subTest(kind='commit stream'), self.assertRaises(ValueError):
                self.audit(vector, bad)

    def test_commit_traps_orders_pc_and_backend_mismatches(self):
        for event, field, value in [('retire', 'trap', '1'), ('arch_start', 'trap', '1'),
                                    ('retire', 'order', '99'), ('arch_start', 'order', '99')]:
            vector, commit = copy.deepcopy(self.fixture)
            next(r for r in commit if r['event'] == event)[field] = value
            with self.subTest(event=event, field=field), self.assertRaises(ValueError):
                self.audit(vector, commit)
        for event, field, value in [('retire', 'pc', '000000008000ffff'),
                                    ('uop_alloc', 'insn', f'{o.REFILL:08x}')]:
            vector, commit = copy.deepcopy(self.fixture)
            next(r for r in commit if r['event'] == event and int(r['insn'], 16) == o.FULL)[field] = value
            with self.subTest(event=event), self.assertRaises(ValueError):
                self.audit(vector, commit)

    def test_schema_config_reset_cycle_and_missing_pair(self):
        for index, field, value in [(0, 'event', 'reset'), (0, 'vlen_bits', '512'),
                                    (1, 'event', 'reset'), (1, 'cycle', '-1'),
                                    (2, 'cycle', '0'), (1, 'insn', 'xxxxxxxx')]:
            vector, commit = copy.deepcopy(self.fixture)
            vector[index][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.audit(vector, commit)
        self.audit()
        content = self.vector.read_text().replace('cycle,event', 'cycle,cycle', 1)
        self.vector.write_text(content)
        with self.assertRaisesRegex(ValueError, 'schema'):
            s.audit_work(self.vector, PC_WORDS)
        write_csv(self.vector, s.VECTOR_FIELDS, self.fixture[0])
        self.commit.unlink()
        with self.assertRaises(FileNotFoundError):
            s.audit_work(self.vector, PC_WORDS)


if __name__ == '__main__':
    unittest.main()
