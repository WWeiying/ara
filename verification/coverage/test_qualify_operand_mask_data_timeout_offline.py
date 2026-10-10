"""Fail-closed terminal, oracle, protocol and incomplete-VDB regressions."""
import copy
import csv
import io
from pathlib import Path
import tempfile
import unittest

import qualify_operand_mask_data_timeout_offline as q


def terminal_rows():
    rows = []
    for i in range(2):
        r = dict.fromkeys(q.COMMIT_FIELDS, '0')
        r.update(cycle=str(10 + i), event='retire', order=str(i), pc='80000000', insn='13')
        rows.append(r)
    rows[1].update(pc='8000007a', insn='00a2b023', mem_addr='80001000', mem_wmask='ff', mem_wdata='1')
    return rows


def encoded(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=q.COMMIT_FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


class OfflineTests(unittest.TestCase):
    def test_cut_exact_success_including_same_cycle_posttail(self):
        rows = terminal_rows()
        tail = dict(rows[-1], order='2', mem_addr='0', mem_wmask='0', pc='8000007e', insn='a001')
        cut, kept, result = q.prefix(encoded(rows + [tail]))
        self.assertEqual(len(kept), 2)
        self.assertEqual(cut, encoded(rows))
        self.assertEqual(result['value'], 1)
        self.assertGreater(result['ignored_postterminal_bytes'], 0)

    def test_failed_partial_missing_terminal_rejected(self):
        for field, value in (('mem_wdata', '3'), ('mem_wmask', '0f'), ('trap', '1'),
                             ('event', 'cvx_resp'), ('pc', '80000050')):
            rows = terminal_rows()
            rows[-1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                q.prefix(encoded(rows))
        with self.assertRaises(ValueError):
            q.prefix(encoded(terminal_rows()[:1]))

    def test_reordered_missing_duplicate_unknown_truncated(self):
        for field, value in (('order', '0'), ('order', '2'), ('cycle', '9'), ('event', 'unknown')):
            rows = terminal_rows()
            rows[-1][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                q.prefix(encoded(rows))
        with self.assertRaises(ValueError):
            q.prefix(encoded(terminal_rows())[:-1])

    def test_actual_independent_oracle_and_guards(self):
        symbols = dict(output=10000, compared=20000, gathered=30000, g75_result=40000, num_failed=40008)
        memory, reads = {}, set()
        for phase in range(4):
            add, mask, gather = q.independent.expected(phase)
            for name, stride, data in (('output', 1040, add), ('compared', 32, mask.to_bytes(16, 'little')),
                                       ('gathered', 1040, gather)):
                base = symbols[name] + stride * phase
                for i, value in enumerate(data + bytes([0x69]) * 16):
                    memory[base + i] = value
                    reads.add(base + i)
        for base, value in ((40000, 5256), (40004, 0), (40008, 0)):
            memory.update({base + i: byte for i, byte in enumerate(value.to_bytes(4, 'little'))})
        result = q.independent_actual(memory, reads, symbols)
        self.assertEqual(result['independently_compared_bytes'], 8256)
        for address in (10000, 11024, 20000, 30000, 40000):
            bad = dict(memory)
            bad[address] ^= 1
            with self.subTest(address=address), self.assertRaises(ValueError):
                q.independent_actual(bad, reads, symbols)
        with self.assertRaises(ValueError):
            q.independent_actual(memory, reads - {10000}, symbols)

    def test_unknown_or_error_contract_rejected(self):
        for text in ('[ARA_CONTRACT_ERROR] bad', 'UVM_FATAL bad',
                     '[ARA_CONTRACT_TRACE] sample=post_edge unknown', 'Error: fatal'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                q.protocol(text, [], [], 11)

    def test_missing_protocol_lastdrain_rejected(self):
        with self.assertRaises(ValueError):
            q.protocol('', [], [], 11)

    def test_duplicate_log_partial_must_match_actual_console(self):
        text = '[ARA_CONTRACT_TRACE] first\n[ARA_CONTRACT_TRACE] second\n'
        result = q.duplicate_log_prefix(text[:-4], text)
        self.assertFalse(result['complete'])
        with self.assertRaises(ValueError):
            q.duplicate_log_prefix('[ARA_CONTRACT_TRACE] wrong', text)

    def test_truncated_native_vector_cannot_pass(self):
        header = ','.join(q.VECTOR_FIELDS) + '\n'
        with self.assertRaises(ValueError):
            q.table((header + '241915,write,60,0,0,2,32880c57,1,24,3,128,0,115,ff,').encode(), q.VECTOR_FIELDS)

    def test_mode64_only_not_admissible(self):
        with tempfile.TemporaryDirectory(dir=q.OUT) as name:
            p = Path(name)
            (p / '.mode64').touch()
            result = q.inspect_vdb(p)
            self.assertFalse(result['coverage_admissible'])
            self.assertFalse(result['testdata_present'])

    def test_rvc_memory_decoding_is_used(self):
        result = q.memory_decode(0xc606)
        self.assertEqual(result['kind'], 'write')
        self.assertEqual(result['size'], 4)
        self.assertEqual(result['base'], 2)


if __name__ == '__main__':
    unittest.main()
