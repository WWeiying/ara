#!/usr/bin/env python3
"""Paired SoC acceptance of the shared shifter using sealed, accepted inputs.

Reuse the previously accepted shared-arithmetic image as the baseline. Build
only the candidate, replacing simd_alu alone in the matching source snapshot.
Run this long-lived worker directly under systemd --user.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import run_shared_alu as component
import run_shared_alu_soc as api
import finish_shared_alu_soc as completion

HERE = Path(__file__).resolve().parent
ALU = Path('hardware/src/lane/simd_alu.sv')


def read(path):
    return json.loads(path.read_text())


def parse(text, case, observation_aware=False):
    result = completion.classify(api, text, 'dotproduct_format_audit' if case == 'dotproduct' else case)
    monitors = re.findall(r'^ALU_SOC_MONITOR (\S+)', text, re.M)
    if len(monitors) != 4 or {r[0] for r in result['activity']} != set(monitors):
        raise ValueError('Monitor/activity identity mismatch')
    if observation_aware:
        summaries = re.findall(r'^ALU_OBSERVATION_SUMMARY (\S+) inactive_x_events=(\d+)', text, re.M)
        if len(summaries) != 4 or {name for name,_ in summaries} != set(monitors):
            raise ValueError('Missing observation-aware checker evidence')
    if case in ('mixed', 'shift_mixed', 'vvaddint32'):
        if len(result['hw_cycles']) != 1 or int(result['hw_cycles'][0]) <= 0:
            raise ValueError('Missing positive application timer')
    if case == 'dotproduct':
        regions = re.findall(r'Calulating (\d+)b dotp with vectors with length = (\d+)\s+'
            r'Vector runtime: (\d+)\s+Scalar runtime: (\d+)', text)
        expected = {(str(s), str(n)) for s in (8, 16, 32, 64) for n in (8, 64)} | {('8','512')}
        if (len(regions) != 9 or {(s,n) for s,n,_,_ in regions} != expected or
                'SUCCESS.' not in text or any(int(v) <= 0 or int(sc) <= 0 for _,_,v,sc in regions)):
            raise ValueError('Incomplete checked DOTP regions')
        result['dotproduct_regions'] = regions
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--component', type=Path, required=True)
    p.add_argument('--accepted', type=Path, required=True)
    p.add_argument('--observation-aware', action='store_true',
                   help='Use byte-enable-aware X diagnostics, without relaxing known-bit comparisons')
    a = p.parse_args(); out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    comp = a.component.resolve(); accepted = a.accepted.resolve()
    status = dict(state='PREPARING', started=datetime.now(timezone.utc).isoformat())
    def state(**kw):
        status.update(kw); api.save(out/'status.json', status); print(json.dumps(status), flush=True)
    try:
        cm = component.verify(comp)
        if not cm.get('shift_test') or read(comp/'test.status.json')['state'] != 'PASS':
            raise ValueError('Extended component verification not passed')
        acceptance = read(accepted/'report.json')
        if acceptance['state'] != 'PASS' or not acceptance['exact_result_cycle_activity_equivalence']:
            raise ValueError('Previous SoC acceptance missing')
        finish = Path(acceptance['evidence'])
        old = Path(read(finish/'status.json')['previous'])
        pins = {}
        for inv in (old/'source-pins.json', finish/'source-pins.json', accepted/'source-pins.json'):
            for f, digest in read(inv).items():
                if api.sha(Path(f)) != digest:
                    raise ValueError('Inherited evidence drift: '+f)
            pins[str(inv)] = api.sha(inv)
        if api.sha(comp/'baseline.sv') != api.sha(old/'source'/ALU):
            raise ValueError('Component reference is not the accepted SoC ALU')
        baseline_image = old/'shared/sim/simv'
        if api.sha(baseline_image) != read(old/'shared/image.json')['sha256']:
            raise ValueError('Previous image drift')
        pins[str(baseline_image)] = api.sha(baseline_image)
        for f in (baseline_image.parent/'simv.daidir').rglob('*'):
            if f.is_file(): pins[str(f)] = api.sha(f)
        source = out/'source'
        shutil.copytree(old/'source', source, symlinks=True)
        shutil.copy2(comp/'src/simd_alu.sv', source/ALU)
        for dest, origin in {
            'reference.sv': comp/'src/reference.sv',
            'elfloader.o': old/'elfloader.o',
            'shared_alu_soc_monitor.sv': old/'shared_alu_soc_monitor.sv',
        }.items(): shutil.copy2(origin, out/dest)
        if a.observation_aware:
            for name in ('shared_alu_observation.sv', 'shared_alu_shift_soc_monitor.sv'):
                shutil.copy2(HERE/name, out/name)
        helpers = ('run_shared_alu_shift_soc.py', 'run_shared_alu_soc.py',
            'run_shared_alu.py', 'finish_shared_alu_soc.py', 'build_shared_alu_shift_mixed.py')
        for name in helpers: shutil.copy2(HERE/name, out/name)
        # Do not depend on a mutable linker script or a different toolchain.
        compiler = api.ROOT/'install/riscv-llvm/bin/clang'
        pins[str(compiler.resolve())] = api.sha(compiler)
        with (out/'firmware-build.log').open('w') as log:
            subprocess.run([sys.executable, str(out/'build_shared_alu_shift_mixed.py'),
                str(out/'shift-build'), '--root', str(source)], check=True, timeout=120,
                stdout=log, stderr=subprocess.STDOUT)
        inputs = out/'inputs'; shutil.copytree(old/'inputs', inputs)
        replacement = finish/'vadd1024.elf'
        if api.sha(replacement) != acceptance['substitution']['replacement_sha256']:
            raise ValueError('Checked VADD replacement identity mismatch')
        shutil.copy2(replacement, inputs/'vvaddint32')
        shutil.copy2(out/'shift-build/shift_mixed.elf', inputs/'shift_mixed')
        old_names = read(old/'plan.json')['cases']
        names = ['shift_mixed', 'mixed', 'vvaddint32'] + [n for n in old_names if n not in ('mixed','vvaddint32')]
        if len(names) != len(set(names)) or len(old_names) != acceptance['paired_cases']:
            raise ValueError('Suite identity mismatch')
        d = out/'candidate'; d.mkdir(); (d/'sim').mkdir()
        raw = (old/'shared/sources.f').read_text()
        frozen = raw.replace(str(old/'source')+'/', str(source)+'/')
        for line in frozen.splitlines():
            if line.startswith('/') and (not line.startswith(str(source)+'/') or not Path(line).is_file()):
                raise ValueError('Unsealed source: '+line)
            if line.startswith('+incdir+'):
                for inc in line[len('+incdir+'):].split('+'):
                    if not inc.startswith(str(source)+'/') or not Path(inc).is_dir():
                        raise ValueError('Unsealed include: '+inc)
        (d/'sources.f').write_text(frozen)
        cmd = read(old/'shared/command.json')['command']
        substitutions = {str(old/'shared/sources.f'):str(d/'sources.f'),
                         str(old/'elfloader.o'):str(out/'elfloader.o'),
                         str(old/'simd_alu_reference.sv'):str(out/'reference.sv'),
                         str(old/'shared_alu_soc_monitor.sv'):str(out/'shared_alu_soc_monitor.sv')}
        cmd = [substitutions.get(x, x) for x in cmd]
        if a.observation_aware:
            cmd[cmd.index(str(out/'shared_alu_soc_monitor.sv'))] = str(out/'shared_alu_shift_soc_monitor.sv')
            cmd.append(str(out/'shared_alu_observation.sv'))
        api.save(d/'command.json', dict(command=cmd))
        api.save(out/'plan.json', dict(reference_commit=cm['reference'], component=str(comp),
            accepted_soc=str(accepted), baseline_image=str(baseline_image), cases=names,
            candidate_alu_sha256=api.sha(source/ALU), concurrent_simulators=6,
            observation_aware=a.observation_aware,
            scope='Only simd_alu changed; all other SoC sources retained from accepted snapshot'))
        for f in out.rglob('*'):
            if f.is_file() and f.name != 'status.json': pins[str(f)] = api.sha(f)
        pins[str(accepted/'report.json')] = api.sha(accepted/'report.json')
        api.save(out/'source-pins.json', pins)
        def verify():
            component.verify(comp)
            for f, digest in pins.items():
                if api.sha(Path(f)) != digest: raise ValueError('Sealed input drift: '+f)
        verify(); state(state='BUILDING', completed_pairs=0, total_pairs=len(names))
        rc = api.execute(cmd, d/'sim', d/'build.log', 7200)
        image = d/'sim/simv'
        if rc or not image.is_file(): raise ValueError('Candidate build failed: '+str(rc))
        build_text = (d/'build.log').read_text(errors='replace')
        if re.search(r'(?m)^(?:Error(?:-|:)|Fatal:)', build_text):
            raise ValueError('Candidate compile error')
        pins[str(image)] = api.sha(image)
        for f in (image.parent/'simv.daidir').rglob('*'):
            if f.is_file(): pins[str(f)] = api.sha(f)
        api.save(d/'image.json', dict(sha256=api.sha(image)))
        api.save(out/'source-pins.json', pins)
        images = dict(baseline=baseline_image, candidate=image)
        def run(variant, name):
            case = out/variant/'cases'/name; case.mkdir(parents=True)
            elf = inputs/name
            command = [str(images[variant]), '-no_save', '-l', 'run.vcs.log',
                f'+PRELOAD={elf}', f'+TESTCASE={name}', '+NO_FSDB', '+ntb_random_seed=1']
            limit = 10800 if name in ('llama_q4km_micro','dotproduct') else 3600
            api.save(case/'command.json', dict(command=command, elf_sha256=api.sha(elf), timeout_seconds=limit))
            started = time.monotonic(); rc = api.execute(command, case, case/'console.log', limit)
            row = dict(variant=variant, case=name, returncode=rc, wall_seconds=time.monotonic()-started)
            try:
                if rc: raise ValueError('Simulator exit: '+str(rc))
                row.update(status='PASS', metrics=parse((case/'console.log').read_text(errors='replace'), name,
                           observation_aware=a.observation_aware and variant == 'candidate'))
            except ValueError as exc: row.update(status='FAIL', reason=str(exc))
            api.save(case/'result.json', row)
            return row
        rows = []; pairs = []
        priority = ['rv64uv-ara-vnclip', 'rv64uv-ara-vnclipu', 'rv64uv-ara-vnclip_edges']
        if a.observation_aware:
            rest = [n for n in names if n not in priority]
            batches = [priority, [rest[0]]] + [rest[i:i+3] for i in range(1,len(rest),3)]
        else:
            batches = [[names[0]]] + [names[i:i+3] for i in range(1,len(names),3)]
        for batch in batches:
            verify(); state(state='RUNNING', active_cases=batch)
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda vn:run(*vn), [(v,n) for n in batch for v in images]))
            rows.extend(results); api.save(out/'results.json', rows)
            for i,name in enumerate(batch):
                b,c = results[2*i:2*i+2]
                ok = b['status'] == c['status'] == 'PASS'
                equal = ok and b['metrics'] == c['metrics']
                pairs.append(dict(case=name, functional='PASS' if ok else 'FAIL',
                    exact_result_cycle_activity_equivalence=equal,
                    role='collateral_non_ALU' if name in completion.COLLATERAL else 'ALU_active'))
            api.save(out/'pairs.json', pairs)
            if any(r['functional'] != 'PASS' or not r['exact_result_cycle_activity_equivalence'] for r in pairs):
                state(state='STOPPED_ON_FAILURE_OR_TIMING_CHANGE', completed_pairs=len(pairs)); return 1
            state(completed_pairs=len(pairs))
        verify()
        api.save(out/'report.json', dict(state='PASS', paired_cases=len(pairs),
            exact_result_cycle_activity_equivalence=True,
            scope='Bounded SoC acceptance; no physical/FPGA or coverage signoff'))
        state(state='PASS', active_cases=[])
        return 0
    except Exception as exc:
        state(state='ERROR', reason=str(exc)); raise


if __name__ == '__main__':
    raise SystemExit(main())
