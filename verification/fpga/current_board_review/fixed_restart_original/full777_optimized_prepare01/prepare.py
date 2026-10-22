#!/usr/bin/env python3
"""One bounded reference of a scalar-only optimization of the genuine full777."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.parent
sys.path.insert(0, str(OLD))
spec = importlib.util.spec_from_file_location('original_full777', OLD / 'prepare.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
OUT = HERE / 'prepared01'
sha, save, require = original.sha, original.save, original.require


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Input drift: ' + path)


def execute(command, log, expected=0, limit=90, file_limit=None):
    command = list(map(str, command))
    save(log.with_suffix('.command.json'), dict(command=command, timeout_s=limit, expected_rc=expected))
    def limits():
        if file_limit:
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
    start = time.monotonic()
    with log.open('x') as stream:
        child = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                               timeout=limit, preexec_fn=limits)
    receipt = dict(actual_returncode=child.returncode, elapsed_s=time.monotonic()-start,
                   command_sha256=sha(log.with_suffix('.command.json')), log_sha256=sha(log))
    save(log.with_suffix('.exit.json'), receipt)
    require(child.returncode == expected, 'Unexpected child rc: ' + str(log))
    return receipt


def make_expected():
    calls = original.expected()[1]
    state, a, b = 0x937ad68de41c725f, [], []
    for i in range(512):
        state ^= (state << 13) & ((1 << 64)-1)
        state ^= state >> 7
        state ^= (state << 17) & ((1 << 64)-1)
        x, y = state & 255, (state >> 19) & 255
        if i % 8 == 0: x = y = 0
        elif i % 8 == 1: x, y = 255, 1
        elif i % 8 == 2: x, y = 128, 255
        elif i % 8 == 3: y = 8
        a.append(x); b.append(y)
    unique, indices, saturations, full = [], [], [], []
    for row in calls:
        result = bytearray([0x5b] * 514)
        sat = row['initial_vxsat']
        mask = bytearray(128)
        for i in range(512):
            mode = row['mask']
            active = mode == 0 or (mode == 1 and i % 2) or (mode == 2 and i % 7 == 2)
            if active: mask[i//8] |= 1 << (i % 8)
            if not (active and row['vstart'] <= i < row['vl']): continue
            x = a[i] if a[i] < 128 else a[i]-256
            y = b[i] if b[i] < 128 else b[i]-256
            q, r = divmod(x*y, 128)
            rm = row['vxrm']
            q += int((rm == 0 and r >= 64) or (rm == 1 and (r > 64 or (r == 64 and q & 1))) or
                     (rm == 3 and r != 0 and not q & 1))
            if q > 127: q, sat = 127, 1
            result[i+1] = q & 255
        raw = bytes(result)
        if raw not in unique: unique.append(raw)
        indices.append(unique.index(raw)); saturations.append(sat)
        full.append(dict(row, expected_hex=raw.hex(), expected_vxsat=sat, mask_hex=mask.hex(),
                         a_hex=bytes(a).hex(), b_hex=bytes(b).hex()))
    lines = ['static const uint64_t expected_blocks[][65] = {']
    for raw in unique:
        padded = raw + bytes(6)
        lines.append('{' + ','.join('UINT64_C(0x%016x)' % int.from_bytes(padded[i:i+8], 'little')
                                    for i in range(0, 520, 8)) + '},')
    lines += ['};', 'static const uint16_t expected_index[777] = {' + ','.join(map(str, indices)) + '};',
              'static const uint8_t expected_sat[777] = {' + ','.join(map(str, saturations)) + '};']
    return '\n'.join(lines)+'\n', full, len(unique)


def body(dis, name):
    part = dis.split('<' + name + '>:\n', 1)[1].split('\n\n', 1)[0]
    return [dict(pc=int(m[1],16), insn=int(m[2],16), asm=m[3]) for m in
            re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(.+)$', part, re.M)]


def prepare():
    pins = json.loads((OLD / 'prepared01/pins.json').read_text())
    verify(pins)
    OUT.mkdir(exist_ok=False)
    p = OUT / 'prepared'
    (p / 'original').mkdir(parents=True)
    oldp = OLD / 'prepared01/prepared'
    for name in ('startup.S', 'runtime.c', 'replay.ld', 'main.c'):
        shutil.copyfile(oldp / name, p / name)
    for name in ('scenario.S', 'operations.h', 'successor_oracle.c'):
        shutil.copyfile(oldp / 'original' / name, p / 'original' / name)
    before = (oldp / 'case.c').read_text()
    (p / 'original_case.c').write_text(before)
    header, calls, unique = make_expected()
    (p / 'expected.h').write_text(header)
    save(OUT / 'calls.json', calls)
    after = original.replace(before, 'static word a[1024], b[1024], out[1026];',
        'static word a[1024], b[1024], out[1026] __attribute__((aligned(8)));')
    after = original.replace(after, 'int fixed_main(void) {',
        '#include "expected.h"\n' + (HERE / 'packed.h').read_text() + '\nint fixed_main(void) {')
    after = original.replace(after, 'if(!cap || cap>1024)', 'if(cap!=512)')
    first = '                    for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;'
    last = '                        out[i+1]=initial_destination(accumulator,i);'
    begin, end = after.index(first), after.index(last) + len(last)
    after = after[:begin] + '                    full_init();' + after[end:]
    begin, end = after.index('                    unsigned packed=0;'), after.index('                    ++checks;')
    after = after[:begin] + '''                    if(full_oracle(checks))
                        failure(op,seed,vl,mode,start,cap,0,1);
                    elements += cap;
                    if((vs>>32)!=expected_sat[checks])
                        failure(op,seed,vl,mode,start,cap+3,expected_sat[checks],vs>>32);
''' + after[end:]
    # Retain original scalar routines as source evidence, without unused warnings.
    after = after.replace('static word initial_destination(', 'static __attribute__((unused)) word initial_destination(')
    after = after.replace('static word extra_value(', 'static __attribute__((unused)) word extra_value(')
    after = after.replace('static const unsigned kinds[]', 'static const unsigned __attribute__((unused)) kinds[]')
    after = after.replace('                    word sentinel=(word)0x5b;', '')
    (p / 'case.c').write_text(after)
    (p / 'optimization.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                          fromfile='sealed_prefix777', tofile='scalar_optimized_full777')))
    host = OUT / 'host'; host.mkdir()
    flags = ['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror','-DSEW=8','-DFRACTIONAL_SUITE=1',
             '-DHOST_REFERENCE=1','-I'+str(p),'-I'+str(p/'original')]
    execute(flags + ['-ffunction-sections','-fdata-sections','-Wl,--gc-sections',
            HERE/'scalar_equivalence.c','-o',host/'scalar_equivalence'], host/'scalar_build.log')
    execute([host/'scalar_equivalence'], host/'scalar.log')
    want = original.expected()[0]
    for kind, file in (('original','original_case.c'),('optimized','case.c')):
        execute(flags + [p/file,OLD/'host_model.c','-o',host/kind], host/(kind+'_build.log'))
        execute([host/kind], host/(kind+'.log'))
        text = (host/(kind+'.log')).read_text()
        require([s for s in text.splitlines() if s.startswith('CALL ')] == want, 'All777 call/input/control equality')
        require(original.MARKER in text and 'HOST_END calls=777 injected=0 result=0' in text, 'Full original oracle')
    negatives = []
    for n, name in enumerate(('active','prestart','maskedoff','tail','left_guard','right_guard','vstart','lost_sticky','spurious_sat'),1):
        log = host/(name+'.log')
        execute([host/'optimized',str(n)], log, expected=1)
        text = log.read_text()
        require('RVV_MATRIX_FAIL' in text and 'HOST_END calls=777 injected=1 result=1' in text, 'Negative oracle '+name)
        negatives.append(name)
    save(host/'status.json', dict(status='HOST_EQUIVALENCE_PASS', calls=777, result_bytes=397824, guards=1554,
                                 unique_expected_rows=unique, negative_rejections=negatives,
                                 original_scalar_oracle_crosscheck=True, global_rng_order_unchanged=True))
    original.OUT = OUT
    original.build(p)
    olddis = (OLD/'prepared01/soc'/ (original.ID+'.dis')).read_text()
    identities = {}
    for backend in ('soc','spike'):
        dis = (OUT/backend/(original.ID+'.dis')).read_text()
        for name in ('capacity','op_0','op_1','op_2','op_3'):
            require([x['insn'] for x in body(dis,name)] == [x['insn'] for x in body(olddis,name)], 'Helper bytes '+name)
        instructions = [dict(pc=int(m[1],16), insn=int(m[2],16), asm=m[3]) for m in
                        re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(.+)$',dis,re.M)]
        allowed = {i['pc'] for name in ('capacity','op_0','op_1','op_2','op_3') for i in body(dis,name)}
        vector = [i for i in instructions if i['asm'].split()[0].startswith('v')]
        require(all(i['pc'] in allowed for i in vector), 'Added vector instruction')
        identities[backend] = dict(helper24=body(dis,'op_0'), full_oracle=body(dis,'full_oracle'),
                                   full_init=body(dis,'full_init'), vector_instruction_count=len(vector),
                                   no_new_vector_instructions=True)
    save(OUT/'code_identity.json', identities)
    verify(pins)
    local = [x for x in OUT.rglob('*') if x.is_file()] + [HERE/'prepare.py', HERE/'packed.h', HERE/'scalar_equivalence.c',
             OLD/'prepare.py', OLD/'host_model.c', OLD/'prepared01/pins.json', original.CC, original.SPIKE]
    pins.update({str(x):sha(x) for x in local})
    save(OUT/'input_pins.json', pins)
    save(OUT/'PREPARED.json', dict(status='HOST_AND_COMPILE_PASS_REFERENCE_NOT_RUN', pins_sha256=sha(OUT/'input_pins.json'),
                                 single_reference_instruction_bound=3000000, wall_s=120, file_bytes=256*1024**2,
                                 no_DUT=True))


def reference():
    pins = json.loads((OUT/'input_pins.json').read_text()); verify(pins)
    out = OUT/'reference01'; out.mkdir(exist_ok=False)
    symbols = json.loads((OUT/'spike/symbols.json').read_text())
    debug = out/'debug.cmd'
    debug.write_text(f'until pc 0 {symbols["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\nreg 0 mcycle\nstr {symbols["replay_log"]:x}\nrs\n')
    command = [original.SPIKE,'-d','--debug-cmd='+str(debug),'--isa='+original.ISA,'-m2',
               '--instructions=3000000','-l','--log-commits',OUT/'spike'/(original.ID+'.elf')]
    receipt = execute(command, out/'spike.log', limit=120, file_limit=256*1024**2)
    text = (out/'spike.log').read_text()
    values = re.findall(r'^0x([0-9a-f]{16})$', text, re.M)
    require(len(values)==3 and int(values[0],16)==0, 'Actual reference exit/counters')
    for marker in json.loads((OUT/'spike/programs.json').read_text())['programs'][original.ID]['pass_markers']:
        require(text.count(marker)==1, 'Reference marker '+marker)
    require(not re.search(r'FAIL|TRAP|Error|FATAL',text), 'Reference error veto')
    require('RVV_TRIAL seed=0 vl=512 mask=0 vstart=256 completed=776' in text, 'Full history boundary')
    verify(pins)
    save(out/'status.json', dict(status='SPIKE_PASS_NOT_DUT', **receipt, calls=777,
                               instructions_to_replay_exit=int(values[1],16), cycles_to_replay_exit=int(values[2],16),
                               isa=original.ISA, pins_unchanged=True, original_Linux_replay=False,
                               raw_bytes=(out/'spike.log').stat().st_size))
    print(json.dumps(json.loads((out/'status.json').read_text()),indent=2))


if __name__ == '__main__':
    require(len(sys.argv)==2 and sys.argv[1] in ('prepare','reference'), 'prepare|reference')
    globals()[sys.argv[1]]()
