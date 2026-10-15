#!/usr/bin/env python3
"""Prepare one authentic vfmerge prefix; host/Spike only, no DUT entrypoint."""
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE / 'prepared01'
CAMP = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
ARCH = CAMP / 'rvv_fp_move_partitions02/op0'
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
BASE = HERE.parent / 'integration'
NAME = 'rvv_fp_move_restart_e16_m8_ops0'
IDENTITY = 'fp_merge_prefix195'
ELF_SHA = 'd8abfc1bfebe188b1045a786e2ce17ba571e523c363b365ed28b805c99881710'
MANIFEST_SHA = 'b5c396ee64342bd1b3f3e9202f178fe204a46cce26b2082eb1cb8d5da8919102'
REPORT_SHA = '5a5769d0e3355c26a8b2eaffc2f3e06e3a6d34ca910dd0baae4904cf7d7739d0'
OLD_CC = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
DEFS = ['-DSEW=16', '-DRESTART_MOVES=1', '-DDETAIL_MOVES=0', '-DMOVE_OP_MASK=1']
COMMON = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-nostdlib', '-static', '-ffreestanding',
          '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
          '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wall', '-Wextra', '-Werror']


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def command(args, log, timeout=60):
    args = list(map(str, args))
    started = time.monotonic()
    env = dict(os.environ, TMPDIR=str(OUT / 'tmp'))
    with log.open('xb') as stream:
        result = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT,
                                timeout=timeout, env=env)
    record = dict(argv=args, returncode=result.returncode, elapsed_s=time.monotonic() - started,
                  timeout_s=timeout, log_sha256=sha(log))
    save(log.with_suffix(log.suffix + '.command.json'), record)
    require(result.returncode == 0, 'Command failed: ' + str(log))
    return record


def assigned(text, name):
    node, = [n for n in ast.parse(text).body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    return ast.literal_eval(node.value)


def adapt(source):
    start, end = source.index('static long syscall3('), source.index('static void text(')
    require(source[start:end].count('ecall') == 1, 'Unknown syscall wrapper')
    port = source[:start] + 'extern long replay_write(long,long,long,long);\n#define syscall3 replay_write\n' + source[end:]
    for before, after, count in (
        ('void probe_main(void)', 'int fp_merge_prefix195_main(void)', 1),
        ('syscall3(94,2,0,0);for(;;){}', 'return 2;', 2),
        ('syscall3(29,1,0x5409,1)', '0 /* No Linux tty drain in bare metal. */', 1),
        ('syscall3(94,errors ? 1:0,0,0);for(;;){}', 'return errors ? 1:0;', 1)):
        require(port.count(before) == count, 'Runtime adaptation drift: ' + before)
        port = port.replace(before, after)
    port, n = re.subn(r'__asm__\("\.global _start.*?\);\s*$', '', port, flags=re.S)
    require(n == 1 and 'ecall' not in port and 'syscall3(29' not in port, 'Unadapted startup/service')
    return port


def sequence():
    rows = []
    for seed in range(3):
        for scalar in range(16):
            for invalid in range(2):
                for l, vl in enumerate((0, 1, 2, 3, 256, 511, 512)):
                    for mode in range(4):
                        for st, start in enumerate((1, vl // 2, vl, 511)):
                            for sticky in range(2):
                                rows.append(dict(index=len(rows), seed=seed, scalar=scalar, invalid=invalid,
                                    op=0, length_index=l, vl=vl, mode=mode, start_index=st,
                                    vstart=start, sticky=sticky))
    return rows


def decode_capture(path, rows, bits):
    raw = path.read_bytes()
    size = 48 + 1024 + 1028 + 128
    require(len(raw) == 195 * size, 'Host capture cardinality')
    for i, row in enumerate(rows[:195]):
        chunk = raw[i * size:(i + 1) * size]
        header = struct.unpack_from('<6Q', chunk)
        require(header == (0, row['vl'], 512, (row['sticky'] << 32) | row['vstart'],
                           0xffffffffffff0000 | bits[0], 0x123456789abcdef0), 'Host call mapping')
        aa = struct.unpack_from('<512H', chunk, 48)
        oo = struct.unpack_from('<514H', chunk, 1072)
        require(aa == tuple(bits[x % 16] for x in range(512)), 'Source input drift')
        require(oo == (0x5b, *[bits[(x * 3 + 11) % 16] for x in range(512)], 0x5b), 'Destination input drift')
        require(chunk[-128:] == bytes([(255, 0xaa, 0x24, 0)[row['mode']]]) * 128, 'Mask input drift')


def disassemble(elf):
    objdump = CC.with_name(CC.name.removesuffix('gcc') + 'objdump')
    nm = CC.with_name(CC.name.removesuffix('gcc') + 'nm')
    command([objdump, '-d', elf], elf.with_suffix('.dis'))
    text = elf.with_suffix('.dis').read_text()
    output = subprocess.check_output([str(nm), str(elf)], text=True)
    symbols = {n: int(a, 16) for a, _, n in (line.split() for line in output.splitlines() if len(line.split()) == 3)}
    save(elf.with_suffix('.symbols.json'), {n: hex(a) for n, a in symbols.items()})
    block = text.split('<op_0>:\n', 1)[1].split('\n\n', 1)[0]
    insns = re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+([^\n]+)', block, re.M)
    target, = [x for x in insns if x[2].startswith('vfmerge.vfm')]
    ret, = [x for x in insns if x[2].strip() == 'ret']
    return symbols, insns, dict(pc=target[0], opcode=target[1], instruction=target[2], return_pc=ret[0])


def main():
    require(not OUT.exists(), 'Fresh preparation only; preserve previous evidence')
    manifest = json.loads((ARCH / 'manifest.json').read_text())
    require(sha(ARCH / 'manifest.json') == MANIFEST_SHA, 'Manifest identity')
    entry, = [c for c in manifest['cases'] if c['name'] == NAME]
    require(entry['sha256'] == ELF_SHA and entry['operation_ids'] == [0] and entry['configurations'] == 21504,
            'Wrong archived partition')
    for name, digest in manifest['source_sha256'].items():
        require(sha(SOURCE / name) == digest, 'STOP: source provenance uncertain: ' + name)
    original_elf = ARCH / 'overlay/opt/ara-tests' / NAME
    release_elf = ARCH.parent / 'release/binaries' / NAME
    require(sha(original_elf) == sha(release_elf) == ELF_SHA, 'Original ELF identity')
    report_path = CAMP / 'rvv_failure_retest01/supervisor44/terminal_recovery257.json'
    require(sha(report_path) == REPORT_SHA, 'Historical report identity')
    report = json.loads(report_path.read_text())
    observed, = [x for x in report['report']['results'] if x['name'] == NAME]
    rows = sequence()
    require(len(rows) == 21504 and rows[194] == dict(index=194, seed=0, scalar=0, invalid=0,
        op=0, length_index=6, vl=512, mode=0, start_index=1, vstart=256, sticky=0), 'Prefix mapping')
    printed = re.findall(r'RVV_FP_MOVE_TRIAL vl=(\d+) vstart=(\d+) completed=(\d+)', observed['output'])
    wanted = [(str(x['vl']), str(x['vstart']), str(x['index'])) for x in rows[:195]
              if x['mode'] == 0 and x['sticky'] == 0]
    require(printed == wanted, 'Archived completed194 print sequence differs')
    OUT.mkdir()
    for sub in ('original', 'host', 'soc', 'spike', 'tmp'):
        (OUT / sub).mkdir()
    original = OUT / 'original'
    pins = {}
    def pin(path):
        pins[str(path.resolve())] = sha(path)
    for path in (Path(__file__), HERE / 'host_model.c', ARCH / 'manifest.json', original_elf,
                 release_elf, report_path, CC.resolve(), OLD_CC.resolve(), SPIKE.resolve(), Path('/usr/bin/gcc').resolve()):
        pin(path)
    for name in manifest['source_sha256']:
        pin(SOURCE / name)
        shutil.copyfile(SOURCE / name, original / name)
    for src, dest in ((ARCH / (NAME + '.S'), 'scenario.S'), (ARCH / 'e16/inputs.h', 'inputs.h'),
                      (ARCH / 'e16/operations.h', 'operations.h'), (ARCH / 'manifest.json', 'manifest.json')):
        pin(src)
        shutil.copyfile(src, original / dest)
    gen = (original / 'fp_moves.py').read_text()
    fn, = [n for n in ast.parse(gen).body if isinstance(n, ast.FunctionDef) and n.name == 'assembly']
    ns = dict(OPS=assigned(gen, 'OPS'))
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<archived-assembly-function>', 'exec'), ns)
    require(ns['assembly'](16, 'm8', True) == (original / 'scenario.S').read_text(), 'Generated assembly identity')
    bits = assigned((original / 'floating.py').read_text(), 'BITS')[16]
    inputs = 'static const word inputs[16]={' + ','.join('UINT64_C(0x%x)' % x for x in bits) + '};\n'
    header = '\n'.join('extern unsigned long op_%d(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long,void *);' % i
                       for i in range(8)) + '\n#define FUNCTIONS ' + ','.join('op_%d' % i for i in range(8)) + '\n'
    require((original / 'inputs.h').read_text() == inputs and (original / 'operations.h').read_text() == header,
            'Generated header identity')
    rebuilt = original / 'original_rebuilt.elf'
    command([OLD_CC, *COMMON, '-Wl,-s', *DEFS, '-I' + str(original), original / 'fp_move_oracle.c',
             original / 'scenario.S', '-o', rebuilt], original / 'rebuild.log')
    require(sha(rebuilt) == ELF_SHA, 'STOP: original ELF rebuild not byte-identical')
    source = (original / 'fp_move_oracle.c').read_text()
    point = '        ++cases;\n    }\n'
    require(source.count(point) == 1, 'Unknown case increment')
    prefix = source.replace(point, '        ++cases;\n        if(cases==195)goto prefix_done;\n    }\nprefix_done:\n')
    port, full = adapt(prefix), adapt(source)
    oracle = source[source.index('        unsigned long control='):source.index('        ++cases;')]
    require(oracle in port, 'Original call/oracle changed')
    (OUT / 'prefix.c').write_text(prefix)
    (OUT / 'case.c').write_text(port)
    (OUT / 'runtime_only_full.c').write_text(full)
    for label, before, after in (('prefix', source, prefix), ('runtime', prefix, port)):
        (OUT / (label + '.diff')).write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
            fromfile=label + '_before', tofile=label + '_after')))
    save(OUT / 'call_sequence.json', rows[:195])
    save(OUT / 'identity.json', dict(original_name=NAME, original_elf_sha256=ELF_SHA,
        manifest_sha256=MANIFEST_SHA, original_source_sha256=manifest['source_sha256'],
        byte_identical_original_rebuild=True, source_status='HASH_EXACT_ARCHIVED_SOURCE',
        full_partition_calls=21504, prefix_calls=195, boundary=rows[194], prior_call=rows[193],
        completed_counter_semantics='Printed before call; ++cases follows complete original oracle',
        observed_trial_lines=len(printed), historical_report=str(report_path), report_sha256=REPORT_SHA,
        original_target_pc='0x10666', original_target_opcode='5c805c57',
        oracle_sha256=hashlib.sha256(oracle.encode()).hexdigest(),
        scope='Original ops0 partition prefix, not full parent, Linux replay, or DUT acceptance'))
    print('PROVENANCE_AND_PREFIX_MAPPING_PASS', flush=True)
    host_results = []
    for label, body, count, mutation in [('full', full, 21504, 0), ('prefix', port, 195, 0)] + [
            ('negative%d' % i, port, 195, i) for i in range(1, 10)]:
        c = OUT / 'host' / (label + '.c')
        c.write_text(body + '\n' + (HERE / 'host_model.c').read_text())
        binary = c.with_suffix('')
        command(['/usr/bin/gcc', '-O2', '-Wall', '-Wextra', '-Werror', *DEFS,
                 '-DHOST_CALLS=' + str(count), '-DHOST_MUTATION=' + str(mutation),
                 '-I' + str(original), c, '-o', binary], c.with_suffix('.compile.log'))
        args = [str(binary)] + ([str(binary.with_suffix('.capture'))] if not mutation else [])
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        log = binary.with_suffix('.log')
        log.write_text(result.stdout + result.stderr)
        if mutation:
            require(result.returncode == 1 and 'RVV_FP_MOVE_FAIL' in result.stdout and 'RVV_FP_MOVE_DETAIL' in result.stdout,
                    'Host negative not rejected: ' + label)
        else:
            require(result.returncode == 0 and f'RVV_FP_MOVE_PASS sew=16 cases={count} errors=0' in result.stdout
                    and 'FAIL' not in result.stdout, 'Host positive failed: ' + label)
            decode_capture(binary.with_suffix('.capture'), rows, bits)
        host_results.append(dict(name=label, returncode=result.returncode, calls=count,
            status='EXPECTED_REJECTION' if mutation else 'PASS', log_sha256=sha(log), argv=args))
    require((OUT / 'host/full.capture').read_bytes() == (OUT / 'host/prefix.capture').read_bytes(), 'Predecessor input sequence differs')
    save(OUT / 'host.json', dict(status='PASS_FULL_MODEL_PREFIX_EQUIVALENCE_9_NEGATIVES', results=host_results,
        identical_prefix_capture_sha256=sha(OUT / 'host/prefix.capture'),
        limitation='Independent integer bit-move model, not hardware or instruction execution'))
    print('HOST_FULL21504_PREFIX195_9NEGATIVE_PASS', flush=True)
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        pin(BASE / name)
        shutil.copyfile(BASE / name, OUT / name)
    wrapper = ('extern int fp_merge_prefix195_main(void);\nextern void replay_text(const char*);\n'
        'int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));'
        'if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}'
        'if(fp_merge_prefix195_main()){replay_text("BOARD_CASE_FAIL fp_merge_prefix195\\n");return 1;}'
        'replay_text("BOARD_CASE_PASS fp_merge_prefix195\\nBOARD_REPLAY_PASS\\n");return 0;}\n')
    (OUT / 'main.c').write_text(wrapper)
    programs = {}
    operation_bytes = None
    for backend in ('soc', 'spike'):
        elf = OUT / backend / (IDENTITY + '.elf')
        command([CC, *COMMON, '-mcmodel=medany', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
                 '-T', OUT / 'replay.ld', *DEFS, *(['-DSPIKE_REFERENCE=1'] if backend == 'spike' else []),
                 '-I' + str(original), OUT / 'case.c', original / 'scenario.S', OUT / 'main.c',
                 OUT / 'startup.S', OUT / 'runtime.c', '-lgcc', '-o', elf], elf.with_suffix('.compile.log'))
        symbols, insns, target = disassemble(elf)
        raw = bytes.fromhex(''.join(x[1] for x in insns))
        if operation_bytes is None:
            operation_bytes = raw
        require(operation_bytes == raw, 'Operation instructions differ between backends')
        # Instruction encodings in objdump are big-endian text; ELF stores each little-endian.
        encoded = b''.join(bytes.fromhex(x[1])[::-1] for x in insns)
        require(original_elf.read_bytes().count(encoded) == 1, 'Original op0 instruction body differs')
        require(target['opcode'] == '5c805c57', 'Wrong target instruction')
        programs[backend] = dict(path=str(elf), sha256=sha(elf), calls=195, target=target,
            pass_markers=['RVV_FP_MOVE_PASS sew=16 cases=195 errors=0',
                          'BOARD_CASE_PASS fp_merge_prefix195', 'BOARD_REPLAY_PASS'])
        if backend == 'spike':
            debug = elf.with_suffix('.cmd')
            commands = [f'until pc 0 {symbols["_start"]:x}', 'reg 0 minstret']
            for _ in rows[:195]:
                commands += ['until pc 0 ' + target['pc'], 'reg 0 vl', 'reg 0 vstart', 'reg 0 fflags',
                             'reg 0 a6', 'freg 0 ft0', 'rs 1', 'reg 0 vstart', 'reg 0 fflags',
                             'until pc 0 ' + target['return_pc'], 'reg 0 a0', 'reg 0 fflags', 'rs 1']
            commands += [f'until pc 0 {symbols["replay_exit"]:x}', 'reg 0 minstret', 'reg 0 a0',
                         f'str {symbols["replay_log"]:x}', 'rs']
            debug.write_text('\n'.join(commands) + '\n')
            log = elf.with_suffix('.spike.log')
            cost = command([SPIKE, '-d', '--debug-cmd=' + str(debug), '--isa=rv64gcv_zvfh_zvl1024b', '-m2', elf], log, 120)
            text = log.read_text()
            values = [int(x, 16) for x in re.findall(r'^0x([0-9a-f]+)$', text, re.M)]
            require(len(values) == 1 + 195 * 9 + 2, 'Unexpected Spike debugger output cardinality')
            for i, row in enumerate(rows[:195]):
                v = values[1 + i * 9:1 + (i + 1) * 9]
                require(v[:4] == [row['vl'], row['vstart'], row['sticky'], (row['sticky'] << 32) | row['vstart']],
                        'Spike target input state differs')
                require(v[4] & ((1 << 64) - 1) == 0xffffffffffff0000, 'Spike scalar boxing differs')
                require(v[5:] == [0, row['sticky'], row['sticky'] << 32, 0], 'Spike output/restore fflags or vstart differs')
            require(values[-1] == 0 and values[-2] > values[0] and all(text.splitlines().count(m) == 1
                    for m in programs[backend]['pass_markers']) and not re.search(r'FAIL|DETAIL|TRAP', text), 'Spike oracle/exit failure')
            save(OUT / 'reference.json', dict(status='SPIKE_PREFIX195_PASS_NOT_DUT', **cost,
                start_minstret=values[0], exit_minstret=values[-2], retired=values[-2] - values[0],
                target_calls_observed=195, per_call_debug_fields=['vl', 'vstart', 'fflags', 'control', 'boxed_ft0',
                    'post_vstart', 'post_fflags', 'returned_status', 'restored_fflags'],
                exit_a0=values[-1], boundary=rows[194], elf_sha256=sha(elf),
                limit='Spike retire count is not DUT cycles/runtime; no DUT timeout or launch approved'))
    save(OUT / 'programs.json', programs)
    for path, digest in pins.items():
        require(sha(Path(path)) == digest, 'External input changed during preparation')
    for path in sorted(OUT.rglob('*')):
        if path.is_file():
            pin(path)
    save(OUT / 'pins.json', pins)
    save(OUT / 'complete.json', dict(status='PREPARED_HOST_SPIKE_PREFIX195_PASS_NOT_DUT', pins_sha256=sha(OUT / 'pins.json'),
        pin_count=len(pins), original_elf_sha256=ELF_SHA, calls=195, original_partition_calls=21504,
        VCS_started=False, RTL_modified=False, reference=OUT.joinpath('reference.json').name,
        scope='Prefix of authentic ops0 partition only; not full parent, full21504, Linux or DUT acceptance'))
    print('PREPARED_HOST_SPIKE_PREFIX195_PASS_NOT_DUT', flush=True)


if __name__ == '__main__':
    main()
