#!/usr/bin/env python3
"""Prepare only two authentic e8m4 child prefixes; never launch a DUT."""
import difflib
import hashlib
import itertools
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import prepare_batch as base
from prepare_successor import SPIKE, symbol
from audit_accepted8 import instructions, archived_window, OBJDUMP

HERE = base.HERE
OUT = HERE / 'stall_prefix2_03'
C = base.CAMPAIGN
PART = C / 'rvv_permute_partitions01'
SOURCE = C / 'rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c'
SELECTED = ((1, 154), (20, 169))
BOUND = 98
CAP = 512
MAX_RETIRED = 5_000_000
MAX_LOG = 768 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    base.save(path, data)


def limit_log():
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_LOG, MAX_LOG))


def prefix(source, bound):
    require(bound == BOUND, 'e8m4 boundary must be98, not e8m8 boundary66')
    old = '            ++cases;\n'
    require(source.count(old) == 1, 'Ambiguous original statistics boundary')
    source = source.replace(old, old + f'            if(cases=={bound})goto prefix_done;\n')
    old = '    text(errors ? "RVV_PERMUTE_FAIL sew=":"RVV_PERMUTE_PASS sew=");'
    require(source.count(old) == 1, 'Original final statistics changed')
    return source.replace(old,
        f'prefix_done:\n    if(cases!={bound})++errors;\n'
        '    text(errors ? "RVV_GATHER_PREFIX_FAIL sew=":"RVV_GATHER_PREFIX_PASS sew=");')


def model(op):
    domain = [t for t in itertools.product(range(3), range(21), range(8),
              range(7), range(4), range(4)) if t[1] == op][:BOUND]
    require(domain[-1] == (0, op, 0, 6, 0, 1), 'Original ordinal/tuple mismatch')
    rng, data, idx8, idx16 = 0xe736815b449aec21, [], [], []
    for i in range(CAP):
        rng ^= (rng << 13) & ((1 << 64) - 1)
        rng ^= rng >> 7
        rng ^= (rng << 17) & ((1 << 64) - 1)
        index = (0, 1, CAP-1, CAP, CAP+1, rng % (CAP+32))[i % 6]
        data.append(rng & 255)
        idx8.append(index & 255)
        idx16.append(index)
    rows = []
    for ordinal, (seed, opcode, scalar_index, length, mode, trial) in enumerate(domain, 1):
        vl = (0, 1, 2, 3, CAP//2, CAP-1, CAP)[length]
        start = (1, vl//2, vl if vl <= 1023 else CAP-1, CAP-1)[trial]
        selected = [mode == 0 or (mode == 1 and i % 2 == 1) or
                    (mode == 2 and i % 7 == 2) for i in range(CAP)]
        predicate = [sum(int(selected[i]) << (i % 8)
                         for i in range(b*8, min(b*8+8, CAP))) if b*8 < CAP else 0
                     for b in range(128)]
        output = [91] * CAP
        for i in range(start, vl):
            if selected[i]:
                index = 0 if op == 1 else idx16[i]
                output[i] = data[index] if index < CAP else 0
        rows.append(dict(ordinal=ordinal, tuple=[seed, opcode, scalar_index, length, mode, trial],
                         vl=vl, vstart=start, scalar=0, mode=mode,
                         predicate=predicate, output=output))
    return dict(capacity=CAP, rows=rows, input=data, indices=idx8, indices16=idx16,
                fullcap_checks=CAP*BOUND, guard_checks=2*BOUND,
                final_tuple=rows[-1]['tuple'], original_stopped_tuple=None,
                exact_archived_stall_reproduction=False)


def array(name, values, ctype='unsigned char'):
    return 'static const '+ctype+' '+name+'[]={'+','.join(map(str, values))+'};\n'


def host_shim(name, op, evidence):
    rows = evidence['rows']
    fixture = ''.join(array(key, evidence[field], ctype) for key, field, ctype in (
        ('gold_input', 'input', 'unsigned char'), ('gold_idx8', 'indices', 'unsigned char'),
        ('gold_idx16', 'indices16', 'unsigned short')))
    fixture += array('gold_vl', [r['vl'] for r in rows], 'unsigned long')
    fixture += array('gold_start', [r['vstart'] for r in rows], 'unsigned long')
    fixture += array('gold_predicate', [v for r in rows for v in r['predicate']])
    fixture += array('gold_output', [v for r in rows for v in r['output']])
    body = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
FIXTURE
static unsigned calls, injected;
static const char *negative="none";
static void demand(int ok) { if(!ok)exit(90); }
unsigned long capacity(void) { return 512; }
long replay_write(long n,long fd,long ptr,long len) {
    demand(n==64 && fd==1 && len>=0);
    return (long)fwrite((const void *)ptr,1,(size_t)len,stdout);
}
static unsigned long mock(unsigned opcode,const void *input,const void *indices,void *output,
        unsigned long vl,unsigned long cap,const void *mask,unsigned long scalar,unsigned long start) {
    demand(opcode==OPCODE && calls<98 && cap==512 && scalar==0);
    unsigned j=calls++;
    demand(vl==gold_vl[j] && start==gold_start[j]);
    demand(!memcmp(input,gold_input,512));
    demand(!memcmp(indices,OPCODE==20 ? (const void *)gold_idx16 : (const void *)gold_idx8,
                   OPCODE==20 ? 1024 : 512));
    demand(!memcmp(mask,gold_predicate+j*128,128));
    unsigned char *d=output;
    demand(d[-1]==91 && d[512]==91);
    for(unsigned i=0;i<512;++i)demand(d[i]==91);
    memcpy(d,gold_output+j*512,512);
    if(!injected && strcmp(negative,"none")) {
        long at=-2;
        if(!strcmp(negative,"guard0"))at=-1;
        if(!strcmp(negative,"guard1"))at=512;
        if(!strcmp(negative,"prestart") && start)at=0;
        if(!strcmp(negative,"tail") && vl<512)at=(long)vl;
        if(!strcmp(negative,"active") || !strcmp(negative,"masked"))
            for(unsigned i=(unsigned)start;i<vl;++i) {
                int picked=(((const unsigned char *)mask)[i/8]>>(i%8))&1;
                if((picked && !strcmp(negative,"active")) ||
                   (!picked && !strcmp(negative,"masked"))) { at=(long)i; break; }
            }
        if(!strcmp(negative,"csr")) { injected=1; return 1; }
        if(at>=-1) { d[at]^=1; injected=1; }
    }
    return 0;
}
FUNCTIONS
extern int IDENTITY_main(void);
int main(int argc,char **argv) {
    if(argc==2)negative=argv[1];
    int rc=IDENTITY_main();
    demand(calls==98 && (!strcmp(negative,"none") || injected));
    printf("HOST_PREFIX_CALLS=%u INJECTED=%u\n",calls,injected);
    return rc;
}
'''
    functions = '\n'.join(
        'unsigned long op_%d(const void *a,const void *b,void *c,unsigned long d,unsigned long e,'
        'const void *f,unsigned long g,unsigned long h){return mock(%d,a,b,c,d,e,f,g,h);}' % (i, i)
        for i in range(21))
    return body.replace('FIXTURE', fixture).replace('OPCODE', str(op)).replace(
        'FUNCTIONS', functions).replace('IDENTITY', name)


def host_checks(prepared, cases, models):
    out = OUT / 'host'
    out.mkdir()
    cc = Path('/usr/bin/gcc').resolve(strict=True)
    results = []
    for case in cases:
        name, op = case['id'], case['operation']
        folder = prepared / name
        source = (folder / 'case.c').read_text()
        csr = '__asm__ volatile("csrr %0,vlenb":"=r"(max_start));'
        require(source.count(csr) == 1, 'Host CSR replacement ambiguous')
        host = out / (name+'.host.c')
        host.write_text(source.replace(csr, 'max_start=128;'))
        shim = out / (name+'.shim.c')
        shim.write_text(host_shim(name, op, models[name]))
        elf = out / name
        command = [str(cc), '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-fno-tree-vectorize', '-DSEW=8', '-DRESTART_PERMUTATIONS=1',
                   '-DPERMUTE_OP_MASK='+str(1 << op), '-I'+str(folder/'original'),
                   str(host), str(shim), '-o', str(elf)]
        subprocess.run(command, check=True, timeout=30)
        tests = []
        for injection in ('none', 'active', 'prestart', 'masked', 'tail', 'guard0', 'guard1', 'csr'):
            run = subprocess.run([str(elf), injection], capture_output=True, text=True, timeout=15)
            log = out / (name+'.'+injection+'.log')
            log.write_text(run.stdout+run.stderr)
            expected = 0 if injection == 'none' else 1
            marker = 'RVV_GATHER_PREFIX_'+('PASS' if expected == 0 else 'FAIL')+' sew=8 cases=98 errors='
            require(run.returncode == expected and marker in run.stdout and
                    'HOST_PREFIX_CALLS=98' in run.stdout, name+': host gate '+injection)
            tests.append(dict(injection=injection, status='PASS', returncode=run.returncode,
                              log_sha256=base.sha(log)))
        results.append(dict(name=name, status='PASS', command=command, tests=tests,
            whole_rng_indices_masks_oracle_checked=True, expected_calls=98,
            expected_fullcap_checks=50176, expected_guards=196))
    save(out/'host_gate.json', dict(status='HOST_TWO_PREFIX_FULLORACLE_AND_14_NEGATIVES_PASS',
         compiler=str(cc), compiler_sha256=base.sha(cc), results=results,
         scope='Independent Python fixtures + actual original C oracle with host vector mocks; not DUT'))


def reference_trace(path, elf, name, model_data):
    routine = instructions(elf, name+'_op_'+str(model_data['rows'][0]['tuple'][1]))
    target, = [r for r in routine if r['text'].startswith(('vrgather.', 'vrgatherei16.'))]
    csr, = [r for r in routine if r['text'].startswith('csrr\ta0,vstart')]
    store, = [r for r in instructions(elf, 'replay_exit') if r['text'].startswith('sd\t')]
    output, _ = symbol(elf, 'output', OBJDUMP)
    log_address, _ = symbol(elf, 'replay_log', OBJDUMP)
    tohost, _ = symbol(elf, 'tohost', OBJDUMP)
    ram_log = bytearray(8192)
    regs, events, reads, current, returned, count, exited = {}, [], set(), None, 0, 0, False
    load_count = 0

    def complete():
        if current is not None:
            require(reads == set(range(CAP+2)), 'Incomplete cap-wide scalar reads/guards')

    pattern = re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    with path.open() as stream:
        for line in stream:
            match = pattern.match(line)
            if not match:
                continue
            pc, code = int(match[1], 16), int(match[2], 16)
            if pc < 0x80000000:
                continue
            count += 1
            require(count <= MAX_RETIRED, 'Reference retired budget exceeded')
            rest = match[3]
            write = re.search(r'\bmem\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s*$', rest)
            if write and code & 127 == 35:
                address, value = int(write[1], 16), int(write[2], 16)
                if ((code >> 12) & 7) == 0 and log_address <= address < log_address+8192:
                    ram_log[address-log_address] = value & 255
            rd = re.search(r'\bx(\d+)\s+(0x[0-9a-f]+)', rest)
            if pc == target['pc']:
                complete()
                j = len(events)
                require(j < BOUND and code == int(target['insn'], 16), 'Wrong target/count')
                current = model_data['rows'][j]
                require(regs.get(13) == current['vl'] and regs.get(14) == CAP and
                        regs.get(16) == 0 and regs.get(17) == current['vstart'], 'Actual tuple differs')
                events.append(dict(ordinal=j+1, retired=count, pc=hex(pc), insn=target['insn'],
                                   vl=regs[13], vstart=regs[17], scalar=regs[16],
                                   original_tuple=current['tuple']))
                reads = set()
            if pc == csr['pc']:
                require(rd and int(rd[1]) == 10 and int(rd[2], 16) == 0, 'vstart did not reset')
                returned += 1
            mem = re.search(r'\bmem\s+(0x[0-9a-f]+)\s*$', rest)
            if current is not None and rd and mem:
                address = int(mem[1], 16)
                if output <= address < output+CAP+2:
                    index = address-output
                    want = 91 if index in (0, CAP+1) else current['output'][index-1]
                    require(int(rd[2], 16) & 255 == want, 'Scalar oracle output read differs')
                    reads.add(index)
                    load_count += 1
            if rd:
                regs[int(rd[1])] = int(rd[2], 16)
            if pc == store['pc']:
                require(write and int(write[1], 16) == tohost and
                        int(write[2], 16) == 1, 'HTIF did not encode exit0')
                exited = True
                break
    complete()
    require(exited and len(events) == returned == BOUND, 'Incomplete target/return/exit gate')
    require(load_count >= (CAP+2)*BOUND, 'Missing scalar reads')
    return dict(firmware_retired_to_htif_store=count, boot_rom_retirement_excluded=5,
                target_hits=len(events), returned_vstart_zero=returned,
                fullcap_scalar_checks=CAP*BOUND, both_guard_checks=2*BOUND,
                actual_output_scalar_loads=load_count, events=events,
                reconstructed_runtime_console=ram_log.split(b'\0', 1)[0].decode('ascii'),
                htif_store_value=1,
                retired_counts_are_not_dut_cycles=True)


def main():
    require(not OUT.exists(), 'Fresh prefix preparation required; no overwrite/retry')
    manifest, triage = read(PART/'manifest.json'), read(C/'stall_family_triage02/triage.json')
    require(base.sha(SOURCE) == manifest['source_sha256']['permutation_oracle.c'] ==
            'b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca', 'Archived C drift')
    baseline = {str(p):base.sha(p) for p in (
        SOURCE, PART/'manifest.json', PART/'parent_mapping.json',
        C/'stall_family_triage02/triage.json', HERE/'STALL_PARENT_PLAN.md',
        HERE/'remainder75_01/vcs_candidate04_01/complete.json',
        HERE/'remainder75_01/review_ready.json', HERE/'acceptance_audit01/audit.json',
        Path(__file__), base.INTEGRATION/'prepare.py', Path(base.__file__))}
    OUT.mkdir()
    prepared = OUT/'prepared'
    prepared.mkdir()
    diffdir = OUT/'source_diffs'
    diffdir.mkdir()
    cases, models = [], {}
    sys.path.insert(0, str(base.INTEGRATION))
    from prepare import adapt
    for op, recovery in SELECTED:
        original_name = 'rvv_permute_restart_e8_m4_ops'+str(op)
        name = 'gather_prefix_e8_m4_ops'+str(op)
        case, = [x for x in manifest['cases'] if x['name'] == original_name]
        record, = [x for x in triage['cases'] if x['name'] == original_name]
        require(case['operation_ids'] == [op] and case['configurations'] == 2688 and
                case['sha256'] == record['elf_sha256'], 'Original child mapping differs')
        report_path = C/f'rvv_recovery08_{recovery}/terminal_scene/report.json'
        require(base.sha(report_path) == record['report_sha256'], 'Original report drift')
        report = read(report_path)
        require(next(x for x in report['results'] if x['name'] == original_name)['status'] == 'stalled',
                'Not authentic stalled child')
        snapshots = report['progress_diagnosis']['snapshots']
        require(snapshots[0]['core']['retired'] == snapshots[1]['core']['retired'] and
                record['last_trial'] is None, 'Archive stall/unknown-tuple evidence differs')
        original = prepared/name/'original'
        original.mkdir(parents=True)
        for p in (PART/original_name/'operations.S', PART/original_name/'operations.h',
                  PART/'release/binaries'/original_name, report_path,
                  report_path.parent/original_name):
            baseline[str(p)] = base.sha(p)
        require(baseline[str(PART/'release/binaries'/original_name)] == case['sha256'] and
                baseline[str(report_path.parent/original_name)] == case['sha256'], 'ELF alias drift')
        shutil.copyfile(SOURCE, original/'scenario.c')
        for f in ('operations.S', 'operations.h'):
            shutil.copyfile(PART/original_name/f, original/f)
        shutil.copyfile(PART/'release/binaries'/original_name, original/'original_linux.elf')
        save(original/'case.json', dict(case=case, archived_stall=record))
        adapted = adapt((original/'scenario.c').read_text(), name)
        port = prefix(adapted, BOUND)
        # The loop/setup/assembly/oracle body is not narrowed or otherwise changed.
        anchor = '            ++cases;\n'
        require(adapted[adapted.index('    for(unsigned seed='):adapted.index(anchor)+len(anchor)] ==
                port[port.index('    for(unsigned seed='):port.index(anchor)+len(anchor)],
                'Original predecessor calls/setup/oracle changed')
        (prepared/name/'case.c').write_text(port)
        for label, before, after in (('adapter', (original/'scenario.c').read_text(), adapted),
                                    ('prefix', adapted, port)):
            (diffdir/(name+'.'+label+'.diff')).write_text(''.join(difflib.unified_diff(
                before.splitlines(True), after.splitlines(True),
                fromfile=name+'/'+label+'_before.c', tofile=name+'/'+label+'_after.c')))
        models[name] = model(op)
        save(OUT/(name+'.host_expected.json'), models[name])
        cases.append(dict(id=name, operation=op, original_case=case,
            original_linux_elf_sha256=case['sha256'], archive_report_sha256=record['report_sha256'],
            source_directory=str(PART/original_name), original_stopped_tuple=None,
            exact11_stall_reproduction=False, prefix_calls=98, endpoint=[0,op,0,6,0,1],
            assembly='operations.S', defines=['SEW=8', 'RESTART_PERMUTATIONS=1',
                                           'PERMUTE_OP_MASK='+str(1 << op)],
            pass_markers=[f'BOARD_CASE_PASS {name}', 'BOARD_REPLAY_PASS',
                          'RVV_GATHER_PREFIX_PASS sew=8 cases=98 errors=0']))
    for f in ('runtime.c', 'startup.S', 'replay.ld'):
        baseline[str(base.INTEGRATION/f)] = base.sha(base.INTEGRATION/f)
        shutil.copyfile(base.INTEGRATION/f, prepared/f)
    save(OUT/'baseline_pins.json', baseline)
    provenance = dict(cases=cases, vlen=1024, nr_lanes=4, generator_sha256=base.sha(Path(__file__)),
        scope='Two source child prefixes; not original Linux ELF/parent/eleven-stall acceptance',
        files={str(p.relative_to(prepared)):base.sha(p) for p in prepared.rglob('*') if p.is_file()})
    save(prepared/'provenance.json', provenance)
    host_checks(prepared, cases, models)
    base.HERE = OUT
    soc, spike = base.build(prepared, provenance, 'soc'), base.build(prepared, provenance, 'spike')
    proof = []
    original_build = OUT/'original_linux_rebuild'
    original_build.mkdir()
    gcc = (base.ROOT/'install/riscv-gcc/bin/riscv64-unknown-elf-gcc').resolve(strict=True)
    for case in cases:
        name, op = case['id'], case['operation']
        routine = instructions(Path(soc[name]['path']), name+'_op_'+str(op))
        old = archived_window(prepared/name/'original/original_linux.elf', routine)
        target, = [r for r in old if r['text'].startswith(('vrgather.', 'vrgatherei16.'))]
        require(target['pc'] == next(x for x in triage['cases'] if
                x['name'] == case['original_case']['name'])['last_pc'], 'Archived PC binding differs')
        require([r['insn'] for r in routine] == [r['insn'] for r in
                instructions(Path(spike[name]['path']), name+'_op_'+str(op))], 'Backend asm differs')
        rebuilt = original_build/(name+'.elf')
        original = prepared/name/'original'
        rebuild_command = [str(gcc), '-Os', '-march=rv64gcv', '-mabi=lp64d', '-nostdlib', '-static',
            '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize',
            '-fno-tree-slp-vectorize', '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
            '-Wall', '-Wextra', '-Werror', '-DSEW=8', '-DRESTART_PERMUTATIONS=1',
            '-DPERMUTE_OP_MASK='+str(1 << op), '-I'+str(original),
            str(original/'scenario.c'), str(original/'operations.S'), '-o', str(rebuilt)]
        subprocess.run(rebuild_command, check=True, timeout=30)
        identical = base.sha(rebuilt) == case['original_linux_elf_sha256']
        proof.append(dict(name=name, source_sha256=base.sha(SOURCE),
            original_linux_elf_sha256=case['original_linux_elf_sha256'],
            proof='Archived manifest source hash/defines plus exact13-instruction ELF routine match',
            original_c_entire_binary_rebuild_proven=identical,
            original_linux_rebuild_sha256=base.sha(rebuilt), original_linux_rebuild_command=rebuild_command,
            original_routine=old,
            soc_routine=routine, unchanged_all13_routine_encodings=True))
    save(OUT/'source_elf_proof.json', dict(status='TWO_ARCHIVE_SOURCE_AND_ASM_IDENTITIES_VERIFIED', results=proof))
    reference = OUT/'reference'
    reference.mkdir()
    sys.path.insert(0, str(base.ROOT/'verification'))
    from ara_verify.spike_probe import check_spike_vstart, probe_paths
    cc, src = probe_paths(base.ROOT)
    require(check_spike_vstart(SPIKE, cc, reference/'vstart_probe', src)['status'] == 'PASS',
            'Existing Spike restart capability failed')
    results = []
    for case in cases:
        name, entry = case['id'], spike[case['id']]
        elf = Path(entry['path'])
        log_pc, _ = symbol(elf, 'replay_log', OBJDUMP)
        debug, log, commits = (reference/(name+ext) for ext in ('.cmd', '.log', '.commits.log'))
        # Spike's --instructions does not bound interactive "until". Bound rs itself.
        debug.write_text(f'rs {MAX_RETIRED}\nstr {log_pc:x}\nquit\n')
        command = [str(SPIKE), '-d', '--debug-cmd='+str(debug), '--isa=rv64gcv_zvl1024b',
                   '-m2', '--log-commits',
                   '--log='+str(commits), str(elf)]
        start = time.monotonic()
        with log.open('x') as stream:
            run = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                 timeout=120, preexec_fn=limit_log)
        evidence = reference_trace(commits, elf, name, models[name])
        console = evidence.pop('reconstructed_runtime_console')
        runtime_log = reference/(name+'.runtime.log')
        runtime_log.write_text(console)
        require(run.returncode == 0 and all(m in console for m in entry['pass_markers']) and
                not re.search(r'FAIL|TRAP|MISMATCH|RVV_PERMUTE_DETAIL', console), 'Spike strict oracle/exit gate failed')
        results.append(dict(name=name, status='PASS', returncode=0, elapsed_s=time.monotonic()-start,
            elf_sha256=entry['sha256'], soc_elf_sha256=soc[name]['sha256'], command=command,
            log_sha256=base.sha(log), commit_log_sha256=base.sha(commits),
            runtime_log_sha256=base.sha(runtime_log), runtime_log_from_actual_committed_sb=True,
            commit_bytes=commits.stat().st_size, **evidence))
        save(reference/'reference.json', dict(status='IN_PROGRESS_NOT_DUT', results=results))
    for p, digest in baseline.items():
        require(base.sha(Path(p)) == digest, 'Baseline pin changed: '+p)
    save(reference/'reference.json', dict(status='SPIKE_TWO_PREFIX_FULLORACLE_PASS_NOT_DUT', results=results,
         spike_sha256=base.sha(SPIKE), limits=dict(seconds_per_case=120,
         total_instructions_per_case=MAX_RETIRED, file_bytes=MAX_LOG), old_pins_unchanged=True))
    pins = {str(p):base.sha(p) for p in OUT.rglob('*') if p.is_file()}
    save(OUT/'prepared_pins.json', pins)
    save(OUT/'prepared_ready.json', dict(status='PREPARED_TWO_CHILD_PREFIXES_HOST_SPIKE_PASS_NOT_DUT',
         cases=[c['id'] for c in cases], prefix_calls_each=98, source_single_reuse=False,
         original_stopped_tuple=None, exact11_failure_reproduction=False,
         full_parent_closure=False, vcs_started=False, rtl_modified=False,
         source_elf_proof_sha256=base.sha(OUT/'source_elf_proof.json'),
         host_gate_sha256=base.sha(OUT/'host/host_gate.json'), reference_sha256=base.sha(reference/'reference.json'),
         pins_sha256=base.sha(OUT/'prepared_pins.json')))
    print('PREPARED_TWO_CHILD_PREFIXES_HOST_SPIKE_PASS_NOT_DUT', OUT, flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if OUT.exists():
            save(OUT/'preparation_error.json', dict(status='PREPARATION_STOPPED_NOT_DUT',
                 error=type(error).__name__+': '+str(error), retry=False))
        raise
