import json
import unittest
import collect_fence_t_u_padding_post_v3 as tool


class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=json.loads(tool.old.PLAN.read_bytes());cls.rundir=tool.Path(cls.plan['run']['cwd'])
        cls.console=(cls.rundir/'console.log').read_text();cls.vcs=(cls.rundir/'run.vcs.log').read_text()

    def test_real_complete_logs_not_OS_receipt(self):
        result=tool.terminal_log(self.console,True)
        self.assertEqual(result['reported_CPU_seconds'],118.7)
        self.assertTrue(result['CPU_is_not_wall_time'])
        self.assertEqual(tool.terminal_log(self.vcs,False)['simulation_time'],result['simulation_time'])

    def test_truncated_extra_duplicate_finish_and_coverage_rejected(self):
        for text in (self.console.rsplit('CPU Time:',1)[0],self.console+'extra\n',
                     self.console+'\n$finish at simulation time 1\n',
                     self.console.replace(' Coverage status: End of All Coverages ...','missing'),
                     self.console.replace('Core Test *** SUCCESS *** (tohost = 0)','missing')):
            with self.assertRaises(ValueError):tool.terminal_log(text,True)

    def test_complete_VDB_native_identity_and_all_shapes(self):
        result,pins=tool.vdb_witness(self.rundir,self.plan)
        self.assertEqual(set(result['metric_instance_counts']),{'line','cond','fsm','branch','tgl'})
        self.assertEqual(len(pins),7)
        self.assertTrue(result['exact_baseline_shape'])

    def test_wrong_native_command_rejected(self):
        plan=json.loads(json.dumps(self.plan));plan['run']['argv'][-1]='other_case'
        with self.assertRaises(ValueError):tool.vdb_witness(self.rundir,plan)


if __name__=='__main__':unittest.main()
