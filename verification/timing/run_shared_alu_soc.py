#!/usr/bin/env python3
"""Frozen-source VCS SoC ALU acceptance; run directly under systemd --user.

Two images differ only in simd_alu. Both include the same read-only old-ALU
checker in each real VALU and the already selected shared integer multiplier.
This is functional/performance acceptance, not physical or coverage signoff.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = 'b69df88f0'
ALU = Path('hardware/src/lane/simd_alu.sv')
ISA = '''vadd vsub vrsub vadc vsbc vmadc vmsbc vsadd vsaddu
vaadd vaaddu vasub vasubu vaverage_matrix vmin vminu vmax vmaxu
vmseq vmsne vmslt vmsltu vmsle vmsleu vmsgt vmsgtu vwadd vwaddu
vwsub vwsubu vwredsum vwredsumu vredsum vredmin vredminu vredmax
vredmaxu vnclip vnclipu vnclip_edges vnsra vnsrl vsll vsra vsrl
vssra vssrl vmask_carry_tail_edges vmask_compare_edges vmask_logical_matrix
vwar_pending_source_edges vreduction_overlap_edges vreduction_lmul_edges
vwiden_overlap_edges vwiden_lmul4_edges vunit_vstart_edges vstore_mask_tail_edges'''.split()
ACTIVITY = re.compile(r'ALU_SOC_ACTIVITY (\S+) eval=(\d+),(\d+),(\d+),(\d+) '
    r'wb=(\d+) wb_blocked=(\d+) pending=(\d+) queue_full=(\d+) mask=(\d+)')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, value):
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2)+'\n')
    tmp.replace(p)


def reference_module(source):
    renamed, replacements = re.subn(r'\bmodule simd_alu\b',
                                   'module simd_alu_reference', source)
    if replacements != 1:
        raise ValueError('Cannot identify baseline module')
    return re.sub(r'\bendmodule\s*:\s*simd_alu\b',
                  'endmodule : simd_alu_reference', renamed)


def execute(cmd, cwd, log, timeout):
    # A timed-out VCS build can leave compiler children unless its whole group
    # is stopped. The long-lived service still owns all these child groups.
    with log.open('w') as stream:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=stream,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            return 124


def parse(text, case):
    if 'Core Test *** SUCCESS ***' not in text or re.search(r'Fatal:|Error:|\bFAILED\b|ALU_SOC_MISMATCH', text):
        raise ValueError('Firmware/assertion failure or missing EOC')
    activity = sorted(ACTIVITY.findall(text))
    monitors = re.findall(r'^ALU_SOC_MONITOR (\S+)', text, re.M)
    if len(set(monitors)) != 4 or len(activity) != 4 or len({r[0] for r in activity}) != 4:
        raise ValueError('Missing/duplicate four-lane monitor evidence')
    if not sum(int(x) for r in activity for x in r[1:5]):
        raise ValueError('No valid ALU evaluations')
    finish = re.findall(r'\$finish at simulation time\s+(\d+)', text)
    if len(finish) != 1:
        raise ValueError('Missing unique simulation completion time')
    regions = re.findall(r'The execution took (\d+) cycles', text)
    timer = re.findall(r'\[hw-cycles\]:\s*(\d+)', text)
    micro = re.findall(r'^MICRO (\S+) PASS cycles=(\d+)(.*)$', text, re.M)
    if case == 'dotproduct' and len(regions) != 9:
        raise ValueError('Dotproduct region set incomplete')
    if case == 'mixed' and len(timer) != 1:
        raise ValueError('Missing mixed-program cycle measurement')
    if case == 'llama_q4km_micro':
        expected = {'quantize_f32_to_q8_k_k1536', 'quantize_f32_to_q8_k_k8960',
            'q4_k_x_q8_k_dot_n1536_nrc1', 'q4_k_x_q8_k_dot_n8960_nrc1',
            'q6_k_x_q8_k_dot_n1536_nrc1', 'q6_k_x_q8_k_dot_n8960_nrc1'}
        if len(micro) != 6 or {r[0] for r in micro} != expected or 'Q4_K_M micro verification: PASS (0/6 failed)' not in text:
            raise ValueError('Llama numerical/region evidence incomplete')
    return dict(activity=activity, finish_time=finish[0], kernel_cycles=regions,
                hw_cycles=timer, micro=micro)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--template', type=Path, required=True,
                   help='Accepted VCS source manifest (fast shared-multiplier SoC)')
    a = p.parse_args()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    status = dict(state='PREPARING', started=datetime.now(timezone.utc).isoformat())
    def state(**kw):
        status.update(kw); save(out/'status.json', status)
        print(json.dumps(status), flush=True)
    try:
        template = json.loads(a.template.read_text())
        old_alu = subprocess.check_output(['git','show',f'{BASE}:{ALU}'], cwd=ROOT)
        if hashlib.sha256(old_alu).hexdigest() != next(r['sha256'] for r in template['files'] if r['path'] == str(ROOT/ALU)):
            raise ValueError('Baseline ALU differs from accepted source manifest')
        snapshot = out/'source'; snapshot.mkdir()
        inventory = {}
        for row in template['files']:
            source = Path(row['path'])
            if source != ROOT/ALU and sha(source) != row['sha256']:
                raise ValueError('Unexpected template source drift: '+str(source))
            if source.is_relative_to(ROOT):
                target = snapshot/source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                inventory[str(target)] = sha(target)
        for name in ('shared_alu_soc_monitor.sv','build_shared_alu_mixed.py','run_shared_alu_soc.py'):
            target = out/name
            shutil.copy2(ROOT/'verification/timing'/name, target)
            inventory[str(target)] = sha(target)
        reference = out/'simd_alu_reference.sv'
        reference.write_text(reference_module(old_alu.decode()))
        inventory[str(reference)] = sha(reference)
        baseline = out/'simd_alu_baseline.sv'; baseline.write_bytes(old_alu)
        inventory[str(baseline)] = sha(baseline)
        dpi_source = next(Path(x) for x in template['extra_sources'] if x.endswith('elfloader.o'))
        dpi = out/'elfloader.o'; shutil.copy2(dpi_source,dpi); inventory[str(dpi)] = sha(dpi)
        raw = Path(template['filelist']).read_text()
        # Filelist and include paths must be confined to the sealed source tree.
        frozen = raw.replace(str(ROOT)+'/', str(snapshot)+'/')
        for line in frozen.splitlines():
            if line.startswith('/') and (not line.startswith(str(snapshot)+'/') or not Path(line).is_file()):
                raise ValueError('Unsealed filelist source: '+line)
            if line.startswith('+incdir+'):
                for inc in line[len('+incdir+'):].split('+'):
                    if not inc.startswith(str(snapshot)+'/') or not Path(inc).is_dir():
                        raise ValueError('Unsealed include: '+inc)
        inputs = out/'inputs'; inputs.mkdir()
        names = ['rv64uv-ara-vadd','mixed'] + ['rv64uv-ara-'+n for n in ISA if n != 'vadd'] + ['vvaddint32','dotproduct','llama_q4km_micro']
        for name in names:
            if name != 'mixed':
                shutil.copy2(ROOT/'apps/bin'/name,inputs/name)
        # Preserve the linker script used by the new independent-golden test.
        link = snapshot/'apps/common/link.ld'; link.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/'apps/common/link.ld',link); inventory[str(link)] = sha(link)
        (snapshot/'install').symlink_to(ROOT/'install',target_is_directory=True)
        compiler = ROOT/'install/riscv-llvm/bin/clang'
        save(out/'compiler.json',dict(path=str(compiler.resolve()),sha256=sha(compiler)))
        subprocess.run([sys.executable,str(out/'build_shared_alu_mixed.py'),str(out/'mixed-build'),
                        '--root',str(snapshot)],check=True,timeout=120)
        shutil.copy2(out/'mixed-build/mixed.elf',inputs/'mixed')
        for f in inputs.iterdir(): inventory[str(f)] = sha(f)
        for f in (out/'mixed-build').iterdir(): inventory[str(f)] = sha(f)
        variants = ('baseline','shared')
        for v in variants:
            d = out/v; d.mkdir(); (d/'sim').mkdir()
            filelist = frozen if v == 'shared' else frozen.replace(str(snapshot/ALU),str(baseline))
            f = d/'sources.f'; f.write_text(filelist); inventory[str(f)] = sha(f)
        save(out/'source-pins.json',inventory)
        save(out/'plan.json',dict(baseline_commit=BASE,cases=names,paired_runs=2*len(names),
             template=str(a.template.resolve()),template_sha256=sha(a.template),
             knobs=dict(lanes=4,vlen=1024,l2_mb=2,qbs=1,akv=1,akv_v2=1,shared_multiplier=1),
             interpretation='ALU counters are evaluation beats and interface cycles, not instruction counts'))
        def check_pins():
            for f,h in inventory.items():
                if sha(Path(f)) != h: raise ValueError('Sealed input drift: '+f)
        vcs = shutil.which('vcs')
        if not vcs: raise ValueError('VCS not in PATH')
        def build(v):
            d = out/v
            cmd = [vcs,'-full64','-sverilog','+v2k','-Mlib=./incremental_db','-Mupdate','-j8',
                '-lca','+nospecify','+notimingchecks','+lint=TFIPC-L','+vpi','+lint=PCWM','+error+30',
                '-top','ara_tb','-timescale=1ns/100fs',
                '+define+SIMULATION','+define+no_warning','+define+TSMC_NO_WARNING',
                '+define+ARA_NO_FSDB','+define+ARA_FAIL_FAST_ASSERTS','+define+ARA_SHARED_SIMD_MUL',
                '-f',str(d/'sources.f'),str(dpi),str(reference),str(out/'shared_alu_soc_monitor.sv'),
                '-l','comp.vcs.log']
            save(d/'command.json',dict(command=cmd))
            rc = execute(cmd,d/'sim',d/'build.log',7200)
            if rc or not (d/'sim/simv').is_file(): raise ValueError(f'{v} build failed ({rc})')
            save(d/'image.json',dict(sha256=sha(d/'sim/simv')))
            print('BUILD_PASS '+v,flush=True)
        state(state='BUILDING',completed_pairs=0,total_pairs=len(names))
        with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(build,variants))
        check_pins()
        images = {v:sha(out/v/'sim/simv') for v in variants}
        def run(v,name):
            d = out/v/'cases'/name; d.mkdir(parents=True)
            image = out/v/'sim/simv'
            if sha(image) != images[v]: raise ValueError('Image drift')
            cmd = [str(image),'-no_save','-l','run.vcs.log',f'+PRELOAD={inputs/name}',
                   f'+TESTCASE={name}','+NO_FSDB','+ntb_random_seed=1']
            limit = 10800 if name in ('llama_q4km_micro','dotproduct') else 3600
            save(d/'command.json',dict(command=cmd,elf_sha256=sha(inputs/name),timeout_seconds=limit))
            started = time.monotonic(); rc = execute(cmd,d,d/'console.log',limit)
            result = dict(variant=v,case=name,returncode=rc,wall_seconds=time.monotonic()-started)
            try:
                if rc: raise ValueError('Nonzero exit: '+str(rc))
                result.update(parse((d/'console.log').read_text(errors='replace'),name),status='PASS')
            except ValueError as exc:
                result.update(status='FAIL',reason=str(exc))
            save(d/'result.json',result)
            return result
        rows = []; pairs = []
        # The first two discriminating pairs run before broad regression.
        batches = [[names[0]],[names[1]]] + [names[i:i+3] for i in range(2,len(names),3)]
        for batch in batches:
            check_pins(); state(state='RUNNING',active_cases=batch)
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda vn:run(*vn),[(v,n) for n in batch for v in variants]))
            rows.extend(results); save(out/'results.json',rows)
            for i,name in enumerate(batch):
                b,s = results[2*i:2*i+2]
                keys = ('activity','finish_time','kernel_cycles','hw_cycles','micro')
                ok = b['status'] == s['status'] == 'PASS'
                equal = ok and all(b[k] == s[k] for k in keys)
                pairs.append(dict(case=name,functional='PASS' if ok else 'FAIL',
                                  exact_cycle_activity_equivalence=equal))
            save(out/'pairs.json',pairs)
            if any(x['functional'] != 'PASS' or not x['exact_cycle_activity_equivalence'] for x in pairs):
                state(state='STOPPED_ON_FAILURE_OR_TIMING_CHANGE',completed_pairs=len(pairs)); return 1
            state(completed_pairs=len(pairs))
        check_pins()
        state(state='PASS',active_cases=[],completed_pairs=len(pairs),
              scope='Frozen full-SoC functional and exact cycle equivalence; no physical/FPGA signoff')
        return 0
    except Exception as exc:
        state(state='ERROR',reason=str(exc)); raise


if __name__ == '__main__':
    raise SystemExit(main())
