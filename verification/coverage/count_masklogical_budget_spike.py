"""Same native ELF in Spike for runtime budgeting, not RTL acceptance."""
import json
from pathlib import Path
import re
import subprocess
import time

from run_masklogical_restart_count_probe import digest, ELF, ELF_SHA, ROOT

SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
OUT = ROOT / 'verification/out/masklogical-full-budget-spike-20261008-01'
SCRIPT = Path(__file__).with_name('masklogical_budget_spike.cmd')


def main():
    if digest(ELF) != ELF_SHA:
        raise ValueError('Original 68-case ELF changed')
    OUT.mkdir(parents=True, exist_ok=False)
    # MMIO addresses are writable backing pages for native CRT/fake UART only.
    # Stop before the CRT completion store, since this ELF does not use tohost.
    command = [str(SPIKE), '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
               '-m0x80000000:0x200000,0xc0000000:0x1000,0xd0000000:0x1000',
               '-d', '--debug-cmd=' + str(SCRIPT), str(ELF)]
    record = dict(command=command, pins={str(p): digest(p) for p in (SPIKE, SCRIPT, ELF, Path(__file__))},
                  purpose='Budget only; no four-state cold source or RTL correctness claim',
                  timeout_s=120)
    (OUT / 'command.json').write_text(json.dumps(record, indent=2) + '\n')
    start = time.monotonic()
    try:
        with (OUT / 'spike.log').open('x') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        count = 0
        mask_count = 0
        entered = False
        registers = []
        exceptions = []
        with (OUT / 'spike.log').open() as log:
            for line in log:
                match = re.match(r'core\s+0:\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)', line)
                if match:
                    pc, insn = (int(x, 16) for x in match.groups())
                    entered |= pc == 0x80000000
                    if entered:
                        count += 1
                        mask_count += int(insn & 127 == 0x57 and (insn >> 12) & 7 == 2 and
                                          insn >> 26 in (0x1b, 0x18, 0x1f, 0x1c))
                if re.fullmatch(r'0x[0-9a-f]+\s*', line):
                    registers.append(int(line, 16))
                if 'exception ' in line:
                    exceptions.append(line.strip())
        record.update(returncode=result.returncode, instructions_from_entry=count, mask_instructions=mask_count,
                      terminal_registers_pc_a0_minstret=registers, exceptions=exceptions[:20])
        if result.returncode != 0 or len(registers) != 3 or registers[0] != 0x800000e4 or mask_count != 68:
            raise ValueError('Budget run did not complete the exact full matrix')
        record['status'] = 'FULL_MATRIX_BUDGET_COUNTED'
    except Exception as exc:
        record.update(status='BUDGET_UNAVAILABLE', error=type(exc).__name__ + ': ' + str(exc))
    record['elapsed_s'] = time.monotonic() - start
    (OUT / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))
    return 0 if record['status'] == 'FULL_MATRIX_BUDGET_COUNTED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
