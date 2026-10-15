#!/usr/bin/env python3
"""One bounded reference only, requiring prior compiled static budget evidence."""
import json
import resource
import subprocess
import time
import sys
from pathlib import Path
sys.dont_write_bytecode = True
from prepare_prefix import OUT, base, save, SPIKE, symbol, OBJDUMP, MAX_LOG
from reference_check import model, audit_trace, require, MAX_RETIRED, NAME


def main():
    reference = OUT/'reference'
    require(not reference.exists(), 'One attempt only; existing reference must be preserved')
    cost = json.loads((OUT/'static_cost.json').read_text())
    proof = json.loads((OUT/'source_elf_proof.json').read_text())
    software = json.loads((OUT/'software_prepared.json').read_text())
    pins = json.loads((OUT/'baseline_pins.json').read_text())
    require(cost['status'] == 'STATIC_COMPILED_BUDGET_FITS' and
            cost['instructions_upper'] < MAX_RETIRED and
            cost['table_sha256'] == base.sha(OUT/'cost_table.json'), 'No valid cost gate')
    require(software['status'] == 'SOFTWARE_HOST_READY_REFERENCE_NOT_RUN', 'Software gate')
    for p,d in pins.items():
        require(base.sha(Path(p)) == d, 'Input drift: '+p)
    elf = Path(proof['spike_elf']['path'])
    require(base.sha(elf) == proof['spike_elf']['sha256'] == cost['table']['spike_elf_sha256'], 'ELF drift')
    reference.mkdir()
    logaddr,_ = symbol(elf,'replay_log',OBJDUMP)
    debug = reference/'spike.cmd'
    debug.write_text(f'rs {MAX_RETIRED}\nstr {logaddr:x}\nquit\n')
    command = [str(SPIKE),'-d','--debug-cmd='+str(debug),'--isa=rv64gcv_zvl1024b','-m2',
               '--log-commits','--log='+str(reference/'commits.log'),str(elf)]
    save(reference/'command.json', dict(command=command, seconds=120, max_steps=MAX_RETIRED,
        max_log_bytes=MAX_LOG, spike_sha256=base.sha(SPIKE), elf_sha256=base.sha(elf),
        cost_sha256=base.sha(OUT/'static_cost.json'), attempt=1, retry=False,
        actual_isa='rv64gcv_zvl1024b', vlen=1024, comment='Integer16 data, no FP16 instructions required'))
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_LOG,MAX_LOG))
    start = time.monotonic()
    try:
        with (reference/'spike.log').open('x') as stream:
            run = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                 timeout=120, preexec_fn=limits)
        elapsed = time.monotonic()-start
        save(reference/'execution.json',dict(returncode=run.returncode,elapsed_s=elapsed,command=command))
        require(run.returncode == 0, 'Reference nonzero exit')
        measured = audit_trace(reference/'commits.log',elf,model())
        require(measured['firmware_retired_to_htif_store'] <= cost['instructions_upper'], 'Static estimate violated')
        (reference/'runtime.log').write_text(measured['reconstructed_console'])
        save(reference/'reference.json',dict(**measured, elapsed_s=elapsed, returncode=run.returncode,
            spike_sha256=base.sha(SPIKE),commit_sha256=base.sha(reference/'commits.log'),
            commit_bytes=(reference/'commits.log').stat().st_size,
            limits=dict(seconds=120,retired=MAX_RETIRED,bytes=MAX_LOG)))
        for p,d in pins.items():
            require(base.sha(Path(p)) == d, 'Post-reference input drift: '+p)
        save(OUT/'preparation_complete.json',dict(**{k:v for k,v in software.items() if k!='status'},
            status='REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT',
            reference_sha256=base.sha(reference/'reference.json')))
        print('REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT',measured['firmware_retired_to_htif_store'])
    except Exception as e:
        save(reference/'not_completed.json',dict(status='REFERENCE_NOT_ACCEPTED',error=repr(e),
            elapsed_s=time.monotonic()-start,attempt=1,retry=False))
        raise


if __name__ == '__main__':
    main()
