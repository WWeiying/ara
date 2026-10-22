import copy
import json
import unittest
import postprocess_gap115_events_v2 as m
from test_postprocess_gap115_events import Events


class ActualEpochs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = (m.run.RUN/'run.vcs.log').read_text()
        cls.audit = m.run.reset.check_real_uvm_log(m.run.RUN/'run.vcs.log', require_events=True,
            require_backend=True, require_axi=True, vector_trace=m.run.RUN/'vector_trace.csv', reset_kind='read')
        _, cr = m.run.reset.read_csv(m.run.RUN/'commit_trace.csv')
        _, vr = m.run.reset.read_csv(m.run.RUN/'vector_trace.csv')
        cls.epochs, _ = m.run.reset.split_epochs(cr, vr)
        cls.symbols = json.loads((m.run.PRE/'preflight.json').read_bytes())['symbols']

    def test_actual_nonreset_global_clocks_and_two_epoch_conservation(self):
        value = m.events_audit(self.log, self.epochs, self.audit, self.symbols)
        self.assertEqual(value['cvx_epochs'], [dict(requests=39, responses=39, aborted=0),
                                              dict(requests=75, responses=75, aborted=0)])
        self.assertEqual([(e['allocations'], e['completions'], e['aborted']) for e in value['backend_epochs']],
                         [(35, 33, 2), (67, 67, 0)])
        self.assertFalse(value['axi_burst_conservation_verified'])
        self.assertFalse(value['uvm_check_report_pass'])
        self.assertEqual(self.audit['status'], 'FAIL')

    def test_actual_missing_event_and_cycle_drift_rejected(self):
        for mutate in ('missing', 'cycle'):
            epochs = copy.deepcopy(self.epochs)
            row = next(r for r in epochs[1][0] if r['event'] == 'cvx_req')
            if mutate == 'missing': epochs[1][0].remove(row)
            else: row['cycle'] = str(int(row['cycle'])+2)
            with self.assertRaises(ValueError): m.events_audit(self.log, epochs, self.audit, self.symbols)

    def test_real_uvm_error_rejected(self):
        with self.assertRaises(ValueError):
            m.events_audit(self.log+'\nUVM_ERROR fake protocol error\n', self.epochs, self.audit, self.symbols)


if __name__ == '__main__': unittest.main()
