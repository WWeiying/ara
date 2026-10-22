import copy
from pathlib import Path
import unittest
import prepare_native_batch767_host as host


class HostTests(unittest.TestCase):
    def test_actual_formal767_exact766prefix_and6162OR(self):
        self.assertEqual(host.population()['full_OR_instances'],6162)

    def fixture(self):
        before=dict(tests=[str(i) for i in range(766)],design='fixed',metrics={'cond':{
            str(i):dict(width=2,checksum='frozen',bits='1') for i in range(6162)}})
        after=copy.deepcopy(before);after['tests'].append('new')
        single=copy.deepcopy(after);single['tests']=['new']
        return before,after,single

    def test_missing_instance_rejected(self):
        args=self.fixture();del args[1]['metrics']['cond']['0']
        with self.assertRaises(Exception):host.full_or(*args)

    def test_lost_hit_rejected(self):
        args=self.fixture();args[1]['metrics']['cond']['0']['bits']='0'
        with self.assertRaises(Exception):host.full_or(*args)

    def test_shape_drift_rejected(self):
        args=self.fixture();args[2]['metrics']['cond']['0']['checksum']='different'
        with self.assertRaises(Exception):host.full_or(*args)

    def test_exact_in_directory_stdout(self):
        text='StandardOutput=append:/fresh/service.log\nStandardError=inherit\nExecStart="/worker" "run" "--output" "/fresh" "--seal" "sealed"\n'
        host.stdout_gate(text,Path('/fresh'),'sealed',Path('/worker'))
        with self.assertRaises(Exception):
            host.stdout_gate(text.replace('/fresh/service.log','/external.log'),Path('/fresh'),'sealed',Path('/worker'))


if __name__=='__main__':unittest.main()
