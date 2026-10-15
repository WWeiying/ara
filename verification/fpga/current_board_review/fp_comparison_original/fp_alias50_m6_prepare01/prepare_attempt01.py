#!/usr/bin/env python3
"""Authentic first50 FP alias calls: software preparation, never DUT launch."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
import prepare_prefix as prior

base = prior.base
sha, read, save = prior.sha, prior.read, prior.save
NAME = 'alias_v8_e16m8_prefix50'
OLDNAME = 'alias_v8_e16m8_prefix682'
ISA = 'rv64gcv_zvfh_zvl1024b'
OUT = HERE / 'prepared01'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image/image.json')
IMAGE_SHA = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
FAIL = re.compile(r'RVV_FP_COMPARE_(?:FAIL|DETAIL|CAPACITY_FAIL)|BOARD_\w*FAIL|BOARD_REPLAY_TRAP|Received trap|Unknown command|Bad or missing arguments')


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def accepted(text, markers):
    return not FAIL.search(text) and all(text.splitlines().count(m) == 1 for m in markers)


def instruction_blocks(disassembly):
    result = {}
    for i in range(10):
        match = re.search(rf'^[0-9a-f]+ <op_{i}>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)', disassembly, re.M | re.S)
        need(match is not None, f'missing helper op_{i}')
        result[f'op_{i}'] = re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(.+)$', match[1], re.M)
    return result


def main():
    OUT.mkdir(exist_ok=False)
    prep = OUT / 'prepared'
    case = prep / NAME
    original = case / 'original'
    original.mkdir(parents=True)
    old = PARENT / 'prepared02'
    oldcase = old / 'prepared' / OLDNAME
    pins = {}

    def pin(path, expected=None):
        path = Path(path).resolve()
        digest = sha(path)
        need(expected is None or digest == expected, 'pin drift: ' + str(path))
        pins[str(path)] = digest
        return digest

    for p in (Path(__file__), Path(prior.__file__), PARENT / 'recover.py',
              Path(base.__file__), Path(base.prepare.__file__), base.CC.resolve(),
              base.SPIKE, Path('/usr/bin/gcc').resolve(), old / 'prepared/provenance.json',
              old / 'old_prefix_equivalence.json', PARENT / 'provenance01/parents.json',
              PARENT / 'provenance01/original_rebuild.json', PARENT / 'TERMINAL08.md'):
        pin(p)
    pin(IMAGE, IMAGE_SHA)
    oldprov = read(old / 'prepared/provenance.json')
    record = next(x for x in oldprov['records'] if x['id'] == OLDNAME)
    entry = next(x for x in oldprov['cases'] if x['id'] == OLDNAME)
    parent = record['parent']
    pin(parent['original_elf'], parent['sha256'])
    pin(parent['manifest'])
    pin(oldcase / 'original_rebuilt.elf', parent['sha256'])
    for n in ('parent.c', 'scenario.S', 'operations.h', 'fixtures.h'):
        src = oldcase / 'original' / n
        pin(src, oldprov['files'][str(src.relative_to(old / 'prepared'))])
        shutil.copyfile(src, original / n)
    pin(parent['assembly'], sha(original / 'scenario.S'))
    need(sha(original / 'parent.c') == prior.OLD, 'original C identity')
    for n in ('startup.S', 'runtime.c', 'replay.ld'):
        pin(old / 'prepared' / n, oldprov['files'][n])
        shutil.copyfile(old / 'prepared' / n, prep / n)
    source = (original / 'parent.c').read_text()
    point = '        ++cases;\n    }\n'
    need(source.count(point) == 1, 'ambiguous prefix boundary')
    prefix = source.replace(point, '        ++cases;\n        if(cases==50)goto prefix_done;\n    }\nprefix_done:\n')
    port = base.adapt(prefix, NAME)
    pin(oldcase / 'case.c')
    need(port == (oldcase / 'case.c').read_text().replace(OLDNAME, NAME).replace('cases==682', 'cases==50'), 'unexpected change versus mature port')
    oracle = source[source.index('        if((uint32_t)status)'):source.index('        ++cases;')]
    need(oracle in port, 'original oracle modified')
    (original / 'prefix.c').write_text(prefix)
    (case / 'case.c').write_text(port)
    for label, a, b in [('prefix', source, prefix), ('wrapper', prefix, port)]:
        (case / (label + '.diff')).write_text(''.join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), fromfile=label+'_before', tofile=label+'_after')))

    ledger = [dict(seed=0, op=0, vl=vl, mask=mode, sticky=sticky, vstart=0)
              for vl in (0, 1, 2, 3, 256, 511, 512) for mode in range(4) for sticky in range(2)][:50]
    pin(oldcase / 'call_sequence.json')
    need(ledger == read(oldcase / 'call_sequence.json')[:50], 'predecessor ledger mismatch')
    report = prior.CAMP / 'rvv_compare_uncovered01/original_board_report.json'
    pin(report, '7ed11ee7257c8571d8d5d4bf87780231d82fd5373173343598d21d47ed5aa00f')
    raw = read(report)
    raw = raw.get('report', raw)
    historical = next(r for r in raw['results'] if r['name'] == parent['name'])
    detail = historical['output'].splitlines()[0]
    fields = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', detail)}
    need(all(ledger[-1][k] == fields[k] for k in ('op', 'seed', 'vl', 'mask', 'sticky')), 'call50 not archived tuple')
    need(fields['errors'] == 64 and fields['expected_flags'] == fields['actual_flags'] == 17, 'wrong historical symptom')
    save(case / 'call_sequence.json', ledger)
    defs = ['-D' + x for x in entry['defines']]
    markers = ['RVV_FP_COMPARE_PASS sew=16 cases=50 errors=0', f'BOARD_CASE_PASS {NAME}', 'BOARD_REPLAY_PASS']

    host = OUT / 'host'
    host.mkdir()
    host_source = prior.HOST.replace('    ++calls;\n', '''    ++calls;
    if(HOST_MUTATION==7 && calls==HOST_CALLS)o[(cap-1)/8]^=1u<<((cap-1)%8);
    if(HOST_MUTATION==8 && calls==HOST_CALLS)o[(cap+7)/8]^=1;
    if(HOST_MUTATION==9 && calls==1)o[0]^=1;
    if(HOST_MUTATION==10 && calls==HOST_CALLS-1)o[1]^=8;
''')
    host_results = []
    labels = {0:'positive', 1:'call50_active_bit0', 2:'call50_NV', 4:'left_guard',
              5:'returned_vstart', 6:'permitted_tail_ones', 7:'call50_active_bit511',
              8:'right_guard', 9:'first_VL0_old_bit', 10:'predecessor49_active_bit11'}
    for mutation, label in labels.items():
        hp = host / f'mutation{mutation}.c'
        hp.write_text(port + '\n' + host_source + '\n' + '\n'.join(
            f'unsigned long op_{i}(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){{return emulate({i},a,b,o,vl,cap,m,start,flags);}}' for i in range(10)) +
            f'\nint main(void){{for(unsigned op=0;op<6;++op)for(unsigned a=0;a<16;++a)for(unsigned b=0;b<16;++b){{struct fixture r=independent(op,inputs[a],inputs[b]);if(r.bit!=expected[op][a][b].bit || r.flags!=expected[op][a][b].flags)abort();}}return {NAME}_main();}}\n')
        exe = hp.with_suffix('')
        base.command(['/usr/bin/gcc', '-O2', *defs, '-DHOST_CAP=512', '-DHOST_CALLS=50', f'-DHOST_MUTATION={mutation}', '-I'+str(original), hp, '-o', exe], exe.with_suffix('.compile.log'))
        result = subprocess.run([exe], capture_output=True, text=True, timeout=10)
        log = exe.with_suffix('.log')
        log.write_text(result.stdout + result.stderr)
        positive = mutation in (0, 6)
        need((result.returncode == 0 and accepted(result.stdout, markers[:1])) if positive else
             (result.returncode == 1 and 'RVV_FP_COMPARE_FAIL sew=16 cases=50' in result.stdout), 'host ' + label)
        host_results.append(dict(mutation=mutation, label=label, expected='PASS' if positive else 'REJECT', actual_returncode=result.returncode, log_sha256=sha(log)))
    for token in ('RVV_FP_COMPARE_DETAIL op=0', 'RVV_FP_COMPARE_FAIL', 'BOARD_CASE_FAIL', 'BOARD_REPLAY_TRAP'):
        need(not accepted('\n'.join(markers) + '\n' + token, markers), 'contradictory PASS gate')
    need(not accepted('\n'.join(markers[:-1]), markers), 'missing marker accepted')
    save(OUT / 'host.json', dict(status='PASS', fixture_entries=1536, operation_runs=host_results, marker_negatives=5))
    print('HOST: 2 positive, 8 rejecting mutations, 5 marker negatives PASS', flush=True)

    provenance = dict(schema_version=1, cases=[dict(entry, id=NAME)], records=[dict(
        id=NAME, parent=parent, limit=50, capacity=512, first=ledger[0], last=ledger[-1],
        historical_report=str(report), historical_detail=detail, all49_predecessors=True,
        original_rebuild_byte_identical=True, existing_rebuild=str(oldcase/'original_rebuilt.elf'),
        oracle_sha256=hashlib.sha256(oracle.encode()).hexdigest(),
        scope='Current M6 first data-failure regression preparation only; not682/full parent/Linux')],
        files={str(p.relative_to(prep)):sha(p) for p in prep.rglob('*') if p.is_file()})
    save(prep / 'provenance.json', provenance)
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0', '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror', '-nostdlib', '-static', '-Wl,--build-id=none', '-Wl,--gc-sections', '-T', prep/'replay.ld']
    maps = {}
    for backend in ('soc', 'spike'):
        dest = OUT / backend
        dest.mkdir()
        main_c = dest / (NAME + '_main.c')
        oldmain = old / backend / (OLDNAME + '_main.c')
        pin(oldmain)
        main_c.write_text(oldmain.read_text().replace(OLDNAME, NAME))
        elf = dest / (NAME + '.elf')
        base.command([base.CC, *flags, *defs, *(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []), '-I'+str(original), case/'case.c', original/'scenario.S', main_c, prep/'startup.S', prep/'runtime.c', '-lgcc', '-o', elf], dest/(NAME+'.compile.log'))
        objdump = base.CC.with_name(base.CC.name.removesuffix('gcc')+'objdump')
        nm = base.CC.with_name(base.CC.name.removesuffix('gcc')+'nm')
        pin(objdump.resolve()); pin(nm.resolve())
        dis = elf.with_suffix('.dis')
        base.command([objdump, '-d', elf], dis)
        syms = {n:a for a, _, n in (line.split() for line in subprocess.check_output([nm, elf], text=True).splitlines())}
        save(dest/(NAME+'.symbols.json'), syms)
        blocks = instruction_blocks(dis.read_text())
        linux = Path(parent['original_elf']).read_bytes()
        for helper, insns in blocks.items():
            sequence = b''.join(bytes.fromhex(code)[::-1] for _, code, _ in insns)
            need(linux.count(sequence) == 1, 'helper not byte-identical in archived Linux ELF: '+helper)
        need(len(blocks['op_0']) == 16, 'op0 instruction count')
        targets = [(pc, code, asm) for pc, code, asm in blocks['op_0'] if asm.startswith('vmfeq.vv')]
        need(len(targets) == 1 and targets[0][1] == '62881457', 'wrong target opcode')
        maps[backend] = dict(elf_sha256=sha(elf), helpers=blocks, target=targets[0], return_pc=blocks['op_0'][-1][0], symbols=syms)
        save(dest/'programs.json', dict(schema_version=1, programs={NAME:dict(path=str(elf), sha256=sha(elf), cases=[NAME], pass_markers=markers)}, prepared=str(prep), provenance_sha256=sha(prep/'provenance.json'), backend='spike-htif' if backend=='spike' else 'vcs-soc'))
    save(OUT/'address_map.json', maps)

    # Read-only debugger checkpoints: no firmware instrumentation or added instructions.
    dest = OUT/'spike'; m = maps['spike']; syms = m['symbols']
    commands = ['until pc 0 '+syms['_start'], 'reg 0 minstret']
    target_regs = ('vl', 'vstart', 'vtype', 'fflags', 'a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7')
    for row in ledger:
        commands += ['until pc 0 '+m['target'][0], 'pc 0', 'insn 0']
        commands += ['reg 0 '+r for r in target_regs]
        for symbol, size in (('a',1024), ('b',1024), ('mask',128)):
            commands += [f'mem {int(syms[symbol],16)+off:x}' for off in range(0,size,8)]
        commands += ['rs 1', 'reg 0 fflags', 'reg 0 vstart', 'until pc 0 '+m['return_pc'], 'reg 0 a0']
        commands += [f'mem {int(syms["output"],16)+off:x}' for off in range(0,130,8)]
        commands += ['rs 1']
    commands += ['until pc 0 '+syms['replay_exit'], 'reg 0 minstret', 'reg 0 a0', 'str '+syms['replay_log'], 'rs']
    debug = dest/(NAME+'.cmd'); debug.write_text('\n'.join(commands)+'\n')
    log = dest/(NAME+'.spike.log')
    started = time.monotonic()
    base.command([base.SPIKE, '-d', '--debug-cmd='+str(debug), '--isa='+ISA, '-m2', dest/(NAME+'.elf')], log, 120)
    elapsed = time.monotonic()-started
    text = log.read_text()
    need(accepted(text, markers), 'Spike original full oracle/exit markers')
    values = iter(int(v,16) for v in re.findall(r'^0x([0-9a-f]+)$', text, re.M))
    start_retired = next(values)
    table = [int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)', (original/'fixtures.h').read_text().splitlines()[0])]
    need(len(table)==16, 'fixture inputs')
    summaries = []
    def memory(size):
        return b''.join(next(values).to_bytes(8,'little') for _ in range((size+7)//8))[:size]
    for call, row in enumerate(ledger,1):
        need(next(values) == int(m['target'][0],16), 'actual target PC')
        regs = dict(zip(target_regs, (next(values) for _ in target_regs)))
        expected_regs = dict(vl=row['vl'], vstart=0, vtype=11, fflags=row['sticky'], a0=int(syms['a'],16), a1=int(syms['b'],16), a2=int(syms['output'],16)+1, a3=row['vl'], a4=512, a5=int(syms['mask'],16), a6=0, a7=row['sticky'])
        need(regs == expected_regs, f'call{call} setup')
        av = memory(1024); bv = memory(1024); masks = memory(128)
        aa = [int.from_bytes(av[i:i+2],'little') for i in range(0,1024,2)]
        bb = [int.from_bytes(bv[i:i+2],'little') for i in range(0,1024,2)]
        need(aa == [table[i%16] for i in range(512)] and bb == [table[(3*i)%16] for i in range(512)], f'call{call} input arrays')
        need(masks == bytes([255,170,36,0][row['mask']])*128, f'call{call} loaded predicate')
        flags = row['sticky']
        wanted = []
        for a,b in zip(aa,bb):
            nan_a=(a&0x7c00)==0x7c00 and bool(a&1023)
            nan_b=(b&0x7c00)==0x7c00 and bool(b&1023)
            snan=(nan_a and not a&512) or (nan_b and not b&512)
            wanted.append((int(not(nan_a or nan_b) and (a==b or not((a|b)&0x7fff))),16 if snan else 0))
        for _, f in wanted[:row['vl']]: flags |= f
        need(next(values)==flags and next(values)==0 and next(values)==flags<<32, f'call{call} actual flags/status')
        output = memory(130)
        need(output[0]==output[65]==91 and output[66:]==bytes([91])*64, f'call{call} guards/untouched memory')
        for i,(bit,f) in enumerate(wanted):
            actual=(output[1+i//8]>>(i%8))&1
            oldbit=(aa[i//16]>>(i%16))&1
            allowed={bit} if i<row['vl'] else {oldbit} if row['vl']==0 else {oldbit,1,bit}
            need(actual in allowed, f'call{call} result bit{i}')
        summaries.append(dict(call=call, tuple=row, flags=flags, returned_vstart=0, output_hex=output.hex(), checked_bits=512, checked_guards=2))
    end_retired = next(values); exit_code = next(values)
    need(exit_code==0 and next(values,None) is None, 'Spike exit/checkpoint cardinality')
    need(len(re.findall(r'^0x0000000062881457 vmfeq.vv v8, v8, v16$', text, re.M))==50, 'actual opcode checkpoints')
    need(summaries[-1]['output_hex'][2:130]=='01'*64, 'call50 full result')
    save(OUT/'reference_calls.json', summaries)
    retired = end_retired-start_retired
    reference = dict(status='PASS_50_ORIGINAL_PREFIX_HOST_SPIKE_NOT_DUT', isa=ISA, calls=50, predecessors=49, capacity=512, result_bits=25600, guard_checks=100, returned_vstart_checks=50, flags_checks=50, source_values_checked=51200, predicate_bytes_checked=6400, start_minstret=start_retired, exit_minstret=end_retired, retired=retired, actual_process_returncode=0, firmware_exit_code=exit_code, spike_elapsed_s=elapsed, debugger_checkpoints_only=True, raw_log_sha256=sha(log), elf_sha256=maps['spike']['elf_sha256'], no_dut=True)
    save(OUT/'reference.json', reference)
    rates=[696.459657,702.001894]
    save(OUT/'budget.json',dict(reference_retired=retired, calibration='Existing M4 authentic130 prefixes, TERMINAL08.md; not M6 runtime measurement', retired_per_second=rates, estimates_s=[retired/r for r in rates], conservative_273_rate_s=retired/273, proposed_case_limit_s=5400, hard_user_limit_s=10800, caveat='Estimates only; no deadline increase or launch authorized'))
    need(all(sha(Path(p))==h for p,h in pins.items()), 'input pins changed')
    save(OUT/'input_pins.json', pins)
    artifacts={str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file()}
    save(OUT/'artifact_pins.json', artifacts)
    save(HERE/'READY.json', dict(status='READY_FOR_REVIEW_50_ORIGINAL_CALLS_NOT_DUT', scope='M6 first50 only, not682/full parent/Linux', reference=reference, soc_manifest=str(OUT/'soc/programs.json'), soc_elf_sha256=maps['soc']['elf_sha256'], original_elf_sha256=parent['sha256'], m6_image_sha256=IMAGE_SHA, input_pins_sha256=sha(OUT/'input_pins.json'), artifact_pins_sha256=sha(OUT/'artifact_pins.json'), input_pins_unchanged=True, no_dut_launched=True))
    print(json.dumps(read(HERE/'READY.json')),flush=True)


if __name__ == '__main__':
    main()
