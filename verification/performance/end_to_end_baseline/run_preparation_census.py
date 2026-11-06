#!/usr/bin/env python3
"""Reuse audited model libraries; enable existing preparation traces only."""
import argparse
import json
from pathlib import Path
import subprocess

from audit import digest, require, verify_pins
from preparation_census import check

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')


def traced_source(source):
    for key in ('GGML_RISCV_QBS_TRACE_M4_PREPARE', 'GGML_RISCV_QBS_TRACE_LIFETIME'):
        old = 'env("'+key+'", "0")'
        require(source.count(old) == 1, 'Trace fixture anchor: '+key)
        source = source.replace(old, 'env("'+key+'", "1")', 1)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.is_relative_to(VERIFY/'verification/out'), 'Verification output required')
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREPARING', performance_measured=False, library_objects_rebuilt=0)
    pins = {}
    commands = []

    def save():
        (out/'status.json').write_text(json.dumps(state, indent=2)+'\n')

    def pin(path):
        path = str(Path(path).resolve(strict=True))
        sha = digest(path)
        require(path not in pins or pins[path] == sha, 'Pin identity changed')
        pins[path] = sha

    def run(argv, label, bound=180):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv, timeout=bound))
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        state.update(state=label.upper()); save()
        with (out/(label+'.log')).open('xb') as log:
            child = subprocess.Popen(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT)
            state['child_pid'] = child.pid; save()
            try:
                code = child.wait(timeout=bound)
            except BaseException:
                child.kill(); child.wait(); raise
            finally:
                state['child_pid'] = None; save()
        require(code == 0, label+' failed')
        verify_pins(pins)

    save()
    try:
        model = args.model.resolve(strict=True)
        accepted = json.loads((args.audit/'result.json').read_text())
        require(accepted['state'] == 'PAIRED_QWEN3_OUTPUT_MODEL_REAUDITED' and
                Path(accepted['run']) == model, 'Wrong accepted model')
        require(digest(model/'result.json') == accepted['worker_result_sha256'] and
                digest(model/'source-pins.json') == accepted['source_pins_sha256'] and
                digest(model/'qemu.log') == accepted['log_sha256'], 'Accepted model drift')
        pins.update(json.loads((model/'source-pins.json').read_text()))
        verify_pins(pins)
        for path in (Path(__file__), HERE/'preparation_census.py', HERE/'audit.py',
                     HERE/'check_output_model.py', args.audit/'result.json', model/'commands.json'):
            pin(path)
        original = (model/'model.cpp').read_text()
        source = traced_source(original)
        (out/'model.cpp').write_text(source); pin(out/'model.cpp')
        recipe = json.loads((model/'commands.json').read_text())
        def command(label):
            matches = [r['argv'] for r in recipe if r['label'] == label]
            require(len(matches) == 1, 'Missing/duplicate recipe')
            return list(matches[0])
        cc = command('compile')
        cc[cc.index('-c')+1] = str(out/'model.cpp'); cc[cc.index('-o')+1] = str(out/'model.o')
        # Record the observed translation unit's headers without rebuilding libraries.
        dep = cc[:cc.index('-o')] + ['-M', '-MT', 'model']
        import shlex
        dependencies = subprocess.check_output(dep, text=True, timeout=120)
        for path in shlex.split(dependencies.replace('\\\n', ' ').split(':', 1)[1]): pin(path)
        run(cc, 'compile')
        link = command('link')
        link = [str(out/'model.o') if v == str(model/'model.o') else v for v in link]
        link[link.index('-o')+1] = str(out/'test')
        run(link, 'link'); pin(out/'test')
        listing = (model/'initramfs.list').read_text()
        require(listing.count(str(model/'test')) == 1, 'Init payload anchor')
        listing = listing.replace(str(model/'test'), str(out/'test'))
        (out/'initramfs.list').write_text(listing); pin(out/'initramfs.list')
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        pin(cpio)
        with (out/'initramfs.cpio').open('xb') as stream:
            subprocess.run([cpio, out/'initramfs.list'], stdout=stream, check=True, timeout=60)
        pin(out/'initramfs.cpio')
        qemu = command('qemu')
        require('xaraqbs=true' in qemu[qemu.index('-cpu')+1], 'Native QBS emulator required')
        qemu[qemu.index('-initrd')+1] = str(out/'initramfs.cpio')
        (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        run(qemu, 'qemu', 7200)
        measured = check((out/'qemu.log').read_text())
        verify_pins(pins)
        state.update(state='ACTUAL_QWEN3_PREPARATION_ROUTES_PASS', measured=measured,
                     accepted_model=str(model), only_existing_trace_flags_changed=True,
                     elf_sha256=digest(out/'test'), log_sha256=digest(out/'qemu.log'),
                     source_pins_sha256=digest(out/'source-pins.json'))
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc)); raise
    finally:
        save(); (out/'result.json').write_text(json.dumps(state, indent=2)+'\n')


if __name__ == '__main__': main()
