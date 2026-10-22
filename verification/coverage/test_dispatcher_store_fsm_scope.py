"""Frozen-source structural checks; not a native FSM exclusion approval."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class StoreFSMScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The integration checkout has later edits; this mirror matches the
        # frozen image byte-for-byte. Never accept it without the build hash.
        original = ROOT / 'hardware/src/ara_dispatcher.sv'
        path = ROOT.parent / 'ara_dsa/hardware/src/ara_dispatcher.sv'
        pins = json.loads((ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
        if hashlib.sha256(path.read_bytes()).hexdigest() != pins[str(original)]:
            raise ValueError('Dispatcher source differs from frozen build')
        cls.text = path.read_text()

    def test_decode_blocked_has_only_default_and_guarded_assignment(self):
        assignments = re.findall(r'\bdecode_blocked\s*=\s*([^;]+);', self.text)
        self.assertEqual(assignments, ["1'b0", 'acc_req_i.req_valid && acc_req_i.resp_ready && !ara_req_ready_i'])
        self.assertIn('if (arch_decode) begin\n      // Decode before the late backend-ready signal.', self.text)
        section = self.text.split('if (arch_decode) begin', 1)[1]
        self.assertLess(section.index('decode_blocked ='), section.index('if (acc_req_i.req_valid'))

    def test_arch_decode_allows_exactly_four_states(self):
        expressions = re.findall(r'assign arch_decode\s*=\s*([^;]+);', self.text)
        self.assertEqual(len(expressions), 1)
        states = re.findall(r'\bstate_q == (\w+)', expressions[0])
        self.assertEqual(states, ['NORMAL_OPERATION', 'OVERLAP_ISSUE_ORIGINAL', 'WAIT_IDLE', 'WAIT_IDLE_FLUSH'])
        self.assertIn('!ara_req_valid_o && ara_idle_i', expressions[0])
        self.assertIn('lsu_ex_state_q == LSU_FLUSH_DONE', expressions[0])

    def test_only_store_response_entry_requires_blocked_decode(self):
        self.assertEqual(len(re.findall(r'\bstate_d\s*=\s*WAIT_STORE_RESPONSE\s*;', self.text)), 1)
        self.assertIn('if (ara_store_accepted_i && decode_blocked &&\n'
                      '        ara_req_valid_o && is_store(ara_req_o.op) && !pending_seg_mem_op_q) begin\n'
                      "      acc_resp_o.req_ready = 1'b1;\n"
                      '      store_trans_id_d = acc_req_i.trans_id;\n'
                      '      state_d = WAIT_STORE_RESPONSE;', self.text)


if __name__ == '__main__':
    unittest.main()
