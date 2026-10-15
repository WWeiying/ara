"""Run the inherited cancellation suite on07, plus real signal decision races."""
import dis
import os
from pathlib import Path
import signal
import sys
from unittest.mock import patch

import replay_restart_atomic as r
import test_restart_abort as inherited


class AtomicTests(inherited.AbortTests):
    def setUp(self):
        replacement = patch.object(inherited, 'r', r)
        replacement.start()
        self.addCleanup(replacement.stop)
        super().setUp()

    def inject(self, signum, before_query):
        path = self.root / 'complete.json'
        code = r.AbortLatch.publish.__code__
        instructions = list(dis.get_instructions(code))
        # Stop immediately before/after the actual sigpending call, not just
        # at a coarse source line. No signal-state or publication mocks.
        load = next(i for i, op in enumerate(instructions) if op.argval == 'sigpending')
        call = next(i for i in range(load + 1, len(instructions))
                    if instructions[i].opname in ('CALL_FUNCTION', 'CALL_METHOD', 'CALL'))
        offset = instructions[call if before_query else call + 1].offset
        observations = []
        def trace(frame, event, arg):
            if frame.f_code is code:
                frame.f_trace_opcodes = True
                if event == 'opcode' and frame.f_lasti == offset and not observations:
                    os.kill(os.getpid(), signum)
                    observations.append(dict(pending=signum in signal.sigpending(), exists=path.exists()))
            return trace
        with self.abort.signals():
            sys.settrace(trace)
            try:
                accepted = self.abort.publish(path, {}, True)
            finally:
                sys.settrace(None)
            self.assertTrue(self.abort.is_set())
        self.assertEqual(observations, [dict(pending=True, exists=False)])
        record = r.read(path)
        self.assertEqual(accepted, not before_query)
        self.assertEqual(record['status'], 'NOT_PASS' if before_query else 'PASS_2_ORIGINAL_PREFIXES_260_CALLS_M4')

    def test_sigint_immediately_before_final_query_veto(self):
        self.inject(signal.SIGINT, True)

    def test_sigterm_immediately_before_final_query_veto(self):
        self.inject(signal.SIGTERM, True)

    def test_sigint_after_final_query_is_after_decision(self):
        self.inject(signal.SIGINT, False)

    def test_sigterm_after_final_query_is_after_decision(self):
        self.inject(signal.SIGTERM, False)

    def after_kernel_sample(self, signum):
        real = signal.sigpending
        observations = []
        def snapshot_then_signal():
            snapshot = real()
            os.kill(os.getpid(), signum)
            observations.append(dict(sample_contains=signum in snapshot, now_pending=signum in real()))
            return snapshot
        with self.abort.signals(), patch.object(signal, 'sigpending', snapshot_then_signal):
            self.assertTrue(self.abort.publish(self.root / 'complete.json', {}, True))
            self.assertTrue(self.abort.is_set())
        self.assertEqual(observations, [dict(sample_contains=False, now_pending=True)])

    def test_sigint_after_kernel_sample_before_return_is_after_decision(self):
        self.after_kernel_sample(signal.SIGINT)

    def test_sigterm_after_kernel_sample_before_return_is_after_decision(self):
        self.after_kernel_sample(signal.SIGTERM)


if __name__ == '__main__':
    import unittest
    unittest.main()
