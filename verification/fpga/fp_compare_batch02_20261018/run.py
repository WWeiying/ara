#!/usr/bin/env python3
"""Replay authentic batch02 FP comparisons without changing the oracle or RTL."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent / 'current_board_review/comparison_alias_original'
sys.path.insert(0, str(BASE))
import prepare19 as helper

CAMP = helper.CAMP
RUNTIME = helper.BASE
OLD_CC = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc')
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/fp_compare_oracle.c')
IMAGE = Path('/home/wangwy/fpga_runs/indexed_fault_overlap_fix_20261018_02/image')
CASES = [
    dict(name='rvv_fp_compare_unmasked_alias_v8_e32_m4', arch='rvv_fp_comparisons_unmasked_alias_v8_01',
         release=45, destination=1, unboxed=0, op=5, seed=0, length=4, mode=3, sticky=0, call=319,
         sha256='f865b29fb96de73afab71abcf4dbdbb739803ace01edbaae344eb3733b4c212f'),
    dict(name='rvv_fp_compare_unboxed_unmasked_alias_v16_e32_m1', arch='rvv_fp_comparisons_unboxed_v16_unmasked_01',
         release=46, destination=2, unboxed=1, op=2, seed=27, length=6, mode=2, sticky=1, call=15286,
         sha256='df847db0c09834783d85a1931e7f74b9f0950f1a6aec4d502e43ab915c840efb'),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def command(argv, cwd, label, timeout=60, env=None):
    argv = list(map(str, argv))
    save(cwd/(label+'.command.json'), argv)
    started = time.time()
    with (cwd/(label+'.log')).open('x') as log:
        try:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=timeout)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
    record = dict(returncode=code, elapsed_s=time.time()-started)
    save(cwd/(label+'.process.json'), record)
    return record


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    source = SOURCE.read_text()
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-nostdlib', '-static', '-ffreestanding',
             '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
             '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wall', '-Wextra', '-Werror']
    pins = {}
    programs = {}
    for c in CASES:
        case = out/c['name']; case.mkdir()
        original = case/'original'; original.mkdir()
        arch = CAMP/c['arch']
        old = CAMP/f"rvv_additions{c['release']}/binaries"/c['name']
        assert sha(old) == c['sha256']
        for path, name in [(SOURCE, 'parent.c'), (arch/(c['name']+'.S'), 'scenario.S'),
                           (arch/'e32/fixtures.h', 'fixtures.h'), (arch/'e32/operations.h', 'operations.h')]:
            pins[str(path)] = sha(path)
            shutil.copyfile(path, original/name)
        defines = [f'-D{x}' for x in ['SEW=32', 'UNMASKED_COMPARISONS=1', 'RESTART_COMPARISONS=0',
                   f"UNBOXED_COMPARISONS={c['unboxed']}", f"DESTINATION_KIND={c['destination']}"]]
        result = command([OLD_CC, *flags, '-Wl,-s', *defines, '-I'+str(original), original/'parent.c',
                          original/'scenario.S', '-o', case/'original_rebuilt.elf'], case, 'original_rebuild')
        assert result['returncode'] == 0
        # Some older parents precede two later unboxed additions to the C oracle.
        if sha(case/'original_rebuilt.elf') != c['sha256']:
            historical = BASE.parent/'fp_comparison_original/provenance01/fp_compare_oracle_3652.c'
            shutil.copyfile(historical, original/'historical.c')
            pins[str(historical)] = sha(historical)
            result = command([OLD_CC, *flags, '-Wl,-s', *defines, '-I'+str(original), original/'historical.c',
                              original/'scenario.S', '-o', case/'historical_rebuilt.elf'], case, 'historical_rebuild')
            assert result['returncode'] == 0 and sha(case/'historical_rebuilt.elf') == c['sha256'], c['name']
            parent = historical.read_text()
        else:
            parent = source
        assert c['call'] == c['seed']*560+c['op']*56+c['length']*8+c['mode']*2+c['sticky']+1
        oracle = parent[parent.index('        if((uint32_t)status)'):parent.index('        ++cases;')]
        for mode in ('single', 'prefix'):
            run = case/mode; run.mkdir()
            adapted = parent
            if mode == 'single':
                point = '        unsigned prior=errors,vl=lengths[l],flags=sticky,start=0;'
                gate = (f"        if(seed!={c['seed']} || op!={c['op']} || l!={c['length']} || "
                        f"mode!={c['mode']} || sticky!={c['sticky']})continue;\n")
                assert adapted.count(point) == 1
                adapted = adapted.replace(point, gate+point)
                count = 1
            else:
                point = '        ++cases;\n    }\n'
                assert adapted.count(point) == 1
                adapted = adapted.replace(point, f"        ++cases;\n        if(cases=={c['call']})goto prefix_done;\n    }}\nprefix_done:\n")
                count = c['call']
            name = c['name']+'_'+mode
            adapted = helper.adapt(adapted, name)
            assert oracle in adapted
            (run/'case.c').write_text(adapted)
            (run/'wrapper.diff').write_text(''.join(difflib.unified_diff(parent.splitlines(True), adapted.splitlines(True))))
            for n in ('startup.S', 'runtime.c', 'replay.ld'):
                shutil.copyfile(RUNTIME/n, run/n)
                pins[str(RUNTIME/n)] = sha(RUNTIME/n)
            (run/'main.c').write_text('extern void replay_text(const char*);\nextern int '+name+'_main(void);\n'
                'int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));'
                'if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}\n'
                'replay_text("BOARD_CASE_BEGIN '+name+'\\n");\n'
                'if('+name+'_main()){return 1;}\nreplay_text("BOARD_REPLAY_PASS\\n");return 0;}\n')
            for backend in ('soc', 'spike'):
                extra = ['-DSPIKE_REFERENCE=1'] if backend == 'spike' else []
                result = command([helper.CC, *flags, '-mcmodel=medany', '-ffunction-sections', '-fdata-sections',
                    '-Wl,--gc-sections', '-T', run/'replay.ld', *defines, *extra, '-I'+str(original),
                    run/'case.c', original/'scenario.S', run/'main.c', run/'startup.S', run/'runtime.c',
                    '-lgcc', '-o', run/(backend+'.elf')], run, backend+'_compile')
                assert result['returncode'] == 0
            nm = subprocess.check_output([str(helper.CC.with_name('riscv64-unknown-elf-nm')), '-n', run/'spike.elf'],text=True)
            symbols = {row.split()[2]: row.split()[0] for row in nm.splitlines() if len(row.split())==3}
            (run/'spike.cmd').write_text('until pc 0 '+symbols['replay_exit']+'\nreg 0 a0\nstr '+symbols['replay_log']+'\nrs\n')
            r = command([helper.SPIKE, '-d', '--debug-cmd='+str(run/'spike.cmd'),
                         '--isa=rv64gcv_zfh_zvfh_zvl1024b', '-m2', run/'spike.elf'], run, 'spike', timeout=180)
            markers = [f'RVV_FP_COMPARE_PASS sew=32 cases={count} errors=0', 'BOARD_REPLAY_PASS']
            log = (run/'spike.log').read_text()
            assert r['returncode']==0 and all(m in log for m in markers) and 'RVV_FP_COMPARE_FAIL' not in log
            programs[name] = dict(directory=str(run), count=count, mode=mode, source=c,
                                  soc_sha256=sha(run/'soc.elf'), pass_markers=markers)
    save(out/'prepared.json', dict(programs=programs, pins=pins,
         files={str(p):sha(p) for p in out.rglob('*') if p.is_file()},
         scope='Byte-identical original Linux rebuild; unchanged helper and oracle; bare-metal runtime adaptation. Not original Linux ELF execution.'))
    print('PREPARED_SPIKE_4_PASS_NOT_DUT', flush=True)


def replay(out, prepared, long_prefix):
    out.mkdir(parents=True, exist_ok=False)
    plan = json.loads((prepared/'prepared.json').read_text())
    for group in ('pins', 'files'):
        for path, digest in plan[group].items(): assert sha(path)==digest, path
    ledger = json.loads((IMAGE/'image.json').read_text())
    snap = Path(ledger['snapshot'])
    assert sha(snap/'snapshot.json') == ledger['snapshot_sha256']
    frozen = json.loads((snap/'snapshot.json').read_text())
    for path, digest in frozen['live_source_sha256'].items():
        p = Path(path)
        if p.is_relative_to(ROOT/'hardware/src') or p.is_relative_to(ROOT/'hardware/deps'):
            assert sha(p)==digest, 'RTL drift: '+path
    for path, digest in ledger['files'].items(): assert sha(path)==digest, path
    spec = importlib.util.spec_from_file_location('board_runtime', RUNTIME/'run.py')
    runtime = importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
    save(out/'identity.json',dict(image=ledger, prepared=str(prepared), prepared_sha256=sha(prepared/'prepared.json')))

    def execute(item):
        name, entry = item
        dest = out/name; dest.mkdir()
        elf = Path(entry['directory'])/'soc.elf'
        assert sha(elf)==entry['soc_sha256']
        timeout = 10800 if entry['count']>1000 else 1800
        r = command([ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
                     '+PRELOAD='+str(elf), '+TESTCASE='+name, '+NO_FSDB'], dest, 'vcs',
                    timeout=timeout, env=runtime.environment())
        log = (dest/'vcs.log').read_text(errors='replace')
        bad = re.findall(r'RVV_FP_COMPARE_(?:FAIL|DETAIL|CAPACITY_FAIL)[^\r\n]*|BOARD_REPLAY_(?:TRAP|SERVICE_FAIL|VLEN_FAIL)[^\r\n]*', log)
        r.update(name=name, status='PASS' if r['returncode']==0 and not bad and
                 all(m in log for m in entry['pass_markers']) and 'Core Test *** SUCCESS ***' in log else 'NOT_PASS',
                 diagnostics=bad, original_helper_calls=entry['count'])
        save(dest/'result.json', r)
        print(json.dumps(r), flush=True)
        return r

    singles = [(n,e) for n,e in plan['programs'].items() if e['mode']=='single']
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(execute, singles))
    if all(r['status']=='PASS' for r in results):
        prefixes = [(n,e) for n,e in plan['programs'].items() if e['mode']=='prefix' and (long_prefix or e['count']<1000)]
        with ThreadPoolExecutor(max_workers=2) as pool: results += list(pool.map(execute, prefixes))
    save(out/'results.json', dict(results=results, long_prefix=long_prefix,
         scope='Current SoC/VCS; not FPGA repair acceptance or full17920 parent closure.'))
    return 0 if all(r['status']=='PASS' for r in results) else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['prepare', 'replay'])
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--prepared', type=Path)
    p.add_argument('--long-prefix', action='store_true')
    a = p.parse_args(); out = a.out.resolve()
    assert out.is_relative_to(HERE) and not out.exists()
    if a.command=='prepare': prepare(out)
    else:
        assert a.prepared
        raise SystemExit(replay(out, a.prepared.resolve(), a.long_prefix))
