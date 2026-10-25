import copy
import csv
from pathlib import Path
import tempfile
import unittest
import fault_checks as checks
from run_handoff import ROOT, log_checker


class FaultChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rtl = (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text()
        raw = (ROOT / 'verification/out/reader-handoff-baseline-20261024-01/work/run.vcs.log').read_text()
        records = log_checker.check_log(raw, cls.rtl)['hardware_records']
        qbs = [r for r in records if 'activation_access' in r]
        akv = [r for r in records if 'command' in r]
        cls.records = [copy.deepcopy(qbs[3]), copy.deepcopy(akv[0]), copy.deepcopy(qbs[4]),
                       copy.deepcopy(akv[0]), *copy.deepcopy(akv[1:9]), copy.deepcopy(qbs[5]),
                       copy.deepcopy(akv[-1])]
        counters = dict(qbs=0, akv=0)
        for (owner, _), row in zip(checks.ORDER, cls.records):
            counters[owner] += 1
            row['seq'] = counters[owner]
        cls.records[1].update(success=0, fault=1, validation_fault=0, read_fault=5, context_ready=0)

    def log(self, records):
        lines = [checks.BEGIN]
        for (owner, _), row in zip(checks.ORDER, records):
            lines.append('[' + owner.upper() + '_PERF] ' + ' '.join(f'{k}={v}' for k,v in row.items()))
        return '\n'.join([*lines, checks.PASS, log_checker.TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0'])

    def test_complete_log(self):
        self.assertEqual(checks.check_log(self.log(self.records), self.rtl)['commands'], 14)

    def test_wrong_fault_or_reuse_rejected(self):
        for ordinal, field, value in ((1,'read_fault',0), (1,'validation_fault',1),
                (2,'context_read_bytes',0), (12,'commit_groups',1)):
            records = copy.deepcopy(self.records)
            records[ordinal][field] = value
            with self.subTest(ordinal=ordinal, field=field), self.assertRaises(ValueError):
                checks.check_log(self.log(records), self.rtl)

    def wave(self, shared):
        aliases = [s['alias'] for s in checks.profile(shared)['signals']]
        rows = []
        akv_count = 0
        for owner, _ in checks.ORDER:
            if owner == 'akv':
                akv_count += 1
            phases = ['accept', 'write', 'fault', 'terminal', 'idle'] if owner == 'akv' and akv_count == 1 else ['accept','terminal','idle']
            for phase in phases:
                row = {a:'0' for a in aliases}
                row.update(reset_n='1', normal_vlsu_idle='1', activation_context_valid_q='1')
                if phase == 'accept':
                    row[owner+'_command_fire']='1'
                elif phase != 'idle':
                    row[owner+'_active_q']='1'
                if phase == 'write':
                    row['akv_q_write_valid']='1'
                elif phase == 'fault':
                    row.update(reader_fault_valid_o='1', reader_fault_ready_i='1', reader_fault_kind_o='5')
                elif phase == 'terminal':
                    row[owner+'_terminal']='1'
                    row[owner+'_fault_valid']='1' if owner=='akv' and akv_count==1 else '0'
                row['time_100fs']=str((len(rows)+1)*10000)
                rows.append(row)
        return rows

    def check_wave(self, rows, shared):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'cycles.csv'
            with path.open('w',newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
            return checks.check_cycles(path, shared)

    def test_shared_and_baseline_scope(self):
        for shared in (False, True):
            self.assertEqual(self.check_wave(self.wave(shared), shared)['faults'],1)

    def test_partial_write_must_be_observed(self):
        rows = self.wave(True)
        for row in rows:
            row['akv_q_write_valid']='0'
        with self.assertRaisesRegex(ValueError,'partial Q write'):
            self.check_wave(rows,True)

    def test_foreign_context_and_fault_drain(self):
        for field, value in (('activation_context_generation_q','bad'), ('reader_burst_fifo_count_q','1')):
            rows = self.wave(True)
            row = next(r for r in rows if r['reader_fault_valid_o']=='1')
            row[field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check_wave(rows,True)


if __name__ == '__main__':
    unittest.main()
