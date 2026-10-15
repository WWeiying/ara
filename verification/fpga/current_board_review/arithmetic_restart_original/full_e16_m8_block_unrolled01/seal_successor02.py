"""No recompile or Host replay; freeze only the finite-reference driver delta."""
import json
from pathlib import Path
import prepare as p
HERE=p.HERE
prior=json.loads((HERE/'entry.json').read_text());pins=dict(prior['pins'])
for path,digest in pins.items():p.old.require(p.sha(path)==digest,'Original sealed entry unchanged '+path)
extra=[HERE/'reference_successor02.py',HERE/'seal_successor02.py',HERE/'REFERENCE_EXECUTOR02.md',HERE/'entry.json',
    Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/riscv/interactive.cc'),
    Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/riscv/sim.cc')]
pins.update({str(path):p.sha(path) for path in extra})
entry=dict(prior,pins=pins,status='SEALED_SUCCESSOR02_FINITE_REFERENCE_PENDING_TESLA_NO_DUT',
    original_blocked_entry_sha256=p.sha(HERE/'entry.json'),executor=str(HERE/'reference_successor02.py'),
    executor_sha256=p.sha(HERE/'reference_successor02.py'),debug_script='rs 4000000\nquit\n',
    original_driver_unchanged=True,source_oracle_ELF_unchanged=True,Host_reruns=0,reference_invocations=0,
    debug_counter_receipt_available=False,firmware_count_basis='EXACT_CLOSED_COMMIT_RETIREMENT_LEDGER_NOT_DEBUG_COUNTER')
p.save(HERE/'entry02.json',entry);print('SEALED_SUCCESSOR02',p.sha(HERE/'entry02.json'),'pins',len(pins))
