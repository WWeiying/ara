"""Same full5985 constructed suite plus actual byte transport successor tests."""
import sys
import time
import unittest
import checker as c
import replay as r
from test_host import Host
from byte_preflight02 import ByteTransport

NAMES=('checker.py','replay.py','test_host.py','test_host02.py','host_records.py','byte_preflight02.py',
    'reset_profile.json','owner_policy.py','terminal_gate.py','reference_terminal_binding.json','owner_contract.json',
    'worker_lifecycle.py','lifecycle_context.py','soc_spec.json')
def main():
    pins={str(c.HERE/n):c.sha(c.HERE/n) for n in NAMES}
    r.durable(c.HERE/'host02_loaded_code_preflight.json',dict(pins=pins,captured_before_tests=True,
        note='Disk hashes captured after imports; no claim of earlier version loaded-code attestation.'))
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(ByteTransport),unittest.defaultTestLoader.loadTestsFromTestCase(Host)])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    c.common.base.verify_pins(pins)
    r.durable(c.HERE/'host02.json',dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',tests=result.testsRun,
        failures=len(result.errors)+len(result.failures),errors=len(result.errors),pins=pins,input_pins_pre_post_unchanged=True,
        actual_abi_entry_checked=result.wasSuccessful(),full5985_streams=1,full_positive_shapes=[c.SHAPE] if result.wasSuccessful() else [],
        CSV_reads=0,DUT_reference_build_runs=0,
        full_positive_summary={k:v for k,v in getattr(Host,'strict',{}).items() if k!='call_ledger'},
        owner_summary={k:v for k,v in getattr(Host,'coverage',{}).items() if k not in ('owner_ledger','harmless_configuration_replay_arch_orders')},
        fixture='Synthetic full source events and real linked scalar paths; not executed firmware'))
    return int(not result.wasSuccessful())
if __name__=='__main__':raise SystemExit(main())
