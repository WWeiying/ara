import json
from pathlib import Path
import tempfile
import unittest
from execute_once import sha,validate_host

class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.wait=self.root/'wait.json';self.log=self.root/'host.log'
        self.log.write_text('22 checker tests: OK\n')
        self.data=dict(actual_wait_exit=0,timed_out=False,log_sha256=sha(self.log))
        self.wait.write_text(json.dumps(self.data));self.entry=dict(host_wait_sha256=sha(self.wait))
    def test_positive(self):validate_host(self.entry,self.wait,self.log)
    def test_receipt_changed_still_numeric_zero(self):
        self.data['note']='replacement';self.wait.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError,'receipt'):validate_host(self.entry,self.wait,self.log)
    def test_log_changed(self):
        self.log.write_text('replacement OK\n')
        with self.assertRaisesRegex(ValueError,'log'):validate_host(self.entry,self.wait,self.log)
    def test_false_is_not_integer_zero(self):
        self.data['actual_wait_exit']=False;self.wait.write_text(json.dumps(self.data));self.entry['host_wait_sha256']=sha(self.wait)
        with self.assertRaisesRegex(ValueError,'typed'):validate_host(self.entry,self.wait,self.log)
    def test_numeric_timeout_zero_is_not_false(self):
        self.data['timed_out']=0;self.wait.write_text(json.dumps(self.data));self.entry['host_wait_sha256']=sha(self.wait)
        with self.assertRaisesRegex(ValueError,'typed'):validate_host(self.entry,self.wait,self.log)
    def test_bad_numeric_exit(self):
        self.data['actual_wait_exit']=1;self.wait.write_text(json.dumps(self.data));self.entry['host_wait_sha256']=sha(self.wait)
        with self.assertRaisesRegex(ValueError,'typed'):validate_host(self.entry,self.wait,self.log)
if __name__=='__main__':unittest.main(verbosity=2)
