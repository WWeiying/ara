import copy
import csv
import unittest
import collect_itlb_asid_exec_bulk_csr as c


class Lifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = c.life.OUT / 'itlb-asid-exec-bulk-old-image-773-agent-20261007-01'
        with (run / 'commit_trace.csv').open() as f:
            allrows = list(csv.DictReader(f))
        # Actual frozen sequence, not a count-only mock.
        cls.rows = [r for r in allrows if r['event'] != 'retire' or
                    0x800024d0 <= int(r['pc'], 16) <= 0x800024e6]
        pp = c.life.OUT / 'itlb-asid-exec-bulk-preflight-agent-20261007-01/preflight.json'
        cls.symbols = c.life.read_bound(pp, c.core.PREFLIGHT_SHA)['symbols']

    def reject(self, mutate, message=None):
        rows = copy.deepcopy(self.rows)
        mutate(rows)
        if message:
            with self.assertRaisesRegex(ValueError, message):
                c.csr_lifecycle(rows, self.symbols)
        else:
            with self.assertRaises(ValueError):
                c.csr_lifecycle(rows, self.symbols)

    def test_actual_independent_start_before_retire_and_tid_reuse(self):
        result = c.csr_lifecycle(self.rows, self.symbols)
        records = result['records']
        self.assertEqual([r['trans_id'] for r in records], [3, 4] * 3)
        self.assertTrue(all(records[i+1]['start'] < records[i]['retire_cycle']
                            for i in (0, 2, 4)))
        self.assertTrue(all(r['response'] <= r['retire_cycle'] <= r['consumer_cycle']
                            for r in records))

    def test_multiple_distinct_pending_requests(self):
        rows = copy.deepcopy(self.rows)
        response = next(r for r in rows if r['event'] == 'cvx_resp')
        rows.remove(response)
        second_req = next(i for i, r in enumerate(rows)
                          if r['event'] == 'cvx_req' and r['trans_id'] == '4')
        response['cycle'] = rows[second_req]['cycle']
        rows.insert(second_req + 1, response)
        self.assertEqual(c.csr_lifecycle(rows, self.symbols)['requests'], 6)

    def test_duplicate_response(self):
        self.reject(lambda rows: rows.insert(0, next(r for r in rows if r['event'] == 'cvx_resp')))

    def test_missing_response(self):
        self.reject(lambda rows: rows.remove(next(r for r in rows if r['event'] == 'cvx_resp')))

    def test_late_response(self):
        self.reject(lambda rows: next(r for r in rows if r['event'] == 'cvx_resp').update(cycle='118021'))

    def test_changed_request(self):
        self.reject(lambda rows: next(r for r in rows if r['event'] == 'cvx_req').update(insn='00f027f3'))

    def test_exact_retire_identity(self):
        for field, value in (('pc', '800024d4'), ('rd', '15'), ('rd_wdata', '1'), ('trap', '1')):
            self.reject(lambda rows: next(r for r in rows if r['event'] == 'retire' and
                int(r['insn'], 16) == c.WORDS[0]).update({field: value}))

    def test_real_consumer_value_address_and_be(self):
        for field, value in (('mem_addr', '80000000'), ('mem_wdata', '1'),
                             ('mem_wmask', '0f'), ('cycle', '118019')):
            self.reject(lambda rows: next(r for r in rows if int(r['insn'], 16) == 0xf9b8).update({field: value}))

    def test_overwrite_before_consumer(self):
        self.reject(lambda rows: next(r for r in rows if int(r['insn'], 16) == 0x00302873).update(rd='14'))

    def test_foreign_intervening_encoding(self):
        self.reject(lambda rows: next(r for r in rows if int(r['insn'], 16) == 0x95ca).update(insn='95ce'))

    def test_decoded_dependency_is_not_assumed(self):
        self.assertEqual(c.reads(0x00f027f3), {0})
        self.assertEqual(c.reads(0x95ca), {11, 18})
        self.assertEqual(c.reads(0xf9b8), {11, 14})
        self.assertEqual(c.reads(0xfdbc), {11, 15})
        with self.assertRaises(ValueError):
            c.reads(0xffff)

    def test_historical_source_pins_match(self):
        self.assertEqual(len(c.source_pins()), 5)


if __name__ == '__main__':
    unittest.main()
