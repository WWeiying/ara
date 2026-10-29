#!/usr/bin/env python3
"""Paired model probe and native-command shape census; not performance data."""
import argparse
import json
from pathlib import Path
import re
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / 'tile_boundary'))
from run_ordinary import runtime
from model_check import check


def transform(text):
    def replace(anchor, value):
        nonlocal text
        if text.count(anchor) != 1:
            raise ValueError('Ambiguous census anchor: ' + anchor)
        text = text.replace(anchor, value)

    text = '#include "command_census.h"\n' + text
    replace('    for (unsigned kind = 0; kind < 2; ++kind) {',
            '    std::vector<graph_command_record> commands(1048576);\n'
            '    for (unsigned kind = 0; kind < 2; ++kind) {')
    replace('            asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" ::: "memory");',
            '            need(graph_command_census_begin(commands.data(), commands.size()), "census_begin");\n'
            '            asm volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" ::: "memory");')
    replace('            need(fc <= 31 && (fc & 8) && vc <= 7, "csr");',
            '            need(fc <= 31 && (fc & 8) && vc <= 7, "csr");\n'
            '            size_t command_count = 0;\n'
            '            need(graph_command_census_finish(&command_count) && command_count > 0, "census_incomplete");')
    replace('            write(f, logits, count*sizeof(float));', '''            write(f, logits, count*sizeof(float));
            const uint64_t recorded = command_count;
            write(f, &recorded, sizeof(recorded));
            write(f, commands.data(), command_count*sizeof(commands[0]));
            std::printf("GRAPH_COMMAND_RECORD mode=%u kind=%u step=%u count=%zu\\n",
                        mode, kind, step, command_count);''')
    replace('        need(!std::memcmp(va.data(), vb.data(), na*sizeof(float)), "paired_logits");', '''        need(!std::memcmp(va.data(), vb.data(), na*sizeof(float)), "paired_logits");
        uint64_t ca_count, cb_count;
        read(a, &ca_count, sizeof(ca_count)); read(b, &cb_count, sizeof(cb_count));
        need(ca_count == cb_count && ca_count > 0 && ca_count <= 1048576, "command_count");
        for (uint64_t i = 0; i < ca_count; ++i) {
            graph_command_record ra, rb;
            read(a, &ra, sizeof(ra)); read(b, &rb, sizeof(rb));
            need(!std::memcmp(&ra, &rb, sizeof(ra)), "command_sequence");
            need(ra.status == 0 && ra.descriptor_present == 1 && ra.reserved == 0, "command_status");
        }
        std::printf("GRAPH_COMMAND_COMPARE kind=%u step=%u count=%llu exact=1\\n",
                    record/3, record%3, (unsigned long long)ca_count);''')
    return text


def census_check(text):
    base = check(text)
    rows = re.findall(r'^GRAPH_COMMAND_RECORD mode=(\d+) kind=(\d+) step=(\d+) count=(\d+)$',
                      text.replace('\r', ''), re.M)
    wanted = [(m, k, t) for m in range(2) for k in range(2) for t in range(3)]
    if [tuple(map(int, r[:3])) for r in rows] != wanted:
        raise ValueError('Missing or duplicate census records')
    counts = [int(r[3]) for r in rows]
    if counts[:6] != counts[6:] or not all(0 < n <= 1048576 for n in counts):
        raise ValueError('Invalid paired command counts')
    compares = re.findall(r'^GRAPH_COMMAND_COMPARE kind=(\d+) step=(\d+) count=(\d+) exact=1$',
                          text.replace('\r', ''), re.M)
    if compares != [(str(k), str(t), str(counts[k*3+t])) for k in range(2) for t in range(3)]:
        raise ValueError('Missing exact command sequence comparisons')
    return dict(base, native_call_shapes_verified=True, native_calls_per_mode=sum(counts[:6]),
                native_calls_per_step=counts[:6], hardware_command_counts_verified=False,
                reuse_counts_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    s = runtime.s
    s.require(out.is_relative_to(ROOT/'verification/out') and not out.exists(), 'Fresh output required')
    out.mkdir()
    owner = runtime.Execution(out)
    old = ROOT/'verification/out/graph-cycles-model-20261029-03'
    result = dict(state='FAIL', performance_measured=False)
    try:
        receipt = s.read_json(old/'result.json')
        s.require(receipt['state']=='PASS' and receipt['post_pins_match'], 'Prior model not accepted')
        s.require(check((old/'qemu.log').read_text())==receipt['measured'], 'Prior log mismatch')
        s.require(s.digest(old/'source-pins.json')==receipt['source_pins_sha256'], 'Prior pins mismatch')
        pins = s.read_json(old/'source-pins.json'); s.verify_pins(pins)
        (out/'test.cpp').write_text(transform((old/'test.cpp').read_text()))
        cc = s.read_json(old/'compile.command.json')['argv']
        cc[cc.index('-c')+1] = str(out/'test.cpp'); cc[cc.index('-o')+1] = str(out/'test.o')
        owner.execute(cc, out/'compile.log', 180, 'COMPILE')
        compiler = '/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-gcc'
        owner.execute([compiler, '-std=c11', '-march=rv64gc', '-mabi=lp64d', '-O2',
            '-Wall', '-Wextra', '-Werror', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
            '-I'+str(ROOT/'software/qbs/include'), '-c', HERE/'command_census.c',
            '-o', out/'census.o'], out/'census-compile.log', 120, 'CENSUS_COMPILE')
        link = s.read_json(old/'link.command.json')['argv']
        link = [str(out/'test.o') if x==str(old/'test.o') else
                '-Wl,-Map='+str(out/'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
        link[link.index('-o')+1] = str(out/'test')
        link[2:2] = [str(out/'census.o'), '-Wl,--wrap=qbs_native_execute_command']
        owner.execute(link, out/'link.log', 180, 'LINK')
        objdump = '/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-objdump'
        owner.execute([objdump, '-d', out/'test'], out/'disassembly.log', 120, 'LINK_AUDIT')
        asm = (out/'disassembly.log').read_text()
        wrapped = re.findall(r'\b(?:jal|jalr|j)\s+[^\n]*<__wrap_qbs_native_execute_command>', asm)
        s.require(len(wrapped)>=2, 'Native bridge callsites not wrapped')
        callers=[]; function=''
        for line in asm.splitlines():
            label=re.match(r'^[0-9a-f]+ <([^>]+)>:',line)
            if label: function=label[1]
            if re.search(r'\b(?:jal|jalr|j)\s+[^\n]*<qbs_native_execute_command>',line):
                callers.append(function)
        s.require(callers and set(callers)=={'__wrap_qbs_native_execute_command'}, 'Unwrapped native callsite')
        (out/'initramfs.list').write_text((old/'initramfs.list').read_text().replace(str(old/'test'), str(out/'test')))
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out/'initramfs.cpio').open('wb') as image:
            subprocess.run([cpio,out/'initramfs.list'],stdout=image,check=True,timeout=60)
        qemu=s.read_json(old/'qemu.command.json')['argv']
        qemu[qemu.index('-initrd')+1]=str(out/'initramfs.cpio')
        files=[Path(__file__),HERE/'command_census.c',HERE/'command_census.h',HERE/'model_check.py',
               old/'result.json',old/'qemu.log',old/'source-pins.json',out/'test.cpp',out/'test',
               out/'census.o',out/'initramfs.cpio',out/'initramfs.list',out/'disassembly.log',
               Path(compiler).resolve(),Path(objdump).resolve(),cpio]
        s.merge_pins(pins,s.hashes(files));s.verify_pins(pins);s.atomic_json(out/'source-pins.json',pins)
        owner.execute(qemu,out/'qemu.log',7200,'QEMU_FUNCTIONAL')
        measured=census_check((out/'qemu.log').read_text());s.verify_pins(pins)
        result.update(state='PASS',measured=measured,post_pins_match=True,
                      wrapped_callsites=len(wrapped), source_pins_sha256=s.digest(out/'source-pins.json'))
    except BaseException as exc:
        result['error']=repr(exc)
        raise
    finally:
        s.atomic_json(out/'result.json',result)
        owner.state.update(state=result['state'],child_pid=None);owner.save()


if __name__=='__main__':
    def interrupted(sig, frame): raise InterruptedError(str(sig))
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupted)
    main()
