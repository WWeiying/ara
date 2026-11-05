#!/usr/bin/env python3
"""Run compact-pipeline SoC acceptance, then matched shared-vs-shared DC."""
import argparse
from pathlib import Path
import subprocess
import sys
import run_operand_ext as api


def compare_reports(old, new):
    if old['state'] != 'PASS' or new['state'] != 'PASS':
        raise ValueError('Both SoC campaigns must pass')
    before = {p['case']: p for p in old['pairs']}
    after = {p['case']: p for p in new['pairs']}
    if len(before) != old['paired_cases'] or len(after) != new['paired_cases']:
        raise ValueError('Duplicate or incomplete paired cases')
    if before.keys() != after.keys():
        raise ValueError('SoC case sets differ')
    fields = ('baseline_finish', 'shared_finish', 'baseline_hw_cycles',
              'shared_hw_cycles', 'baseline_micro', 'shared_micro')
    for name, row in before.items():
        for field in fields:
            if row[field] != after[name][field]:
                raise ValueError(f'Observable SoC difference: {name}/{field}')
    return dict(state='PASS', paired_cases=len(before), comparison='Exact prior/current cycles and microkernel output records')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    for flag in ('accepted', 'prior-soc', 'prior-ppa', 'component', 'tag-check', 'edges', 'pipeline-check'):
        p.add_argument('--'+flag, type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    def state(**fields):
        api.save(out/'status.json', fields)
        print(fields, flush=True)
    try:
        scripts = ['run_shared_fma_compact.py', 'run_shared_fma_soc.py',
                   'run_shared_alu_soc.py', 'run_operand_ext.py', 'run_shared_fma_ppa.py',
                   'shared_fma_soc_monitor.sv', 'shared_fma_timing.sv', 'shared_alu_ppa.tcl']
        pins = {str(api.HERE/f): api.sha(api.HERE/f) for f in scripts}
        for rel in ('hardware/include/ara_pkg.sv', 'hardware/src/lane/vmfpu.sv',
                    'hardware/src/lane/simd_fpnew.sv', 'hardware/src/lane/simd_fma_shared.sv',
                    'backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env'):
            pins[str(api.ROOT/rel)] = api.sha(api.ROOT/rel)
        for directory in (a.accepted, a.prior_soc, a.prior_ppa, a.component, a.tag_check, a.edges, a.pipeline_check):
            api.verify(directory.resolve())
            pins.update(api.read(directory.resolve()/'source-pins.json'))
            for name in ('source-pins.json', 'report.json', 'status.json', 'manifest.json', 'library-pins.json'):
                path = directory.resolve()/name
                if path.is_file():
                    pins[str(path)] = api.sha(path)
        api.save(out/'source-pins.json', pins)
        api.verify(out)
        state(state='SOC_RUNNING')
        cmd = [sys.executable, str(api.HERE/'run_shared_fma_soc.py'), str(out/'soc')]
        for key in ('accepted', 'component', 'tag_check', 'edges', 'pipeline_check'):
            cmd += ['--'+key.replace('_', '-'), str(getattr(a, key).resolve())]
        with (out/'soc-worker.log').open('w') as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        comparison = compare_reports(api.read(a.prior_soc/'report.json'), api.read(out/'soc/report.json'))
        api.save(out/'performance-comparison.json', comparison)
        api.verify(out)
        state(state='PPA_RUNNING', paired_cases=comparison['paired_cases'])
        cmd = [sys.executable, str(api.HERE/'run_shared_fma_ppa.py'), str(out/'ppa'),
               '--soc', str(out/'soc'), '--prior-shared-ppa', str(a.prior_ppa.resolve())]
        with (out/'ppa-worker.log').open('w') as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        api.verify(out)
        if api.read(out/'ppa/report.json')['state'] != 'MEASURED':
            raise ValueError('Missing mapped PPA result')
        state(state='MEASURED', note='Review PPA before adoption; shared feature remains default-off')
    except Exception as exc:
        state(state='STOPPED', reason=str(exc))
        raise


if __name__ == '__main__':
    main()
