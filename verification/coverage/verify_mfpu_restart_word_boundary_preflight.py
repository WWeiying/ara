"""Independent replay of sealed Spike preflight; never launches DUT or EDA."""
from dataclasses import replace
import io
import json
from pathlib import Path
import unittest

import prepare_mfpu_restart_word_boundary as m
import test_prepare_mfpu_restart_word_boundary as base_tests

PREFLIGHT_SHA = '2118049e46b590fa6097a5546a1fc98aa21e157dfae1bb1edd20430821577b78'


def context_check(commits, symbols):
    targets = [i for i,c in enumerate(commits) if c.pc == symbols['mr_target_fma']]
    m.require(len(targets) == 12, 'Exactly twelve target sites')
    registers = {}; before = {}
    for i,c in enumerate(commits):
        if i in targets: before[i] = dict(registers)
        registers.update(c.vector_writes)
    for n,i in enumerate(targets):
        c = commits[i]
        m.require((c.vector_sew,c.vector_lmul,c.vector_vl) == (16,'m8',512), 'Actual FMA configuration changed')
        write, read = commits[i-2:i]
        m.require(write.pc == c.pc-8 and write.instruction == 0x00851073
                  and write.csr_writes.get(8) == m.STARTS[n], 'Every FMA must rewrite exact vstart')
        m.require(read.pc == c.pc-4 and read.instruction == 0x008026f3
                  and list(read.gpr_writes.values()) == [m.STARTS[n]], 'Actual pre-FMA CSR read mismatch')
        m.require(c.csr_writes.get(8) == 0, 'FMA must clear vstart')
        if n % 4 == 0:
            expected = int.from_bytes(bytes.fromhex('0048')*64,'little')
            m.require(all(before[i].get(r) == expected for r in range(24,32)), 'Phase must reinitialize full destination group to eight')
        for k,(csr,value) in enumerate(((0xc20,512),(0xc21,11),(8,0),(15,0),(3,0))):
            read = commits[i+1+k]
            m.require((read.instruction >> 20) == csr and (read.instruction & 0x707f) == 0x2073
                      and list(read.gpr_writes.values()) == [value], 'Actual post-FMA CSR read mismatch')
    return {'actual_vstart_rewrites':12, 'actual_FMA_configurations':12,
            'actual_post_FMA_CSR_reads':60, 'full_destination_group_reinitializations':3}


class ActualContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = m.life.read_bound(m.OUT/'preflight.json', PREFLIGHT_SHA)
        m.life.check(cls.record['pins'])
        cls.commits = m.reused.reused.old.shared.shared.spike_trace.parse_spike_commits(m.OUT/'spike.trace')
        cls.symbols = cls.record['symbols']

    def test_actual_context(self):
        self.assertEqual(context_check(self.commits,self.symbols)['actual_vstart_rewrites'],12)

    def test_actual_missing_or_wrong_restart_and_configuration(self):
        i = next(i for i,c in enumerate(self.commits) if c.pc == self.symbols['mr_target_fma'])
        for j,alteration in ((i-2,{'csr_writes':{8:0}}),(i,{'vector_lmul':'m4'}),
                             (i,{'csr_writes':{8:508}}),(i+5,{'gpr_writes':{16:1}})):
            commits = list(self.commits); commits[j] = replace(commits[j],**alteration)
            with self.assertRaises(ValueError): context_check(commits,self.symbols)
        with self.assertRaises(ValueError): context_check(self.commits[:i-2]+self.commits[i-1:],self.symbols)

    def test_actual_phase_reinitialization_missing(self):
        targets = [i for i,c in enumerate(self.commits) if c.pc == self.symbols['mr_target_fma']]
        index = targets[4]
        # Mutate the last architectural write to v31 before phase two.
        j = max(j for j,c in enumerate(self.commits[:index]) if 31 in c.vector_writes)
        writes = dict(self.commits[j].vector_writes); writes[31] = 0
        commits = list(self.commits); commits[j] = replace(commits[j],vector_writes=writes)
        with self.assertRaises(ValueError): context_check(commits,self.symbols)


def main():
    record = m.life.read_bound(m.OUT/'preflight.json', PREFLIGHT_SHA)
    m.life.check(record['pins'])
    loader = unittest.TestLoader()
    suite = unittest.TestSuite((loader.loadTestsFromModule(base_tests), loader.loadTestsFromTestCase(ActualContextTests)))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    m.require(result.wasSuccessful() and not result.skipped and result.testsRun == 10, stream.getvalue())
    commits = m.reused.reused.old.shared.shared.spike_trace.parse_spike_commits(m.OUT/'spike.trace')
    checks = m.validate_commits(commits,record['symbols'],record['instruction'])
    m.require(checks == record['checks'], 'Replay differs from sealed preflight')
    context = context_check(commits,record['symbols'])
    output = m.OUT/'acceptance.json'
    if output.exists():
        accepted = json.loads(output.read_bytes())
        m.life.check(accepted['pins'])
        m.require(accepted['checks'] == checks and accepted['context'] == context, 'Acceptance replay differs')
    else:
        log = m.OUT/'acceptance-tests.log'
        log.write_text(stream.getvalue())
        pins = {**record['pins'],str(m.OUT/'preflight.json'):PREFLIGHT_SHA,
                str(Path(__file__).resolve()):m.life.digest(Path(__file__)),str(log):m.life.digest(log)}
        m.life.save(output,{'status':'EXACT_MFPU_RESTART_SPIKE_PREFLIGHT_PASS_AWAIT_PARENT_DUT_AUTHORIZATION',
            'pins':pins,'checks':checks,'context':context,'tests_passed':10,'tests_skipped':0,
            'DUT_launched':False,'EDA_launched':False,'coverage_admitted':False,
            'source_snapshot_binding':record['source_bindings'],
            'scope_constraints':record['scope_constraints'],
            'raw726_are_candidates_not_measured_gain':True})
    print(json.dumps({'acceptance':str(output),'seal':m.life.digest(output),'tests_passed':10,
                      'DUT_launched':False,'context':context}))


if __name__ == '__main__': main()
