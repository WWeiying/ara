#!/usr/bin/env python3
"""Prepare all59 original missing adjacency pairs; host/Spike only, never DUT."""
import argparse
from collections import Counter
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
OLD = HERE.parent / 'whole_register_original'
SEALED = OLD / 'prepared01'
spec = importlib.util.spec_from_file_location('whole_original_prepare', OLD / 'prepare.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
require = original.require
sha = original.sha


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def key(row):
    return tuple(row[n] for n in ('seed', 'op', 'mode', 'index'))


def ordinal(row):
    seed, op, mode, index = key(row)
    return ((seed * 20 + op) * 5 + mode) * 5 + index


def geometry():
    source = read(SEALED / 'tuples.json')
    cases, skipped = original.geometry(0, 20)
    require(cases == source['cases'] and skipped == source['skipped'], 'Original tuple geometry drift')
    sequence = list(map(key, cases))
    partitions = [original.geometry(op, op+1)[0] for op in range(20)]
    retained = {pair for part in partitions for pair in zip(map(key, part), map(key, part[1:]))}
    edges = []
    for i, pair in enumerate(zip(sequence, sequence[1:])):
        if pair in retained:
            continue
        first, second = cases[i:i+2]
        exclusions = [r for r in skipped if ordinal(first) < ordinal(r) < ordinal(second)]
        require(ordinal(second)-ordinal(first)-1 == len(exclusions), 'Unaccounted intervening call')
        edges.append(dict(pair=len(edges), executed_ids=[i, i+1], calls=[first, second],
                          first_ordinal=ordinal(first), last_ordinal=ordinal(second),
                          intervening_skips=exclusions,
                          transition='seed' if first['seed'] != second['seed'] else 'operation',
                          expected_second_entry_vtype=(1 << 63) if first['mode'] == 4 else (0, 9, 18, 24)[first['mode']]))
    require(len(sequence) == 1134 and len(skipped) == 366 and len(edges) == 59, 'Original coverage count differs')
    continuous = set(zip(sequence, sequence[1:]))
    require(len(continuous & retained) == 1074 and len(retained-continuous) == 40, 'Partition adjacency differs')
    return edges, dict(original_calls=1134, original_exclusions=366, original_edges=1133,
                      retained_edges=1074, artificial_partition_edges=40, missing_edges=59,
                      executed_pair_calls=118, pair_exclusions=sum(len(e['intervening_skips']) for e in edges))


def check_edges(candidate, expected):
    require(candidate == expected, 'Missing, duplicated or changed original adjacency')


def run(cmd, log, timeout=60):
    started = time.monotonic()
    with log.open('x') as stream:
        result = subprocess.run(list(map(str, cmd)), stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    require(result.returncode == 0, 'Command failed: ' + str(log))
    return time.monotonic()-started


def marker(edge):
    return f"RVV_WHOLE_PASS cases=2 skips={len(edge['intervening_skips'])} errors=0"


def host_source(port):
    find = '__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));'
    require(port.count(find) == 1, 'Unknown vlenb boundary')
    text = port.replace(find, 'vlenb=128; /* host-only ISA emulation */')
    require('__asm__' not in text, 'Unknown host ISA operation')
    text += r'''
#include <stdio.h>
#include <stdlib.h>
static int host_mutation;
static unsigned host_calls;
long replay_write(long n,long fd,long p,long z) {
    if(n!=64 || fd!=1)abort();
    return fwrite((void*)p,1,z,stdout);
}
static unsigned long emulate(unsigned op,const void *aa,void *oo,unsigned long start,unsigned long mode) {
    const unsigned char *a=aa; unsigned char *o=oo;
    unsigned n=1U<<(op<16?op/4:op-16), width=1U<<(op<16?op%4:mode);
    for(unsigned i=start*width;i<n*128;++i)o[i]=a[i];
    if(++host_calls==2) {
        if(host_mutation==1)o[-1]^=1;
        if(host_mutation==2)o[0]^=1;
        if(host_mutation==3)o[n*128-1]^=1;
        if(host_mutation==4)o[n*128]^=1;
        if(host_mutation==5)o[1055]^=1;
        if(host_mutation==6)return (start<<32)|1;
        if(host_mutation==7)return (start+1)<<32;
    }
    return start<<32;
}
'''
    for op in range(20):
        text += f'unsigned long op_{op}(const void*a,void*o,unsigned long s,unsigned long m){{return emulate({op},a,o,s,m);}}\n'
    text += 'int main(int argc,char**argv){host_mutation=argc>1?atoi(argv[1]):0;int r=whole_original_main();return host_calls==2?r:91;}\n'
    return text


COMMIT = re.compile(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$')


def validate_spike(path, symbols, targets, edge, name):
    raw = path.read_text()
    values = [int(x, 16) for x in re.findall(r'^0x([0-9a-f]+)$', raw, re.M)]
    require(len(values) == 8, f'Debugger evidence count differs: {values}')
    first, second = edge['calls']
    require(values[1:3] == [first['start'], first['mode']] and values[4:6] == [second['start'], second['mode']], 'Target arguments differ')
    require(values[3] == edge['expected_second_entry_vtype'], 'Predecessor vtype history lost')
    require(values[6] == 0 and values[7] > 0, 'Nonzero raw exit or missing instruction count')
    require(marker(edge) in raw and f'BOARD_CASE_PASS {name}' in raw and 'BOARD_REPLAY_PASS' in raw,
            'Missing exact original completion markers')
    require('FAIL' not in raw and 'TRAP' not in raw and 'exception' not in raw, 'Reference failure/trap')
    regs = {r: 0 for r in range(32)}
    entries = {symbols[f'op_{op}']: op for op in range(20)}
    target_pcs = {t['pc']: op for op, t in targets.items()}
    preload_pcs = {symbols[f'op_{op}']+offset for op in range(20) for offset in (4, 8)}
    calls, retired_targets = [], []
    output_reads = [[], []]
    input_setup, output_setup = {}, {}
    commits = preloads = stores = 0
    for line in raw.splitlines():
        m = COMMIT.match(line)
        if not m:
            continue
        commits += 1
        pc, insn, tail = int(m[2], 16), int(m[3], 16), m[4]
        require(pc != symbols['trap_entry'], 'Default trap reached')
        if pc in entries:
            index = len(calls)
            require(index < 2, 'Extra original operation call')
            row = edge['calls'][index]
            require(entries[pc] == row['op'], 'Wrong predecessor/successor operation')
            require([regs[i] for i in (10, 11, 12, 13)] ==
                    [symbols['input'], symbols['output']+32, row['start'], row['mode']], 'Original call setup changed')
            require(input_setup == {i:(i*37+row['seed']*71+3)&255 for i in range(1024)}, 'Full original input initialization differs')
            require(output_setup == {i:0x5b for i in range(1088)}, 'Full old destination initialization differs')
            input_setup.clear(); output_setup.clear()
            calls.append(row)
        if pc in target_pcs:
            require(len(retired_targets) < 2, 'Extra target instruction')
            op = edge['calls'][len(retired_targets)]['op']
            require(target_pcs[pc] == op and insn == targets[op]['opcode'], 'Target PC/opcode sequence differs')
            retired_targets.append(dict(op=op, pc=pc, opcode=insn))
        if pc in preload_pcs:
            preloads += 1
        if insn & 127 == 0x27:
            stores += 1
        if insn & 127 in (3, 0x23):
            for address, value in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?', tail):
                address = int(address, 16)
                if insn & 127 == 0x23 and (insn >> 12) & 7 == 0 and value:
                    if symbols['input'] <= address < symbols['input']+1024:
                        input_setup[address-symbols['input']] = int(value,16)&255
                    if symbols['output'] <= address < symbols['output']+1088:
                        output_setup[address-symbols['output']] = int(value,16)&255
                if insn & 127 == 3 and symbols['output'] <= address < symbols['output']+1088:
                    require(len(calls) in (1,2) and (insn >> 12) & 7 == 4, 'Unexpected output oracle access')
                    output_reads[len(calls)-1].append(address-symbols['output'])
        regs.update({int(r):int(v,16) for r,v in re.findall(r'\bx\s*([0-9]+)\s+0x([0-9a-f]+)',tail)})
        regs[0] = 0
    require(calls == edge['calls'] and len(retired_targets) == 2 and preloads == 4 and stores == 2,
            'Operation/preload/store instruction counts differ')
    require(output_reads == [list(range(1088)),list(range(1088))], 'Incomplete or reordered full byte oracle')
    return dict(status='SPIKE_PAIR_PASS_NOT_DUT', pair=edge['pair'], target_instructions=retired_targets,
                retired_commits=commits, minstret_at_raw_exit=values[7], inherited_entry_vtypes=[values[0],values[3]],
                output_byte_checks=[1088,1088], input_initialized_bytes=[1024,1024],
                whole_preloads=preloads, whole_output_stores=stores, raw_exit=values[6], original_skips=len(edge['intervening_skips']))


def main(out):
    require(out.is_relative_to(HERE) and out != HERE and not out.exists(), 'Fresh owned output required')
    pins = read(SEALED / 'source_pins.json')
    for path, digest in pins.items():
        require(sha(Path(path)) == digest, 'Sealed provenance drift: '+path)
    old_complete = read(SEALED / 'complete.json')
    require(old_complete['status'] == 'HOST_SPIKE_FULL1134_AND_20_PARTITIONS_PASS_NOT_DUT', 'Original preparation not accepted')
    for name in ('whole_oracle.c', 'whole.py'):
        require(sha(SEALED/'original'/name) == sha(original.SOURCE/name), 'Original C/generator copy differs')
    for name in ('whole.S', 'operations.h'):
        require(sha(SEALED/'original'/name) == sha(original.ARCH/name), 'Archived assembly/header copy differs')
    edges, coverage = geometry()
    original_text = (SEALED / 'original/whole_oracle.c').read_text()
    canonical = original.common.adapt(original_text, 'whole_original').replace(
        'for(unsigned op=0;op<20;++op)', 'for(unsigned op=WHOLE_OP_BEGIN;op<WHOLE_OP_END;++op)')
    require(canonical == (SEALED / 'case.c').read_text(), 'Existing port not exact original adaptation')
    needle = '            unsigned start=starts[st];\n'
    require(canonical.count(needle) == 1, 'Unknown tuple selection location')
    guard = ('            unsigned ordinal=((seed*20+op)*5+mode)*5+st;\n'
             '            if(ordinal<EDGE_BEGIN || ordinal>EDGE_END)continue;\n')
    port = canonical.replace(needle, needle+guard)
    require(port.replace(guard, '') == canonical, 'Original setup/skip/oracle changed')
    out.mkdir()
    (out / 'original').mkdir()
    for name in ('whole_oracle.c', 'whole.py', 'whole.S', 'operations.h'):
        shutil.copyfile(SEALED / 'original' / name, out / 'original' / name)
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(SEALED / name, out / name)
    (out / 'case.c').write_text(port)
    (out / 'host.c').write_text(host_source(port))
    (out / 'selection.diff').write_text(''.join(difflib.unified_diff(canonical.splitlines(True),port.splitlines(True),
        fromfile='sealed/prepared01/case.c',tofile='history_edges/case.c')))
    save(out / 'edges.json', dict(coverage=coverage, pairs=edges))
    negatives = []
    changed = json.loads(json.dumps(edges)); changed[0]['calls'][1]['mode'] ^= 1
    for name, candidate in [('missing_pair',edges[:-1]),('duplicate_pair',edges+[edges[0]]),
                            ('changed_tuple',changed),('reversed_order',list(reversed(edges)))]:
        try: check_edges(candidate, edges)
        except ValueError: negatives.append(name)
        else: raise ValueError('Coverage mutation accepted: '+name)
    save(out / 'host_coverage.json',dict(status='EXACT59_COVERAGE_PASS_NOT_DUT',coverage=coverage,negatives_rejected=negatives))
    consumed = [Path(__file__), HERE/'README.md', OLD/'WHOLE_CONTINUOUS_HISTORY_PLAN.md',
                SEALED/'source_pins.json', SEALED/'complete.json', SEALED/'tuples.json', SEALED/'case.c',
                *[SEALED/'original'/n for n in ('whole_oracle.c','whole.py','whole.S','operations.h')],
                *[SEALED/n for n in ('startup.S','runtime.c','replay.ld')]]
    pins.update({str(p):sha(p) for p in consumed})
    save(out / 'input_pins.json', pins)
    flags = ['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding',
             '-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
             '-msmall-data-limit=0','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror',
             '-nostdlib','-static','-Wl,--build-id=none','-Wl,--gc-sections','-DDETAIL_BYTES=1',
             '-DWHOLE_OP_BEGIN=0','-DWHOLE_OP_END=20','-T',out/'replay.ld','-I'+str(out/'original')]
    nm = original.CC.with_name(original.CC.name.removesuffix('gcc')+'nm')
    objdump = original.CC.with_name(original.CC.name.removesuffix('gcc')+'objdump')
    results = []
    try:
        for edge in edges:
            number = edge['pair']; name = f'whole_edge{number:02d}'
            d = out / f'pair{number:02d}'; d.mkdir()
            defines = [f"-DEDGE_BEGIN={edge['first_ordinal']}",f"-DEDGE_END={edge['last_ordinal']}"]
            host = d / 'host'
            run(['/usr/bin/gcc','-O2','-Wall','-Wextra','-Werror','-DDETAIL_BYTES=1',
                 '-DWHOLE_OP_BEGIN=0','-DWHOLE_OP_END=20',*defines,'-I'+str(out/'original'),out/'host.c','-o',host],d/'host.compile.log')
            for mutation in range(8):
                r = subprocess.run([str(host),str(mutation)],capture_output=True,text=True,timeout=10)
                (d / f'host_mutation{mutation}.log').write_text(r.stdout+r.stderr)
                require(r.returncode == (1 if mutation else 0), 'Host oracle exit differs')
                require(('RVV_WHOLE_FAIL' in r.stdout) if mutation else (marker(edge) in r.stdout and 'FAIL' not in r.stdout), 'Host oracle marker differs')
            save(d/'host.json',dict(status='HOST_PAIR_AND7_NEGATIVES_PASS_NOT_DUT',pair=number,executed_calls=2,negatives_rejected=list(range(1,8))))
            wrapper = d / 'main.c'
            wrapper.write_text('extern int whole_original_main(void);\nextern void replay_text(const char*);\n'
                'int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));'
                'if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}'
                'if(whole_original_main()){replay_text("BOARD_CASE_FAIL\\n");return 1;}'
                f'replay_text("BOARD_CASE_PASS {name}\\nBOARD_REPLAY_PASS\\n");return 0;}}\n')
            symbols, targets, elfs = {}, {}, {}
            for backend in ('spike','soc'):
                elf = d / (backend+'.elf')
                run([original.CC,*flags,*defines,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
                     out/'case.c',out/'original/whole.S',wrapper,out/'startup.S',out/'runtime.c','-lgcc','-o',elf],d/(backend+'.compile.log'))
                text = subprocess.check_output([str(nm),str(elf)],text=True,timeout=15)
                syms = {n:int(a,16) for a,_,n in (line.split() for line in text.splitlines() if len(line.split())==3)}
                dis = subprocess.check_output([str(objdump),'-d',str(elf)],text=True,timeout=15)
                (d/(backend+'.dis')).write_text(dis)
                instructions = {int(a,16):(int(code,16),mnemonic) for a,code,mnemonic in re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)$',dis,re.M)}
                found = {}
                for op in range(20):
                    pc = syms[f'configured_{op}']+8
                    opcode, assembly = instructions[pc]
                    require(re.match(r'(vl[1248]r(e(8|16|32|64))?[.]v|vmv[1248]r[.]v)',assembly), 'Original target decode differs')
                    n = 1 << (op//4 if op < 16 else op-16)
                    expected = (0x02850c07 | ((n-1)<<29) | ((0,5,6,7)[op%4]<<12)) if op < 16 else (0x9e803c57 | ((n-1)<<15))
                    require(opcode == expected, 'Original target encoding differs')
                    found[op] = dict(pc=pc,opcode=opcode,assembly=assembly)
                save(d/(backend+'.symbols.json'),syms); save(d/(backend+'.targets.json'),found)
                symbols[backend] = syms; targets[backend] = found
                elfs[backend] = dict(path=str(elf),sha256=sha(elf))
            require([v['opcode'] for v in targets['spike'].values()] == [v['opcode'] for v in targets['soc'].values()], 'Spike/SoC target instruction drift')
            s = symbols['spike']; a,b = edge['calls']
            debug = d / 'spike.cmd'
            debug.write_text(f'until pc 0 {s["op_"+str(a["op"])]:x}\nreg 0 vtype\n'
                f'until pc 0 {targets["spike"][a["op"]]["pc"]:x}\nreg 0 a2\nreg 0 a3\n'
                f'until pc 0 {s["op_"+str(b["op"])]:x}\nreg 0 vtype\n'
                f'until pc 0 {targets["spike"][b["op"]]["pc"]:x}\nreg 0 a2\nreg 0 a3\n'
                f'until pc 0 {s["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\nstr {s["replay_log"]:x}\nrs\n')
            elapsed = run([original.SPIKE,'-d','--debug-cmd='+str(debug),'--isa=rv64gcv_zvl1024b','-m2',
                           '-l','--log-commits',d/'spike.elf'],d/'spike.log',90)
            result = validate_spike(d/'spike.log',s,targets['spike'],edge,name)
            result.update(elfs=elfs,spike_elapsed_s=elapsed,trace_sha256=sha(d/'spike.log'))
            save(d/'complete.json',result); results.append(result)
            print('PAIR_REFERENCE_PASS',number,edge['executed_ids'],result['retired_commits'],flush=True)
        for path,digest in pins.items():
            require(sha(Path(path)) == digest, 'Input drift during preparation: '+path)
        save(out/'complete.json',dict(status='HOST_SPIKE_ALL59_EDGES_118_CALLS_PASS_NOT_DUT',coverage=coverage,
            pairs=results,target_instructions=sum(len(r['target_instructions']) for r in results),
            retired_commits=sum(r['retired_commits'] for r in results),
            output_byte_checks=sum(sum(r['output_byte_checks']) for r in results),
            host_negative_rejections=59*7,coverage_negative_rejections=len(negatives),input_pins=pins,
            original_linux_sha256=old_complete['original_linux_sha256'],
            scope='59 independently fresh adjacent-call pairs; not continuous1134 history, DUT PASS or Linux replay'))
        print('HOST_SPIKE_ALL59_EDGES_118_CALLS_PASS_NOT_DUT',flush=True)
    except Exception as error:
        save(out/'failure.json',dict(status='PREPARATION_NOT_PASS',error=str(error),completed_pairs=[r['pair'] for r in results]))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    main(args.out.resolve())
