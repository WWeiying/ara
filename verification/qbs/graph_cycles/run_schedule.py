#!/usr/bin/env python3
"""Check schedules/cache activity in an isolated paired real-model run."""
import argparse
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
from run_census import runtime, census_check, audit_calls, HERE, ROOT
from schedule_check import check


def instrument(text):
    additions = [
        ('    for (int node_n = 0; node_n < cgraph->n_nodes && atomic_load_explicit(&tp->abort, memory_order_relaxed) != node_n; node_n++) {',
         '    GGML_ASSERT(graph_schedule_begin(params.graph_epoch, cgraph->n_nodes, params.ith, params.nth));\n'),
        ('        struct ggml_tensor * result_node = cgraph->nodes[node_n];',
         '        GGML_ASSERT(graph_schedule_append(qbs_first_node, node_n, node->op));\n'),
        ('    if (state->ith == 0 && riscv_model_observe) {\n        fprintf(stderr, "GGML_RISCV_MODEL_GRAPH_END',
         '    GGML_ASSERT(graph_schedule_finish(tp->ec == GGML_STATUS_SUCCESS));\n')]
    for anchor, body in additions:
        if text.count(anchor) != 1: raise ValueError('Schedule anchor changed')
        text = text.replace(anchor, body+anchor)
    return '#include "schedule_census.h"\n'+text


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve();s=runtime.s
    s.require(out.is_relative_to(ROOT/'verification/out') and not out.exists(),'Fresh output required')
    out.mkdir();owner=runtime.Execution(out)
    old=ROOT/'verification/out/graph-command-model-20261029-02'
    probe=ROOT/'verification/out/graph-cycles-model-20261029-03'
    prepared=ROOT/'verification/out/graph-cycles-source-20261029-01'
    result=dict(state='FAIL',performance_measured=False)
    try:
        receipt=s.read_json(old/'result.json')
        s.require(receipt['state']=='PASS' and receipt['post_pins_match'],'Previous run unaccepted')
        s.require(census_check((old/'qemu.log').read_text())==receipt['measured'],'Previous log differs')
        s.require(s.digest(old/'source-pins.json')==receipt['source_pins_sha256'],'Previous pins differ')
        pins=s.read_json(old/'source-pins.json');s.verify_pins(pins)
        (out/'ggml-cpu.c').write_text(instrument((prepared/'ggml-cpu.c').read_text()))
        shutil.copyfile(prepared/'records.h',out/'records.h')
        cc=s.read_json(probe/'probe-compile.command.json')['argv']
        cc[cc.index('-c')+1]=str(out/'ggml-cpu.c');cc[cc.index('-o')+1]=str(out/'ggml-cpu.c.o')
        cc.extend(['-I'+str(HERE)])
        owner.execute(cc,out/'cpu-compile.log',180,'CPU_COMPILE')
        recipes_path=ROOT/'verification/out/m4-sums-models-20261029-01/libraries/on/compile_commands.json'
        recipes=s.read_json(recipes_path)
        recipe=next(r for r in recipes if r['file'].endswith('/ggml-cpu/repack.cpp'))
        snapshot=shlex.split(recipe['command'])
        snapshot[snapshot.index('-c')+1]=str(HERE/'cache_snapshot.cpp')
        snapshot[snapshot.index('-o')+1]=str(out/'cache_snapshot.o')
        snapshot.extend(['-fno-tree-vectorize','-fno-tree-slp-vectorize'])
        owner.execute(snapshot,out/'snapshot-compile.log',180,'SNAPSHOT_COMPILE')
        compiler='/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-gcc'
        owner.execute([compiler,'-std=c11','-march=rv64gc','-mabi=lp64d','-O2',
            '-Wall','-Wextra','-Werror','-fno-tree-vectorize','-fno-tree-slp-vectorize',
            '-c',HERE/'schedule_census.c','-o',out/'schedule.o'],out/'schedule-compile.log',120,'SCHEDULE_COMPILE')
        archive=out/'libggml-cpu.a';shutil.copyfile(probe/'libggml-cpu.a',archive)
        owner.execute(['/usr/bin/ar','r',archive,out/'ggml-cpu.c.o'],out/'archive.log',120,'ARCHIVE')
        for name,source in [('before.a',probe/'libggml-cpu.a'),('after.a',archive)]:
            shutil.copyfile(source,out/name)
            owner.execute(['/usr/bin/ar','d',out/name,'ggml-cpu.c.o'],out/(name+'.log'),120,'ARCHIVE_VERIFY')
        s.require(s.digest(out/'before.a')==s.digest(out/'after.a'),'Other archive members changed')
        link=s.read_json(old/'link.command.json')['argv']
        link=[str(archive) if x==str(probe/'libggml-cpu.a') else
              '-Wl,-Map='+str(out/'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
        link[link.index('-o')+1]=str(out/'test')
        link[2:2]=[str(out/'schedule.o'),str(out/'cache_snapshot.o')]
        owner.execute(link,out/'link.log',180,'LINK')
        prefix='/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-'
        owner.execute([prefix+'objdump','-d',out/'test'],out/'disassembly.log',120,'LINK_AUDIT')
        wrapped=audit_calls((out/'disassembly.log').read_text())
        owner.execute([prefix+'nm','-C',out/'test'],out/'symbols.log',120,'TLS_AUDIT')
        symbols=(out/'symbols.log').read_text()
        values=[line for line in symbols.splitlines() if re.search(r'\bu ggml_riscv_q8_K_prepared::worker_state\(\)::value$',line)]
        s.require(len(values)==1,'Cache snapshot must share the existing worker TLS instance')
        (out/'initramfs.list').write_text((old/'initramfs.list').read_text().replace(str(old/'test'),str(out/'test')))
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out/'initramfs.cpio').open('wb') as image:
            subprocess.run([cpio,out/'initramfs.list'],stdout=image,check=True,timeout=60)
        qemu=s.read_json(old/'qemu.command.json')['argv'];qemu[qemu.index('-initrd')+1]=str(out/'initramfs.cpio')
        files=[Path(__file__),HERE/'schedule_check.py',HERE/'schedule_census.c',HERE/'schedule_census.h',
               HERE/'cache_snapshot.cpp',old/'result.json',old/'qemu.log',old/'source-pins.json',
               recipes_path,out/'test',out/'ggml-cpu.c',out/'records.h',archive,
               out/'initramfs.cpio',out/'initramfs.list',out/'symbols.log',out/'disassembly.log']
        s.merge_pins(pins,s.hashes(files));s.verify_pins(pins);s.atomic_json(out/'source-pins.json',pins)
        owner.execute(qemu,out/'qemu.log',7200,'QEMU_FUNCTIONAL')
        measured=check((out/'qemu.log').read_text());s.verify_pins(pins)
        result.update(state='PASS',measured=measured,post_pins_match=True,wrapped_callsites=wrapped,
                      source_pins_sha256=s.digest(out/'source-pins.json'))
    except BaseException as exc:
        result['error']=repr(exc);raise
    finally:
        s.atomic_json(out/'result.json',result);owner.state.update(state=result['state'],child_pid=None);owner.save()


if __name__=='__main__':
    def interrupted(sig, frame): raise InterruptedError(str(sig))
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupted)
    main()
