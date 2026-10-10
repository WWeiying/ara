"""Run real Tcl context fixtures as a fail-fast script, not interactive stdin."""
from unittest.mock import patch
import subprocess
import unittest

import test_capture_ff1_native904 as original


class FF1NativeV2Tests(original.FF1NativeTests):
    def tcl_context(self, corrupt=False):
        run = subprocess.run
        def fail_fast(*args, **kwargs):
            script = kwargs['input']
            kwargs['input'] = 'if {[catch {\n' + script + '\n} detail]} {puts stderr $detail; exit 1}\n'
            return run(*args, **kwargs)
        with patch('test_capture_ff1_native904.subprocess.run', side_effect=fail_fast):
            return super().tcl_context(corrupt)


if __name__ == '__main__':
    unittest.main()
