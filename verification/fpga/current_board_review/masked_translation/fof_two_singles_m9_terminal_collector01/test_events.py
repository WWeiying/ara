"""Focused real-filesystem checks for the only new waiting behavior."""
import tempfile
import threading
import unittest
from pathlib import Path
from events import wait_terminal
import audit

class Events(unittest.TestCase):
    def test_already_complete(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ('complete.json','service_exit.json'):(Path(d)/n).touch()
            self.assertTrue(wait_terminal(d,.1))
    def test_real_close_events(self):
        with tempfile.TemporaryDirectory() as d:
            def finish():
                for n in ('complete.json','service_exit.json'):
                    with (Path(d)/n).open('x') as f:f.write('{}')
            t=threading.Timer(.05,finish);t.start()
            try:self.assertTrue(wait_terminal(d,1))
            finally:t.join()
    def test_partial_terminal_refused(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'complete.json').touch()
            with self.assertRaises(TimeoutError):wait_terminal(d,.05)
    def test_no_terminal_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(TimeoutError):wait_terminal(d,.05)
    def test_unknown_exit_not_numericzero(self):
        for value in (None,False,True,'0',-15,1):self.assertFalse(audit.zero(value))
        self.assertTrue(audit.zero(0))

if __name__=='__main__':unittest.main(verbosity=2)
