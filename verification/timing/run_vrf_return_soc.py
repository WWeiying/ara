#!/usr/bin/env python3
"""Change only VRF routing in the accepted SoC snapshot; reuse checked baseline runs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import time
import run_shared_alu_soc as api
from run_shared_alu_shift_soc import parse

HERE = Path(__file__).resolve().parent
VRF = Path('hardware/src/lane/vector_regfile.sv')


def read(p):
    return json.loads(p.read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--accepted', required=True, type=Path)
    p.add_argument('--component', required=True, type=Path)
    a = p.parse_args()
    old = a.accepted.resolve(); comp = a.component.resolve(); out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    status = dict(state='PREPARING', completed_cases=0)
    def state(**kw):
        status.update(kw); api.save(out/'status.json', status); print(json.dumps(status), flush=True)
    try:
        if read(old/'report.json')['state'] != 'PASS' or read(comp/'status.json')['state'] != 'PASS':
            raise ValueError('Acceptance gate missing')
        pins = {}
        for inventory in (old/'source-pins.json', comp/'source-pins.json'):
            for f, digest in read(inventory).items():
                if api.sha(Path(f)) != digest: raise ValueError('Inherited input drift: '+f)
            pins[str(inventory)] = api.sha(inventory)
        if api.sha(comp/'baseline.sv') != api.sha(old/'source'/VRF):
            raise ValueError('Different reference VRF')
        names = read(old/'plan.json')['cases']
        if len(names) != read(old/'report.json')['paired_cases']: raise ValueError('Case count mismatch')
        source = out/'source'; shutil.copytree(old/'source', source, symlinks=True)
        shutil.copy2(comp/'src/vector_regfile.sv', source/VRF)
        shutil.copytree(old/'inputs', out/'inputs')
        baseline = {}
        for name in names:
            log = old/'candidate/cases'/name/'console.log'
            row = read(log.parent/'result.json')
            if row['status'] != 'PASS': raise ValueError('Unchecked reference: '+name)
            metrics = json.loads(json.dumps(parse(log.read_text(errors='replace'), name, observation_aware=True)))
            if metrics != row['metrics']: raise ValueError('Reference parse drift: '+name)
            command = read(log.parent/'command.json')
            if api.sha(out/'inputs'/name) != command['elf_sha256']: raise ValueError('ELF drift: '+name)
            baseline[name] = metrics
            for f in (log, log.parent/'result.json', log.parent/'command.json'):
                pins[str(f)] = api.sha(f)
        for f in ('elfloader.o', 'reference.sv', 'shared_alu_shift_soc_monitor.sv', 'shared_alu_observation.sv'):
            shutil.copy2(old/f, out/f)
        for f in ('run_vrf_return_soc.py', 'vrf_return_soc_monitor.sv', 'run_shared_alu_soc.py',
                  'run_shared_alu_shift_soc.py', 'run_shared_alu.py', 'finish_shared_alu_soc.py'):
            shutil.copy2(HERE/f, out/f)
        d = out/'candidate'; d.mkdir(); (d/'sim').mkdir()
        raw = (old/'candidate/sources.f').read_text()
        frozen = raw.replace(str(old/'source')+'/', str(source)+'/')
        for line in frozen.splitlines():
            if line.startswith('/') and (not line.startswith(str(source)+'/') or not Path(line).is_file()):
                raise ValueError('Unsealed source: '+line)
            if line.startswith('+incdir+'):
                for inc in line[len('+incdir+'):].split('+'):
                    if not inc.startswith(str(source)+'/') or not Path(inc).is_dir():
                        raise ValueError('Unsealed include: '+inc)
        (d/'sources.f').write_text(frozen)
        cmd = [x.replace(str(old)+'/', str(out)+'/') for x in read(old/'candidate/command.json')['command']]
        cmd.append(str(out/'vrf_return_soc_monitor.sv'))
        api.save(d/'command.json', dict(command=cmd))
        api.save(out/'plan.json', dict(cases=names, workers=6, accepted=str(old), component=str(comp),
            scope='Only vector_regfile changed; read-only old-router monitor added',
            baseline='Reuse all 62 checked candidate runs, exact ELF/source/image pins; no rerun'))
        for f in out.rglob('*'):
            if f.is_file() and f.name != 'status.json': pins[str(f)] = api.sha(f)
        def verify():
            for f, digest in pins.items():
                if api.sha(Path(f)) != digest: raise ValueError('Input drift: '+f)
        api.save(out/'source-pins.json', pins)
        verify(); state(state='BUILDING', total_cases=len(names))
        rc = api.execute(cmd, d/'sim', d/'build.log', 7200)
        image = d/'sim/simv'
        if rc or not image.is_file() or re.search(r'(?m)^(Error-|Error:|Fatal:)', (d/'build.log').read_text(errors='replace')):
            raise ValueError('VCS build failed: '+str(rc))
        pins[str(image)] = api.sha(image)
        for f in (image.parent/'simv.daidir').rglob('*'):
            if f.is_file(): pins[str(f)] = api.sha(f)
        api.save(out/'source-pins.json', pins)
        def run(name):
            case = d/'cases'/name; case.mkdir(parents=True)
            cmd = [str(image), '-no_save', '-l', 'run.vcs.log', f'+PRELOAD={out/"inputs"/name}',
                   f'+TESTCASE={name}', '+NO_FSDB', '+ntb_random_seed=1']
            api.save(case/'command.json', dict(command=cmd, elf_sha256=api.sha(out/'inputs'/name)))
            start = time.monotonic()
            rc = api.execute(cmd, case, case/'console.log', 10800 if name in ('dotproduct','llama_q4km_micro') else 3600)
            row = dict(case=name, returncode=rc, wall_seconds=time.monotonic()-start)
            try:
                if rc: raise ValueError('Simulator exit '+str(rc))
                text = (case/'console.log').read_text(errors='replace')
                if re.search(r'Fatal:|Error:|VRF_SOC_.*MISMATCH|VRF_RETURN_(COLLISION|UNKNOWN|INVALID)', text):
                    raise ValueError('VRF monitor failure')
                metrics = json.loads(json.dumps(parse(text, name, observation_aware=True)))
                checks = re.findall(r'^VRF_SOC_CHECKED (\S+) returns=(\d+)', text, re.M)
                if len(checks) != 4 or len({x[0] for x in checks}) != 4 or not sum(int(x[1]) for x in checks):
                    raise ValueError('Missing four-lane return checks')
                if metrics != baseline[name]: raise ValueError('Result/cycle/activity changed')
                row.update(status='PASS', metrics=metrics, vrf_checks=checks)
            except ValueError as exc:
                row.update(status='FAIL', reason=str(exc))
            api.save(case/'result.json', row)
            return row
        rows = []
        for index in range(0, len(names), 6):
            batch = names[index:index+6]
            verify(); state(state='RUNNING', active_cases=batch)
            with ThreadPoolExecutor(max_workers=6) as pool: results = list(pool.map(run, batch))
            rows.extend(results); api.save(out/'results.json', rows)
            state(completed_cases=len(rows))
            if any(r['status'] != 'PASS' for r in results):
                state(state='STOPPED_ON_FAILURE'); return 1
        verify()
        api.save(out/'report.json', dict(state='PASS', cases=len(rows), baseline_reused=True,
            exact_result_cycle_activity_equivalence=True, scope='Bounded SoC regression, not FPGA/signoff'))
        state(state='PASS', active_cases=[])
        return 0
    except Exception as exc:
        state(state='ERROR', reason=str(exc)); raise


if __name__ == '__main__':
    raise SystemExit(main())
