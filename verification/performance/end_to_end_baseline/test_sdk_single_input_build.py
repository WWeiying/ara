import unittest
from pathlib import Path
import tempfile

from build_sdk_single_input_native import inherited_compile_pins
from check_sdk_single_input import oracle_paths,verify_oracle_inputs
from audit import digest


class SDKInheritedPinsTests(unittest.TestCase):
    def test_common_headers_retain_exact_identities(self):
        a={'/caller.cpp':'a','/shared.h':'same'}
        b={'/limits.h':'old-toolchain','/shared.h':'same'}
        self.assertEqual(inherited_compile_pins(a,b),{**a,**b})
        self.assertNotIn('/limits.h',a)

    def test_conflicting_identities_are_not_overwritten(self):
        with self.assertRaisesRegex(ValueError,'Conflicting inherited dependency'):
            inherited_compile_pins({'/shared.h':'old'},{'/shared.h':'new'})

    def test_all_oracles_are_pinned_and_late_changes_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            files=oracle_paths(tmp)
            self.assertEqual(len(files),13)
            for path in files:path.write_bytes(b'sealed')
            inventory={str(p):digest(p) for p in files}
            program=dict(oracle_build=tmp,oracle_inputs=inventory)
            verify_oracle_inputs(program,inventory)
            with self.assertRaisesRegex(ValueError,'Oracle identity'):
                verify_oracle_inputs(program,{})
            with self.assertRaisesRegex(ValueError,'Incomplete oracle'):
                verify_oracle_inputs(dict(program,oracle_inputs={}),inventory)
            files[-1].write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Oracle identity'):
                verify_oracle_inputs(program,inventory)


if __name__=='__main__':unittest.main()
