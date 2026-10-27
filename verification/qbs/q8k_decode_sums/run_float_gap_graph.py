#!/usr/bin/env python3
"""Run private paired GGML graphs with the already validated policy object."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json, hashes
from run_tile_context_engine import run_command


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'): raise ValueError('Independent output required')
    base=ROOT/'verification/out/q8k-float-gap-pair-20261026-01'
    manifest=json.loads((base/'manifest.json').read_text())
    compile_cmd=json.loads((base/'test-compile.command.json').read_text())
    link=json.loads((base/'link.command.json').read_text())
    qemu=json.loads((base/'qemu.command.json').read_text())
    source=HERE/'float_gap_graph.cpp'
    init=ROOT/'verification/out/q8k-signed-max-model-20261026-01/init'
    cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
    inherited=[Path(x) for x in link if x.endswith(('.a','.o')) and x!=str(base/'test.o')]
    inherited += [Path(qemu[0]),Path(qemu[qemu.index('-kernel')+1]),Path(qemu[qemu.index('-bios')+1]),init]
    pins=hashes(inherited)
    if any(manifest.get(p)!=h for p,h in pins.items()): raise ValueError('Inherited input drift')
    pins.update(hashes([source,Path(__file__),cpio]))
    out.mkdir(parents=True,exist_ok=False)
    state=dict(state='BUILDING',pid=os.getpid(),child_pid=None)
    def save(): atomic_json(out/'status.json',state)
    def started(pid): state.update(child_pid=pid);save()
    def run(cmd,label,limit):
        state.update(state=label,child_pid=None);save()
        atomic_json(out/(label+'.command.json'),cmd)
        if run_command(cmd,out/(label+'.log'),limit,os.environ.copy(),started): raise RuntimeError(label+' failed')
    try:
        compile_cmd[compile_cmd.index('-c')+1]=str(source)
        compile_cmd[compile_cmd.index('-o')+1]=str(out/'test.o')
        ggml=Path('/home/wangwy/llama/llama.cpp/ggml/src')
        # GGML internal headers define unused static helpers in this test TU.
        compile_cmd += ['-Wno-unused-function','-I'+str(ggml),'-I'+str(ggml/'ggml-cpu')]
        run(compile_cmd,'compile',180)
        link=[str(out/'test.o') if x==str(base/'test.o') else x for x in link]
        link=[('-Wl,-Map='+str(out/'link.map')) if x.startswith('-Wl,-Map=') else x for x in link]
        link[link.index('-o')+1]=str(out/'test')
        run(link,'link',180)
        listing=out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'
                           'dir /model 755 0 0\ndir /tmp 1777 0 0\n'
                           f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as f:
            subprocess.run([str(cpio),str(listing)],stdout=f,check=True,timeout=60)
        pins.update(hashes([out/n for n in ('test.o','test','initramfs.list','initramfs.cpio')]))
        atomic_json(out/'manifest.json',pins)
        qemu[qemu.index('-initrd')+1]=str(out/'initramfs.cpio')
        # Keep the original read-only drive: the shared init mounts /model.
        drive=Path(qemu[qemu.index('-drive')+1].split(',')[0].removeprefix('file='))
        pins.update(hashes([drive]));atomic_json(out/'manifest.json',pins)
        run(qemu,'qemu',900)
        text=(out/'qemu.log').read_text()
        expected=[f'FLOAT_GAP_GRAPH_PASS mode={m} scenario={s} epoch={e}'
                  for m in range(2) for s in range(3) for e in range(2)]
        if [l for l in text.splitlines() if l.startswith('FLOAT_GAP_GRAPH_PASS ')]!=expected:
            raise ValueError('Missing graph results')
        if text.splitlines().count('FLOAT_GAP_GRAPH_SUITE_PASS graphs=12 paired_bytes=3168 performance=not_measured')!=1:
            raise ValueError('Missing paired comparison')
        if 'FLOAT_GAP_GRAPH_FAIL' in text or 'GUEST_TEST_EXIT=0' not in text: raise ValueError('Guest failure')
        summaries=[dict(w.split('=',1) for w in line.split()[1:])
                   for line in text.splitlines() if line.startswith('GGML_RISCV_QBS_LIFETIME_SUMMARY ')]
        if len(summaries)!=2: raise ValueError('Missing policy activity summaries')
        if ([int(s['quantizations']) for s in summaries]!=[12,8] or
                [int(s['cross_op_quantization_skips']) for s in summaries]!=[0,4]):
            raise ValueError('Expected two float-gap scenarios to reuse; writes must not reuse')
        for s, expected_cross in zip(summaries, (0,4)):
            if any(int(s[k])!=expected_cross for k in ('cross_op_fill','cross_op_reuse','cross_op_release')):
                raise ValueError('Cross-operation context accounting mismatch')
        executions=[dict(w.split('=',1) for w in line.split()[1:])
                    for line in text.splitlines() if line.startswith('GGML_RISCV_QBS_EXEC ')]
        if len(executions)!=2: raise ValueError('Missing native execution summaries')
        for s, fills, reuse in zip(executions,(12,8),(0,8)):
            if (int(s['context_fill'])!=fills or int(s['context_release'])!=fills or
                    int(s['context_reuse'])!=reuse or int(s['native_qbexec'])!=24 or
                    int(s['emulated_commands'])!=0):
                raise ValueError('Native context lifetime/work mismatch')
        if hashes(map(Path,pins))!=pins: raise ValueError('Input drift')
        state.update(state='PASS',graphs=12,quantizations=[12,8],skips=[0,4],
                     scope='Graph outputs, CSR and aggregate context admission; not RTL performance')
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc));raise
    finally:
        state['child_pid']=None;save()
        atomic_json(out/'result.json',state)


if __name__=='__main__': main()
