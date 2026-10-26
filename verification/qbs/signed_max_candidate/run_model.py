#!/usr/bin/env python3
"""Private real-model candidate gate, with cross-operation context enabled."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/qbs'))
sys.path.insert(0, str(HERE.parent/'combined_zvfh_m4/model'))
from native_audit import audit
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command
from run_ggml_segmented import verify_native_build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build, out = args.build.resolve(strict=True), args.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Use independent verification/out')
    b = json.loads((build/'build.json').read_text())
    pins = json.loads((build/'manifest.json').read_text())
    if b['state'] != 'READY' or b['signed_max_candidate'] is not True or \
            digest(build/'manifest.json') != b['manifest_sha256'] or hashes(map(Path, pins)) != pins:
        raise ValueError('Candidate graph/library build drift')
    obj = Path(b['quantizer_object'])
    base = ROOT/'verification/out/q8k-model-off-on-20261026-01'
    oldpins = json.loads((base/'source-pins.json').read_text())
    libs = [base/('libraries/llama/'+p) for p in ('src/libllama.a', 'ggml/src/libggml.a',
            'ggml/src/libggml-cpu.a', 'ggml/src/libggml-base.a')]
    for lib in libs:
        if oldpins.get(str(lib)) != digest(lib):
            raise ValueError('Accepted model archive drift')
    # libllama is unchanged; the GGML archive sources were checked by the graph builder.
    llama = Path('/home/wangwy/llama/llama.cpp')
    model_sources = [p for p in (llama/'src').rglob('*') if p.is_file() and p.suffix in ('.cpp','.c','.h','.hpp')]
    for path in model_sources:
        if oldpins.get(str(path)) != digest(path):
            raise ValueError('Accepted model source drift: '+str(path))
    platform = Path('/home/wangwy/llama/platforms/cva6-qemu')
    cxx, cc = [platform/('tools/bin/riscv64-linux-'+name) for name in ('g++','gcc')]
    cpio = platform/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    qemu = ROOT/'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
    disk = platform/'images/qwen2.5-q4km-capture.ext4'
    source = HERE.parent/'combined_zvfh_m4/model/test.cpp'
    init = ROOT/'verification/akv/quantized_kv/model_live/init.c'
    more = [*libs, *model_sources, llama/'include/llama.h', base/'source-pins.json', source, init,
            HERE/'model_context.patch', Path(__file__), build/'build.json', build/'manifest.json',
            cxx.resolve(), cc.resolve(), cpio, qemu, disk,
            platform/'images/Image', platform/'images/fw_dynamic.bin', *map(Path, verify_native_build(qemu))]
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT):
            more.append(Path(path).resolve())
    pins.update(hashes(more))
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREPARING', pid=os.getpid(), child_pid=None)
    def save(): atomic_json(out/'status.json', state)
    def started(pid):
        state['child_pid'] = pid
        save()
    def interrupted(sig, _): raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupted)
    def run(command, label, timeout):
        command = list(map(str, command))
        atomic_json(out/(label+'.command.json'), command)
        state.update(state=label.upper(), child_pid=None)
        save()
        if run_command(command, out/(label+'.log'), timeout, os.environ.copy(), started):
            raise RuntimeError(label+' failed or timed out')
        state['child_pid'] = None
    save()
    try:
        shutil.copyfile(source, out/'test.cpp')
        subprocess.run(['git','apply',str(HERE/'model_context.patch')], cwd=out,
                       env=dict(os.environ,GIT_CEILING_DIRECTORIES=str(out.parent)), check=True)
        run([cxx,'-std=c++17','-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-O3','-UNDEBUG',
             '-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror',
             '-I'+str(llama/'include'),'-I'+str(llama/'ggml/include'),'-c',out/'test.cpp','-o',out/'test.o'], 'compile',180)
        run([cxx,'-static',out/'test.o',obj,*libs,'-ldl','-lm','-pthread',
             '-Wl,-Map='+str(out/'link.map'),'-o',out/'test'], 'link',180)
        run([cc,'-march=rv64gc','-mabi=lp64d','-O2','-static',init,'-o',out/'init'], 'init',120)
        listing = out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /model 755 0 0\ndir /tmp 1777 0 0\n'+
                           f'file /init {out/"init"} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as stream:
            subprocess.run([cpio,listing],stdout=stream,check=True,timeout=60)
        pins.update(hashes([out/name for name in ('test.cpp','test.o','test','init','link.map','initramfs.list','initramfs.cpio')]))
        atomic_json(out/'manifest.json',pins)
        if hashes(map(Path,pins)) != pins: raise ValueError('Build drift')
        run([qemu,'-M','virt','-cpu','rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
             '-smp','1','-m','4G','-display','none','-monitor','none','-serial','stdio',
             '-bios',platform/'images/fw_dynamic.bin','-kernel',platform/'images/Image',
             '-initrd',out/'initramfs.cpio','-drive',f'file={disk},if=virtio,format=raw,readonly=on',
             '-append','console=ttyS0 rdinit=/init'], 'qemu',7200)
        text = (out/'qemu.log').read_text()
        result = audit(text)
        actions = re.findall(r'GGML_RISCV_QBS_CROSS_OP[^\n]+action=(reuse_keep|reuse_release)[^\n]+quantization_skipped=1',text)
        if not actions: raise ValueError('Default cross-op reuse never exercised')
        if hashes(map(Path,pins)) != pins: raise ValueError('Execution drift')
        result.update(cross_op_reuse_events=len(actions), log_sha256=digest(out/'qemu.log'),
                      manifest_sha256=digest(out/'manifest.json'), signed_max_candidate=True,
                      production_modified=False, cross_op_context=True)
        atomic_json(out/'result.json',result)
        state['state']='PASS'
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc))
        atomic_json(out/'result.json',dict(state='FAIL',error=repr(exc)))
        raise
    finally:
        state['child_pid']=None
        save()


if __name__ == '__main__': main()
