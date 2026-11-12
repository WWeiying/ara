#!/usr/bin/env python3
"""Build the current single-C SDK AUTO firmware from frozen captured data."""
import argparse
import io
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile

from panel4_prepare import ROOT, HERE, OUT, REV, GCC, sha, save, require

OLD = OUT/'akv-qk-panel4-abba-build-20261023-02'
OLD_ELF_SHA = 'b22725d72f7e7467c733471381e8da6226c332954883ee0ab7cb89f60d85da6c'


def verify(pins):
    require(bool(pins), 'Empty pins')
    for path, digest in pins.items():
        require(sha(path) == digest, 'Input drift: '+str(path))


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--host', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); out = a.output.absolute(); host = a.host.resolve(strict=True)
    require(out == out.resolve() and out.parent == OUT and re.fullmatch(
        r'enablement_panel4_[A-Za-z0-9_-]+', out.name) and not out.exists(), 'Fresh PANEL4 output required')
    proof = json.loads((host/'result.json').read_text())
    require(proof['state'] == 'PANEL4_HOST_SELECTOR_PASS_NOT_NATIVE' and proof['post_pins_match']
        and proof['source_pins_sha256'] == sha(host/'source-pins.json'), 'Host selector gate')
    pins = json.loads((host/'source-pins.json').read_text())
    verify(pins); verify(proof['artifacts'])
    out.mkdir(); source = out/'source'; source.mkdir(); inputs = out/'inputs'; inputs.mkdir()
    commands = []

    def pin(path): pins[str(path)] = sha(path)

    def run(label, argv):
        argv = list(map(str, argv)); commands.append(dict(label=label, argv=argv))
        with (out/(label+'.log')).open('xb') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        return (out/(label+'.log')).read_text()

    pin(host/'source-pins.json'); pin(host/'result.json'); pin(GCC.resolve())
    for name in ('panel4_firmware.py', 'panel4_prepare.py', 'panel4_auto_soc.c'):
        src = HERE/name; dst = inputs/name
        shutil.copyfile(src, dst); pin(src); pin(dst)
    paths = ['apps/llama_q4km_operator', 'apps/llama_q4km_micro', 'apps/common']
    archive = subprocess.check_output(['git', '-C', str(ROOT), 'archive', REV, *paths])
    (out/'apps.tar').write_bytes(archive); pin(out/'apps.tar')
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        require(all((m.isfile() or m.isdir()) and '..' not in Path(m.name).parts
                    and not Path(m.name).is_absolute() for m in tar.getmembers()), 'Unsafe apps archive')
        tar.extractall(source)
    shutil.copytree(Path(proof['sdk'])/'software', source/'software')
    require(sha(source/'software/akv/src/akv_v2_attention_rvv.S') == proof['assembly_sha256'], 'Assembly drift')
    fw = source/'apps/llama_q4km_operator/panel4_auto_soc.c'
    shutil.copyfile(inputs/'panel4_auto_soc.c', fw)
    old_build = json.loads((OLD/'build.json').read_text())
    require(old_build['elf_sha256'] == OLD_ELF_SHA and sha(old_build['elf']) == OLD_ELF_SHA, 'Old ELF identity')
    old_artifacts = json.loads((OLD/'artifacts.json').read_text())
    require(sha(OLD/'artifacts.json') == old_build['artifacts_sha256'], 'Old artifact receipt drift')
    for name in ('data.S', 'link.ld'):
        src = OLD/name; require(old_artifacts[str(src)] == sha(src), 'Old data/link identity')
        shutil.copyfile(src, out/name); pin(src); pin(out/name)
    manifest = json.loads((OLD/'manifest.json').read_text())
    require(sha(OLD/'manifest.json') == old_build['manifest_sha256'], 'Old manifest identity')
    blobs = re.findall(r'^\.incbin "([^"]+)"$', (out/'data.S').read_text(), re.M)
    require(len(blobs) == 5, 'Captured tensor membership')
    for blob in blobs:
        require(manifest[blob] == sha(blob), 'Captured tensor drift'); pin(Path(blob))
    pin(OLD/'build.json'); pin(OLD/'artifacts.json'); pin(OLD/'manifest.json')
    common = source/'apps/common'; operator = source/'apps/llama_q4km_operator'
    sources = [fw, *(operator/n for n in ('akv_runtime.c', 'akv_prefill_reference.c', 'akv_attention.S', 'akv_v2_attention.S')),
        *(common/n for n in ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')), out/'data.S']
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-O3',
        '-std=gnu11', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize', '-fno-common',
        '-ffunction-sections', '-fdata-sections', '-ffreestanding', '-fno-builtin',
        '-fno-tree-loop-distribute-patterns', '-DNR_LANES=4', '-DVLEN=1024', '-DAKV_REFILL_OVERLAP=0',
        '-Wno-unknown-pragmas', '-I'+str(common), '-I'+str(source/'apps/include'), '-I'+str(source/'software/akv/include')]
    for path in source.rglob('*'):
        if path.is_file(): pin(path)
    for i, src in enumerate(sources):
        dep = out/f'{i}.d'; run(f'deps-{i}', [GCC, *flags, '-M', '-MF', dep, '-MT', 'bench', src])
        for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]): pin(Path(name).resolve(strict=True))
    for name in ('libm.a', 'libgcc.a'):
        pin(Path(subprocess.check_output([GCC, '-print-file-name='+name], text=True).strip()).resolve(strict=True))
    objdump = GCC.with_name('riscv64-unknown-elf-objdump'); pin(objdump)
    save(out/'source-pins.json', pins); verify(pins)
    objects = []
    for i, src in enumerate(sources):
        obj = out/f'{i}.o'; run(f'compile-{i}', [GCC, *flags, '-c', src, '-o', obj]); objects.append(obj)
    elf = out/'panel4_auto.elf'
    run('link', [GCC, *flags, '-static', '-nostdlib', '-nostartfiles', *objects,
        '-Wl,--gc-sections', '-Wl,-Map='+str(out/'link.map'), '-T', out/'link.ld', '-lm', '-lgcc', '-o', elf])
    dis = run('disassembly', [objdump, '-d', elf])
    for symbol in ('akv_attention_execute_v2_native_auto',
        'akv_v2_compute_scores_f16_d128_gqa6_panel4', 'akv_v2_compute_scores_f16_d128_gqa6', 'getenv'):
        require('<'+symbol+'>:' in dis, 'Missing AUTO firmware symbol: '+symbol)
    verify(pins); save(out/'commands.json', commands)
    artifacts = {str(f): sha(f) for f in out.rglob('*') if f.is_file()}
    result = dict(state='PANEL4_AUTO_BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=sha(elf),
        source_pins_sha256=sha(out/'source-pins.json'), post_pins_match=True, artifacts=artifacts,
        native_source_sha256=proof['native_source_sha256'], assembly_sha256=proof['assembly_sha256'],
        sdk_revision=REV, overlay_files=proof['overlay_files'], trials=['off', 'auto', 'auto', 'off', 'badcap'],
        kv=128, outputs=1536, rounding='RNE', native_arithmetic_executed=False, performance_measured=False)
    save(out/'build.json', result)
    print(json.dumps({k:v for k,v in result.items() if k != 'artifacts'}, sort_keys=True))


if __name__ == '__main__': main()
