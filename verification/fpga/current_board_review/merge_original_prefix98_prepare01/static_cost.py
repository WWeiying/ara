#!/usr/bin/env python3
"""Bind an explicitly reviewed compiled-loop cost table before any reference."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from prepare_prefix import OUT, base, save
from reference_check import require, MAX_RETIRED


def main():
    table = json.loads((OUT/'cost_table.json').read_text())
    proof = json.loads((OUT/'source_elf_proof.json').read_text())
    require(table['spike_elf_sha256'] == proof['spike_elf']['sha256'] ==
            base.sha(Path(proof['spike_elf']['path'])), 'Compiled cost ELF drift')
    require(table['calls'] == 98 and table['capacity'] == 512, 'Cost scope')
    total = sum(t['iterations'] * t['instructions_per_iteration_upper'] for t in table['terms'])
    require(total < MAX_RETIRED and table['raw_bytes_upper'] < 768*1024*1024,
            'Static bounds do not fit; reference must not run')
    save(OUT/'static_cost.json', dict(status='STATIC_COMPILED_BUDGET_FITS',
        table_sha256=base.sha(OUT/'cost_table.json'), table=table,
        instructions_upper=total, max_steps=MAX_RETIRED, max_seconds=120,
        max_log_bytes=768*1024*1024, software_only=True))
    print('STATIC_COMPILED_BUDGET_FITS', total)


if __name__ == '__main__':
    main()
