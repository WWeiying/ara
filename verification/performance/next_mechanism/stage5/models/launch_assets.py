"""Relink only diagnostic environment settings; preserve frozen preparations."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve()
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
CHECK = HERE.with_name('prefill_check.py')
CHECK_SHA = '2d00cd0f6fb7218889fa88e3d8f9ce3c5285867441cf645d3bda237731495267'
WORKER_SHA = '136c906eb33d1edf94b2bae76bed6f9c6897c40ac4e8cca4a2881282431c9859'
GUEST_SECONDS, SERVICE_SECONDS = 10000, 12600
QUIET = ('GGML_RISCV_QBS_TRACE_CALLS', 'GGML_RISCV_QBS_TRACE_LIFETIME',
         'GGML_RISCV_QBS_TRACE_M4_PREPARE')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)


def worker(out):
    path = out/'inputs/run.py'
    require(out.parent == OUT and sha(path) == WORKER_SHA, 'Frozen final preparation required')
    spec = importlib.util.spec_from_file_location('unchanged_model_worker', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def command(out, assets, base, symbols):
    original = base.recipes(out, read(out/'contract.json'), symbols)
    original[original.index('-initrd') + 1] = str(assets/'initramfs.cpio')
    original[original.index('-dfilter') + 1] = ','.join(hex(symbols[n][0]) + '+1' for n in
        ('qbs_native_execute_command', 'akv_experimental_resident_pv_prepare'))
    return original


def build(out, assets):
    base = worker(out)
    require(assets.parent == OUT and not assets.exists(), 'Fresh owned launch assets required')
    require(read(out/'prepare.json')['state'] == 'PREPARED_NOT_EXECUTED' and
            not (out/'attempt.json').exists(), 'Do not alter a launched consumer')
    require(sha(CHECK) == CHECK_SHA, 'Reviewed checker correction required')
    original_pins = read(out/'source-pins.json')
    require(sha(out/'source-pins.json') == read(out/'prepare.json')['source_pins_sha256'], 'Preparation drift')
    assets.mkdir(); (assets/'inputs').mkdir()
    source = (out/'inputs/model_pair.cpp').read_text()
    anchor = '    env(STAGE5_REVIEWED_RESIDENT_ENV, mode ? "1" : "0");'
    require(source.count(anchor) == 1, 'Frozen frontend environment anchor drift')
    source = source.replace(anchor, ''.join('    env("' + name + '", "0");\n' for name in QUIET) + anchor)
    (assets/'inputs/model_pair.cpp').write_text(source)
    jobs = {row['label']: row for row in read(out/'commands.json')}
    rows = []
    def run(label, argv):
        argv = list(map(str, argv))
        with (assets/(label + '.log')).open('x') as log:
            done = subprocess.run(argv, cwd=assets, stdout=log, stderr=subprocess.STDOUT,
                env=dict(PATH=str(base.CC.parent) + ':/usr/bin:/bin', HOME=str(assets),
                         LANG='C', LC_ALL='C'), timeout=120)
        rows.append(dict(label=label, argv=argv, returncode=done.returncode))
        require(done.returncode == 0, 'Launch asset build failed: ' + label)
        return (assets/(label + '.log')).read_text()
    def rebase(argv):
        changes = {str(out/'inputs/model_pair.cpp'): str(assets/'inputs/model_pair.cpp'),
                   str(out/'frontend.o'): str(assets/'frontend.o'),
                   str(out/'frontend.d'): str(assets/'frontend.d'),
                   str(out/'test'): str(assets/'test'),
                   '-Wl,-Map=' + str(out/'link.map'): '-Wl,-Map=' + str(assets/'link.map')}
        return [changes.get(str(a), str(a)) for a in argv]
    run('frontend', rebase(jobs['frontend']['argv']))
    run('link', rebase(jobs['link']['argv']))
    names = run('symbols', [base.CC.with_name('riscv64-linux-nm'), '-S', assets/'test'])
    symbols = base.symbols(names); save(assets/'symbols.json', symbols)
    disassembly = '\n'.join(run('disassemble-' + name,
        [base.CC.with_name('riscv64-linux-objdump'), '-d', '--disassemble=' + name, assets/'test'])
        for name in base.SYMBOLS)
    pcs = {'qk': [], 'pv': []}
    for match in re.finditer(r'(?m)^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s', disassembly):
        pc, insn = int(match[1], 16), int(match[2], 16)
        for kind, f7 in (('qk', 3), ('pv', 2)):
            if insn & 127 == 0x5b and (insn >> 12) & 7 == 7 and insn >> 25 == f7:
                pcs[kind].append(pc)
    require(all(pcs.values()), 'Native resident instructions missing')
    save(assets/'pcs.json', pcs)
    listing = (out/'initramfs.list').read_text().replace(str(out/'test'), str(assets/'test'))
    (assets/'initramfs.list').write_text(listing)
    with (assets/'initramfs.cpio').open('xb') as stream:
        subprocess.run([base.CPIO, assets/'initramfs.list'], stdout=stream, check=True, timeout=60)
    save(assets/'qemu-command.json', command(out, assets, base, symbols))
    save(assets/'commands.json', rows)
    for name in shlex.split((assets/'frontend.d').read_text().replace('\\\n', '').split(':', 1)[1]):
        path = Path(name).resolve()
        require(path.is_relative_to(assets) or original_pins.get(str(path)) == sha(path),
                'Unpinned frontend dependency: ' + str(path))
    manifest = dict(prepared=str(out), source_sha256=sha(HERE), checker_sha256=CHECK_SHA,
        original_pins_sha256=sha(out/'source-pins.json'), original_prepare_sha256=sha(out/'prepare.json'),
        original_elf_sha256=sha(out/'test'), executed_elf_sha256=sha(assets/'test'),
        env_overrides={key: '0' for key in QUIET}, trace_summary_enabled=True,
        native_entry_trace_preserved=True, dfilter_policy='two-function-entry-PC-plus-one',
        guest_seconds=GUEST_SECONDS, service_seconds=SERVICE_SECONDS, automatic_retry=False,
        same_elf_within_pair=True, model_inputs_changed=False, libraries_rebuilt=False,
        qemu_timing_comparison_permitted=False,
        artifacts={str(p): sha(p) for p in assets.rglob('*') if p.is_file()})
    save(assets/'manifest.json', manifest)
    print(json.dumps(dict(state='LAUNCH_ASSETS_BUILT_NOT_EXECUTED', output=str(assets),
                          manifest_sha256=sha(assets/'manifest.json')), sort_keys=True), flush=True)


def checked(out, assets, review, source_review):
    require(sha(HERE) == source_review and sha(CHECK) == CHECK_SHA and
            sha(assets/'manifest.json') == review, 'Unreviewed launch assets')
    manifest = read(assets/'manifest.json')
    require(manifest['prepared'] == str(out) and manifest['source_sha256'] == source_review and
            manifest['guest_seconds'] == GUEST_SECONDS and manifest['service_seconds'] == SERVICE_SECONDS,
            'Launch asset contract drift')
    base = worker(out)
    require(manifest['original_pins_sha256'] == sha(out/'source-pins.json') and
            manifest['original_prepare_sha256'] == sha(out/'prepare.json'), 'Original preparation drift')
    base.verify(manifest['artifacts'])
    require(read(assets/'qemu-command.json') == command(out, assets, base, read(assets/'symbols.json')),
            'Launch command differs from explicit observability policy')
    pins = dict(manifest['artifacts'], **{str(HERE): source_review, str(CHECK): CHECK_SHA,
                str(assets/'manifest.json'): review})
    return base, pins


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('action', choices=('build', 'service-command', 'run'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--assets', type=Path, required=True)
    for name in ('assets-sha256', 'source-sha256', 'review-sha256', 'review-prepare-sha256'):
        p.add_argument('--' + name)
    a = p.parse_args(); out, assets = a.output.resolve(), a.assets.resolve()
    if a.action == 'build':
        build(out, assets); return 0
    base, pins = checked(out, assets, a.assets_sha256, a.source_sha256)
    if a.action == 'service-command':
        argv = base.service_command(out, a.review_sha256, a.review_prepare_sha256)
        argv[argv.index('--property=RuntimeMaxSec=10800')] = '--property=RuntimeMaxSec=' + str(SERVICE_SECONDS)
        argv[argv.index(str(out/'inputs/run.py'))] = str(HERE)
        argv += ['--assets', str(assets), '--assets-sha256', a.assets_sha256,
                 '--source-sha256', a.source_sha256]
        print(json.dumps(argv)); return 0
    receipt = out/'launch-assets-binding.json'
    require(not receipt.exists(), 'One attempt only')
    save(receipt, dict(assets=str(assets), pins=pins, original_preparation_unchanged=True))
    pins[str(receipt)] = sha(receipt)
    old_read, old_load, old_recipes = base.read, base.load, base.recipes
    mapped = {out/name: assets/name for name in ('qemu-command.json', 'symbols.json', 'pcs.json')}
    def read_bound(path):
        value = old_read(mapped.get(Path(path), path))
        if Path(path) == out/'source-pins.json':
            base.merge(value, pins)
        return value
    def load_bound(path, name):
        if Path(path) != out/'inputs/check.py':
            return old_load(path, name)
        module = old_load(CHECK, name)
        # Relocated symbols/PCs describe the relinked diagnostic-only frontend.
        # All other checker reads still use the original full log and spec.
        class InputView:
            def __truediv__(self, name):
                return mapped.get(out/name, out/name)
        module.Path = lambda value: InputView() if Path(value) == out else Path(value)
        return module
    def recipes_bound(output, contract, symbols):
        argv = old_recipes(output, contract, symbols)
        argv[argv.index('-initrd') + 1] = str(assets/'initramfs.cpio')
        argv[argv.index('-dfilter') + 1] = ','.join(hex(symbols[n][0]) + '+1' for n in
            ('qbs_native_execute_command', 'akv_experimental_resident_pv_prepare'))
        return argv
    old_subprocess = base.subprocess
    class Processes:
        def __getattr__(self, name): return getattr(old_subprocess, name)
        def Popen(self, *args, **kwargs):
            child = old_subprocess.Popen(*args, **kwargs); wait = child.wait
            child.wait = lambda timeout=None: wait(timeout=GUEST_SECONDS if timeout == 5400 else timeout)
            return child
    base.read, base.load, base.recipes, base.subprocess = read_bound, load_bound, recipes_bound, Processes()
    ok = base.execute(a)
    base.verify(pins)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
