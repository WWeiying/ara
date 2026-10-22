#!/usr/bin/env python3
"""One-call real-SoC indexed fault discriminator; no RTL build or edits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ORIGINAL = Path('/home/wangwy/fpga_runs/ara_va_rvv_retest_20261018_01/original_reproducer')
OLD = ROOT / 'verification/fpga/current_board_review/indexed_overlap_original'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
FROZEN = IMAGE.parents[1] / 'frozen'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
CASES = {'fault_overlap': (1, 1, 0), 'resident_overlap': (0, 1, 0),
         'fault_nonoverlap': (1, 0, 0), 'fault_overlap_context': (1, 1, 1),
         'resident_nonoverlap': (0, 0, 0),
         'fault_overlap_mid': (1, 1, 0), 'fault_overlap_last': (1, 1, 0)}
FAULT_ELEMENTS = {'fault_overlap_mid': 17, 'fault_overlap_last': 31}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, value):
    p.write_text(json.dumps(value, indent=2) + '\n')


def env():
    e = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
    vcs = '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
    verdi = '/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1'
    e.update(PATH=vcs+'/bin:/usr/bin:/bin', VCS_HOME=vcs, VERDI_HOME=verdi,
             VCS_TARGET_ARCH='linux64', SNPSLMD_LICENSE_FILE='27000@t7920',
             LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
    return e


def run(command, directory, label, timeout=60, stderr=None, environment=None):
    command = list(map(str, command))
    save(directory / (label+'.command.json'), dict(command=command, cwd=str(directory)))
    started = time.monotonic()
    with (directory / (label+'.log')).open('x') as out:
        if stderr:
            with (directory / stderr).open('x') as err:
                r = subprocess.run(['timeout', '--kill-after=10s', str(timeout), *command],
                                   cwd=directory, stdout=out, stderr=err, env=environment)
        else:
            r = subprocess.run(['timeout', '--kill-after=10s', str(timeout), *command],
                               cwd=directory, stdout=out, stderr=subprocess.STDOUT, env=environment)
    info = dict(returncode=r.returncode, seconds=round(time.monotonic()-started, 3))
    save(directory / (label+'.exit.json'), info)
    return info


def prepare(out, diagnose_context=False):
    out.mkdir(parents=True, exist_ok=False)
    source = out / 'inputs'; source.mkdir()
    ledger = json.loads((IMAGE/'image.json').read_text())
    assert sha(FROZEN/'snapshot.json') == ledger['snapshot_sha256']
    for p, digest in ledger['files'].items():
        assert sha(p) == digest, p
    snapshot = json.loads((FROZEN/'snapshot.json').read_text())
    deltas = []
    for p, digest in snapshot['live_source_sha256'].items():
        if Path(p).exists() and sha(p) != digest:
            deltas.append(p)
    critical = ['hardware/src/ara_dispatcher.sv','hardware/src/lane/lane.sv',
                'hardware/src/lane/lane_sequencer.sv','hardware/src/vlsu/vldu.sv',
                'hardware/src/vlsu/vlsu.sv','hardware/src/ara_soc.sv',
                'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv']
    for p in critical:
        assert sha(ROOT/p) == sha(FROZEN/'sources'/p), p
    save(out/'image-audit.json', dict(image=ledger, source_deltas=deltas,
         matched_critical={p:sha(ROOT/p) for p in critical},
         limitation='Short Sv39 adapter, not original Linux end-to-end; inspect source_deltas for image/current differences'))
    pins = {}
    def copy(p, name):
        shutil.copyfile(p, source/name); pins[str(p)] = sha(p)
    copy(ORIGINAL/'vector_probe.S', 'vector_probe.S')
    copy(ORIGINAL/'vector_probe.c', 'vector_probe.original.c')
    copy(HERE/'fixture.c', 'fixture.c')
    copy(HERE/'run.py', 'run.py')
    copy(OLD/'fixture.S', 'fixture.S')
    for n in ('startup.S','runtime.c','replay.ld'):
        copy(OLD/'reference03'/n, n)
    context = ROOT/'apps/riscv-tests/isa/rv64uv/linux_vector_context.c'
    copy(context, 'linux_vector_context.original.c')
    text = context.read_text()
    functions = []
    for name in ('linux_save','linux_restore'):
        match = re.search(r'static void __attribute__\(\(naked, noinline, used\)\)\n'+name+r'\(.*?\n}', text, re.S)
        assert match, name
        functions.append(match[0])
    (source/'context.inc').write_text('\n'.join(text.splitlines()[:4])+'\n'+
        'struct vstate { uint64_t vstart, vtype, vl, vcsr, vlenb; };\n'+ '\n'.join(functions)+'\n')
    save(out/'source-pins.json', pins)
    flags = ['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding',
             '-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
             '-msmall-data-limit=0','-nostdlib','-static','-Wl,--build-id=none','-T',source/'replay.ld']
    for name, (fault, overlap, context_mode) in CASES.items():
        case = out/name; case.mkdir()
        defines = [f'-DFAULT={fault}',f'-DOVERLAP={overlap}',f'-DCONTEXT={context_mode}',
                   f'-DCONTEXT_DIAG={int(diagnose_context)}',
                   f'-DFAULT_ELEMENT={FAULT_ELEMENTS.get(name, 0)}']
        for backend in ('soc','spike'):
            command = [CC,*flags,*defines,*(['-DSPIKE_REFERENCE'] if backend=='spike' else []),
                       *[source/n for n in ('fixture.c','fixture.S','vector_probe.S','startup.S','runtime.c')],
                       '-lgcc','-o',case/(backend+'.elf')]
            assert run(command,case,backend+'.compile')['returncode'] == 0
            dis = subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-objdump')),
                                           '-d',str(case/(backend+'.elf'))],text=True)
            (case/(backend+'.dis')).write_text(dis)
            assert '0625f107' in dis and '0625f407' in dis, 'original helper encoding changed'
        r = run([SPIKE,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                 '-m2','-l','--log-commits',case/'spike.elf'],case,'spike',stderr='spike.trace')
        assert r['returncode'] == 0, name
        trace = (case/'spike.trace').read_text()
        faults = re.findall(r'exception (trap_\w+), epc 0x([0-9a-f]+)',trace)
        assert [v[0] for v in faults] == (['trap_load_page_fault'] if fault else [])+['trap_supervisor_ecall'], faults
        save(case/'reference.json',dict(status='SPIKE_PASS_NOT_DUT',faults=faults,scope='one-call semantic adapter, unchanged gather32 ASM'))
    capture = (OLD/'repair06_worker/capture.tcl').read_text().replace('indexed_first_round.fsdb','focused.fsdb')
    capture = capture.replace('1000000ns','200000ns').replace('1000000NS','200000NS')
    (out/'capture.tcl').write_text(capture)
    save(out/'prepared.json',dict(status='PREPARED',cases=CASES,fault_elements=FAULT_ELEMENTS,
         inputs={p.name:sha(p) for p in source.iterdir()},
         tools={str(p):sha(p) for p in (CC,SPIKE)},scope='32 original indices and all 32 output checks; first/mid/last-element faults; no Linux boot or syscall emulation'))


def execute(out, case_name):
    case = out/case_name
    assert not (case/'vcs.log').exists(), 'no automatic rerun'
    ledger = json.loads((out/'image-audit.json').read_text())['image']
    for p, digest in ledger['files'].items():
        assert sha(p) == digest, p
    command = [ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1',
               '+PRELOAD='+str(case/'soc.elf'),'+TESTCASE=system_'+case_name,'+NO_FSDB',
               '+COMMIT_TRACE='+str(case/'commit_trace.csv'),'-ucli','-do',out/'capture.tcl']
    r = run(command,case,'vcs',timeout=300,environment=env())
    log = (case/'vcs.log').read_text(errors='replace')
    r.update(case=case_name,elf_sha256=sha(case/'soc.elf'),
             status='PASS' if r['returncode']==0 and 'SYSTEM_PASS' in log and
             'SYSTEM_FAIL' not in log and 'Core Test *** SUCCESS ***' in log else 'NOT_PASS',
             faults=re.findall(r'SYSTEM_FAULT[^\r\n]*',log),
             diagnostics=re.findall(r'SYSTEM_(?:FAIL|PASS|MISMATCH)[^\r\n]*',log),
             fsdb_bytes=(case/'focused.fsdb').stat().st_size if (case/'focused.fsdb').exists() else 0)
    save(case/'result.json',r)
    print(json.dumps(r,indent=2),flush=True)
    return r['status']=='PASS'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','run','controls'])
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--case',choices=CASES)
    p.add_argument('--image',type=Path)
    p.add_argument('--diagnose-context',action='store_true')
    a=p.parse_args(); out=a.out.resolve()
    if a.image:
        IMAGE = a.image.resolve()
        FROZEN = IMAGE.parent / 'frozen'
    assert out.is_relative_to(HERE), 'output must be inside owned system directory'
    if a.command=='prepare': prepare(out, a.diagnose_context)
    elif a.command=='run':
        assert a.case
        raise SystemExit(0 if execute(out,a.case) else 1)
    else:
        names = [n for n in CASES if n != 'fault_overlap']
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda name: execute(out,name), names))
        save(out/'controls.json',dict(cases=names,passed=results,
             scope='four independent one-call controls/supplement; no fault_overlap pilot rerun'))
        raise SystemExit(0 if all(results) else 1)
