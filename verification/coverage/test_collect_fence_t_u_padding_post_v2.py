"""Policy checks on retained logs; synthetic retirement fixtures, no EDA."""
import unittest
from unittest.mock import patch
import collect_fence_t_u_padding_post_v2 as tool
import test_collect_fence_t_u_padding_post as fixtures


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plan=__import__('json').loads(tool.old.PLAN.read_bytes())
        run=tool.Path(plan['run']['cwd'])
        cls.console=(run/'console.log').read_text()
        cls.vcs=(run/'run.vcs.log').read_text()

    def test_actual_both_logs_exact_policy_errors_retained(self):
        for text in (self.console,self.vcs):
            result=tool.policy_log(text)
            self.assertEqual(result['actual_UVM_errors'],2)
            self.assertFalse(result['require_contract_promoted'])

    def test_extra_duplicate_or_malformed_error_rejected(self):
        line=next(l for l in self.vcs.splitlines() if l.startswith('UVM_ERROR ') and '[' in l)
        for extra in (line,line.replace('UVM_ERROR','UVM_FATAL'),
                      'UVM_ERROR malformed',line.replace('CVXIF/NO_TRAFFIC','CVXIF/DUP_ID')):
            with self.assertRaises(ValueError):tool.policy_log(self.vcs+'\n'+extra+'\n')

    def test_missing_zero_and_nonzero_counter_rejected(self):
        for bad in (self.vcs.replace('requests=0 responses=0 aborted=0','requests=1 responses=0 aborted=0'),
                    self.vcs.replace('protocol_errors=0','protocol_errors=1'),
                    self.vcs.replace('UVM_ERROR :    2','UVM_ERROR :    0'),
                    self.vcs.replace('[VID/COUNT] allocations=0','[OTHER/COUNT] allocations=0')):
            with self.assertRaises(ValueError):tool.policy_log(bad)

    def test_wrong_message_source_line_and_missing_error_rejected(self):
        for bad in (self.vcs.replace('sv(504)','sv(503)'),
                    self.vcs.replace('scoreboard observed no complete CVXIF traffic','changed message'),
                    '\n'.join(l for l in self.vcs.splitlines() if not l.startswith('UVM_ERROR ') or '[VID/NO_TRAFFIC]' not in l)):
            with self.assertRaises(ValueError):tool.policy_log(bad)

    def test_frozen_source_and_adapter_compile(self):
        self.assertTrue(callable(tool.collector()))

    def test_vector_retirement_rejected_before_oracle(self):
        metadata=dict(Symbols=[dict(Symbol=dict(Name=dict(Name='padding_u_ecall'),Value=1))])
        for word in (0x57,0x7057,0x7,0x5027,0x5b):
            with patch.object(tool.old.oracle,'parse_padding_trace',return_value=[dict(insn=word)]):
                with self.assertRaises(ValueError):tool.evaluate(self.console,'',metadata,b'',[],self.vcs)

    def test_full_synthetic_retirement_with_exact_policy(self):
        fixtures.CollectorTests.setUpClass()
        fixture=fixtures.CollectorTests();console,rows=fixture.fixture(1011)
        import csv,io
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=tool.old.oracle.frozen.FIELDS)
        writer.writeheader();hexfields={'pc','insn','rd_wdata','mem_addr','mem_rmask','mem_wmask','mem_wdata'}
        writer.writerows({k:format(v,'x') if k in hexfields else v for k,v in r.items()} for r in rows)
        # Retained logs provide policy structure; synthetic UART values remain explicit.
        text=self.console
        result=tool.evaluate(text,stream.getvalue(),fixture.metadata,fixture.blob,
                             fixture.plan['proof']['sites'],self.vcs)
        self.assertEqual(result['scalar_policy']['console']['actual_UVM_errors'],2)
        self.assertEqual(result['retirement']['capture_stores_checked'],195)
        self.assertFalse(result['cyclequalified'])
        self.assertFalse(result['UVM_clean']);self.assertFalse(result['admissibility_decided'])


if __name__=='__main__':unittest.main()
