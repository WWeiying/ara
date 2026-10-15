#!/usr/bin/env python3
"""Source/Host/compile only; reference is one separately bounded command."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from newscope import HERE, PARENT, PREVIOUS, PACKED, CASE, NAME, HISTORICAL, IMAGE, IMAGE_SHA, BOUND
from model import model, INPUT, compare, require
from elf import disassemble

CAMP = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
OLDNAME = 'alias_v8_e16m8_prefix682'
RUN = HERE / 'prepared01'
REPORTS = [CAMP/'rvv_compare_uncovered01/original_board_report.json',
           CAMP/'rvv_recovery08_11/terminal_scene/report.json']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, text):
    with Path(path).open('x') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def save(path, value):
    write(path, json.dumps(value, indent=2)+'\n')


def command(argv, stem, timeout, expect=0):
    argv = list(map(str, argv))
    save(str(stem)+'.command.json', dict(command=argv, timeout_s=timeout, expected_exit=expect))
    start = time.monotonic()
    with Path(str(stem)+'.log').open('xb') as stream:
        child = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT)
        timed_out = False
        try:
            rc = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            rc = child.wait()
    outcome = dict(returncode=rc, pid=child.pid, elapsed_s=time.monotonic()-start, timed_out=timed_out)
    save(str(stem)+'.exit.json', outcome)
    require(type(rc) is int and rc == expect and not timed_out, 'Actual child outcome '+str(stem))
    return outcome


def replace_one(text, old, new):
    require(text.count(old) == 1, 'Exact immutable source transformation '+old)
    return text.replace(old, new)


def verify_pins(pins):
    require(all(sha(path) == digest for path, digest in pins.items()), 'Input pin drift')


def origin():
    rows = model()['rows']
    original = (CASE/'original/parent.c').read_text()
    require(sha(CASE/'original/parent.c') == '3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c', 'Exact original C')
    for fragment in ('seed<32', 'op<10', 'l<7', 'mode<4', 'sticky<2',
                     'lengths[]={0,1,2,3,cap/2,cap-1,cap}', 'trial<(RESTART_COMPARISONS ? 4U:1U)'):
        require(fragment in original, 'Original enumeration '+fragment)
    contexts = next(x for x in read(PARENT/'ready_audit01/original_contexts.json') if x['name'] == HISTORICAL)
    mappings = []
    for path in REPORTS:
        data = read(path)
        report = data['report'] if 'report' in data else data
        record = next(x for x in report['results'] if x['name'] == HISTORICAL)
        entry = next(x for x in report['inputs']['cases'] if x['name'] == HISTORICAL)
        require(entry['sha256'] == '266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754', 'Report original ELF')
        details = []
        for line in record['output'].splitlines():
            if not line.startswith('RVV_FP_COMPARE_DETAIL '):
                continue
            t = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)}
            ordinal = 1+t['seed']*560+t['op']*56+[0,1,2,3,256,511,512].index(t['vl'])*8+t['mask']*2+t['sticky']
            g = rows[ordinal-1]
            require((g['seed'],g['op'],g['vl'],g['mode'],g['sticky']) ==
                    (t['seed'],t['op'],t['vl'],t['mask'],t['sticky']), 'Independent actual source ordinal')
            require(g['flags'] == t['expected_flags'], 'Historical expected flags versus integer oracle')
            details.append(dict(ordinal=ordinal, tuple=t, raw_line=line))
        require(len(details) == 20, 'Twenty retained source details')
        summary = re.findall(r'RVV_FP_COMPARE_FAIL sew=16 cases=17920 errors=(\d+)', record['output'])
        require(len(summary) == 1 and record['status'] == 'failed' and record['exit_code'] == 1, 'Original failed report')
        if path == REPORTS[1]:
            require([x['raw_line'] for x in details] == contexts['retained_details'], 'Structured versus original report')
        mappings.append(dict(path=str(path), sha256=sha(path), details=details, errors=int(summary[0]),
                             maximum=max(x['ordinal'] for x in details)))
    require([m['maximum'] for m in mappings] == [699,700] and [m['errors'] for m in mappings] == [1252,1472], 'Separate report boundaries')
    oldseq = read(CASE/'call_sequence.json')
    seq = [dict(seed=g['seed'], op=g['op'], vl=g['vl'], mask=g['mode'], sticky=g['sticky'], vstart=0) for g in rows]
    require(seq[:682] == oldseq, 'All original682 predecessors unchanged')
    return dict(scope='Original continuous first700/699 predecessors, not full17920 or Linux',
                reports=mappings, union_retained_ordinals=sorted({x['ordinal'] for m in mappings for x in m['details']}),
                selected_maximum=700, endpoint=seq[-1], call_sequence=seq,
                historical_error_totals_not_combined=True, first682_identical=True)


def packed_tables(rows):
    inputs, records = [], []
    for g in rows:
        indices = []
        for name in ('a','b'):
            data = tuple(sum(g[name][i+j] << (16*j) for j in range(4)) for i in range(0,512,4))
            if data not in inputs:
                inputs.append(data)
            indices.append(inputs.index(data))
        zero = [sum((1 not in g['allowed'][8*k+b]) << b for b in range(8)) for k in range(64)]
        one = [sum((0 not in g['allowed'][8*k+b]) << b for b in range(8)) for k in range(64)]
        records.append((g['seed'],g['op'],g['vl'],g['mode'],g['sticky'],*indices,g['flags'],zero,one))
    require(len(inputs) == 5, 'Same original input ROM rows')
    text = 'static const uint64_t input_rows[][128]={\n'
    text += '\n'.join('{'+','.join('UINT64_C('+hex(v)+')' for v in row)+'},' for row in inputs)+'\n};\n'
    text += 'struct packed_case {uint16_t seed,op,vl,mode,sticky,ai,bi,flags; uint8_t zero[64],one[64];};\n'
    text += f'static const struct packed_case packed_cases[{BOUND}]={{\n'
    for r in records:
        text += '{'+','.join(map(str,r[:8]))+',{'+','.join(map(str,r[8]))+'},{'+','.join(map(str,r[9]))+'}},\n'
    return text+'};\n'


def main():
    require(not RUN.exists(), 'Fresh one-attempt preparation only')
    RUN.mkdir()
    try:
        mapping = origin()
        pins = read(PACKED/'pins.json')
        # Reuse prepared inputs and evidence, not a second traversal of old reference logs.
        pins = {p:h for p,h in pins.items() if not p.endswith(('.log','.trace'))}
        for path in [*HERE.glob('*.py'), *REPORTS, PARENT/'ready_audit01/original_contexts.json',
                     IMAGE/'image.json', PREVIOUS/'strict.py', PREVIOUS/'model.py', PREVIOUS/'elf.py',
                     PREVIOUS/'prepared01/complete.json', PREVIOUS/'reference01/result.json',
                     PACKED/'host.c',PACKED/'host_flow.c',PACKED/'run01/case.c',PACKED/'run01/tables.h',
                     CASE/'original/parent.c',CASE/'call_sequence.json']:
            pins[str(path)] = sha(path)
        require(sha(IMAGE/'image.json') == IMAGE_SHA, 'Frozen M9 image identity')
        prior = read(PREVIOUS/'prepared01/complete.json')
        require(prior['status'] == 'PASS_M8_ORIGINAL_ALIAS682_NOT_FULL17920_OR_LINUX'
                and prior['aborted'] is False and prior['pins_unchanged'] is True, 'Accepted predecessor baseline')
        verify_pins(pins)
        static_seconds = prior['results'][0]['elapsed_s']*700/682
        save(RUN/'source_budget_gate.json', dict(mapping=mapping, image=str(IMAGE), image_sha256=IMAGE_SHA,
             baseline_calls=682, baseline_actual_M8_s=prior['results'][0]['elapsed_s'], added_calls=18,
             static_ratio_s=static_seconds, static_margin20_s=static_seconds*1.2,
             candidate_budget_s=10800, preparation_only=True,
             limitation='Proportional estimate only; actual new reference count required before DUT admission'))
        require(static_seconds*1.2 < 10800, 'Static preparation budget')
        rows = model()['rows']
        fixture = (CASE/'original/fixtures.h').read_text()
        oldinput = [int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)', fixture)]
        expected = json.loads(fixture.split('expected[6][16][16]=',1)[1].split(';',1)[0].replace('{','[').replace('}',']'))
        require(oldinput == INPUT, 'Exact original fixture inputs')
        require(all(compare(op,a,b) == tuple(expected[op][i][j]) for op in range(6)
                    for i,a in enumerate(INPUT) for j,b in enumerate(INPUT)), 'Independent integer fixture1536 match')
        write(RUN/'tables.h', packed_tables(rows))
        source = (PACKED/'run01/case.c').read_text().replace(OLDNAME,NAME)
        source = replace_one(source, 'if(cases==682)', 'if(cases==700)')
        write(RUN/'case.c', source)
        original = (CASE/'case.c').read_text().replace(OLDNAME,NAME)
        original = replace_one(original, 'if(cases==682)', 'if(cases==700)')
        write(RUN/'original_source_port.c', original)
        write(RUN/'boundary.diff', ''.join(difflib.unified_diff((PACKED/'run01/case.c').read_text().splitlines(True),
              source.splitlines(True),fromfile='sealed682',tofile='successor700')))
        host = (PACKED/'host.c').read_text().replace('682','700').replace('698368','716800').replace('11173888','11468800')
        write(RUN/'host_exhaustive.c',host)
        command(['gcc','-O2','-Wall','-Wextra','-Werror','-I'+str(CASE/'original'),'-I'+str(RUN),
                 RUN/'host_exhaustive.c','-o',RUN/'host_exhaustive'],RUN/'host_exhaustive_compile',120)
        command([RUN/'host_exhaustive'],RUN/'host_exhaustive',120)
        flow = (PACKED/'host_flow.c').read_text().replace(OLDNAME,NAME).replace('calls==682','calls==700')
        flow = replace_one(flow,'    ++calls;', '''    if(calls==699) {
        if(mutation==7)status^=1UL<<36;
        if(mutation==8)o[0]^=1;
        if(mutation==9)o[64]^=1;
        if(mutation==10)status|=1;
    }
    ++calls;''')
        write(RUN/'host_flow.c',flow)
        host_results = []
        for variant, src in [('original',RUN/'original_source_port.c'),('packed',RUN/'case.c')]:
            command(['gcc','-O2','-Wall','-Wextra','-Werror','-fno-tree-vectorize','-fno-tree-slp-vectorize',
                     '-DSEW=16','-DUNMASKED_COMPARISONS=1','-DDESTINATION_KIND=1',
                     '-I'+str(CASE/'original'),'-I'+str(RUN),src,RUN/'host_flow.c','-o',RUN/variant],RUN/(variant+'_compile'),120)
            for mutation in range(11):
                stem = RUN/(variant+str(mutation))
                host_results.append(command([RUN/variant,mutation,str(stem)+'.bin'],stem,60,0 if mutation==0 else 1))
        for mutation in range(11):
            require(sha(RUN/('original'+str(mutation)+'.bin')) == sha(RUN/('packed'+str(mutation)+'.bin')), 'Actual source/packed call flow')
        save(RUN/'host_result.json',dict(status='HOST_FULL700_SOURCE_PACKED_EQUIVALENT_NOT_DUT', calls_each=700,
             exhaustive_byte_alternatives=11468800, input_halfword_checks=716800, fixture_checks=1536,
             positive_pairs=1,negative_pairs=10,endpoint700_negatives=['NV','activebit','guard','vstart'],results=host_results))
        for backend in ('soc','spike'):
            argv = read(PARENT/'prepared02'/backend/(OLDNAME+'.compile.log.command.json'))
            argv[argv.index('-Os')] = '-O2'
            argv[argv.index(str(CASE/'case.c'))] = str(RUN/'case.c')
            oldmain = PARENT/'prepared02'/backend/(OLDNAME+'_main.c')
            newmain = RUN/(backend+'_main.c')
            write(newmain,oldmain.read_text().replace(OLDNAME,NAME))
            argv[argv.index(str(oldmain))] = str(newmain)
            argv[argv.index('-o')+1] = str(RUN/(backend+'.elf'))
            for token in argv:
                if Path(token).is_file():
                    pins[token] = sha(token)
            command(argv,RUN/(backend+'_compile'),120)
            spec, text = disassemble(RUN/(backend+'.elf'))
            write(RUN/(backend+'.dis'),text)
            save(RUN/(backend+'.spec.json'),spec)
            oldspec, _ = disassemble(PACKED/'run01'/(backend+'.elf'))
            helpers = ['capacity']+['op_'+str(i) for i in range(10)]
            require(all([r['insn'] for r in spec['functions'][h]] ==
                        [r['insn'] for r in oldspec['functions'][h]] for h in helpers), 'Sealed original helper bytes')
            for name, instructions in spec['functions'].items():
                if name in helpers:
                    continue
                require(not any(len(r['insn'])==8 and ((int(r['insn'],16)&127)==87 or
                        ((int(r['insn'],16)&127) in (7,39) and (int(r['insn'],16)>>12)&7 in (0,5,6,7)))
                        for r in instructions), 'No added vector instructions')
            sy = spec['symbols']
            require(sy['__bss_end'] < sy['__stack_top']-65536 and sy['__stack_top']==0x800ffff0, 'Original stack reserve')
        import strict
        for backend in ('soc','spike'):
            spec = strict.specification(RUN/(backend+'.elf'), backend=='spike')
            save(RUN/(backend+'.strict_spec.json'),spec)
        for path in RUN.iterdir():
            if path.is_file():pins[str(path)] = sha(path)
        verify_pins(pins)
        save(RUN/'pins.json',pins)
        save(RUN/'PREPARED.json',dict(status='COMPILED_HOST_PASS_REFERENCE_NOT_RUN',calls=700,
             predecessor_count=699,result_bits=358400,guards=1400,flags=700,vstart=700,
             helper_instructions=12880,image_sha256=IMAGE_SHA,pins_sha256=sha(RUN/'pins.json'),
             source_scope='Exact two historical-report retained context union through700, not parent17920/Linux'))
        print('PREPARED_SOURCE_HOST_COMPILE700_NOT_REFERENCE_OR_DUT',flush=True)
    except BaseException as error:
        save(RUN/'STOPPED.json',dict(firstcause=repr(error),no_retry=True,no_DUT=True))
        raise


if __name__ == '__main__':
    main()
