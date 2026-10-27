#!/usr/bin/env python3
"""Private old/new context-policy model pair, all other runtime options fixed."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from collections import Counter

from compile_float_gap_candidate import candidate
from compile_context_attribution import DATABASE, ROOT, SOURCE
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'verification/qbs'))
sys.path.insert(0, str(ROOT / 'verification/qbs/combined_zvfh_m4/model'))
from native_audit import native_accounting
from analyze_prepare_reuse import analyze
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command


def check(text):
    lines = text.splitlines()
    expected = [f'Q8K_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
                for k in range(2) for s in range(3)]
    if [s for s in lines if s.startswith('Q8K_MODEL_COMPARE ')] != expected:
        raise ValueError('Missing/incorrect paired logits, tokens or CSR')
    for marker in ('Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured', 'GUEST_TEST_EXIT=0'):
        if lines.count(marker) != 1:
            raise ValueError('Missing complete model success')
    if 'Q8K_MODEL_FAIL' in text or 'Kernel panic' in text:
        raise ValueError('Guest failure')
    activity = analyze(text)
    old, new = [activity[str(m)]['totals'] for m in (0, 1)]
    saved = old['quantizations'] - new['quantizations']
    if saved <= 0 or new['cross_op_quantization_skips'] - old['cross_op_quantization_skips'] != saved:
        raise ValueError('No balanced quantization reduction')
    # Work counts must match, but context events are deliberately different.
    # Check real lifecycle totals before neutralizing only those three fields
    # for the existing strict native-workload accounting checker.
    mode = None
    contexts = {0: Counter(), 1: Counter()}
    normalized = []
    keys = ('context_fill', 'context_release', 'context_reuse')
    for line in lines:
        if line.startswith('Q8K_MODEL_BEGIN '):
            mode = int(line.split('enabled=')[1])
        if line.startswith('GGML_RISCV_QBS_EXEC '):
            if mode not in contexts:
                raise ValueError('Unscoped native summary')
            pairs = dict(word.split('=', 1) for word in line.split()[1:])
            for key in keys:
                value = int(pairs[key])
                if value < 0:
                    raise ValueError('Negative context count')
                contexts[mode][key] += value
                pairs[key] = '0'
            line = 'GGML_RISCV_QBS_EXEC ' + ' '.join(f'{k}={v}' for k,v in pairs.items())
        normalized.append(line)
    if any(c['context_fill'] <= 0 or c['context_fill'] != c['context_release'] for c in contexts.values()):
        raise ValueError('Context lifetime imbalance')
    work = native_accounting('\n'.join(normalized))
    for row in work.values():
        for key in keys:
            del row[key]
    return dict(state='PASS', comparisons=6, logits_compared=911616,
                quantizations_saved=saved, activity=activity, context_counts=contexts,
                native_work=work, performance_measured=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Use independent verification/out')
    base = ROOT / 'verification/out/q8k-signed-max-model-20261026-01'
    archived = json.loads((base / 'manifest.json').read_text())
    link = json.loads((base / 'link.command.json').read_text())
    testcmd = json.loads((base / 'compile.command.json').read_text())
    qemu = json.loads((base / 'qemu.command.json').read_text())
    artifacts = [Path(x) for x in link if x.endswith(('.a', '.o'))]
    artifacts += [base / 'init', base / 'test.cpp', Path(qemu[0]),
                  Path(qemu[qemu.index('-bios')+1]), Path(qemu[qemu.index('-kernel')+1]),
                  Path(qemu[qemu.index('-drive')+1].split(',')[0].removeprefix('file='))]
    for path in artifacts:
        if archived.get(str(path)) != digest(path):
            raise ValueError('Sealed artifact drift: '+str(path))
    pins = hashes(artifacts + [SOURCE, DATABASE, Path(__file__), HERE/'compile_float_gap_candidate.py'])
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None)
    def save(): atomic_json(out/'status.json', state)
    def started(pid):
        state['child_pid'] = pid
        save()
    def run(argv, label, bound):
        state.update(state=label.upper(), child_pid=None)
        save()
        atomic_json(out/(label+'.command.json'), argv)
        if run_command(argv, out/(label+'.log'), bound, os.environ.copy(), started):
            raise RuntimeError(label+' failed')
        state['child_pid'] = None
    try:
        text = candidate(SOURCE.read_text())
        marker = 'profile_for_type(weights->type).weight == QBS_WEIGHT_PROFILE_INVALID)'
        if text.count(marker) != 1:
            raise ValueError('Candidate guard drift')
        text = text.replace(marker, 'profile_for_type(weights->type).weight == QBS_WEIGHT_PROFILE_INVALID &&\n'
                            '                    env_true("GGML_QBS_FLOAT_GAP_TEST"))')
        (out/'qbs.cpp').write_text(text)
        records = [r for r in json.loads(DATABASE.read_text()) if Path(r['file']).resolve() == SOURCE]
        if len(records) != 1: raise ValueError('Production compile record')
        cmd = shlex.split(records[0]['command'])
        cmd[cmd.index('-c')+1] = str(out/'qbs.cpp')
        cmd[cmd.index('-o')+1] = str(out/'qbs.o')
        cmd += ['-iquote', str(SOURCE.parent)]
        run(cmd, 'qbs-compile', 180)
        text = (base/'test.cpp').read_text()
        old = 'env("GGML_RISCV_QBS_M4_PREPARE", mode ? "1" : "0");'
        if text.count(old) != 1: raise ValueError('Model harness drift')
        text = text.replace(old, 'env("GGML_RISCV_QBS_M4_PREPARE", "1");\n'
                            '    env("GGML_QBS_FLOAT_GAP_TEST", mode ? "1" : "0");')
        (out/'test.cpp').write_text(text)
        testcmd[testcmd.index('-c')+1] = str(out/'test.cpp')
        testcmd[testcmd.index('-o')+1] = str(out/'test.o')
        run(testcmd, 'test-compile', 180)
        link[2] = str(out/'test.o')
        link.insert(3, str(out/'qbs.o'))
        link[link.index('-o')+1] = str(out/'test')
        link = ['-Wl,-Map='+str(out/'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
        run(link, 'link', 180)
        listing = out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'
                           'dir /model 755 0 0\ndir /tmp 1777 0 0\n'
                           f'file /init {base/"init"} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out/'initramfs.cpio').open('xb') as stream:
            subprocess.run([str(cpio),str(listing)], stdout=stream, check=True, timeout=60)
        pins.update(hashes([cpio]+[out/n for n in ('qbs.cpp','qbs.o','test.cpp','test.o',
                              'test','link.map','initramfs.list','initramfs.cpio')]))
        atomic_json(out/'manifest.json', pins)
        qemu[qemu.index('-initrd')+1] = str(out/'initramfs.cpio')
        run(qemu, 'qemu', 7200)
        result = check((out/'qemu.log').read_text())
        if hashes(map(Path,pins)) != pins: raise ValueError('Execution drift')
        result.update(log_sha256=digest(out/'qemu.log'), runtime_modified=False,
                      scope='Old/new context policy only; M4 preparation fixed ON')
        atomic_json(out/'result.json', result)
        state['state']='PASS'
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        atomic_json(out/'result.json', state)
        raise
    finally:
        state['child_pid']=None
        save()


if __name__ == '__main__': main()
