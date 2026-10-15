#!/usr/bin/env python3
"""Read-only identities/ELF/report checks. No raw parse or producer import."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
WORK = OUT.parent / 'full_small2_vcs_m6_plan01'
REF = OUT.parent / 'full_small2_prepare01'
PLAN = '7ec58e3f38f5877838c7edf898d4b85d4872437dcdc54e7542357e8f2736f9ee'
READY = 'db878aa262c882af8cf32dfa803426382b3869c1a0f47662c4a434bd8b6439b6'


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def elf_code(spec):
    data = Path(spec['elf']).read_bytes()
    need(data[:6] == b'\x7fELF\x02\x01', 'ELF64 LE')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phsize, count = struct.unpack_from('<HH', data, 54)
    loads = []
    for i in range(count):
        p = struct.unpack_from('<IIQQQQQQ', data, phoff + phsize*i)
        if p[0] == 1:
            loads.append((p[3], p[3]+p[5], p[2]))
    for address, insn in spec['code'].items():
        pc = int(address)
        width = 4 if insn & 3 == 3 else 2
        matches = [(lo, offset) for lo, hi, offset in loads if lo <= pc and pc+width <= hi]
        need(len(matches) == 1, 'Unique ELF instruction mapping')
        lo, offset = matches[0]
        need(int.from_bytes(data[offset+pc-lo:offset+pc-lo+width], 'little') == insn, 'Actual ELF/code differs')


def verify():
    start = time.monotonic()
    need(sha(WORK/'prepared01/plan.json') == PLAN and sha(REF/'READY.json') == READY, 'Exact plan/READY')
    plan, ready = read(WORK/'prepared01/plan.json'), read(REF/'READY.json')
    need(len(plan['pins']) == 860, 'Exact860 pins')
    for path, expected in plan['pins'].items():
        need(sha(path) == expected, 'Plan pin drift: '+path)
    for table in (ready['evidence_pins'], read(REF/'recovery01/fullparse01/input_pins.json')):
        need(all(plan['pins'].get(p) == h for p,h in table.items()), 'Missing reference evidence pin')
    need(plan['pins'][str(REF/'READY.json')] == READY, 'Missing READY pin')
    need((plan['jobs'],plan['case_timeout_s'],plan['worker_timeout_s'],plan['service_timeout_s']) ==
         (2,10800,12000,13200), 'Fixed budgets')
    image = Path(plan['image'])/'image.json'
    need(sha(image) == plan['image_sha256'] == 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0', 'Exact M6')
    host = read(WORK/'host03.json')
    need(host['status'] == 'PASS_HOST_ONLY' and host['tests'] == 14 and host['failures'] == 0, 'Host03')
    need(all(plan['pins'].get(p) == h for p,h in host['pins'].items()), 'Host final script pins')
    need(read(WORK/'prepared01/dryrun.json')['status'] == 'DRYRUN_ONLY_NO_PROCESS' and
         len(read(WORK/'prepared01/dryrun.json')['commands']) == 2, 'Existing dryrun2')
    recovery = read(REF/'recovery01/fullparse01/status.json')
    need(sha(REF/'recovery01/fullparse01/status.json') ==
         '0edaf36f891f25675e9b8638f2d8a92eea3894e8f5916e345d5ee4ed36f465b3', 'Exact approved fullparse outcome')
    need(recovery['status'] == 'FULL2_REFERENCE_ACCEPTED_BY_RECOVERY01_NOT_DUT' and
         recovery['pins_pre_post_unchanged'] and recovery['reference_retries'] == 0, 'Recovery status')
    execution = read(REF/'recovery01/execution01/outcome.json')
    need(type(execution['returncode']) is int and execution['returncode'] == 0 and
         not execution['timeout'] and execution['attempt'] == 1 and execution['elapsed_s'] < 600, 'Actual prior process wait')
    summaries = []
    for shape, sew, ops, calls in [('rvv_matrix_e8_mf8',8,25,4095), ('rvv_matrix_e32_mf2',32,35,5985)]:
        root = REF/shape
        proof, model = read(root/'sourceproof.json'), read(root/'model.json')
        result = read(REF/'recovery01/fullparse01'/f'{shape}.json')
        case, = [c for c in plan['cases'] if c['shape'] == shape]
        need(case['elf'] == proof['backends']['soc']['elf'] and case['sha256'] == proof['backends']['soc']['sha256'], 'Same SoC ELF')
        need(plan['specs'][shape]['backend'] == proof['backends']['soc'], 'Actual worker backend spec')
        need(proof['byte_equivalent_original_reconstruction'] and proof['full_order_preserved'] and
             not proof['partitioned'], 'Original reconstruction/full scope')
        original = Path(proof['original_elf']).read_bytes()
        need(hashlib.sha256(original).hexdigest() == proof['original_sha256'], 'Original ELF')
        for backend in ('soc','spike'):
            spec = proof['backends'][backend]
            need(sha(spec['elf']) == spec['sha256'], 'ELF hash')
            elf_code(spec)
            need(len(spec['helpers']) == ops+1, 'Complete original helper set')
            for name, window in spec['helpers'].items():
                need(len(window) == (3 if name == 'capacity' else 13), 'Original helper length')
                blob = b''
                for index, row in enumerate(window):
                    width = 4 if row['insn'] & 3 == 3 else 2
                    need(spec['code'][str(row['pc'])] == row['insn'], 'Helper in actual image')
                    if index+1 < len(window):
                        need(window[index+1]['pc'] == row['pc']+width, 'Continuous helper bytes')
                    blob += row['insn'].to_bytes(width,'little')
                need(original.count(blob) == 1, 'Unique original ELF helper-byte match')
        expected = [(seed,op,vl,mode,(0,vl//2,vl if vl<16 else 15)[si])
                    for seed in range(3) for op in range(ops) for vl in (0,1,2,3,8,15,16)
                    for mode in range(3) for si in range(1 if op in (19,20,21,22,23) else 3)]
        need(len(expected) == len(model) == len(result['call_ledger']) == calls, 'Full ordered count')
        for ordinal,(want,g,c) in enumerate(zip(expected,model,result['call_ledger'])):
            for row in (g,c):
                need(tuple(row[k] for k in ('seed','op','vl','mode','vstart')) == want and row['ordinal'] == ordinal, 'Original ordering')
            need(len(g['a']) == len(g['b']) == len(g['expected']) == 16 and len(g['mask']) == 128, 'Complete model arrays')
            need(c['reads'] == list(range(18)) and c['returned_vstart'] == 0, 'Complete prior result/guard evidence')
            target = proof['backends']['spike']['helpers'][f'op_{g["op"]}'][8]
            need((c['target_pc'],c['target_insn']) == (target['pc'],target['insn']), 'Prior actual target identity')
        need((result['calls'],result['results'],result['guards'],result['helper_instructions']) ==
             (calls,16*calls,2*calls,13*calls), 'Full result scope')
        need(result['actual_execution']['returncode'] == 0 and not result['actual_execution']['timeout'] and
             result['raw_sha256'] == plan['pins'][str(root/'reference01/commits.log')], 'Prior reference wait/raw binding')
        summaries.append(dict(shape=shape, calls=calls, ops=ops, seeds=3, results=16*calls, guards=2*calls,
                              soc_elf_sha256=case['sha256'], firmware=result['firmware_through_htif']))
    need(sha(WORK/'prepared01/plan.json') == PLAN, 'Late plan change')
    save('verified.json', dict(status='STATIC_IDENTITIES_AND_PRIOR_REPORTS_VERIFIED_NOT_NEW_RAW_AUDIT',
         plan_sha256=PLAN,reference_ready_sha256=READY,pin_count=860,shapes=summaries,
         raw_parses=0,Host_runs=0,Spike_runs=0,DUT_runs=0,builds=0,
         prior_recovery_actual_exit=execution,elapsed_s=time.monotonic()-start,reviewer_sha256=sha(__file__)))
    print('VERIFIED static identities and existing reports; no raw parse',flush=True)


def main():
    if sys.argv[1:] == ['--child']:
        verify()
        return 0
    need(not sys.argv[1:], 'Unexpected arguments')
    command = [sys.executable,'-B',str(Path(__file__).resolve()),'--child']
    save('process_started.json',dict(command=command,timeout_s=180,script_sha256=sha(__file__),started=time.time()))
    start=time.monotonic()
    with (OUT/'process.log').open('x') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        timeout=False
        try:
            rc=child.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timeout=True
            child.kill()
            rc=child.wait()
    save('process_exit.json',dict(returncode=rc,timeout=timeout,elapsed_s=time.monotonic()-start,
         child_pid=child.pid,command=command,attempt=1,raw_parses=0))
    print('review actual exit',rc,'timeout',timeout,flush=True)
    return int(timeout or rc != 0)


if __name__ == '__main__':
    sys.exit(main())
