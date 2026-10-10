import copy
import json
import unittest

import qualify_gap111_terminal as q


class QualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre = json.loads((q.runner.PRE / 'preflight-manifest.json').read_bytes())
        cls.symbols = pre['symbols']
        cls.reference = q.scalar_api.reference_prefix(q.scalar_api.spike_trace.parse_spike_commits(
            q.runner.PRE / 'spike.trace'), cls.symbols['tohost'])
        registers = dict.fromkeys(range(32), 0)
        rows = []
        for c in cls.reference:
            if rows and rows[-1]['pc'] == 0x40004024:
                rows.append(dict(event='retire', trap=1, pc=0x40004028, insn=0x73,
                                 rd=0, rd_wdata=0, mem_addr=0, mem_rmask=0, mem_wmask=0, mem_wdata=0))
            writes = {r: v for r, v in c.gpr_writes.items() if r}
            if len(writes) > 1:
                raise AssertionError('Not scalar reference')
            rd, value = next(iter(writes.items()), (0, 0))
            row = dict(event='retire', trap=0, pc=c.pc, insn=c.instruction,
                       rd=rd, rd_wdata=value, mem_addr=0, mem_rmask=0, mem_wmask=0, mem_wdata=0)
            decoded = q.scalar_api.memory_decode(c.instruction)
            if decoded:
                address = (registers[decoded['base']] + decoded['offset']) & ((1 << 64) - 1)
                mask = ((1 << decoded['size']) - 1) << (address & 7)
                row['mem_addr'] = address
                row['mem_' + ('r' if decoded['kind'] == 'read' else 'w') + 'mask'] = mask
                if decoded['kind'] == 'write':
                    row['mem_wdata'] = registers[decoded['register']] & ((1 << (8 * decoded['size'])) - 1)
            rows.append(row)
            registers.update(writes)
        for order, row in enumerate(rows):
            row.update(order=order, cycle=order)
        cls.rows = rows

    def test_exact_type_not_bool(self):
        with self.assertRaises(ValueError): q.exact({'count': True}, {'count': 1}, 'bad')

    def test_partial_scalar_rejected(self):
        with self.assertRaises(ValueError): q.scalar_gate({'status': 'PREFIX'}, [])

    def test_real_architecture_adapter_retains_memory_checks(self):
        function = q.architecture_function()
        self.assertEqual(function.__globals__['runner'].oracle, q.runner.oracle)
        with self.assertRaises(ValueError): function([], [], {})

    def test_wrong_trap_owner_rejected(self):
        function = q.architecture_function()
        row = dict(order=0, event='retire', trap=1, pc=0x40004024, insn=0x73,
                   rd=0, rd_wdata=0, mem_rmask=0, mem_wmask=0)
        with self.assertRaisesRegex(ValueError, 'trap PC'): function([row], [], {})

    def test_actual740_zero_FSM_and_false_gain_rejected(self):
        before = json.loads((q.runner.oracle.BASE / 'combined-bits.json').read_bytes())
        record = json.loads(q.ANCHOR.read_bytes())
        single = copy.deepcopy(before)
        result = q.target_gain(before, single, record['targets'])
        self.assertEqual(result['new_targets'], 0)
        target = record['targets'][0]
        scope, index = target['scope'], target['compiled']['raw_index']
        row = single['metrics']['fsm'][scope]
        row['bits'] = hex(int(row['bits'], 16) | 1 << (27 - index))
        self.assertEqual(q.target_gain(before, single, record['targets'])['new_targets'], 1)
        row['checksum'] = '0'
        with self.assertRaises(ValueError): q.target_gain(before, single, record['targets'])

    def test_UVM_messages_and_nonzero_contract_rejected(self):
        for message in ('UVM_ERROR @ 1: reporter problem', 'UVM_FATAL : 1', 'Fatal-[BAD] failed'):
            with self.assertRaises(ValueError):
                q.scalar_api.log_gate('Core Test *** SUCCESS ***\n' + message, require_contract=False)

    def test_zero_UVM_summary_allowed(self):
        self.assertEqual(q.scalar_api.log_gate('Core Test *** SUCCESS ***\nUVM_ERROR : 0\nUVM_FATAL : 0',
                                              require_contract=False), {})

    def test_full_independent_Spike_fixture_including_RVC(self):
        result = q.architecture_function()(self.rows, self.reference, self.symbols)
        self.assertEqual(result['memory_accesses'], 3561)
        self.assertEqual(result['oracle']['checks'], 26)
        self.assertGreater(result['memory_counts'].get('compressed_write', 0), 0)

    def test_wrong_GPR_memory_or_branch_rejected(self):
        for field, predicate in [('rd_wdata', lambda r: r['rd'] != 0),
                                 ('mem_wdata', lambda r: r['mem_wmask'] != 0),
                                 ('mem_rmask', lambda r: r['mem_rmask'] != 0),
                                 ('pc', lambda r: r['insn'] & 127 == 0x63)]:
            rows = [dict(r) for r in self.rows]
            row = next(r for r in rows if predicate(r))
            row[field] ^= 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                q.architecture_function()(rows, self.reference, self.symbols)


if __name__ == '__main__':
    unittest.main()
