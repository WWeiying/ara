#!/usr/bin/env python3
"""Check reset-held producer activity using the already frozen FIFO candidate."""
import argparse
from pathlib import Path
import re
import shutil
import run_operand_ext as api


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('component', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    comp, out = a.component.resolve(), a.output.resolve()
    api.verify(comp)
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(comp/'src', out/'src')
    shutil.copytree(comp/'include', out/'include')
    here = Path(__file__).resolve().parent
    shutil.copy2(here/'operand_fifo_reset_tb.sv', out/'src/operand_fifo_reset_tb.sv')
    shutil.copy2(__file__, out/'worker.py')
    shutil.copy2(here/'run_operand_ext.py', out/'run_operand_ext.py')
    api.save(out/'source-pins.json', {str(f): api.sha(f) for f in out.rglob('*') if f.is_file()})
    try:
        src = out/'src'
        sources = [str(src/Path(x).name) for x in api.PACKAGES]
        sources += [str(src/x) for x in ('operand_queue.sv', 'operand_fifo_reset_tb.sv')]
        cmd = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps',
               '-top', 'operand_fifo_reset_tb', '-o', 'simv', '+incdir+'+str(out/'include'), *sources]
        api.save(out/'command.json', {'command': cmd})
        api.save(out/'status.json', {'state': 'BUILDING'})
        api.command(cmd, out, out/'compile.log', None)
        api.save(out/'status.json', {'state': 'RUNNING'})
        text = api.command(['./simv', '-no_save'], out, out/'run.log', 'OPERAND_FIFO_RESET_PASS')
        depths = re.findall(r'OPERAND_FIFO_RESET_CASE_PASS depth=(\d+)', text)
        if len(depths) != 4 or set(depths) != {'1', '2', '3', '5'}:
            raise ValueError('Incomplete reset matrix')
        api.verify(out); api.verify(comp)
        api.save(out/'status.json', {'state': 'PASS', 'depths': depths,
                 'reset_activity': 'push with ones/X, flush+push, post-reset empty, overwrite then read'})
    except Exception as exc:
        api.save(out/'status.json', {'state': 'FAIL', 'reason': str(exc)})
        raise


if __name__ == '__main__':
    main()
